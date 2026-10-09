"""Load the dimensional model into ClickHouse with staging + atomic swap.

Protocol per load:
1. ``CREATE TABLE IF NOT EXISTS`` every table, its ``__staging`` twin and the
   load log; verify live column names/types against the declared schema.
2. Truncate and fill every staging table, verifying server-side row counts.
3. Only after all tables are staged, ``EXCHANGE TABLES`` each live/staging
   pair (atomic per table on the Atomic database engine), then truncate the
   now-stale staging copies and append one ``etl_load_log`` row.

A failure before step 3 leaves the served warehouse unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import pandas as pd

from .config import WarehouseSettings, load_warehouse_settings
from .model import WarehouseModel, build_warehouse_model
from .schema import LOAD_LOG, LOAD_ORDER, TABLES, TableSpec, quote_identifier


logger = logging.getLogger(__name__)
STAGING_SUFFIX = "__staging"


class WarehouseLoadError(RuntimeError):
    """Raised when a staged load cannot be verified."""


class WarehouseSchemaError(WarehouseLoadError):
    """Raised when a live table no longer matches the declared schema."""


@dataclass(frozen=True)
class LoadResult:
    load_id: str
    snapshot_id: str
    row_counts: dict[str, int]


def _normalize_type(value: str) -> str:
    return "".join(value.split())


def coerce_batch(spec: TableSpec, batch: pd.DataFrame) -> pd.DataFrame:
    """Map pandas values to what the declared ClickHouse type expects.

    NaN/NaT become None for Nullable columns (NaN would load as a float NaN),
    Date columns become ``datetime.date`` and integer columns plain int64.
    """
    out = batch.copy()
    for name, kind in spec.columns:
        column = out[name]
        nullable = "Nullable(" in kind
        if kind.startswith("Date") and not kind.startswith("DateTime"):
            values = pd.to_datetime(column)
            out[name] = [None if pd.isna(v) else v.date() for v in values]
        elif nullable:
            if "Int" in kind:
                column = column.astype("Int64")
            out[name] = column.astype(object).where(column.notna(), None)
        elif re.match(r"U?Int\d+$", kind):
            out[name] = column.astype("int64")
        elif kind == "Bool":
            out[name] = column.astype(bool)
    return out


class ClickHouseWarehouseLoader:
    def __init__(self, client: Any, database: str) -> None:
        quote_identifier(database)
        self.client = client
        self.database = database

    def _name(self, table: str) -> str:
        return f"{quote_identifier(self.database)}.{quote_identifier(table)}"

    def _verify_schema(self, table: str, spec: TableSpec) -> None:
        rows = self.client.query(
            "SELECT name, type FROM system.columns "
            "WHERE database = {database:String} AND table = {table:String} ORDER BY position",
            parameters={"database": self.database, "table": table},
        ).result_rows
        live = [(name, _normalize_type(kind)) for name, kind in rows]
        declared = [(name, _normalize_type(kind)) for name, kind in spec.columns]
        if live != declared:
            raise WarehouseSchemaError(
                f"{table} schema differs from the declared model; migrate it explicitly "
                f"(live={[n for n, _ in live]}, declared={[n for n, _ in declared]})"
            )

    def ensure_schema(self) -> None:
        for spec in (*(TABLES[name] for name in LOAD_ORDER), LOAD_LOG):
            targets = [spec.name]
            if spec is not LOAD_LOG:
                targets.append(spec.name + STAGING_SUFFIX)
            for table in targets:
                self.client.command(spec.ddl(self.database, table))
                self._verify_schema(table, spec)

    def _count(self, table: str) -> int:
        return int(self.client.query(f"SELECT count() FROM {self._name(table)}").result_rows[0][0])

    def load(self, model: WarehouseModel) -> LoadResult:
        load_id = uuid4().hex
        self.ensure_schema()
        expected = model.row_counts()
        for name in LOAD_ORDER:
            spec = TABLES[name]
            staging = name + STAGING_SUFFIX
            self.client.command(f"TRUNCATE TABLE {self._name(staging)}")
            for batch in model.iter_batches(name):
                self.client.insert_df(
                    table=staging, df=coerce_batch(spec, batch), database=self.database,
                    column_names=spec.column_names,
                )
            staged = self._count(staging)
            if staged != expected[name]:
                raise WarehouseLoadError(
                    f"{name}: staged {staged} rows but the model has {expected[name]}"
                )
            logger.info("Staged %s rows=%d load_id=%s", name, staged, load_id)

        for name in LOAD_ORDER:
            self.client.command(
                f"EXCHANGE TABLES {self._name(name)} AND {self._name(name + STAGING_SUFFIX)}"
            )
        for name in LOAD_ORDER:
            self.client.command(f"TRUNCATE TABLE {self._name(name + STAGING_SUFFIX)}")

        counts = model.row_counts()
        log_row = pd.DataFrame(
            [{
                "load_id": load_id,
                "snapshot_id": model.snapshot_id,
                "curated_metadata_sha256": model.curated_metadata_sha256,
                "silver_output_sha256": model.silver_output_sha256,
                "loaded_at": pd.Timestamp.now(tz="UTC"),
                "table_row_counts": json.dumps(counts, sort_keys=True),
                "status": "SUCCESS",
            }]
        )
        self.client.insert_df(
            table=LOAD_LOG.name, df=log_row, database=self.database,
            column_names=LOAD_LOG.column_names,
        )
        logger.info("Warehouse load complete load_id=%s snapshot_id=%s", load_id, model.snapshot_id)
        return LoadResult(load_id=load_id, snapshot_id=model.snapshot_id, row_counts=counts)


def create_clickhouse_client(settings: WarehouseSettings) -> Any:
    """HTTP client with bounded connect/read timeouts and a server-side cap."""
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=settings.host,
        port=settings.port,
        username=settings.user,
        password=settings.password.get_secret_value(),
        database=settings.database,
        secure=settings.secure,
        connect_timeout=settings.connect_timeout_seconds,
        send_receive_timeout=settings.query_timeout_seconds,
        settings={"max_execution_time": settings.query_timeout_seconds},
    )


def run_warehouse_load(
    curated_dir: Path,
    silver_dir: Path,
    *,
    settings: WarehouseSettings | None = None,
    client_factory: Callable[[WarehouseSettings], Any] = create_clickhouse_client,
    staging_root: Path | None = None,
) -> dict[str, Any]:
    """Build the model into a temporary staging directory and load it.

    Raises WarehouseConfigError when the warehouse is disabled. The staging
    Parquet files are removed after the load, successful or not.
    """
    settings = (settings or load_warehouse_settings()).require_enabled()
    staging_root = Path(staging_root) if staging_root else Path(curated_dir).parent
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".warehouse_staging.", dir=staging_root) as staging:
        model = build_warehouse_model(Path(curated_dir), Path(silver_dir), Path(staging))
        client = client_factory(settings)
        try:
            result = ClickHouseWarehouseLoader(client, settings.database).load(model)
        finally:
            client.close()
    return {
        "load_id": result.load_id,
        "snapshot_id": result.snapshot_id,
        "row_counts": result.row_counts,
        "settings": settings.redacted(),
    }
