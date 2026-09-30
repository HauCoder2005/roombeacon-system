"""Publish the canonical DuckDB Silver table and its compatibility mirror.

``silver.rental_listings`` is the source of truth.  The Parquet file is a
deprecated, temporary compatibility mirror and is refreshed only after the
canonical table has passed grain and schema validation.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.duckdb.connection import create_analytics_connection, resolve_runtime_path
from roombeacon_crawler.config.get_env import env

logger = logging.getLogger(__name__)

CANONICAL_TABLE = "silver.rental_listings"
COMPATIBILITY_MIRROR = "rental_latest.parquet"
REQUIRED_COLUMNS = [
    "source_code", "rental_post_id", "source_listing_id", "title_raw", "url",
    "price_amount", "area_value", "location_raw", "latest_observed_at",
]


@dataclass
class SilverMetadata:
    generated_at: str
    row_count: int
    unique_listing_count: int
    canonical_table: str
    compatibility_mirror: str
    mirror_status: str
    min_observed_at: str | None
    max_observed_at: str | None
    schema_version: str
    materializer_version: str
    columns: list[str]
    source_distribution: dict[str, int]


class SilverMaterializationError(Exception):
    """Raised when canonical Silver or compatibility publication fails."""


class SilverMaterializer:
    """Materialize DuckDB Silver, validate it, then export the Parquet mirror."""

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
        self.output_file = self.output_dir / COMPATIBILITY_MIRROR
        self.metadata_file = self.output_dir / "rental_latest.metadata.json"
        self.tmp_file = self.output_dir / "rental_latest.parquet.tmp"

    def materialize(self, processed_df: pd.DataFrame, conn: Any | None = None) -> SilverMetadata:
        """Run the only supported publication order: DuckDB, validate, mirror."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        connection = conn if conn is not None else create_analytics_connection()
        self._validate_dataframe(processed_df)

        try:
            self.materialize_duckdb_silver(processed_df, connection)
            canonical = self.validate_silver(connection)
            self.export_parquet_mirror(connection, canonical)
            metadata = self._build_metadata(canonical)
            self.metadata_file.write_text(
                json.dumps(asdict(metadata), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return metadata
        except SilverMaterializationError:
            raise
        except Exception as exc:
            logger.error("Silver publication failed (error_class=%s)", type(exc).__name__)
            raise SilverMaterializationError("Silver publication failed") from exc
        finally:
            if self.tmp_file.exists():
                self.tmp_file.unlink()

    def materialize_duckdb_silver(self, processed_df: pd.DataFrame, conn: Any) -> None:
        """Atomically replace ``silver.rental_listings`` from a validated frame."""
        self._validate_dataframe(processed_df)
        conn.register("_roombeacon_silver_input", processed_df)
        try:
            conn.execute("BEGIN TRANSACTION")
            conn.execute("CREATE SCHEMA IF NOT EXISTS silver")
            conn.execute("DROP TABLE IF EXISTS silver._rental_listings_next")
            conn.execute(
                "CREATE TABLE silver._rental_listings_next AS "
                "SELECT * FROM _roombeacon_silver_input"
            )
            self._validate_table(conn, "silver._rental_listings_next")
            conn.execute("DROP TABLE IF EXISTS silver.rental_listings")
            conn.execute("ALTER TABLE silver._rental_listings_next RENAME TO rental_listings")
            conn.execute("COMMIT")
        except Exception as exc:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            if isinstance(exc, SilverMaterializationError):
                raise
            raise SilverMaterializationError("Canonical DuckDB Silver materialization failed") from exc
        finally:
            try:
                conn.unregister("_roombeacon_silver_input")
            except Exception:
                pass

    def validate_silver(self, conn: Any) -> pd.DataFrame:
        """Read back and validate the canonical table; return its exact dataset."""
        self._validate_table(conn, CANONICAL_TABLE)
        frame = conn.execute(f"SELECT * FROM {CANONICAL_TABLE}").df()
        self._validate_dataframe(frame)
        return frame

    def export_parquet_mirror(self, conn: Any, canonical: pd.DataFrame | None = None) -> None:
        """Atomically refresh the deprecated mirror from canonical DuckDB Silver."""
        frame = canonical if canonical is not None else self.validate_silver(conn)
        if self.tmp_file.exists():
            self.tmp_file.unlink()
        try:
            escaped_path = str(self.tmp_file).replace("'", "''")
            conn.execute(
                f"COPY (SELECT * FROM {CANONICAL_TABLE}) TO '{escaped_path}' (FORMAT PARQUET)"
            )
            mirror_columns = [
                row[0] for row in conn.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{escaped_path}')"
                ).fetchall()
            ]
            mirror_row_count, mirror_unique_count, mirror_null_count = conn.execute(
                f"SELECT count(*), count(DISTINCT rental_post_id), "
                f"count(*) FILTER (WHERE rental_post_id IS NULL) "
                f"FROM read_parquet('{escaped_path}')"
            ).fetchone()
            if mirror_columns != list(frame.columns):
                raise SilverMaterializationError("Compatibility mirror columns differ from canonical Silver")
            if mirror_row_count != len(frame):
                raise SilverMaterializationError("Compatibility mirror row count differs from canonical Silver")
            if mirror_null_count or mirror_row_count != mirror_unique_count:
                raise SilverMaterializationError("Compatibility mirror violates rental_post_id grain")
            if mirror_unique_count != frame.rental_post_id.nunique():
                raise SilverMaterializationError("Compatibility mirror identity count differs from canonical Silver")
            self.tmp_file.replace(self.output_file)
        except Exception as exc:
            if isinstance(exc, SilverMaterializationError):
                raise
            raise SilverMaterializationError("Compatibility mirror export failed") from exc

    def _validate_table(self, conn: Any, table_name: str) -> None:
        row_count, unique_count, null_count = conn.execute(
            f"SELECT count(*), count(DISTINCT rental_post_id), "
            f"count(*) FILTER (WHERE rental_post_id IS NULL) FROM {table_name}"
        ).fetchone()
        if row_count == 0:
            raise SilverMaterializationError("Canonical Silver table is empty")
        if null_count:
            raise SilverMaterializationError("Canonical Silver contains null rental_post_id")
        if row_count != unique_count:
            raise SilverMaterializationError("Canonical Silver rental_post_id must be unique")

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

    def _build_metadata(self, frame: pd.DataFrame) -> SilverMetadata:
        observed = frame.latest_observed_at.dropna()
        source_distribution = frame.source_code.value_counts().to_dict()
        return SilverMetadata(
            generated_at=datetime.now(timezone.utc).astimezone().isoformat(),
            row_count=len(frame),
            unique_listing_count=int(frame.rental_post_id.nunique()),
            canonical_table=CANONICAL_TABLE,
            compatibility_mirror=COMPATIBILITY_MIRROR,
            mirror_status="DEPRECATED_TEMPORARY_COMPATIBILITY_MIRROR",
            min_observed_at=str(observed.min()) if not observed.empty else None,
            max_observed_at=str(observed.max()) if not observed.empty else None,
            schema_version="2.0.0",
            materializer_version="2.0.0",
            columns=frame.columns.tolist(),
            source_distribution={str(key): int(value) for key, value in source_distribution.items()},
        )
