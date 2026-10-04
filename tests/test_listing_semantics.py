import pandas as pd
import pytest

from notebooks.utils.listing_semantics import (
    apply_listing_semantics,
    classify_listing_semantics,
    semantic_model_eligibility,
)

@pytest.mark.parametrize("title,intent,scope", [
    ("Cho thuê phòng trọ Quận 3", "RENT", "SINGLE_OR_ORDINARY_UNIT"),
    ("Căn hộ studio cho thuê full nội thất", "RENT", "SINGLE_OR_ORDINARY_UNIT"),
    ("Cho thuê nhà nguyên căn Quận 7", "RENT", "SINGLE_OR_ORDINARY_UNIT"),
    ("BÁN NHÀ mặt tiền Quận 3", "SALE", "UNKNOWN"),
    ("Chính chủ bán gấp 12 phòng trọ", "SALE", "UNKNOWN"),
    ("Sang nhượng hợp đồng kinh doanh phòng trọ", "TRANSFER", "MULTI_UNIT_BUSINESS"),
    ("Cho thuê nguyên tòa nhà 60 phòng trọ mới xây", "RENT", "WHOLE_BUILDING"),
    ("Sang nhượng CHDV 20phòng full nội thất", "TRANSFER", "MULTI_UNIT_BUSINESS"),
    ("Phòng đẹp gần trung tâm", "UNKNOWN", "UNKNOWN"),
    (None, "UNKNOWN", "UNKNOWN"),
    ("BÁN GẤP DÃY TRỌ", "SALE", "UNKNOWN"),
    ("Phòng tại đường Lũy Bán Bích", "UNKNOWN", "UNKNOWN"),
    ("Cho thuê phòng, cần sang nhượng hợp đồng", "TRANSFER", "SINGLE_OR_ORDINARY_UNIT"),
    ("Phòng trọ: (300tr/m2) Góc 2 MT Huỳnh Khương Ninh", "SALE", "UNKNOWN"),
    ("Mặt tiền kinh doanh 100m2 vuông - chỉ 17 tỷ", "SALE", "UNKNOWN"),
    ("Sang 19 căn hộ cần tìm đối tác", "TRANSFER", "MULTI_UNIT_BUSINESS"),
    ("Sang dãy trọ đang kinh doanh", "TRANSFER", "MULTI_UNIT_BUSINESS"),
    ("Cho thuê hoặc bán nhà mặt tiền", "UNKNOWN", "UNKNOWN"),
])
def test_deterministic_vietnamese_semantics(title, intent, scope):
    result = classify_listing_semantics(title)
    assert result["listing_intent"] == intent
    assert result["rental_scope"] == scope
    assert result["listing_intent_reason"]
    assert result["rental_scope_reason"]

def test_semantic_eligibility_keeps_unknown_but_excludes_strong_conflicts():
    frame = apply_listing_semantics(pd.DataFrame({"title_clean": [
        "Phòng đẹp gần trung tâm", "Bán nhà Quận 3",
        "Sang nhượng hợp đồng phòng", "Cho thuê nguyên tòa nhà",
        "Cho thuê căn hộ cao cấp 80 triệu/tháng",
    ]}))
    eligible, reason = semantic_model_eligibility(frame)
    assert eligible.tolist() == [True, False, False, False, True]
    assert reason.iloc[0] == "SEMANTICALLY_COMPATIBLE"
    assert reason.iloc[1].startswith("EXCLUDE_SALE")

def test_classifier_api_has_no_price_input():
    with pytest.raises(TypeError):
        classify_listing_semantics("Cho thuê phòng", price=999_999_999)


@pytest.mark.parametrize("title", [
    "BAN CÔNG 30m2 FULL NỘI THẤT", "Phòng có ban công rộng", "Ban Công Lớn",
    "Phòng trọ có ban công", "Ban công thoáng",
])
def test_balcony_is_never_misclassified_as_sale(title):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] != "SALE"
    assert "ban" not in res["listing_intent_evidence"].lower() or "bán" in res["listing_intent_evidence"].lower()


@pytest.mark.parametrize("title,expected_reason,expected_evidence", [
    ("Bán nhà mặt tiền", "TITLE_EXPLICIT_PROPERTY_SALE", "bán nhà"),
    ("Cần bán gấp nhà", "TITLE_EXPLICIT_URGENT_SALE", "cần bán"),
    ("Bán tòa nhà", "TITLE_EXPLICIT_PROPERTY_SALE", "bán tòa nhà"),
    ("Phòng trọ: bán nhà giá tốt", "TITLE_EXPLICIT_SALE", "bán nhà"),
])
def test_accented_sale_lexicon_is_preserved(title, expected_reason, expected_evidence):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] == "SALE"
    assert res["listing_intent_reason"] in {expected_reason, "TITLE_EXPLICIT_PROPERTY_SALE", "TITLE_EXPLICIT_SALE"}
    assert expected_evidence.lower() in res["listing_intent_evidence"].lower()


@pytest.mark.parametrize("title,expected_intent,expected_scope,expected_reason,expected_evidence", [
    ("Sang nhượng hợp đồng", "TRANSFER", "SINGLE_OR_ORDINARY_UNIT", "TITLE_EXPLICIT_CONTRACT_TRANSFER", "sang nhượng"),
    ("Cần sang lại phòng", "TRANSFER", "SINGLE_OR_ORDINARY_UNIT", "TITLE_EXPLICIT_TRANSFER", "cần sang"),
    ("Chuyển nhượng căn hộ", "TRANSFER", "SINGLE_OR_ORDINARY_UNIT", "TITLE_EXPLICIT_CONTRACT_TRANSFER", "chuyển nhượng"),
    ("Sang dãy trọ đang kinh doanh", "TRANSFER", "MULTI_UNIT_BUSINESS", "TITLE_MULTI_UNIT_TRANSFER", "sang dãy trọ"),
])
def test_transfer_semantics_regression(title, expected_intent, expected_scope, expected_reason, expected_evidence):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] == expected_intent
    assert res["rental_scope"] == expected_scope
    assert res["listing_intent_reason"] == expected_reason
    assert expected_evidence.lower() in res["listing_intent_evidence"].lower()


@pytest.mark.parametrize("title", [
    "Cần tìm bạn phòng trọ ở ghép, đầy đủ tiện nghi, chỉ từ 1tr Q. Thủ Đức",
    "Căn hộ gần Đại học TDTU UFM ở được 2 - 3 bạn toà nhà mới tiện sang Q1 Q4",
    "Phòng có gác nội thất cơ bản tòa nhà mới 100% - ngay Lã Xuân Oai quận 9 giá tốt",
])
def test_friend_and_basic_words_are_never_misclassified_as_sale(title):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] != "SALE"


@pytest.mark.parametrize("title", [
    "Phòng trọ: Nhà Bình Thạnh - hẻm xe hơi - 45m2 - có PN dưới trệt - chỉ 6 tỷ 3 TL",
    "Phòng trọ: Trần Huy Liệu - 130m2 - Ngang 5m - HXH- Chỉ hơn 10 tỷ",
    "Phòng trọ: THÀNH THÁI Q10 - Hẻm kinh doanh 10m - 72m2 - Giảm mạnh còn hơn 10 tỷ",
    "Phòng trọ: HXH Ung Văn Khiêm - Khu D VIP - Hẻm thông D5 - Tiện xây mới - 11.3 tỷ",
    "Phòng trọ: Nhà đẹp - Nguyễn Văn Đậu - Phường 6 Bình Thạnh - 45m2 - HXH - chỉ 6tỷ",
    "Phòng trọ: Chỉ 1 căn dưới 3 tỷ Quận 11 có nội thất kế bên đường bình thới Quận 1",
])
def test_cafeland_prefixed_house_sales_are_classified_as_sale(title):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] == "SALE"


@pytest.mark.parametrize("title", [
    "Nhượng phòng trọ gò vấp đầy đủ nội thất",
    "Nhượng Phòng Trọ Tiện Nghi Gần Đh Bách Khoa, Ueh, Văn Hiến",
    "Nhượng phòng Bình Thạnh vào cuối tháng 9",
    "SANG PHÒNG SINH VIÊN TIỆN DI CHUYỂN CÁC QUẬN - THOÁNG MÁT",
    "Pass phòng KTX giá rẻ",
    "Cho thuê phòng trọ: Cần nhượng phòng gò vấp full nội thất ở ngay",
])
def test_nhuong_phong_and_sang_phong_classified_as_transfer(title):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] == "TRANSFER"


@pytest.mark.parametrize("title", [
    "Bán hợp đồng nhà làm căn hộ dịch vụ phường 12 quận Tân Bình",
    "Bán hợp đồng nhà đang kinh doanh phòng trọ",
])
def test_ban_hop_dong_is_incompatible_transfer_evidence(title):
    res = classify_listing_semantics(title)
    assert res["listing_intent"] == "TRANSFER"
    assert res["listing_intent_reason"] == "TITLE_CONTRACT_SALE_TRANSFER"


@pytest.mark.parametrize("title", [
    "CHO THUÊ 12 PHÒNG GIÁ 95TR/THÁNG",
    "Cho thuê CHDV 16 phòng full nội thất",
    "Cho thuê khách sạn 21 phòng mặt tiền",
    "Căn hộ dịch vụ 15 phòng đang kinh doanh",
])
def test_proven_multi_room_aggregate_context_is_not_ordinary(title):
    res = classify_listing_semantics(title)
    assert res["rental_scope"] == "MULTI_UNIT_BUSINESS"


@pytest.mark.parametrize("title", [
    "Căn hộ 2 phòng ngủ full nội thất",
    "Cho thuê căn hộ 2PN 2WC",
    "Nhà có 1 phòng khách và 2 phòng ngủ",
])
def test_ordinary_layout_counts_remain_non_aggregate(title):
    res = classify_listing_semantics(title)
    assert res["rental_scope"] != "MULTI_UNIT_BUSINESS"


