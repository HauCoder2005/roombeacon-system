"""ClickHouse load protocol, verified against an in-memory fake client."""

import math
import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from roombeacon_warehouse.config import Secret, WarehouseConfigError, WarehouseSettings
from roombeacon_warehouse.loader import (
    ClickHouseWarehouseLoader,
    WarehouseLoadError,
    WarehouseSchemaError,
    run_warehouse_load,
)
from roombeacon_warehouse.model import build_warehouse_model
from roombeacon_warehouse.schema import LOAD_LOG, LOAD_ORDER, TABLES, quote_identifier


class Result:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClickHouse:
    """Tracks tables by name; EXCHANGE swaps contents like the Atomic engine."""

    def __init__(self, drift: dict | None = None, short_insert: str | None = None):
        self.tables: dict[str, list] = {}
        self.schemas: dict[str, list[tuple[str, str]]] = {}
        self.commands: list[str] = []
        self.inserts: list[tuple[str, int]] = []
        self.drift = drift or {}
        self.short_insert = short_insert
        self.closed = False

    def command(self, sql, parameters=None, settings=None):
        self.commands.append(sql)
        create = re.match(r"CREATE TABLE IF NOT EXISTS `(\w+)`\.`(\w+)`", sql)
        if create:
            table = create.group(2)
            if table not in self.tables:
                self.tables[table] = []
                base = table.removesuffix("__staging")
                spec = LOAD_LOG if base == LOAD_LOG.name else TABLES[base]
                self.schemas[table] = list(self.drift.get(base, spec.columns))
            return
        truncate = re.match(r"TRUNCATE TABLE `(\w+)`\.`(\w+)`", sql)
        if truncate:
            self.tables[truncate.group(2)] = []
            return
        exchange = re.match(r"EXCHANGE TABLES `\w+`\.`(\w+)` AND `\w+`\.`(\w+)`", sql)
        if exchange:
            a, b = exchange.groups()
            self.tables[a], self.tables[b] = self.tables[b], self.tables[a]
            return
        raise AssertionError(f"unexpected command: {sql}")

    def insert_df(self, table=None, df=None, database=None, column_names=None, settings=None):
        assert list(df.columns) == list(column_names)
        base = table.removesuffix("__staging")
        spec = LOAD_LOG if base == LOAD_LOG.name else TABLES[base]
        for name, kind in spec.columns:
            for value in df[name]:
                if "Nullable(" in kind:
                    assert not (isinstance(value, float) and math.isnan(value)), (table, name)
                if kind == "Date":
                    assert isinstance(value, date), (table, name, type(value))
        rows = df.to_dict("records")
        if table == self.short_insert:
            rows = rows[:-1]
        self.tables[table] = self.tables.get(table, []) + rows
        self.inserts.append((table, len(rows)))

    def query(self, sql, parameters=None, settings=None):
        if "system.columns" in sql:
            assert set(parameters) == {"database", "table"}
            return Result(self.schemas.get(parameters["table"], []))
        count = re.match(r"SELECT count\(\) FROM `\w+`\.`(\w+)`", sql)
        if count:
            return Result([(len(self.tables[count.group(1)]),)])
        raise AssertionError(f"unexpected query: {sql}")

    def close(self):
        self.closed = True


def _settings(**overrides):
    values = dict(
        enabled=True, host="127.0.0.1", port=8123, database="roombeacon_dw",
        user="roombeacon_loader", password=Secret("pw"), secure=False,
        connect_timeout_seconds=5, query_timeout_seconds=60, source="test",
    )
    values.update(overrides)
    return WarehouseSettings(**values)


def test_load_stages_verifies_then_exchanges_every_table(pipeline_inputs):
    model = build_warehouse_model(pipeline_inputs["curated"], pipeline_inputs["silver"], Path(pipeline_inputs["curated"]).parent / "stage")
    client = FakeClickHouse()

    result = ClickHouseWarehouseLoader(client, "roombeacon_dw").load(model)

    for name in LOAD_ORDER:
        assert len(client.tables[name]) == model.row_counts()[name], name
        assert client.tables[f"{name}__staging"] == []
    exchanges = [c for c in client.commands if c.startswith("EXCHANGE")]
    assert len(exchanges) == len(LOAD_ORDER)
    # All staging inserts happen before the first exchange.
    first_exchange = client.commands.index(exchanges[0])
    assert all(not c.startswith("TRUNCATE") or "__staging" in c for c in client.commands[:first_exchange])
    assert result.row_counts == model.row_counts()
    assert len(client.tables["etl_load_log"]) == 1
    assert client.tables["etl_load_log"][0]["snapshot_id"] == "snap-wh"


def test_reload_replaces_rather_than_appends(pipeline_inputs):
    model = build_warehouse_model(pipeline_inputs["curated"], pipeline_inputs["silver"], Path(pipeline_inputs["curated"]).parent / "stage")
    client = FakeClickHouse()
    loader = ClickHouseWarehouseLoader(client, "roombeacon_dw")

    loader.load(model)
    loader.load(model)

    for name in LOAD_ORDER:
        assert len(client.tables[name]) == model.row_counts()[name]
    assert len(client.tables["etl_load_log"]) == 2


def test_row_count_mismatch_aborts_before_any_exchange(pipeline_inputs):
    model = build_warehouse_model(pipeline_inputs["curated"], pipeline_inputs["silver"], Path(pipeline_inputs["curated"]).parent / "stage")
    client = FakeClickHouse(short_insert="fact_listing_observation__staging")

    with pytest.raises(WarehouseLoadError, match="fact_listing_observation"):
        ClickHouseWarehouseLoader(client, "roombeacon_dw").load(model)

    assert not any(c.startswith("EXCHANGE") for c in client.commands)
    assert not any(table == "etl_load_log" for table, _ in client.inserts)


def test_schema_drift_fails_closed(pipeline_inputs):
    model = build_warehouse_model(pipeline_inputs["curated"], pipeline_inputs["silver"], Path(pipeline_inputs["curated"]).parent / "stage")
    drifted = {"dim_source": (("source_key", "Int64"), ("source_name", "String"))}
    client = FakeClickHouse(drift=drifted)

    with pytest.raises(WarehouseSchemaError, match="dim_source"):
        ClickHouseWarehouseLoader(client, "roombeacon_dw").load(model)
    assert not client.inserts


def test_ddl_is_mergetree_with_quoted_identifiers():
    ddl = TABLES["fact_listing_observation"].ddl("roombeacon_dw")

    assert ddl.startswith("CREATE TABLE IF NOT EXISTS `roombeacon_dw`.`fact_listing_observation`")
    assert "ENGINE = MergeTree" in ddl
    assert "PARTITION BY toYYYYMM(observed_date)" in ddl
    with pytest.raises(ValueError):
        quote_identifier("dw`; DROP TABLE x")
    with pytest.raises(ValueError):
        ClickHouseWarehouseLoader(FakeClickHouse(), "bad name")


def test_run_skips_cleanly_when_disabled(pipeline_inputs):
    with pytest.raises(WarehouseConfigError, match="WAREHOUSE_ENABLED"):
        run_warehouse_load(
            pipeline_inputs["curated"], pipeline_inputs["silver"],
            settings=_settings(enabled=False),
            client_factory=lambda s: pytest.fail("must not connect when disabled"),
        )


def test_run_builds_loads_and_closes_the_client(pipeline_inputs):
    client = FakeClickHouse()

    summary = run_warehouse_load(
        pipeline_inputs["curated"], pipeline_inputs["silver"],
        settings=_settings(), client_factory=lambda s: client,
    )

    assert summary["snapshot_id"] == "snap-wh"
    assert summary["row_counts"]["fact_listing_observation"] == 5
    assert summary["settings"]["password"] == "***"
    assert "pw" not in str(summary)
    assert client.closed is True
