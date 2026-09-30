import json
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from analytics.silver.materializer import (
    SilverMaterializationError,
    SilverMaterializer,
    SilverMetadata,
)


def _silver_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"source_code": "phongtro123", "rental_post_id": 101,
         "source_listing_id": "pt_101", "title_raw": "Phòng trọ Quận 1",
         "url": "https://example.test/101", "price_amount": 3_500_000.0,
         "area_value": 25.0, "location_raw": "Quận 1, TP.HCM",
         "latest_observed_at": "2026-08-23 10:00:00",
         "title_clean": "Phòng trọ Quận 1", "row_quality_status": "READY"},
        {"source_code": "nhatrovn", "rental_post_id": 102,
         "source_listing_id": "nv_102", "title_raw": "Nhà trọ Bình Thạnh",
         "url": "https://example.test/102", "price_amount": 2_800_000.0,
         "area_value": 20.0, "location_raw": "Bình Thạnh, TP.HCM",
         "latest_observed_at": "2026-08-23 11:00:00",
         "title_clean": "Nhà trọ Bình Thạnh", "row_quality_status": "READY_WITH_FLAGS"},
    ])


@pytest.fixture
def materializer(tmp_path: Path) -> SilverMaterializer:
    return SilverMaterializer(output_dir=tmp_path, valid_sources={"phongtro123", "nhatrovn"})


def test_materialize_publishes_duckdb_before_compatibility_mirror(materializer, tmp_path):
    conn = duckdb.connect(str(tmp_path / "analytics.duckdb"))

    metadata = materializer.materialize(_silver_frame(), conn=conn)

    assert isinstance(metadata, SilverMetadata)
    assert metadata.canonical_table == "silver.rental_listings"
    canonical = conn.execute("SELECT * FROM silver.rental_listings ORDER BY rental_post_id").df()
    mirror_path = str(materializer.output_file).replace("'", "''")
    mirror = conn.execute(
        f"SELECT * FROM read_parquet('{mirror_path}') ORDER BY rental_post_id"
    ).df()
    assert list(canonical.columns) == list(mirror.columns)
    assert len(canonical) == len(mirror) == 2
    assert canonical.rental_post_id.nunique() == mirror.rental_post_id.nunique() == 2


def test_failed_canonical_materialization_does_not_refresh_existing_mirror(materializer, tmp_path):
    conn = duckdb.connect(str(tmp_path / "analytics.duckdb"))
    materializer.materialize(_silver_frame(), conn=conn)
    original_bytes = materializer.output_file.read_bytes()
    invalid = pd.concat([_silver_frame(), _silver_frame().iloc[[0]]], ignore_index=True)

    with pytest.raises(SilverMaterializationError):
        materializer.materialize(invalid, conn=conn)

    assert materializer.output_file.read_bytes() == original_bytes
    assert conn.execute("SELECT count(*) FROM silver.rental_listings").fetchone()[0] == 2


def test_validate_silver_rejects_table_grain_mismatch(materializer, tmp_path):
    conn = duckdb.connect(str(tmp_path / "analytics.duckdb"))
    conn.execute("CREATE SCHEMA silver")
    conn.register("bad", pd.concat([_silver_frame(), _silver_frame().iloc[[0]]], ignore_index=True))
    conn.execute("CREATE TABLE silver.rental_listings AS SELECT * FROM bad")

    with pytest.raises(SilverMaterializationError, match="unique"):
        materializer.validate_silver(conn)


def test_metadata_marks_parquet_as_temporary_compatibility_mirror(materializer, tmp_path):
    conn = duckdb.connect(str(tmp_path / "analytics.duckdb"))
    materializer.materialize(_silver_frame(), conn=conn)
    data = json.loads(materializer.metadata_file.read_text(encoding="utf-8"))

    assert data["canonical_table"] == "silver.rental_listings"
    assert data["compatibility_mirror"] == "rental_latest.parquet"
    assert data["mirror_status"] == "DEPRECATED_TEMPORARY_COMPATIBILITY_MIRROR"
    assert data["row_count"] == data["unique_listing_count"] == 2
    assert "password" not in str(data).lower()


def test_materialize_accepts_large_decimal_clean_price(materializer, tmp_path):
    conn = duckdb.connect(str(tmp_path / "analytics.duckdb"))
    frame = _silver_frame()
    frame["price_amount_clean"] = pd.Series(
        [Decimal("3500000.00"), Decimal("1350000000.00")], dtype="object"
    )

    materializer.materialize(frame, conn=conn)

    assert conn.execute(
        "SELECT max(price_amount_clean) FROM silver.rental_listings"
    ).fetchone()[0] == 1_350_000_000
