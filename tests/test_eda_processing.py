from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


NOTEBOOKS_DIR = Path(__file__).resolve().parents[1] / "notebooks"
if str(NOTEBOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS_DIR))

from utils.eda_processing import (  # noqa: E402
    add_eligibility_masks,
    add_price_per_m2,
    annotate_area_quality,
    annotate_price_quality,
    annotate_property_type_inference,
    classify_sample_reliability,
    correct_composite_vnd_price,
    derive_location_fields,
    safe_one_to_one_enrich,
    summarize_processing_impact,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "rental_post_id": 1,
        "source_code": "phongtro123",
        "title_raw": "Phòng trọ 25 m²",
        "price_raw": "3.5 triệu/tháng",
        "price_amount": 3_500_000.0,
        "area_raw": "25 m2",
        "area_value": 25.0,
        "full_address_text": "Phạm Ngũ Lão, Quận 1, TPHCM",
        "property_type_raw": None,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("raw", "original", "expected_value", "expected_reason"),
    [
        (
            "1 triệu 500 nghìn",
            1_000_000.0,
            1_500_000.0,
            "CORRECTED_COMPOSITE_MILLION_THOUSAND",
        ),
        (
            "2 triệu 300 nghìn",
            2_000_000.0,
            2_300_000.0,
            "CORRECTED_COMPOSITE_MILLION_THOUSAND",
        ),
        ("1 triệu", 1_000_000.0, 1_000_000.0, "UNCHANGED"),
        ("500 nghìn", 500_000.0, 500_000.0, "UNCHANGED"),
        ("3,5 triệu/tháng", 3_500_000.0, 3_500_000.0, "UNCHANGED"),
        ("1 triệu 500", 1_000_000.0, 1_000_000.0, "AMBIGUOUS_UNCHANGED"),
        ("Liên hệ", None, None, "UNCHANGED"),
    ],
)
def test_composite_price_correction_is_limited_to_supported_pattern(
    raw: str,
    original: float | None,
    expected_value: float | None,
    expected_reason: str,
) -> None:
    value, reason = correct_composite_vnd_price(raw, original)
    assert value == expected_value
    assert reason == expected_reason


def test_price_annotation_preserves_original_and_input() -> None:
    source = pd.DataFrame(
        [
            _row(price_raw="1 triệu 500 nghìn", price_amount=1_000_000.0),
            _row(
                rental_post_id=2,
                title_raw="Cho thuê theo ngày",
                price_raw="140.000 đồng/ngày",
                price_amount=140_000.0,
            ),
            _row(rental_post_id=3, price_raw=None, price_amount=np.nan),
            _row(rental_post_id=4, price_raw="0 đồng", price_amount=0.0),
            _row(rental_post_id=5, price_raw="không rõ", price_amount=np.nan),
        ]
    )
    snapshot = source.copy(deep=True)

    result = annotate_price_quality(source)

    pd.testing.assert_frame_equal(source, snapshot)
    assert result["price_original"].tolist()[:2] == [1_000_000.0, 140_000.0]
    assert result.loc[0, "price_analytical"] == 1_500_000.0
    assert result.loc[0, "price_quality_status"] == "CORRECTED_COMPOSITE"
    assert result.loc[0, "price_correction_reason"] == "RAW_COMPOSITE_MILLION_THOUSAND"
    assert result.loc[1, "price_quality_status"] == "PERIOD_INCOMPATIBLE_DAILY"
    assert pd.isna(result.loc[1, "price_analytical"])
    assert result.loc[2, "price_quality_status"] == "MISSING"
    assert result.loc[3, "price_quality_status"] == "INVALID_NON_POSITIVE"
    assert result.loc[4, "price_quality_status"] == "REVIEW_AMBIGUOUS"


def test_area_annotation_confirms_only_explicit_distance_contamination() -> None:
    source = pd.DataFrame(
        [
            _row(
                title_raw="Phòng gần đại học, cách trường chỉ 800m",
                area_raw="800",
                area_value=800.0,
            ),
            _row(
                rental_post_id=2,
                source_code="mogi",
                title_raw="Cho thuê nhà kho",
                area_raw="800 m2",
                area_value=800.0,
            ),
            _row(
                rental_post_id=3,
                title_raw="Cho thuê kho diện tích 800 m²",
                area_raw="800",
                area_value=800.0,
            ),
            _row(rental_post_id=4, area_raw="0 m2", area_value=0.0),
            _row(rental_post_id=5, area_raw=None, area_value=np.nan),
            _row(rental_post_id=6, area_raw="25 m2", area_value=25.0),
            _row(
                rental_post_id=7,
                title_raw="Phòng gác cao 2m, gần trường đại học",
                area_raw="2",
                area_value=2.0,
            ),
        ]
    )
    snapshot = source.copy(deep=True)

    result = annotate_area_quality(source)

    pd.testing.assert_frame_equal(source, snapshot)
    assert result.loc[0, "area_quality_status"] == "CONFIRMED_CONTAMINATION"
    assert result.loc[0, "area_exclusion_reason"] == "DISTANCE_TOKEN_PARSED_AS_AREA"
    assert pd.isna(result.loc[0, "area_analytical"])
    assert result.loc[1, "area_quality_status"] == "SUSPICIOUS_EXTREME"
    assert result.loc[1, "area_analytical"] == 800.0
    assert result.loc[2, "area_quality_status"] != "CONFIRMED_CONTAMINATION"
    assert result.loc[3, "area_quality_status"] == "INVALID_NON_POSITIVE"
    assert result.loc[4, "area_quality_status"] == "MISSING"
    assert result.loc[5, "area_quality_status"] == "VALID"
    assert result.loc[6, "area_quality_status"] == "VALID"


def test_location_derivation_keeps_ambiguous_candidates_in_one_row() -> None:
    source = pd.DataFrame(
        [
            _row(full_address_text="Phạm Ngũ Lão, Quận 1, TPHCM"),
            _row(
                rental_post_id=2,
                full_address_text="Đa Kao, Quận 1, TPHCM",
            ),
            _row(rental_post_id=3, full_address_text="Atlantis"),
        ]
    )

    result = derive_location_fields(source)

    assert len(result) == len(source)
    assert result["rental_post_id"].is_unique
    assert result.loc[0, "province_analytical"] == "TPHCM"
    assert result.loc[0, "district_analytical"] == "Quận 1"
    assert result.loc[0, "ward_analytical"] == "Phường Bến Thành"
    assert result.loc[0, "ward_mapping_status"] == "UNAMBIGUOUS"
    assert result.loc[1, "ward_candidate_count"] == 2
    assert result.loc[1, "ward_mapping_status"] == "AMBIGUOUS"
    assert pd.isna(result.loc[1, "ward_analytical"])
    assert result.loc[2, "ward_mapping_status"] == "UNMAPPED"


def test_location_derivation_does_not_turn_trailing_copy_into_a_district() -> None:
    source = pd.DataFrame(
        [
            _row(
                full_address_text=(
                    "Phường Tân Thuận, Quận 7 Thông tin căn hộ: studio có ban công"
                )
            ),
            _row(
                rental_post_id=2,
                full_address_text="Quận trung tâm, gần trường đại học",
            ),
        ]
    )

    result = derive_location_fields(source)

    assert result.loc[0, "district_analytical"] == "Quận 7"
    assert pd.isna(result.loc[1, "district_analytical"])


@pytest.mark.parametrize(
    ("title", "expected_type", "expected_status"),
    [
        ("Cho thuê phòng trọ sinh viên", "ROOM_INFERRED", "INFERRED"),
        ("Căn hộ studio có ban công", "APARTMENT_INFERRED", "INFERRED"),
        ("Cho thuê nhà nguyên căn", "HOUSE_INFERRED", "INFERRED"),
        ("KTX sleepbox giá rẻ", "DORMITORY_INFERRED", "INFERRED"),
        ("Nhà nguyên căn có phòng trọ", None, "AMBIGUOUS"),
        ("Chỗ ở sạch đẹp", None, "UNCLASSIFIED"),
        (None, None, "UNCLASSIFIED"),
    ],
)
def test_property_type_inference_is_explicit_and_ambiguity_safe(
    title: str | None,
    expected_type: str | None,
    expected_status: str,
) -> None:
    source = pd.DataFrame([_row(title_raw=title, property_type_raw="source-value")])
    result = annotate_property_type_inference(source)
    assert result.loc[0, "property_type_source"] == "source-value"
    assert result.loc[0, "property_type_inferred"] == expected_type
    assert result.loc[0, "property_type_inference_status"] == expected_status
    assert result.loc[0, "property_type_raw"] == "source-value"


def test_safe_enrichment_preserves_cardinality_order_and_identity() -> None:
    left = pd.DataFrame(
        {
            "rental_post_id": [3, 1, 2],
            "value": ["c", "a", "b"],
        }
    )
    right = pd.DataFrame(
        {
            "rental_post_id": [1, 2],
            "raw_value": ["A", "B"],
        }
    )

    result = safe_one_to_one_enrich(left, right)

    assert result["rental_post_id"].tolist() == [3, 1, 2]
    assert len(result) == len(left)
    assert result["rental_post_id"].nunique() == left["rental_post_id"].nunique()


def test_safe_enrichment_rejects_duplicate_right_keys() -> None:
    left = pd.DataFrame({"rental_post_id": [1, 2]})
    right = pd.DataFrame({"rental_post_id": [1, 1], "raw": ["a", "b"]})

    with pytest.raises(ValueError, match="right-side.*rental_post_id"):
        safe_one_to_one_enrich(left, right)


def test_eligibility_and_price_per_m2_are_purpose_specific() -> None:
    source = pd.DataFrame(
        [
            {
                **_row(),
                "price_analytical": 3_000_000.0,
                "price_quality_status": "VALID_ORIGINAL",
                "area_analytical": 30.0,
                "area_quality_status": "VALID",
                "ward_analytical": "Phường Bến Thành",
                "ward_mapping_status": "UNAMBIGUOUS",
            },
            {
                **_row(rental_post_id=2),
                "price_analytical": np.nan,
                "price_quality_status": "PERIOD_INCOMPATIBLE_DAILY",
                "area_analytical": 20.0,
                "area_quality_status": "VALID",
                "ward_analytical": "Phường Bến Thành",
                "ward_mapping_status": "UNAMBIGUOUS",
            },
            {
                **_row(rental_post_id=3),
                "price_analytical": 4_000_000.0,
                "price_quality_status": "VALID_ORIGINAL",
                "area_analytical": np.nan,
                "area_quality_status": "CONFIRMED_CONTAMINATION",
                "ward_analytical": None,
                "ward_mapping_status": "AMBIGUOUS",
            },
        ]
    )

    result = add_price_per_m2(add_eligibility_masks(source))

    assert result.loc[0, "price_per_m2"] == 100_000.0
    assert result.loc[0, "price_per_m2_eligible"]
    assert not result.loc[1, "price_eligible"]
    assert not result.loc[1, "price_per_m2_eligible"]
    assert not result.loc[2, "area_eligible"]
    assert not result.loc[2, "location_eligible"]
    assert result.loc[2, "price_eligible"]
    assert result.loc[2, "price_per_m2_reason"] == "AREA_INELIGIBLE"


def test_processing_impact_and_reliability_use_explicit_cut_points() -> None:
    frame = pd.DataFrame(
        {
            "source_code": ["a", "a", "b"],
            "price_quality_status": [
                "VALID_ORIGINAL",
                "CORRECTED_COMPOSITE",
                "MISSING",
            ],
        }
    )

    impact = summarize_processing_impact(frame, "price_quality_status")

    assert impact["row_count"].sum() == 3
    assert impact["percentage"].sum() == pytest.approx(100.0)
    assert classify_sample_reliability(3, 4, 9, 29) == "INSUFFICIENT_SAMPLE"
    assert classify_sample_reliability(7, 4, 9, 29) == "LOW_SAMPLE"
    assert classify_sample_reliability(20, 4, 9, 29) == "USABLE"
    assert classify_sample_reliability(40, 4, 9, 29) == "HIGH_CONFIDENCE"
