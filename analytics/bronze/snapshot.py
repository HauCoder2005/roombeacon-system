"""Build and load the local analytical checkpoint derived from MySQL Bronze.

MySQL remains the canonical Bronze source. This module creates a disposable,
validated Parquet checkpoint so notebooks can analyze one stable population
without opening live database connections during normal execution.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd
from dotenv import load_dotenv


LATEST_FILE = "latest_posts.parquet"
EVIDENCE_FILE = "raw_evidence.parquet"
METADATA_FILE = "metadata.json"
REFRESH_COMMAND = "python -m analytics.bronze.snapshot"

EVIDENCE_COLUMNS = [
    "evidence_observation_id",
    "evidence_version_time_matches",
    "evidence_price_id",
    "price_raw",
    "currency",
    "period",
    "evidence_area_id",
    "area_raw",
    "price_lineage_aligned",
    "area_lineage_aligned",
]

REQUIRED_LATEST_COLUMNS = {
    "rental_post_id",
    "source_code",
    "source_listing_id",
    "title_raw",
    "price_amount",
    "area_value",
    "full_address_text",
    "location_raw",
    "best_address_text",
    "latest_observed_at",
}
REQUIRED_EVIDENCE_COLUMNS = {"rental_post_id", *EVIDENCE_COLUMNS}


class BronzeSnapshotError(RuntimeError):
    """Raised when a Bronze checkpoint cannot be safely built or validated."""


class BronzeSnapshotNotFoundError(BronzeSnapshotError):
    """Raised when the explicit snapshot refresh has not been run."""


def _project_root() -> Path:
    for parent in [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]:
        if (parent / "crawler").is_dir() and (parent / "analytics").is_dir():
            return parent.resolve()
    raise BronzeSnapshotError("Could not locate the RoomBeacon project root")


def default_snapshot_dir(project_root: Path | None = None) -> Path:
    root = Path(project_root).resolve() if project_root else _project_root()
    return root / "data" / "bronze" / "snapshot"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_frames(latest: pd.DataFrame, evidence: pd.DataFrame) -> dict[str, int]:
    missing_latest = REQUIRED_LATEST_COLUMNS - set(latest.columns)
    missing_evidence = REQUIRED_EVIDENCE_COLUMNS - set(evidence.columns)
    if missing_latest or missing_evidence:
        raise BronzeSnapshotError(
            "Snapshot contract is incomplete: "
            f"missing_latest={sorted(missing_latest)}, "
            f"missing_evidence={sorted(missing_evidence)}"
        )
    if latest.empty:
        raise BronzeSnapshotError("Latest Bronze snapshot is empty")
    if latest["rental_post_id"].isna().any():
        raise BronzeSnapshotError("Latest Bronze snapshot contains null rental_post_id")
    unique_ids = int(latest["rental_post_id"].nunique())
    if unique_ids != len(latest):
        raise BronzeSnapshotError(
            f"Latest Bronze grain violation: rows={len(latest)}, unique_ids={unique_ids}"
        )
    if len(evidence) != len(latest):
        raise BronzeSnapshotError(
            f"Evidence grain mismatch: latest_rows={len(latest)}, evidence_rows={len(evidence)}"
        )
    if evidence["rental_post_id"].isna().any() or not evidence["rental_post_id"].is_unique:
        raise BronzeSnapshotError("Raw evidence must have one non-null row per rental_post_id")
    if set(evidence["rental_post_id"]) != set(latest["rental_post_id"]):
        raise BronzeSnapshotError("Latest and raw-evidence rental_post_id populations differ")
    return {
        "latest_row_count": len(latest),
        "unique_rental_post_id_count": unique_ids,
        "raw_evidence_row_count": len(evidence),
        "price_lineage_aligned_count": int(evidence["price_lineage_aligned"].fillna(False).sum()),
        "area_lineage_aligned_count": int(evidence["area_lineage_aligned"].fillna(False).sum()),
    }


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    connection = duckdb.connect(":memory:")
    try:
        connection.register("_snapshot_frame", frame)
        connection.execute(
            "COPY _snapshot_frame TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(path)]
        )
    finally:
        connection.close()


def _read_parquet(path: Path) -> pd.DataFrame:
    connection = duckdb.connect(":memory:")
    try:
        return connection.execute("SELECT * FROM read_parquet(?)", [str(path)]).df()
    finally:
        connection.close()


def write_bronze_snapshot(
    latest: pd.DataFrame,
    evidence: pd.DataFrame,
    snapshot_dir: Path,
    *,
    source_database: str,
    snapshot_id: str | None = None,
    created_at: str | None = None,
    pipeline_version: str = "1.0.0",
) -> dict[str, Any]:
    """Validate and atomically publish a local Bronze analytical checkpoint."""
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    counts = _validate_frames(latest, evidence)
    identifier = snapshot_id or str(uuid4())
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    token = identifier.replace("-", "")
    temporary = {
        LATEST_FILE: snapshot_dir / f".{LATEST_FILE}.{token}.tmp",
        EVIDENCE_FILE: snapshot_dir / f".{EVIDENCE_FILE}.{token}.tmp",
        METADATA_FILE: snapshot_dir / f".{METADATA_FILE}.{token}.tmp",
    }
    canonical = {name: snapshot_dir / name for name in temporary}
    backups = {name: snapshot_dir / f".{name}.{token}.bak" for name in temporary}
    for path in [*temporary.values(), *backups.values()]:
        path.unlink(missing_ok=True)

    try:
        _write_parquet(latest, temporary[LATEST_FILE])
        _write_parquet(evidence, temporary[EVIDENCE_FILE])
        saved_latest = _read_parquet(temporary[LATEST_FILE])
        saved_evidence = _read_parquet(temporary[EVIDENCE_FILE])
        saved_counts = _validate_frames(saved_latest, saved_evidence)
        if saved_counts != counts:
            raise BronzeSnapshotError("Parquet roundtrip changed snapshot validation counts")

        observed = pd.to_datetime(latest["latest_observed_at"], errors="coerce").dropna()
        metadata: dict[str, Any] = {
            "snapshot_id": identifier,
            "snapshot_created_at_utc": timestamp,
            "source_layer": "mysql_bronze",
            "source_database": source_database,
            "grain": "one row per rental_post_id",
            **counts,
            "min_latest_observed_at": str(observed.min()) if not observed.empty else None,
            "max_latest_observed_at": str(observed.max()) if not observed.empty else None,
            "latest_columns": latest.columns.tolist(),
            "raw_evidence_columns": evidence.columns.tolist(),
            "latest_dtypes": {name: str(dtype) for name, dtype in latest.dtypes.items()},
            "raw_evidence_dtypes": {name: str(dtype) for name, dtype in evidence.dtypes.items()},
            "pipeline_version": pipeline_version,
            "files": {
                LATEST_FILE: {"sha256": _sha256(temporary[LATEST_FILE])},
                EVIDENCE_FILE: {"sha256": _sha256(temporary[EVIDENCE_FILE])},
            },
        }
        temporary[METADATA_FILE].write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        promoted: list[str] = []
        try:
            for name, destination in canonical.items():
                if destination.exists():
                    destination.replace(backups[name])
            for name in (LATEST_FILE, EVIDENCE_FILE, METADATA_FILE):
                temporary[name].replace(canonical[name])
                promoted.append(name)
        except Exception:
            for name in promoted:
                canonical[name].unlink(missing_ok=True)
            for name, backup in backups.items():
                if backup.exists():
                    backup.replace(canonical[name])
            raise
        for backup in backups.values():
            backup.unlink(missing_ok=True)
        return metadata
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


def load_bronze_snapshot(snapshot_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load and validate a local checkpoint without contacting MySQL."""
    snapshot_dir = Path(snapshot_dir)
    paths = {
        LATEST_FILE: snapshot_dir / LATEST_FILE,
        EVIDENCE_FILE: snapshot_dir / EVIDENCE_FILE,
        METADATA_FILE: snapshot_dir / METADATA_FILE,
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise BronzeSnapshotNotFoundError(
            "Bronze analytical snapshot not found. Refresh it with: "
            f"{REFRESH_COMMAND}. Missing: {missing}"
        )
    try:
        metadata = json.loads(paths[METADATA_FILE].read_text(encoding="utf-8"))
    except Exception as exc:
        raise BronzeSnapshotError(f"Invalid Bronze snapshot metadata: {exc}") from exc

    for name in (LATEST_FILE, EVIDENCE_FILE):
        expected = metadata.get("files", {}).get(name, {}).get("sha256")
        if not expected or _sha256(paths[name]) != expected:
            raise BronzeSnapshotError(f"Bronze snapshot file does not match metadata: {name}")
    try:
        latest = _read_parquet(paths[LATEST_FILE])
        evidence = _read_parquet(paths[EVIDENCE_FILE])
    except Exception as exc:
        raise BronzeSnapshotError(f"Could not read Bronze snapshot Parquet: {exc}") from exc
    counts = _validate_frames(latest, evidence)
    for key, value in counts.items():
        if metadata.get(key) != value:
            raise BronzeSnapshotError(
                f"Bronze snapshot metadata mismatch for {key}: "
                f"metadata={metadata.get(key)}, actual={value}"
            )
    context = {
        **metadata,
        "snapshot_dir": str(snapshot_dir.resolve()),
        "latest_path": str(paths[LATEST_FILE].resolve()),
        "raw_evidence_path": str(paths[EVIDENCE_FILE].resolve()),
        "view_name": "local_bronze_snapshot",
    }
    return latest, evidence, context


def _read_mysql_frame(connection: Any, query: str, label: str) -> pd.DataFrame:
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [description[0] for description in cursor.description]
            frame = pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
    except Exception as exc:
        raise BronzeSnapshotError(
            f"MySQL Bronze extraction failed for {label}: {type(exc).__name__}: {exc}"
        ) from exc
    print(f"Extracted {label}: {len(frame):,} rows in {time.perf_counter() - started:.2f}s")
    return frame


def _extract_current_bronze(project_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Extract one coherent source population under a consistent read transaction."""
    load_dotenv(project_root / ".env", override=True)
    from roombeacon_crawler.config.get_env import env
    import pymysql

    cfg = env.mysql_bronze
    if Path("/.dockerenv").exists():
        host, port = cfg.host, cfg.port
    else:
        host = os.getenv("BRONZE_MYSQL_HOST_ACCESS_HOST", "127.0.0.1")
        host_port = os.getenv("BRONZE_MYSQL_HOST_PORT")
        if not host_port:
            raise BronzeSnapshotError(
                "BRONZE_MYSQL_HOST_PORT is required for host-side snapshot refresh"
            )
        port = int(host_port)

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            charset=cfg.charset,
            connect_timeout=5,
            read_timeout=300,
            write_timeout=30,
            autocommit=False,
        )
    except Exception as exc:
        raise BronzeSnapshotError(
            f"Could not connect to MySQL Bronze at {host}:{port}/{cfg.database}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    queries = {
        "platforms": "SELECT id, code, name FROM platforms",
        "rental_posts": (
            "SELECT id, platform_id, platform_post_id, first_observed_at, "
            "last_observed_at FROM rental_posts"
        ),
        "rental_post_versions": """
            SELECT id, rental_post_id, crawl_run_id, observed_at, url, title_raw,
                   content_hash, ingestion_origin,
                   JSON_OBJECT(
                     'location_raw', JSON_UNQUOTE(JSON_EXTRACT(source_payload, '$.location_raw')),
                     'map_location', JSON_OBJECT(
                       'provider', JSON_UNQUOTE(JSON_EXTRACT(source_payload, '$.map_location.provider')),
                       'latitude', JSON_UNQUOTE(JSON_EXTRACT(source_payload, '$.map_location.latitude')),
                       'longitude', JSON_UNQUOTE(JSON_EXTRACT(source_payload, '$.map_location.longitude')),
                       'query_raw', JSON_UNQUOTE(JSON_EXTRACT(source_payload, '$.map_location.query_raw'))
                     )
                   ) AS source_payload
            FROM rental_post_versions
        """,
        "post_prices": (
            "SELECT id, rental_post_id, rental_post_version_id, price_raw, "
            "price_amount, currency, period FROM post_prices"
        ),
        "post_addresses": (
            "SELECT id, rental_post_id, rental_post_version_id, full_address_text, "
            "created_at FROM post_addresses"
        ),
        "post_details": (
            "SELECT id, rental_post_id, rental_post_version_id, area_raw, area_value "
            "FROM post_details"
        ),
    }
    frames: dict[str, pd.DataFrame] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
        for name, query in queries.items():
            frames[name] = _read_mysql_frame(connection, query, name)
    finally:
        connection.rollback()
        connection.close()

    # PyMySQL returns DECIMAL values as Python objects. Normalize only the two
    # analytical numeric measures before DuckDB registration so type inference
    # is based on the full numeric domain rather than the first Decimal value.
    frames["post_prices"]["price_amount"] = pd.to_numeric(
        frames["post_prices"]["price_amount"], errors="coerce"
    )
    frames["post_details"]["area_value"] = pd.to_numeric(
        frames["post_details"]["area_value"], errors="coerce"
    )

    local = duckdb.connect(":memory:")
    try:
        for name, frame in frames.items():
            local.register(name, frame)
        latest_sql = (project_root / "analytics" / "duckdb" / "sql" / "latest_posts.sql").read_text()
        latest_sql = latest_sql.replace("mysql_db.", "")
        local.execute(f"CREATE VIEW v_latest_posts AS {latest_sql}")
        snapshot_sql = (project_root / "notebooks" / "sql" / "eda_snapshot.sql").read_text()
        snapshot_sql = snapshot_sql.replace("mysql_db.", "")
        combined = local.execute(snapshot_sql).df()
    finally:
        local.close()

    latest = combined.drop(columns=EVIDENCE_COLUMNS).copy()
    evidence = combined[["rental_post_id", *EVIDENCE_COLUMNS]].copy()
    _validate_frames(latest, evidence)
    return latest, evidence, cfg.database


def build_bronze_snapshot(
    project_root: Path | None = None, snapshot_dir: Path | None = None
) -> dict[str, Any]:
    """Refresh the canonical local checkpoint from current MySQL Bronze."""
    root = Path(project_root).resolve() if project_root else _project_root()
    destination = Path(snapshot_dir) if snapshot_dir else default_snapshot_dir(root)
    started = time.perf_counter()
    latest, evidence, database = _extract_current_bronze(root)
    metadata = write_bronze_snapshot(
        latest,
        evidence,
        destination,
        source_database=database,
    )
    metadata["refresh_runtime_seconds"] = round(time.perf_counter() - started, 3)
    print(
        f"Bronze snapshot refreshed: id={metadata['snapshot_id']} "
        f"rows={metadata['latest_row_count']:,} "
        f"runtime={metadata['refresh_runtime_seconds']:.3f}s path={destination}"
    )
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        build_bronze_snapshot(snapshot_dir=args.snapshot_dir)
    except Exception as exc:
        print(f"Bronze snapshot refresh FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
