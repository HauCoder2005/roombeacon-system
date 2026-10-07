import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import duckdb
import pytest

from analytics.silver.materializer import (
    CANONICAL_FILENAME,
    METADATA_FILENAME,
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


def test_materialize_writes_canonical_parquet_and_metadata(materializer):
    expected = _silver_frame()
    metadata = materializer.materialize(expected, quality_gate_passed=True)

    assert isinstance(metadata, SilverMetadata)
    assert materializer.output_file.name == CANONICAL_FILENAME == "rental_listings.parquet"
    assert materializer.metadata_file.name == METADATA_FILENAME == "rental_listings.metadata.json"
    assert materializer.output_file.exists() and materializer.metadata_file.exists()
    actual = duckdb.connect(":memory:").execute(
        "SELECT * FROM read_parquet(?)", [str(materializer.output_file)]
    ).df()
    assert len(actual) == len(expected) == actual.rental_post_id.nunique()
    assert list(actual.columns) == list(expected.columns)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_failed_quality_gate_does_not_publish_or_replace_silver(materializer):
    materializer.materialize(_silver_frame(), quality_gate_passed=True)
    original_parquet = materializer.output_file.read_bytes()
    original_metadata = materializer.metadata_file.read_bytes()

    with pytest.raises(SilverMaterializationError, match="quality gate failed"):
        materializer.materialize(_silver_frame(), quality_gate_passed=False)

    assert materializer.output_file.read_bytes() == original_parquet
    assert materializer.metadata_file.read_bytes() == original_metadata


def test_invalid_grain_does_not_replace_existing_canonical_file(materializer):
    materializer.materialize(_silver_frame(), quality_gate_passed=True)
    original_bytes = materializer.output_file.read_bytes()
    invalid = pd.concat([_silver_frame(), _silver_frame().iloc[[0]]], ignore_index=True)

    with pytest.raises(SilverMaterializationError, match="unique"):
        materializer.materialize(invalid, quality_gate_passed=True)

    assert materializer.output_file.read_bytes() == original_bytes


def test_metadata_describes_canonical_file(materializer):
    materializer.materialize(
        _silver_frame(), quality_gate_passed=True, source_snapshot={"view_name": "v_latest_posts"}
    )
    data = json.loads(materializer.metadata_file.read_text(encoding="utf-8"))

    assert data["dataset_name"] == "rental_listings"
    assert data["layer"] == "silver"
    assert data["canonical_path"].endswith("rental_listings.parquet")
    assert data["row_count"] == data["distinct_rental_post_id"] == 2
    assert data["column_count"] == len(_silver_frame().columns)
    assert data["columns"] == _silver_frame().columns.tolist()
    assert data["source_snapshot"] == {"view_name": "v_latest_posts"}
    assert "mirror" not in str(data).lower()


def test_materialize_accepts_large_decimal_clean_price(materializer):
    frame = _silver_frame()
    frame["price_amount_clean"] = pd.Series(
        [Decimal("3500000.00"), Decimal("1350000000.00")], dtype="object"
    )

    materializer.materialize(frame, quality_gate_passed=True)
    actual = duckdb.connect(":memory:").execute(
        "SELECT * FROM read_parquet(?)", [str(materializer.output_file)]
    ).df()

    assert actual.price_amount_clean.max() == Decimal("1350000000.00")


def test_metadata_records_output_hash_and_writer_settings(materializer, monkeypatch):
    statements = []
    original_connect = duckdb.connect

    class RecordingConnection:
        def __init__(self):
            self.connection = original_connect(":memory:")

        def register(self, *args, **kwargs):
            return self.connection.register(*args, **kwargs)

        def execute(self, statement, *args, **kwargs):
            statements.append(str(statement))
            return self.connection.execute(statement, *args, **kwargs)

        def close(self):
            return self.connection.close()

    monkeypatch.setattr(duckdb, "connect", lambda *args, **kwargs: RecordingConnection())
    metadata = materializer.materialize(_silver_frame(), quality_gate_passed=True)

    assert len(metadata.output_sha256) == 64
    sql = "\n".join(statements).upper()
    assert "MEMORY_LIMIT" in sql
    assert "THREADS" in sql
    assert "PRESERVE_INSERTION_ORDER" in sql
    assert "COMPRESSION ZSTD" in sql
    assert "ROW_GROUP_SIZE" in sql


def test_metadata_promotion_failure_restores_both_previous_files(
    materializer, monkeypatch
):
    materializer.materialize(_silver_frame(), quality_gate_passed=True)
    original_parquet = materializer.output_file.read_bytes()
    original_metadata = materializer.metadata_file.read_bytes()
    real_replace = Path.replace

    def fail_metadata_promotion(source, target):
        if source.name.startswith(f".{METADATA_FILENAME}.") and source.suffix == ".tmp":
            raise OSError("simulated metadata promotion failure")
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_metadata_promotion)

    with pytest.raises(SilverMaterializationError, match="publication failed"):
        materializer.materialize(_silver_frame(), quality_gate_passed=True)

    assert materializer.output_file.read_bytes() == original_parquet
    assert materializer.metadata_file.read_bytes() == original_metadata


def test_publication_validates_parquet_without_full_dataframe_readback(
    materializer, monkeypatch
):
    monkeypatch.setattr(
        materializer,
        "_read_parquet",
        lambda path: (_ for _ in ()).throw(AssertionError("full readback is forbidden")),
    )

    metadata = materializer.materialize(_silver_frame(), quality_gate_passed=True)

    assert metadata.row_count == 2
