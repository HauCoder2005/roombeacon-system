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


def _expanded(count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    bronze_rows = []
    evidence_rows = []
    base_bronze = _bronze_rows().iloc[0].to_dict()
    base_evidence = _evidence(_bronze_rows()).iloc[0].to_dict()
    for index in range(count):
        bronze_rows.append({
            **base_bronze,
            "rental_post_id": index + 1,
            "source_listing_id": f"listing-{index + 1}",
            "url": f"https://example.test/{index + 1}",
        })
        evidence_rows.append({
            **base_evidence,
            "rental_post_id": index + 1,
            "evidence_observation_id": 100 + index,
            "evidence_price_id": 200 + index,
            "evidence_area_id": 300 + index,
        })
    return pd.DataFrame(bronze_rows), pd.DataFrame(evidence_rows)


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
        "area_semantic_status",
        "area_model_suitability",
        "price_semantic_status",
        "price_model_suitability",
        "coordinate_quality_status",
        "duplicate_candidate_status",
        "temporal_quality_status",
        "row_quality_status",
    } <= set(silver.columns)
    assert silver.loc[0, "title_clean"] == "Phòng trọ Quận 1"
    assert silver.loc[1, "coordinate_quality_status"] == "INVALID"
    assert silver.loc[1, "temporal_quality_status"] == "REQUIRES_REVIEW"


def test_build_compacts_repeated_derived_strings_without_changing_raw_dtypes():
    bronze, evidence = _expanded(100)

    silver = build_silver_dataset(bronze, evidence)

    assert silver["title_raw"].dtype == bronze["title_raw"].dtype
    assert isinstance(silver["row_quality_status"].dtype, pd.CategoricalDtype)
    assert silver["row_quality_status"].astype("string").tolist() == [
        "READY_WITH_FLAGS"
    ] * 100


def test_height_contamination_is_retained_but_not_area_model_supported():
    bronze = _bronze_rows().iloc[[0]].reset_index(drop=True)
    evidence = _evidence(_bronze_rows()).iloc[[0]].reset_index(drop=True)
    bronze.loc[0, "title_raw"] = "Cho thuê phòng gác cao 2m giá 3.5 triệu/tháng"
    bronze.loc[0, "area_value"] = Decimal("2")
    evidence.loc[0, "area_raw"] = "2"

    silver = build_silver_dataset(bronze, evidence)

    assert silver.loc[0, "area_value"] == Decimal("2")
    assert silver.loc[0, "area_value_clean"] == 2
    assert silver.loc[0, "area_semantic_status"] == "LINEAR_MEASUREMENT_CONTRADICTION"
    assert silver.loc[0, "area_model_suitability"] == "REVIEW"


def test_explicit_small_and_large_area_are_not_rejected_by_magnitude_alone():
    bronze, evidence = _expanded(2)
    bronze.loc[0, "area_value"] = Decimal("3")
    evidence.loc[0, "area_raw"] = "3 m2"
    bronze.loc[0, "title_raw"] = "Cho thuê chỗ ngủ riêng diện tích 3m2"
    bronze.loc[1, "area_value"] = Decimal("1500")
    evidence.loc[1, "area_raw"] = "1500 m2"
    bronze.loc[1, "title_raw"] = "Cho thuê kho diện tích 1500m2 theo tháng"

    silver = build_silver_dataset(bronze, evidence)

    assert silver.area_model_suitability.tolist() == ["SUPPORTED", "SUPPORTED"]


def test_currency_shaped_reparsed_area_is_reviewed_without_deleting_row():
    bronze = _bronze_rows().iloc[[0]].reset_index(drop=True)
    evidence = _evidence(_bronze_rows()).iloc[[0]].reset_index(drop=True)
    bronze.loc[0, "area_value"] = None
    evidence.loc[0, "area_raw"] = "6500000 m 2"
    bronze.loc[0, "title_raw"] = "Cho thuê studio full nội thất"

    silver = build_silver_dataset(bronze, evidence)

    assert len(silver) == 1
    assert silver.loc[0, "area_value_clean"] == 6_500_000
    assert silver.loc[0, "area_semantic_status"] == "CURRENCY_SHAPED_AREA_EVIDENCE"
    assert silver.loc[0, "area_model_suitability"] == "REVIEW"


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


@pytest.mark.parametrize(
    ("existing", "raw_price", "expected"),
    [
        (Decimal("3500000.00"), "3.5 triệu/tháng", "MATCH"),
        (Decimal("3500000.00"), "4 triệu/tháng", "DISAGREEMENT"),
        (None, "4 triệu/tháng", "REPARSED_ONLY"),
        (Decimal("3500000.00"), None, "EXISTING_ONLY"),
        (None, None, "NO_PRICE_EVIDENCE"),
        (None, "thỏa thuận", "UNCOMPARABLE"),
    ],
)
def test_price_parser_comparison_status_is_explicit(existing, raw_price, expected):
    bronze = _bronze_rows()
    evidence = _evidence(bronze)
    bronze.loc[0, "price_amount"] = existing
    evidence.loc[0, "price_raw"] = raw_price

    silver = build_silver_dataset(bronze, evidence)

    assert silver.loc[0, "price_parser_comparison_status"] == expected


def test_price_disagreement_preserves_existing_clean_value_and_review_evidence():
    bronze = _bronze_rows()
    evidence = _evidence(bronze)
    evidence.loc[0, "price_raw"] = "4 triệu/tháng"

    silver = build_silver_dataset(bronze, evidence)

    assert silver.loc[0, "price_amount_clean"] == 3_500_000
    assert silver.loc[0, "price_quality_status"] == "VALIDATED_EXISTING"
    assert silver.loc[0, "price_parser_comparison_status"] == "DISAGREEMENT"


def test_price_area_availability_distinguishes_all_missing_combinations():
    bronze, evidence = _expanded(4)
    bronze.loc[1, "price_amount"] = None
    evidence.loc[1, "price_raw"] = None
    bronze.loc[2, "area_value"] = None
    evidence.loc[2, "area_raw"] = None
    bronze.loc[3, ["price_amount", "area_value"]] = None
    evidence.loc[3, ["price_raw", "area_raw"]] = None

    silver = build_silver_dataset(bronze, evidence)

    assert silver.price_area_availability_status.tolist() == [
        "AVAILABLE", "MISSING_PRICE", "MISSING_AREA", "MISSING_BOTH"
    ]
    assert silver.loc[0, "price_area_quality_status"] == "CHECKED_NO_FLAG"
    assert silver.loc[1:, "price_area_quality_status"].eq("INSUFFICIENT_DATA").all()


def test_price_area_quality_preserves_price_area_and_ratio_review_flags():
    bronze, evidence = _expanded(8)
    prices = [3_000_000, 4_000_000, 5_000_000, 6_000_000, 7_000_000, 8_000_000, 30_000_000, 3_000_000]
    areas = [30, 35, 40, 45, 50, 55, 60, 300]
    for index, (price, area) in enumerate(zip(prices, areas)):
        bronze.loc[index, "price_amount"] = Decimal(str(price))
        bronze.loc[index, "area_value"] = Decimal(str(area))
        evidence.loc[index, "price_raw"] = f"{price} VND"
        evidence.loc[index, "area_raw"] = f"{area} m2"

    silver = build_silver_dataset(bronze, evidence)

    assert silver.loc[6, "price_area_quality_status"] == "PRICE_OUTLIER_REVIEW"
    assert silver.loc[7, "price_area_quality_status"] == "AREA_OUTLIER_REVIEW"


def test_duplicate_rules_find_same_and_cross_source_candidates_without_merging_rows():
    bronze, evidence = _expanded(5)
    bronze.loc[1, "source_listing_id"] = "same-source-copy"
    bronze.loc[2, "source_code"] = "nhatrovn"
    bronze.loc[2, "source_listing_id"] = "cross-source-address"
    bronze.loc[2, "title_raw"] = "Different title"
    bronze.loc[3, "source_code"] = "nhatrovn"
    bronze.loc[3, "source_listing_id"] = "cross-source-title"
    bronze.loc[3, "best_address_text"] = "123 Other Street, Phường Bến Nghé, Quận 1"
    bronze.loc[3, "full_address_text"] = "123 Other Street, Phường Bến Nghé, Quận 1"
    bronze.loc[4, "source_code"] = "nhatrovn"
    bronze.loc[4, ["best_address_text", "full_address_text"]] = None

    silver = build_silver_dataset(bronze, evidence)

    assert len(silver) == len(bronze) == silver.rental_post_id.nunique()
    assert silver.loc[0, "duplicate_match_reason"] == "EXACT_FINGERPRINT"
    assert silver.loc[1, "duplicate_scope"] == "CROSS_SOURCE"
    assert silver.loc[2, "duplicate_match_reason"] == "SAME_ADDRESS_PRICE_AREA"
    assert silver.loc[2, "duplicate_scope"] == "CROSS_SOURCE"
    assert silver.loc[3, "duplicate_match_reason"] == "SAME_TITLE_PRICE_WARD"
    assert silver.loc[3, "duplicate_scope"] == "CROSS_SOURCE"
    assert silver.loc[4, "duplicate_scope"] == "NOT_APPLICABLE"


def test_exact_same_source_candidates_have_deterministic_group_and_scope():
    bronze, evidence = _expanded(2)

    first = build_silver_dataset(bronze, evidence)
    second = build_silver_dataset(bronze, evidence)

    assert first.duplicate_scope.eq("SAME_SOURCE").all()
    assert first.duplicate_match_reason.eq("EXACT_FINGERPRINT").all()
    assert first.duplicate_candidate_group.tolist() == second.duplicate_candidate_group.tolist()


def test_shared_coordinate_alone_does_not_create_duplicate_candidate():
    bronze, evidence = _expanded(2)
    bronze.loc[1, "title_raw"] = "Unrelated listing"
    bronze.loc[1, ["best_address_text", "full_address_text"]] = "Unrelated address"
    bronze.loc[1, "price_amount"] = Decimal("9000000")
    bronze.loc[1, "area_value"] = Decimal("90")
    evidence.loc[1, "price_raw"] = "9000000 VND"
    evidence.loc[1, "area_raw"] = "90 m2"

    silver = build_silver_dataset(bronze, evidence)

    assert silver.duplicate_candidate_status.ne("POSSIBLE_DUPLICATE").all()
