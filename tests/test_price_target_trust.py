from decimal import Decimal

import pandas as pd
import pytest

from notebooks.utils.price_area_validation import parse_rental_price_evidence
from notebooks.utils.silver_processing import build_silver_dataset, evaluate_pre_silver_quality_gate


def test_vietnamese_rental_shorthand_parser():
    cases = {
        "giá 3800k quận Bình Thạnh": Decimal("3800000"),
        "phòng 16m2 giá 2.400k": Decimal("2400000"),
        "nhà trọ giá 3tr7": Decimal("3700000"),
        "phòng đẹp 3tr75": Decimal("3750000"),
        "phòng full đồ 3tr750": Decimal("3750000"),
        "giá 3 triệu 800 nghìn": Decimal("3800000"),
        "4 triệu 250 nghìn": Decimal("4250000"),
        "10 triệu 500 nghìn": Decimal("10500000"),
        "căn hộ 1 tỷ": Decimal("1000000000"),
        "biệt thự 1.5 tỷ": Decimal("1500000000"),
        "mặt bằng 38 tỷ": Decimal("38000000000"),
    }
    for text, expected in cases.items():
        parsed, _ = parse_rental_price_evidence(text)
        assert parsed == expected, f"Failed for text: {text}, got: {parsed}, expected: {expected}"


def _bronze_and_evidence(title, numeric, raw, lineage_aligned=True, parser_match=True, area=30.0):
    bronze = pd.DataFrame([{
        "source_code": "test", "rental_post_id": 1, "source_listing_id": "x",
        "title_raw": title, "url": "https://example.test/1", "price_amount": numeric,
        "area_value": area, "full_address_text": "Phường 1, Quận 1",
        "location_raw": "Quận 1", "full_address_inherited": False,
        "map_provider": None, "map_latitude": None, "map_longitude": None,
        "map_query_raw": None, "best_address_text": "Phường 1, Quận 1",
        "best_address_source": "listing", "latest_observed_at": pd.Timestamp("2026-01-02"),
        "first_observed_at": pd.Timestamp("2026-01-01"), "last_observed_at": pd.Timestamp("2026-01-02"),
        "active_days": 1,
    }])
    evidence = pd.DataFrame([{
        "rental_post_id": 1, "evidence_observation_id": 1,
        "evidence_version_time_matches": 1, "evidence_price_id": 1,
        "price_raw": raw, "currency": "VND", "period": "MONTH",
        "evidence_area_id": 1, "area_raw": f"{area} m2",
        "price_lineage_aligned": lineage_aligned, "area_lineage_aligned": True,
    }])
    return bronze, evidence


def _price_population(extreme_title: str, extreme_price: int, extreme_raw: str, extreme_area: float = 30.0):
    bronze_rows, evidence_rows = [], []
    for index, price in enumerate([3_000_000, 4_000_000, 5_000_000, 6_000_000, 7_000_000, 8_000_000, 9_000_000, extreme_price]):
        title = extreme_title if index == 7 else f"Cho thuê căn hộ giá {price // 1_000_000} triệu/tháng"
        raw = extreme_raw if index == 7 else f"{price // 1_000_000} triệu/tháng"
        area = extreme_area if index == 7 else 30.0
        bronze, evidence = _bronze_and_evidence(title, price, raw, area=area)
        bronze.loc[0, "rental_post_id"] = index + 1
        bronze.loc[0, "source_listing_id"] = f"x-{index + 1}"
        evidence.loc[0, "rental_post_id"] = index + 1
        bronze_rows.append(bronze)
        evidence_rows.append(evidence)
    return pd.concat(bronze_rows, ignore_index=True), pd.concat(evidence_rows, ignore_index=True)


def test_explicit_title_evidence_repairs_scale_without_deleting_row():
    bronze, evidence = _bronze_and_evidence("phòng trọ cho thuê giá 3800k", 38_000_000_000, "38 tỷ/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert len(silver) == len(bronze) == 1
    assert silver.loc[0, "price_amount_clean"] == 38_000_000_000
    assert silver.loc[0, "price_model_value"] == 3_800_000
    assert silver.loc[0, "price_target_model_value"] == 3_800_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_REPARSED"
    assert silver.loc[0, "price_target_trust_reason"] == "EXPLICIT_TEXT_PRICE_OVERRIDE_SCALE_ERROR"
    assert evaluate_pre_silver_quality_gate(bronze, silver).passed


def test_2400k_repairs_scale_to_millions():
    bronze, evidence = _bronze_and_evidence("Phòng 16m2 giá 2.400k", 2_400_000_000, "2.4 tỷ/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_amount_clean"] == 2_400_000_000
    assert silver.loc[0, "price_model_value"] == 2_400_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_REPARSED"


def test_3tr7_repairs_scale_to_millions():
    bronze, evidence = _bronze_and_evidence("Phòng trọ giá 3tr7", 3_700_000_000, "3.7 tỷ/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_amount_clean"] == 3_700_000_000
    assert silver.loc[0, "price_model_value"] == 3_700_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_REPARSED"


def test_true_billion_not_blindly_converted_to_million():
    bronze, evidence = _bronze_and_evidence("Biệt thự cao cấp 38 tỷ", 38_000_000_000, "38 tỷ/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_amount_clean"] == 38_000_000_000
    assert silver.loc[0, "price_model_value"] == 38_000_000_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_EXISTING"


def test_high_rental_is_not_rejected_by_magnitude_alone():
    bronze, evidence = _bronze_and_evidence("Cho thuê biệt thự", 100_000_000, "100 triệu/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_model_value"] == 100_000_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_EXISTING"


def test_lineage_trusted_extreme_room_price_can_be_reviewed_for_modeling():
    bronze, evidence = _price_population(
        "Cho thuê phòng trọ giá rẻ gần trường đại học",
        100_000_000,
        "100 triệu/tháng",
    )

    silver = build_silver_dataset(bronze, evidence)
    row = silver.iloc[-1]

    assert len(silver) == len(bronze)
    assert row.price_target_trust_status == "TRUSTED_EXISTING"
    assert row.price_model_value == 100_000_000
    assert row.price_semantic_status in {"ORDINARY_UNIT_OUTLIER_UNCORROBORATED", "CROSS_FIELD_CONTRADICTION"}
    assert row.price_model_suitability == "REVIEW"


def test_student_cbcnv_extreme_billion_rent_reviewed_not_model_suitable():
    bronze, evidence = _price_population(
        "Cho CBCNV & SV thuê , được nấu ăn , giờ giấc tự do",
        2_200_000_000,
        "2.2 tỷ/tháng",
        extreme_area=24.0,
    )
    silver = build_silver_dataset(bronze, evidence)
    row = silver.iloc[-1]
    assert row.price_target_trust_status == "TRUSTED_EXISTING"
    assert row.price_model_value == 2_200_000_000
    assert row.price_semantic_status == "CROSS_FIELD_CONTRADICTION"
    assert row.price_model_suitability == "REVIEW"


def test_ordinary_unit_compact_area_extreme_100m_rent_reviewed():
    bronze, evidence = _price_population(
        "Nhà trọ sạch đẹp rộng rãi giá rẻ [quận8]",
        100_000_000,
        "100 triệu/tháng",
        extreme_area=20.0,
    )
    silver = build_silver_dataset(bronze, evidence)
    row = silver.iloc[-1]
    assert row.price_target_trust_status == "TRUSTED_EXISTING"
    assert row.price_model_value == 100_000_000
    assert row.price_semantic_status == "CROSS_FIELD_CONTRADICTION"
    assert row.price_model_suitability == "REVIEW"


def test_legitimate_large_commercial_170m_rent_remains_supported():
    bronze, evidence = _price_population(
        "Mô tả chi tiết",
        170_000_000,
        "170tr",
        extreme_area=189.0,
    )
    silver = build_silver_dataset(bronze, evidence)
    row = silver.iloc[-1]
    assert row.price_target_trust_status == "TRUSTED_EXISTING"
    assert row.price_model_value == 170_000_000
    assert row.price_semantic_status == "SUPPORTED_MONTHLY_RENT"
    assert row.price_model_suitability == "SUPPORTED"


def test_explicit_supported_high_monthly_rent_remains_model_usable():
    bronze, evidence = _price_population(
        "Cho thuê biệt thự nguyên căn giá 120 triệu/tháng",
        120_000_000,
        "120 triệu/tháng",
    )

    silver = build_silver_dataset(bronze, evidence)
    row = silver.iloc[-1]

    assert row.price_target_trust_status == "TRUSTED_EXISTING"
    assert row.price_semantic_status == "SUPPORTED_MONTHLY_RENT"
    assert row.price_model_suitability == "SUPPORTED"


def test_conflicting_text_prices_become_suspect_unit_scale():
    bronze, evidence = _bronze_and_evidence("Phòng giá 3800k hoặc 38 tỷ", 38_000_000, "38 triệu/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_target_trust_status"] == "SUSPECT_UNIT_SCALE"
    assert pd.isna(silver.loc[0, "price_model_value"])


def test_missing_price_evidence_becomes_missing():
    bronze, evidence = _bronze_and_evidence("Phòng đẹp gần trung tâm", None, None)
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_target_trust_status"] == "MISSING"
    assert pd.isna(silver.loc[0, "price_model_value"])


def test_parser_disagreement_becomes_review():
    bronze, evidence = _bronze_and_evidence("Phòng đẹp", 3_000_000, "5 triệu/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_target_trust_status"] == "PARSER_DISAGREEMENT_REVIEW"
    assert pd.isna(silver.loc[0, "price_model_value"])


def test_1trillion_shorthand_typo_repairs_to_1million():
    bronze, evidence = _bronze_and_evidence("Cần tìm nữ ở ghép giá 1000000tr/tháng", 1_000_000, "1 triệu/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_model_value"] == 1_000_000
    assert silver.loc[0, "price_model_value"] < 1_000_000_000_000


def test_2800000_trieu_repairs_to_2800000():
    bronze, evidence = _bronze_and_evidence("PHÒNG TRỌ MỚI GIÁ CHỈ 2.800.000 TRIỆU", 2_800_000, "2.8 triệu/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_model_value"] == 2_800_000


def test_cadence_m2_becomes_suspect_unit_scale():
    bronze, evidence = _bronze_and_evidence("Cho thuê phòng", 20_000, "20.000 đồng/m2/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_target_trust_status"] == "SUSPECT_UNIT_SCALE"
    assert pd.isna(silver.loc[0, "price_model_value"])


def test_ordinary_unit_billion_anomaly_becomes_suspect_unit_scale():
    bronze, evidence = _bronze_and_evidence("CHO THUÊ CĂN HỘ 2PN1WC VINHOMES QUẬN 9", 8_500_000_000, "8.5 tỷ/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_target_trust_status"] == "SUSPECT_UNIT_SCALE"
    assert pd.isna(silver.loc[0, "price_model_value"])


def test_discount_mention_does_not_override_clean_price():
    bronze, evidence = _bronze_and_evidence("ƯU ĐÃI GIẢM 100K/12 THÁNG, PHÒNG MỚI", 2_500_000, "2.5 triệu/tháng")
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_model_value"] == 2_500_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_EXISTING"


def test_42m_is_repaired_from_explicit_monthly_4_2tr_rent():
    bronze, evidence = _bronze_and_evidence(
        "Cho thuê phòng full nội thất giá 4,2tr/tháng", 42_000_000, "42 triệu/tháng"
    )
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_amount_clean"] == 42_000_000
    assert silver.loc[0, "price_model_value"] == 4_200_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_REPARSED"
    assert silver.loc[0, "price_target_trust_reason"] == "EXPLICIT_TEXT_PRICE_OVERRIDE_SCALE_ERROR"


def test_ambiguous_thousand_range_is_not_silently_reduced_to_one_price():
    bronze, evidence = _bronze_and_evidence(
        "Phòng giá từ 3.000 - 3.800đ", 3_000_000, "3 triệu/tháng"
    )
    silver = build_silver_dataset(bronze, evidence)
    assert pd.isna(silver.loc[0, "price_model_value"])
    assert silver.loc[0, "price_target_trust_status"] == "SUSPECT_UNIT_SCALE"
    assert silver.loc[0, "price_target_trust_reason"] == "AMBIGUOUS_RENT_PRICE_RANGE"


@pytest.mark.parametrize("title", [
    "Giảm 100k tháng đầu", "Giãm trực tiếp 300k", "Ưu đãi giảm giá 200k", "Tặng voucher 500k",
    "Cọc 2 triệu", "Điện 4k/kWh", "Nước 100k", "Wifi 150k", "Phí giữ xe 200k",
])
def test_non_rent_money_role_cannot_create_target_without_rent_evidence(title):
    bronze, evidence = _bronze_and_evidence(title, None, None)
    silver = build_silver_dataset(bronze, evidence)
    assert pd.isna(silver.loc[0, "price_model_value"])
    assert silver.loc[0, "price_target_trust_status"] in {"MISSING", "INSUFFICIENT_EVIDENCE"}


@pytest.mark.parametrize("title", [
    "Cho thuê phòng giá 200k/ngày", "Phòng 500k/đêm",
    "Cho thuê nhà 60 triệu/năm", "Mặt bằng giá 300k/m2/tháng",
])
def test_non_monthly_price_cannot_become_monthly_target(title):
    bronze, evidence = _bronze_and_evidence(title, None, None)
    silver = build_silver_dataset(bronze, evidence)
    assert pd.isna(silver.loc[0, "price_model_value"])
    assert silver.loc[0, "price_target_trust_status"] in {"SUSPECT_UNIT_SCALE", "INSUFFICIENT_EVIDENCE", "MISSING"}


def test_true_high_monthly_rent_remains_lineage_trusted():
    bronze, evidence = _bronze_and_evidence(
        "Cho thuê biệt thự nguyên căn", 120_000_000, "120 triệu/tháng"
    )
    silver = build_silver_dataset(bronze, evidence)
    assert silver.loc[0, "price_model_value"] == 120_000_000
    assert silver.loc[0, "price_target_trust_status"] == "TRUSTED_EXISTING"


def test_dot_grouped_low_monthly_amount_requires_review_not_multiplication():
    bronze, evidence = _bronze_and_evidence(
        "Cho thuê phòng giá rẻ", 13_000, "13.000 đồng/tháng"
    )
    silver = build_silver_dataset(bronze, evidence)
    assert pd.isna(silver.loc[0, "price_model_value"])
    assert silver.loc[0, "price_target_trust_status"] == "SUSPECT_UNIT_SCALE"
    assert silver.loc[0, "price_target_trust_reason"] == "AMBIGUOUS_DOT_GROUPED_MONTHLY_AMOUNT"
