"""Write and validate the canonical file-based RoomBeacon Silver dataset.

The Parquet checkpoint is the persisted Silver dataset. DuckDB remains an
analytical/query engine and is not required to hold a physical Silver table.
"""

import json
import logging
import hashlib
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import duckdb

from analytics.duckdb.connection import resolve_runtime_path
from roombeacon_crawler.config.get_env import env

logger = logging.getLogger(__name__)

CANONICAL_FILENAME = "rental_listings.parquet"
METADATA_FILENAME = "rental_listings.metadata.json"
DEFAULT_DUCKDB_MEMORY_LIMIT = "256MB"
DEFAULT_DUCKDB_THREADS = 2
DEFAULT_PARQUET_ROW_GROUP_SIZE = 122_880
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
    output_sha256: str
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
        token = uuid4().hex
        temporary = {
            CANONICAL_FILENAME: self.output_dir / f".{CANONICAL_FILENAME}.{token}.tmp",
            METADATA_FILENAME: self.output_dir / f".{METADATA_FILENAME}.{token}.tmp",
        }
        canonical = {
            CANONICAL_FILENAME: self.output_file,
            METADATA_FILENAME: self.metadata_file,
        }
        backups = {
            name: self.output_dir / f".{name}.{token}.bak" for name in temporary
        }
        for path in [*temporary.values(), *backups.values()]:
            path.unlink(missing_ok=True)

        try:
            parquet_tmp = temporary[CANONICAL_FILENAME]
            metadata_tmp = temporary[METADATA_FILENAME]
            self._write_parquet(processed_df, parquet_tmp)
            readback = self._read_parquet(parquet_tmp)
            self._validate_readback(processed_df, readback)
            metadata = self._build_metadata(
                readback, source_snapshot, self._sha256(parquet_tmp)
            )
            metadata_tmp.write_text(
                json.dumps(asdict(metadata), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            promoted: list[str] = []
            try:
                for name, destination in canonical.items():
                    if destination.exists():
                        destination.replace(backups[name])
                for name in (CANONICAL_FILENAME, METADATA_FILENAME):
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
        except SilverMaterializationError:
            raise
        except Exception as exc:
            logger.error("Silver publication failed (error_class=%s)", type(exc).__name__)
            raise SilverMaterializationError("Canonical Silver publication failed") from exc
        finally:
            for path in temporary.values():
                path.unlink(missing_ok=True)
            for path in backups.values():
                path.unlink(missing_ok=True)

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
        try:
            memory_limit, threads, row_group_size = SilverMaterializer._writer_settings()
            connection.execute(f"SET memory_limit = '{memory_limit}'")
            connection.execute(f"SET threads = {threads}")
            connection.execute("SET preserve_insertion_order = false")
            connection.register("_silver_output", frame)
            escaped_path = str(path).replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM _silver_output) TO '{escaped_path}' "
                f"(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE {row_group_size})"
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
        output_sha256: str,
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
            schema_version="2.1.0",
            processing_version="2.1.0",
            output_sha256=output_sha256,
            source_distribution={str(key): int(value) for key, value in source_distribution.items()},
            source_snapshot=source_snapshot,
        )

    @staticmethod
    def _writer_settings() -> tuple[str, int, int]:
        memory_limit = os.getenv(
            "ROOMBEACON_DUCKDB_MEMORY_LIMIT", DEFAULT_DUCKDB_MEMORY_LIMIT
        ).strip().upper()
        if not re.fullmatch(r"[1-9][0-9]*(?:KB|MB|GB)", memory_limit):
            raise SilverMaterializationError("Invalid ROOMBEACON_DUCKDB_MEMORY_LIMIT")
        try:
            threads = int(os.getenv("ROOMBEACON_DUCKDB_THREADS", str(DEFAULT_DUCKDB_THREADS)))
            row_group_size = int(
                os.getenv(
                    "ROOMBEACON_PARQUET_ROW_GROUP_SIZE",
                    str(DEFAULT_PARQUET_ROW_GROUP_SIZE),
                )
            )
        except ValueError as exc:
            raise SilverMaterializationError("Invalid Silver writer integer setting") from exc
        if not 1 <= threads <= 8:
            raise SilverMaterializationError("ROOMBEACON_DUCKDB_THREADS must be between 1 and 8")
        if row_group_size < 2_048:
            raise SilverMaterializationError(
                "ROOMBEACON_PARQUET_ROW_GROUP_SIZE must be at least 2048"
            )
        return memory_limit, threads, row_group_size

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
