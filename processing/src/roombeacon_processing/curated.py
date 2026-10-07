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
import numpy as np
import pandas as pd

from analytics.bronze.snapshot import load_bronze_observations

from .price_area_validation import validate_area, validate_price


SCHEMA_VERSION = "1.0.0"
METADATA_FILENAME = "_metadata.json"
SILVER_FILENAME = "rental_listings.parquet"
SILVER_METADATA_FILENAME = "rental_listings.metadata.json"
DUCKDB_MEMORY_LIMIT = "512MB"
DUCKDB_THREADS = 2

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


def _status_map(values: pd.Series, rule) -> pd.Series:
    """Apply a scalar Decimal validator once per distinct value."""
    unique = values.drop_duplicates()
    mapping = {
        value: rule(None if pd.isna(value) else Decimal(str(value))) for value in unique
    }
    return values.map(mapping)


def _changed(current: pd.Series, previous: pd.Series, has_previous: pd.Series) -> pd.Series:
    same = (current == previous) | (current.isna() & previous.isna())
    return has_previous & ~same


def curate_observations(observations: pd.DataFrame, silver: pd.DataFrame) -> pd.DataFrame:
    """Return one curated row per observation, ordered by observation_id."""
    missing = set(SILVER_ATTRIBUTES) - set(silver.columns)
    if missing:
        raise CuratedBuildError(f"Silver is missing curated attributes: {sorted(missing)}")
    attributes = silver[["rental_post_id", *SILVER_ATTRIBUTES]].rename(columns=SILVER_ATTRIBUTES)
    if not attributes.rental_post_id.is_unique:
        raise CuratedBuildError("Silver must have one row per rental_post_id")
    absent = set(observations.rental_post_id) - set(attributes.rental_post_id)
    if absent:
        raise CuratedBuildError(
            f"{len(absent)} observed rental_post_id values are absent from Silver"
        )

    frame = observations.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"])
    frame = frame.sort_values(["rental_post_id", "observed_at", "observation_id"], kind="stable")
    by_post = frame.groupby("rental_post_id", sort=False)
    frame["version_seq"] = by_post.cumcount().add(1).astype("int64")
    has_previous = frame["version_seq"].gt(1)
    frame["is_content_change"] = ~has_previous | _changed(
        frame["content_hash"], by_post["content_hash"].shift(), has_previous
    )
    frame["is_price_change"] = _changed(
        frame["price_amount"], by_post["price_amount"].shift(), has_previous
    )
    frame["observed_date"] = frame["observed_at"].dt.date

    frame["price_status"] = _status_map(frame["price_amount"], validate_price)
    frame["area_status"] = _status_map(frame["area_value"], validate_area)
    clean_pair = frame.price_status.eq("ACCEPTED_CLEAN") & frame.area_status.eq("ACCEPTED_CLEAN")
    frame["price_per_m2"] = np.where(
        clean_pair, frame["price_amount"] / frame["area_value"], np.nan
    )

    frame = frame.merge(attributes, on="rental_post_id", how="left", validate="many_to_one")
    frame["has_trusted_coordinate"] = frame["has_trusted_coordinate"].fillna(False).astype(bool)
    frame["is_market_eligible"] = (
        frame.price_status.eq("ACCEPTED_CLEAN")
        & frame.post_price_model_suitability.eq("SUPPORTED")
        & frame.listing_intent.isin(MARKET_INTENTS)
    )
    frame = frame.sort_values("observation_id", kind="stable").reset_index(drop=True)
    return frame[list(CURATED_COLUMNS)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    connection.execute(f"SET threads = {int(DUCKDB_THREADS)}")
    return connection


def _load_silver(silver_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    silver_path = Path(silver_dir) / SILVER_FILENAME
    metadata_path = Path(silver_dir) / SILVER_METADATA_FILENAME
    if not silver_path.is_file() or not metadata_path.is_file():
        raise CuratedBuildError(f"Canonical Silver is not published in {silver_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = metadata.get("output_sha256")
    if not expected or _sha256(silver_path) != expected:
        raise CuratedBuildError("Canonical Silver does not match its metadata output_sha256")
    columns = ", ".join(f'"{name}"' for name in ("rental_post_id", *SILVER_ATTRIBUTES))
    connection = _connect()
    try:
        silver = connection.execute(
            f"SELECT {columns} FROM read_parquet(?)", [str(silver_path)]
        ).df()
    finally:
        connection.close()
    return silver, metadata


def _write_partitions(frame: pd.DataFrame, directory: Path) -> None:
    connection = _connect()
    try:
        connection.register("_curated", frame)
        connection.execute(
            "COPY (SELECT * FROM _curated ORDER BY observed_date, observation_id) TO ? "
            "(FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (observed_date), "
            "WRITE_PARTITION_COLUMNS true, FILENAME_PATTERN 'part_{i}')",
            [str(directory)],
        )
    finally:
        connection.close()


def _verify_readback(directory: Path, frame: pd.DataFrame) -> None:
    connection = _connect()
    try:
        rows, ids, distinct_ids = connection.execute(
            "SELECT COUNT(*), COUNT(observation_id), COUNT(DISTINCT observation_id) "
            "FROM read_parquet(?, hive_partitioning = false)",
            [str(directory / "**" / "*.parquet")],
        ).fetchone()
    finally:
        connection.close()
    if not rows == ids == distinct_ids == len(frame):
        raise CuratedBuildError("Curated read-back does not preserve observation grain")


def build_curated_observations(
    snapshot_dir: Path, silver_dir: Path, output_dir: Path
) -> CuratedBuildResult:
    """Build curated observations from Parquet inputs and publish atomically."""
    started = time.perf_counter()
    observations, snapshot = load_bronze_observations(Path(snapshot_dir))
    silver, silver_metadata = _load_silver(Path(silver_dir))
    silver_snapshot_id = (silver_metadata.get("source_snapshot") or {}).get("snapshot_id")
    if silver_snapshot_id != snapshot["snapshot_id"]:
        raise CuratedBuildError(
            f"Silver was built from snapshot {silver_snapshot_id}, "
            f"not the current snapshot {snapshot['snapshot_id']}"
        )
    frame = curate_observations(observations, silver)
    del observations, silver

    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    staging = output_dir.parent / f".{output_dir.name}.{token}.tmp"
    backup = output_dir.parent / f".{output_dir.name}.{token}.bak"
    try:
        staging.mkdir()
        _write_partitions(frame, staging)
        _verify_readback(staging, frame)
        files = {
            path.relative_to(staging).as_posix(): {"sha256": _sha256(path)}
            for path in sorted(staging.rglob("*.parquet"))
        }
        observed = frame["observed_at"]
        metadata = {
            "dataset_name": "listing_observations",
            "layer": "historical_curated_observations",
            "grain": "one row per Bronze observation (rental_post_versions.id)",
            "schema_version": SCHEMA_VERSION,
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "source_snapshot_id": snapshot["snapshot_id"],
            "source_watermark": snapshot.get("watermark"),
            "silver_output_sha256": silver_metadata["output_sha256"],
            "row_count": len(frame),
            "post_count": int(frame["rental_post_id"].nunique()),
            "min_observed_at": str(observed.min()),
            "max_observed_at": str(observed.max()),
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
