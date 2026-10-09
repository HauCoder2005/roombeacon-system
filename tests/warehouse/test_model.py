"""Dimensional model built offline from curated Parquet + Silver."""

import json
from pathlib import Path

import pandas as pd
import pytest

from roombeacon_warehouse.model import (
    WarehouseModelError,
    build_warehouse_model,
    stable_key,
)
from roombeacon_warehouse.schema import LOAD_ORDER, TABLES


PII_OR_FREE_TEXT = {"title_raw", "title_clean", "url", "seller_phone", "seller_name", "price_raw", "area_raw"}


def _model(inputs, staging="stage"):
    return build_warehouse_model(
        inputs["curated"], inputs["silver"], Path(inputs["curated"]).parent / staging
    )


def _tables(inputs, staging="stage"):
    model = _model(inputs, staging)
    return {name: model.frame(name) for name in LOAD_ORDER}


def test_model_contains_every_table_with_the_declared_column_order(pipeline_inputs):
    model = _model(pipeline_inputs)

    assert list(model.files) == list(LOAD_ORDER)
    assert set(model.row_counts()) == set(LOAD_ORDER)
    for name in LOAD_ORDER:
        frame = model.frame(name)
        assert list(frame.columns) == TABLES[name].column_names, name
        assert not PII_OR_FREE_TEXT & set(frame.columns), name
    assert model.snapshot_id == "snap-wh"


def test_facts_reference_existing_dimension_keys(pipeline_inputs):
    t = _tables(pipeline_inputs)
    dims = {
        "date_key": set(t["dim_date"].date_key),
        "source_key": set(t["dim_source"].source_key),
        "location_key": set(t["dim_location"].location_key),
    }
    for dim in ("dim_date", "dim_source", "dim_location"):
        key = TABLES[dim].column_names[0]
        assert t[dim][key].is_unique, dim
    for fact in ("fact_listing_observation", "fact_listing_snapshot", "agg_market_daily"):
        frame = t[fact]
        for column, keys in (
            ("date_key", dims["date_key"]), ("as_of_date_key", dims["date_key"]),
            ("source_key", dims["source_key"]), ("location_key", dims["location_key"]),
            ("district_location_key", dims["location_key"]),
        ):
            if column in frame:
                assert set(frame[column]) <= keys, (fact, column)


def test_observation_fact_keeps_curated_grain(pipeline_inputs):
    t = _tables(pipeline_inputs)
    fact = t["fact_listing_observation"]

    assert fact.observation_id.tolist() == [101, 102, 103, 104, 105]
    assert fact.date_key.tolist() == [20260920, 20260921, 20260921, 20260921, 20260921]
    # Ward-level location for post 11; district fallback for post 12 (no ward).
    locations = t["dim_location"].set_index("location_key")
    assert locations.loc[fact.location_key.iloc[0], "location_level"] == "WARD"
    assert locations.loc[fact.location_key.iloc[3], "location_level"] == "DISTRICT"
    assert locations.loc[fact.district_location_key.iloc[0], "district"] == "Quận 1"


def test_snapshot_fact_has_one_row_per_post_with_history_counts(pipeline_inputs):
    snapshot = _tables(pipeline_inputs)["fact_listing_snapshot"].set_index("rental_post_id")

    assert snapshot.index.tolist() == [11, 12, 13]
    assert snapshot.loc[11, "observation_count"] == 3
    assert snapshot.loc[11, "content_version_count"] == 2
    assert snapshot.loc[11, "price_amount_clean"] == 3_500_000.0
    assert pd.isna(snapshot.loc[12, "price_amount_clean"])
    assert set(snapshot.as_of_date_key) == {20260921}


def test_dim_date_is_contiguous_and_calendar_correct(pipeline_inputs):
    dates = _tables(pipeline_inputs)["dim_date"]

    assert dates.date_key.tolist() == [20260920, 20260921]
    row = dates.set_index("date_key").loc[20260920]
    assert (row.year, row.quarter, row.month, row.day) == (2026, 3, 9, 20)
    assert row.day_of_week == 7 and bool(row.is_weekend)  # 2026-09-20 is a Sunday


def test_market_daily_uses_last_daily_state_of_eligible_rent_listings(pipeline_inputs):
    t = _tables(pipeline_inputs)
    marts = t["agg_market_daily"]
    q1 = t["dim_location"].query("location_level == 'DISTRICT' and district == 'Quận 1'").location_key.item()
    q7 = t["dim_location"].query("location_level == 'DISTRICT' and district == 'Quận 7'").location_key.item()
    pt = t["dim_source"].query("source_code == 'phongtro123'").source_key.item()
    mogi = t["dim_source"].query("source_code == 'mogi'").source_key.item()

    q1_0921 = marts.query("date_key == 20260921 and district_location_key == @q1 and source_key == @pt").iloc[0]
    assert q1_0921.listings_observed == 2       # posts 11 and 13
    assert q1_0921.observations == 3            # 102, 103, 105
    assert q1_0921.new_listings == 1            # post 13 first seen this day
    assert q1_0921.content_changes == 2         # 103 changed, 105 first sighting
    assert q1_0921.price_changes == 1           # 3.0M -> 3.5M
    assert q1_0921.market_eligible_listings == 2
    # Last state of the day: post 11 at 3.5M (not the 08:00 3.0M), post 13 at 4.0M.
    assert q1_0921.median_price == pytest.approx(3_750_000.0)
    assert q1_0921.median_area == pytest.approx(22.5)

    q7_0921 = marts.query("date_key == 20260921 and district_location_key == @q7 and source_key == @mogi").iloc[0]
    assert q7_0921.market_eligible_listings == 0
    assert pd.isna(q7_0921.median_price)


def test_keys_are_stable_across_builds_and_runs(pipeline_inputs):
    first = _tables(pipeline_inputs, "stage_a")
    second = _tables(pipeline_inputs, "stage_b")

    for name in LOAD_ORDER:
        pd.testing.assert_frame_equal(
            first[name].drop(columns=[c for c in ("load_id",) if c in first[name]]),
            second[name].drop(columns=[c for c in ("load_id",) if c in second[name]]),
        )
    assert stable_key("SOURCE", "mogi") == stable_key("SOURCE", "mogi")
    assert 0 < stable_key("SOURCE", "mogi") < 2**63


def test_tampered_curated_partition_is_rejected(pipeline_inputs):
    curated = Path(pipeline_inputs["curated"])
    victim = next(curated.rglob("*.parquet"))
    victim.write_bytes(victim.read_bytes() + b"tamper")

    with pytest.raises(WarehouseModelError, match="sha256"):
        _model(pipeline_inputs)


def test_silver_from_another_snapshot_is_rejected(pipeline_inputs):
    meta_path = Path(pipeline_inputs["silver"]) / "rental_listings.metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["source_snapshot"]["snapshot_id"] = "other"
    meta_path.write_text(json.dumps(meta))

    with pytest.raises(WarehouseModelError, match="snapshot"):
        _model(pipeline_inputs)
