from decimal import Decimal

import pandas as pd
import pytest

from notebooks.utils.silver_processing import (
    SilverQualityGateError,
    build_silver_dataset,
    evaluate_pre_silver_quality_gate,
)


def _bronze_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_code": "phongtro123",
                "rental_post_id": 1,
                "source_listing_id": "a-1",
                "title_raw": " 🏠  Phòng trọ Quận 1  ",
                "url": "https://example.test/1",
                "price_amount": Decimal("3500000.00"),
                "area_value": Decimal("25.00"),
                "full_address_text": "Phường Bến Nghé, Quận 1, TP.HCM",
                "location_raw": "Quận 1",
                "full_address_inherited": False,
                "map_provider": "google_maps_embed",
                "map_latitude": 10.7769,
                "map_longitude": 106.7009,
                "map_query_raw": None,
                "best_address_text": "Phường Bến Nghé, Quận 1, TP.HCM",
                "best_address_source": "full_address_text",
                "latest_observed_at": "2026-09-30 10:00:00",
                "first_observed_at": "2026-09-28 10:00:00",
                "last_observed_at": "2026-09-30 10:00:00",
                "active_days": 2,
            },
            {
                "source_code": "nhatrovn",
                "rental_post_id": 2,
                "source_listing_id": "b-2",
                "title_raw": "Phòng trọ Quận 1",
                "url": "https://example.test/2",
                "price_amount": None,
                "area_value": Decimal("25.00"),
                "full_address_text": None,
                "location_raw": "Quận 1",
                "full_address_inherited": False,
                "map_provider": "unknown",
                "map_latitude": 999.0,
                "map_longitude": 106.7,
                "map_query_raw": None,
                "best_address_text": "Quận 1",
                "best_address_source": "location_raw",
                "latest_observed_at": "2026-09-29 10:00:00",
                "first_observed_at": "2026-09-30 10:00:00",
                "last_observed_at": "2026-09-29 10:00:00",
                "active_days": -1,
            },
        ]
    )


def _evidence(rows: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rental_post_id": rows.rental_post_id,
            "evidence_observation_id": [11, 22],
            "evidence_version_time_matches": [True, True],
            "evidence_price_id": [111, 222],
            "price_raw": ["3.5 triệu/tháng", None],
            "currency": ["VND", "VND"],
            "period": ["MONTH", "MONTH"],
            "evidence_area_id": [111, 222],
            "area_raw": ["25 m2", "25 m2"],
            "price_lineage_aligned": [True, True],
            "area_lineage_aligned": [True, True],
        }
    )


def test_build_silver_dataset_preserves_raw_grain_and_adds_quality_evidence():
    bronze = _bronze_rows()
    silver = build_silver_dataset(bronze, _evidence(bronze))

    assert len(silver) == len(bronze)
    assert silver.rental_post_id.tolist() == bronze.rental_post_id.tolist()
    pd.testing.assert_frame_equal(silver[bronze.columns], bronze)
    assert silver.rental_post_id.is_unique
    assert {
        "title_clean",
        "title_quality_status",
        "price_amount_clean",
        "price_quality_status",
        "area_value_clean",
        "area_quality_status",
        "coordinate_quality_status",
        "duplicate_candidate_status",
        "temporal_quality_status",
        "row_quality_status",
    } <= set(silver.columns)
    assert silver.loc[0, "title_clean"] == "Phòng trọ Quận 1"
    assert silver.loc[1, "coordinate_quality_status"] == "INVALID"
    assert silver.loc[1, "temporal_quality_status"] == "REQUIRES_REVIEW"


def test_quality_gate_passes_valid_preserving_transformation():
    bronze = _bronze_rows()
    silver = build_silver_dataset(bronze, _evidence(bronze))

    report = evaluate_pre_silver_quality_gate(bronze, silver)

    assert report.passed
    assert report.results["row_count_preserved"]
    assert report.results["raw_source_fields_unchanged"]
    assert report.results["invalid_coordinates_not_usable"]
    assert report.results["documented_status_values_only"]


def test_quality_gate_rejects_row_deletion_and_raw_mutation():
    bronze = _bronze_rows()
    silver = build_silver_dataset(bronze, _evidence(bronze)).iloc[:1].copy()
    silver.loc[silver.index[0], "title_raw"] = "mutated"

    with pytest.raises(SilverQualityGateError) as exc_info:
        evaluate_pre_silver_quality_gate(bronze, silver)

    assert "row_count_preserved" in str(exc_info.value)
    assert "raw_source_fields_unchanged" in str(exc_info.value)


def test_duplicate_candidates_and_outliers_remain_in_silver():
    bronze = _bronze_rows()
    duplicate = bronze.iloc[[0]].copy()
    duplicate["rental_post_id"] = 3
    duplicate["source_listing_id"] = "a-3"
    bronze = pd.concat([bronze, duplicate], ignore_index=True)
    evidence = _evidence(bronze.iloc[:2])
    evidence = pd.concat([evidence, evidence.iloc[[0]].assign(rental_post_id=3)], ignore_index=True)

    silver = build_silver_dataset(bronze, evidence)
    report = evaluate_pre_silver_quality_gate(bronze, silver)

    assert report.passed
    assert len(silver) == 3
    assert silver.duplicate_candidate_status.eq("POSSIBLE_DUPLICATE").sum() == 2
    assert "numeric_outlier_status" in silver


def test_missing_title_is_classified_without_nullable_boolean_failure():
    bronze = _bronze_rows()
    bronze.loc[1, "title_raw"] = None

    silver = build_silver_dataset(bronze, _evidence(bronze))

    assert silver.loc[1, "title_clean"] is None
    assert silver.loc[1, "title_quality_status"] == "MISSING"


def test_clean_numeric_columns_use_stable_non_object_dtype_for_duckdb():
    bronze = _bronze_rows()
    bronze.loc[1, "price_amount"] = Decimal("1350000000.00")
    evidence = _evidence(bronze)
    evidence.loc[1, "price_raw"] = "1350 triệu/tháng"

    silver = build_silver_dataset(bronze, evidence)

    assert silver.price_amount_clean.dtype != object
    assert silver.area_value_clean.dtype != object
    assert silver.price_amount_clean.max() == 1_350_000_000
