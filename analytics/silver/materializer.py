"""Write and validate the canonical file-based RoomBeacon Silver dataset.

The Parquet checkpoint is the persisted Silver dataset. DuckDB remains an
analytical/query engine and is not required to hold a physical Silver table.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import duckdb

from analytics.duckdb.connection import resolve_runtime_path
from roombeacon_crawler.config.get_env import env

logger = logging.getLogger(__name__)

CANONICAL_FILENAME = "rental_listings.parquet"
METADATA_FILENAME = "rental_listings.metadata.json"
REQUIRED_COLUMNS = [
    "source_code", "rental_post_id", "source_listing_id", "title_raw", "url",
    "price_amount", "area_value", "location_raw", "latest_observed_at",
]


@dataclass
class SilverMetadata:
    dataset_name: str
    layer: str
    generated_at: str
    row_count: int
    distinct_rental_post_id: int
    column_count: int
    columns: list[str]
    canonical_path: str
    min_observed_at: str | None
    max_observed_at: str | None
    schema_version: str
    processing_version: str
    source_distribution: dict[str, int]
    source_snapshot: dict[str, Any] | None = None


class SilverMaterializationError(Exception):
    """Raised when canonical Silver file publication or validation fails."""


class SilverMaterializer:
    """Small, compatibility-safe writer for canonical Silver Parquet."""

    def __init__(
        self,
        output_dir: Path | str | None = None,
        valid_sources: set[str] | None = None,
    ) -> None:
        self.output_dir = (
            resolve_runtime_path(env.processing.silver_dir)
            if output_dir is None else Path(output_dir).resolve()
        )
        self.valid_sources = valid_sources
        self.output_file = self.output_dir / CANONICAL_FILENAME
        self.metadata_file = self.output_dir / METADATA_FILENAME
        self.tmp_file = self.output_dir / f"{CANONICAL_FILENAME}.tmp"
        self.tmp_metadata_file = self.output_dir / f"{METADATA_FILENAME}.tmp"

    def materialize(
        self,
        processed_df: pd.DataFrame,
        *,
        quality_gate_passed: bool,
        source_snapshot: dict[str, Any] | None = None,
    ) -> SilverMetadata:
        """Safely publish validated Silver directly to canonical Parquet."""
        if not quality_gate_passed:
            raise SilverMaterializationError(
                "Pre-Silver quality gate failed; canonical Silver was not published"
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._validate_dataframe(processed_df)
        for temporary in (self.tmp_file, self.tmp_metadata_file):
            temporary.unlink(missing_ok=True)

        try:
            self._write_parquet(processed_df, self.tmp_file)
            canonical = self._read_parquet(self.tmp_file)
            self._validate_readback(processed_df, canonical)
            metadata = self._build_metadata(canonical, source_snapshot)
            self.tmp_metadata_file.write_text(
                json.dumps(asdict(metadata), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.tmp_file.replace(self.output_file)
            self.tmp_metadata_file.replace(self.metadata_file)
            return metadata
        except SilverMaterializationError:
            raise
        except Exception as exc:
            logger.error("Silver publication failed (error_class=%s)", type(exc).__name__)
            raise SilverMaterializationError("Canonical Silver publication failed") from exc
        finally:
            self.tmp_file.unlink(missing_ok=True)
            self.tmp_metadata_file.unlink(missing_ok=True)

    def read_and_validate(self) -> pd.DataFrame:
        """Read the canonical Parquet checkpoint and validate its grain."""
        if not self.output_file.exists():
            raise SilverMaterializationError(
                f"Canonical Silver does not exist: {self.output_file}"
            )
        frame = self._read_parquet(self.output_file)
        self._validate_dataframe(frame)
        return frame

    @staticmethod
    def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
        """Write a DataFrame to Parquet without creating a physical DuckDB table."""
        connection = duckdb.connect(":memory:")
        connection.register("_silver_output", frame)
        try:
            escaped_path = str(path).replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM _silver_output) TO '{escaped_path}' (FORMAT PARQUET)"
            )
        finally:
            connection.close()

    @staticmethod
    def _read_parquet(path: Path) -> pd.DataFrame:
        connection = duckdb.connect(":memory:")
        try:
            escaped_path = str(path).replace("'", "''")
            return connection.execute(
                f"SELECT * FROM read_parquet('{escaped_path}')"
            ).df()
        finally:
            connection.close()

    def _validate_readback(self, expected: pd.DataFrame, actual: pd.DataFrame) -> None:
        self._validate_dataframe(actual)
        if len(actual) != len(expected):
            raise SilverMaterializationError("Silver read-back row count differs")
        if actual.rental_post_id.nunique() != expected.rental_post_id.nunique():
            raise SilverMaterializationError("Silver read-back identity count differs")
        if list(actual.columns) != list(expected.columns):
            raise SilverMaterializationError("Silver read-back columns differ")

    def _validate_dataframe(self, frame: pd.DataFrame) -> None:
        if frame.empty:
            raise SilverMaterializationError("Silver dataset is empty")
        missing = [column for column in REQUIRED_COLUMNS if column not in frame]
        if missing:
            raise SilverMaterializationError(f"Missing required Silver columns: {missing}")
        if frame.rental_post_id.isna().any() or not frame.rental_post_id.is_unique:
            raise SilverMaterializationError("Silver rental_post_id must be non-null and unique")
        sources = set(frame.source_code.dropna().unique())
        valid_sources = self.valid_sources
        if valid_sources is None:
            from roombeacon_crawler.sources.registry import source_registry
            valid_sources = set(source_registry.list_sources())
        invalid_sources = sources - valid_sources
        if invalid_sources:
            raise SilverMaterializationError(f"Invalid source_code values: {sorted(invalid_sources)}")

    def _build_metadata(
        self,
        frame: pd.DataFrame,
        source_snapshot: dict[str, Any] | None,
    ) -> SilverMetadata:
        observed = frame.latest_observed_at.dropna()
        source_distribution = frame.source_code.value_counts().to_dict()
        return SilverMetadata(
            dataset_name="rental_listings",
            layer="silver",
            generated_at=datetime.now(timezone.utc).astimezone().isoformat(),
            row_count=len(frame),
            distinct_rental_post_id=int(frame.rental_post_id.nunique()),
            column_count=len(frame.columns),
            columns=frame.columns.tolist(),
            canonical_path=str(self.output_file),
            min_observed_at=str(observed.min()) if not observed.empty else None,
            max_observed_at=str(observed.max()) if not observed.empty else None,
            schema_version="2.0.0",
            processing_version="2.0.0",
            source_distribution={str(key): int(value) for key, value in source_distribution.items()},
            source_snapshot=source_snapshot,
        )
