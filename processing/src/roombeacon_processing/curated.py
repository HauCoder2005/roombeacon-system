"""Historical Curated Observations: cleaned Bronze history as partitioned Parquet.

Grain is exactly one row per Bronze observation (``rental_post_versions`` row)
from the validated snapshot. Each row carries observation-level validation
(the same domain rules Silver uses) plus post-level administrative and
semantic attributes from the canonical Silver built from the *same* snapshot.
This layer is the only input of the Analytics & Data Warehouse plane.

Free text, URLs and seller/contact fields are never written here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import time
from typing import Any
from uuid import uuid4

import duckdb
import pandas as pd

from analytics.bronze.snapshot import verify_bronze_observations

from .price_area_validation import validate_area, validate_price


SCHEMA_VERSION = "1.0.0"
METADATA_FILENAME = "_metadata.json"
SILVER_FILENAME = "rental_listings.parquet"
SILVER_METADATA_FILENAME = "rental_listings.metadata.json"
# Measured on ~400k observations: 256MB/1 thread peaks near 370MB RSS, which
# fits the low-RAM Airflow scheduler; larger inputs spill to temp_directory.
# The partitioned COPY must not carry a global ORDER BY: that sort cannot
# spill and was the out-of-memory point below ~320MB.
DUCKDB_MEMORY_LIMIT = "256MB"
DUCKDB_THREADS = 1

# Silver column -> curated column (post-level attributes of the latest state).
SILVER_ATTRIBUTES: dict[str, str] = {
    "province_text_extracted": "province",
    "district_text_extracted": "district",
    "ward_current": "ward",
    "ward_mapping_status": "ward_mapping_status",
    "admin_consistency_status": "admin_consistency_status",
    "listing_intent": "listing_intent",
    "rental_scope": "rental_scope",
    "price_model_suitability": "post_price_model_suitability",
    "row_quality_status": "post_row_quality_status",
    "has_trusted_coordinate": "has_trusted_coordinate",
    "duplicate_candidate_group": "duplicate_candidate_group",
}
MARKET_INTENTS = frozenset({"RENT", "UNKNOWN"})

CURATED_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "rental_post_id",
    "source_code",
    "source_listing_id",
    "crawl_run_id",
    "observed_at",
    "observed_date",
    "version_seq",
    "content_hash",
    "is_content_change",
    "is_price_change",
    "ingestion_origin",
    "price_amount",
    "currency",
    "period",
    "price_status",
    "area_value",
    "area_status",
    "price_per_m2",
    "province",
    "district",
    "ward",
    "ward_mapping_status",
    "admin_consistency_status",
    "listing_intent",
    "rental_scope",
    "post_price_model_suitability",
    "post_row_quality_status",
    "has_trusted_coordinate",
    "duplicate_candidate_group",
    "is_market_eligible",
)


class CuratedBuildError(RuntimeError):
    """Raised when curated observations cannot be safely built or published."""


@dataclass(frozen=True)
class CuratedBuildResult:
    snapshot_id: str
    silver_output_sha256: str
    output_dir: str
    row_count: int
    post_count: int
    partition_count: int
    min_observed_at: str | None
    max_observed_at: str | None
    schema_version: str
    runtime_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sql_literals(values) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in sorted(values))


# Single definition used for both in-memory frames and Parquet inputs. The
# window keeps version order per post; LAG gives null-safe change detection.
CURATE_SQL = f"""
WITH ordered AS (
    SELECT o.*,
           ROW_NUMBER() OVER w AS version_seq,
           LAG(o.content_hash) OVER w AS previous_content_hash,
           LAG(CAST(o.price_amount AS DOUBLE)) OVER w AS previous_price_amount
    FROM observations o
    WINDOW w AS (PARTITION BY o.rental_post_id ORDER BY o.observed_at, o.observation_id)
)
SELECT
    CAST(o.observation_id AS BIGINT) AS observation_id,
    CAST(o.rental_post_id AS BIGINT) AS rental_post_id,
    o.source_code,
    o.source_listing_id,
    o.crawl_run_id,
    CAST(o.observed_at AS TIMESTAMP) AS observed_at,
    CAST(o.observed_at AS DATE) AS observed_date,
    CAST(o.version_seq AS BIGINT) AS version_seq,
    o.content_hash,
    (o.version_seq = 1 OR o.content_hash IS DISTINCT FROM o.previous_content_hash) AS is_content_change,
    (o.version_seq > 1
     AND CAST(o.price_amount AS DOUBLE) IS DISTINCT FROM o.previous_price_amount) AS is_price_change,
    o.ingestion_origin,
    CAST(o.price_amount AS DOUBLE) AS price_amount,
    o.currency,
    o.period,
    ps.status AS price_status,
    CAST(o.area_value AS DOUBLE) AS area_value,
    ast.status AS area_status,
    CASE WHEN ps.status = 'ACCEPTED_CLEAN' AND ast.status = 'ACCEPTED_CLEAN'
         THEN CAST(o.price_amount AS DOUBLE) / CAST(o.area_value AS DOUBLE) END AS price_per_m2,
    {", ".join(
        f"COALESCE(s.{src}, FALSE) AS {dst}" if dst == "has_trusted_coordinate" else f"s.{src} AS {dst}"
        for src, dst in SILVER_ATTRIBUTES.items()
    )},
    COALESCE(
        ps.status = 'ACCEPTED_CLEAN'
        AND s.price_model_suitability = 'SUPPORTED'
        AND s.listing_intent IN ({_sql_literals(MARKET_INTENTS)}),
        FALSE
    ) AS is_market_eligible
FROM ordered o
JOIN silver s ON s.rental_post_id = o.rental_post_id
LEFT JOIN price_status ps ON ps.value IS NOT DISTINCT FROM CAST(o.price_amount AS DOUBLE)
LEFT JOIN area_status ast ON ast.value IS NOT DISTINCT FROM CAST(o.area_value AS DOUBLE)
"""


def _status_table(connection, column: str, rule) -> pd.DataFrame:
    """Apply a scalar Silver Decimal validator once per distinct value."""
    values = [
        row[0] for row in connection.execute(
            f"SELECT DISTINCT CAST({column} AS DOUBLE) FROM observations"
        ).fetchall()
    ]
    return pd.DataFrame(
        {
            "value": pd.Series(values, dtype="float64"),
            "status": [rule(None if v is None else Decimal(str(v))) for v in values],
        }
    )


def _prepare(connection) -> None:
    """Validate inputs registered as ``observations``/``silver``; add status tables."""
    silver_columns = {row[0] for row in connection.execute("DESCRIBE silver").fetchall()}
    missing = set(SILVER_ATTRIBUTES) - silver_columns
    if missing:
        raise CuratedBuildError(f"Silver is missing curated attributes: {sorted(missing)}")
    rows, distinct = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT rental_post_id) FROM silver"
    ).fetchone()
    if rows != distinct:
        raise CuratedBuildError("Silver must have one row per rental_post_id")
    (absent,) = connection.execute(
        "SELECT COUNT(DISTINCT o.rental_post_id) FROM observations o "
        "ANTI JOIN silver s ON s.rental_post_id = o.rental_post_id"
    ).fetchone()
    if absent:
        raise CuratedBuildError(f"{absent} observed rental_post_id values are absent from Silver")
    connection.register("price_status", _status_table(connection, "price_amount", validate_price))
    connection.register("area_status", _status_table(connection, "area_value", validate_area))


def curate_observations(observations: pd.DataFrame, silver: pd.DataFrame) -> pd.DataFrame:
    """Return one curated row per observation, ordered by observation_id."""
    connection = _connect()
    try:
        connection.register("observations", observations)
        connection.register("silver", silver)
        _prepare(connection)
        return connection.execute(f"{CURATE_SQL} ORDER BY observation_id").df()[list(CURATED_COLUMNS)]
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect(temp_directory: Path | None = None) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    connection.execute(f"SET threads = {int(DUCKDB_THREADS)}")
    connection.execute("SET preserve_insertion_order = false")
    if temp_directory is not None:
        connection.execute(f"SET temp_directory = {_path_literal(temp_directory)}")
    return connection


def _path_literal(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _verified_silver(silver_dir: Path) -> tuple[Path, dict[str, Any]]:
    silver_path = Path(silver_dir) / SILVER_FILENAME
    metadata_path = Path(silver_dir) / SILVER_METADATA_FILENAME
    if not silver_path.is_file() or not metadata_path.is_file():
        raise CuratedBuildError(f"Canonical Silver is not published in {silver_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = metadata.get("output_sha256")
    if not expected or _sha256(silver_path) != expected:
        raise CuratedBuildError("Canonical Silver does not match its metadata output_sha256")
    return silver_path, metadata


def _write_partitions(connection, directory: Path) -> None:
    connection.execute(
        f"COPY ({CURATE_SQL}) TO ? "
        "(FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (observed_date), "
        "WRITE_PARTITION_COLUMNS true, FILENAME_PATTERN 'part_{i}')",
        [str(directory)],
    )


def _verify_readback(directory: Path, expected_rows: int) -> dict[str, Any]:
    connection = _connect()
    try:
        rows, ids, distinct_ids, posts, first, last = connection.execute(
            "SELECT COUNT(*), COUNT(observation_id), COUNT(DISTINCT observation_id), "
            "COUNT(DISTINCT rental_post_id), MIN(observed_at), MAX(observed_at) "
            "FROM read_parquet(?, hive_partitioning = false)",
            [str(directory / "**" / "*.parquet")],
        ).fetchone()
    finally:
        connection.close()
    if not rows == ids == distinct_ids == expected_rows:
        raise CuratedBuildError("Curated read-back does not preserve observation grain")
    return {"row_count": rows, "post_count": posts, "min": str(first), "max": str(last)}


def build_curated_observations(
    snapshot_dir: Path, silver_dir: Path, output_dir: Path
) -> CuratedBuildResult:
    """Build curated observations from Parquet inputs and publish atomically.

    The transformation runs inside DuckDB directly over the verified Parquet
    files, so memory stays bounded by DUCKDB_MEMORY_LIMIT (spilling to disk)
    rather than by the size of the observation history.
    """
    started = time.perf_counter()
    observations_path, snapshot = verify_bronze_observations(Path(snapshot_dir))
    silver_path, silver_metadata = _verified_silver(Path(silver_dir))
    silver_snapshot_id = (silver_metadata.get("source_snapshot") or {}).get("snapshot_id")
    if silver_snapshot_id != snapshot["snapshot_id"]:
        raise CuratedBuildError(
            f"Silver was built from snapshot {silver_snapshot_id}, "
            f"not the current snapshot {snapshot['snapshot_id']}"
        )

    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    staging = output_dir.parent / f".{output_dir.name}.{token}.tmp"
    backup = output_dir.parent / f".{output_dir.name}.{token}.bak"
    silver_projection = ", ".join(("rental_post_id", *SILVER_ATTRIBUTES))
    try:
        staging.mkdir()
        spill = output_dir.parent / f".{output_dir.name}.{token}.spill"
        connection = _connect(spill)
        try:
            # Views cannot take prepared parameters; paths are escaped literals.
            connection.execute(
                f"CREATE VIEW observations AS SELECT * FROM read_parquet({_path_literal(observations_path)})"
            )
            connection.execute(
                f"CREATE VIEW silver AS SELECT {silver_projection} "
                f"FROM read_parquet({_path_literal(silver_path)})"
            )
            _prepare(connection)
            _write_partitions(connection, staging)
        finally:
            connection.close()
            shutil.rmtree(spill, ignore_errors=True)
        stats = _verify_readback(staging, int(snapshot["observation_row_count"]))
        files = {
            path.relative_to(staging).as_posix(): {"sha256": _sha256(path)}
            for path in sorted(staging.rglob("*.parquet"))
        }
        metadata = {
            "dataset_name": "listing_observations",
            "layer": "historical_curated_observations",
            "grain": "one row per Bronze observation (rental_post_versions.id)",
            "schema_version": SCHEMA_VERSION,
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "source_snapshot_id": snapshot["snapshot_id"],
            "source_watermark": snapshot.get("watermark"),
            "silver_output_sha256": silver_metadata["output_sha256"],
            "row_count": stats["row_count"],
            "post_count": stats["post_count"],
            "min_observed_at": stats["min"],
            "max_observed_at": stats["max"],
            "partitioning": "observed_date",
            "columns": list(CURATED_COLUMNS),
            "files": files,
        }
        (staging / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if output_dir.exists():
            output_dir.rename(backup)
        try:
            staging.rename(output_dir)
        except Exception:
            if backup.exists():
                backup.rename(output_dir)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return CuratedBuildResult(
        snapshot_id=snapshot["snapshot_id"],
        silver_output_sha256=silver_metadata["output_sha256"],
        output_dir=str(output_dir),
        row_count=metadata["row_count"],
        post_count=metadata["post_count"],
        partition_count=len({Path(name).parent.as_posix() for name in files}),
        min_observed_at=metadata["min_observed_at"],
        max_observed_at=metadata["max_observed_at"],
        schema_version=SCHEMA_VERSION,
        runtime_seconds=round(time.perf_counter() - started, 3),
    )
