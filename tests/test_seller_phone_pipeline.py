"""Verify seller-phone extraction and propagation into Bronze artifacts."""

from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.common_html import (
    SourceDetailParser,
    extract_phone_from_text,
)
from roombeacon_crawler.sources.chothuephongtro.parsers.detail_parser import (
    ChothuephongtroDetailParser,
)
from roombeacon_crawler.sources.tromoi.parsers.detail_parser import TromoiDetailParser


class _PhoneDetailParser(SourceDetailParser):
    DESCRIPTION_CLASSES = ("listing-description",)
    CONTACT_CLASSES = ("contact-info",)
    PHONE_ANCHOR_MARKERS = ("seller-call",)


def _card() -> ListingCardRaw:
    return ListingCardRaw(
        source="test-source",
        listing_id="listing-1",
        detail_url="https://example.test/listing-1",
        title_raw="Phòng cho thuê",
        price_raw=None,
        area_raw=None,
        location_raw=None,
        latitude=None,
        longitude=None,
        posted_at_raw=None,
    )


def test_scoped_contact_anchor_wins_over_footer_hotline():
    detail = _PhoneDetailParser("test-source").parse(
        """
        <header><a href="tel:19001234">Hotline hỗ trợ</a></header>
        <div class="contact-info">
            <div class="listing-description">Liên hệ chủ nhà để xem phòng.</div>
            <a class="seller-call" href="tel:0901234567">Gọi chủ nhà</a>
        </div>
        """,
        detail_url="https://example.test/listing-1",
    )

    assert detail is not None
    assert detail.seller_phone_raw == "0901234567"


def test_listing_description_is_safe_phone_fallback():
    detail = _PhoneDetailParser("test-source").parse(
        '<div class="listing-description">Liên hệ/Zalo: 0962 861 999.</div>',
        detail_url="https://example.test/listing-1",
    )

    assert detail is not None
    assert detail.seller_phone_raw == "0962 861 999"


def test_normalize_vietnamese_phone():
    from roombeacon_crawler.sources.common_html import normalize_vietnamese_phone
    assert normalize_vietnamese_phone("+84 901 234 567") == "0901234567"
    assert normalize_vietnamese_phone("84901234567") == "0901234567"
    assert normalize_vietnamese_phone("090-123.45 67") == "0901234567"
    assert normalize_vietnamese_phone("090(123)4567") == "0901234567"
    assert normalize_vietnamese_phone("invalid") is None


def test_normalize_vietnamese_phone():
    from roombeacon_crawler.sources.common_html import normalize_vietnamese_phone
    assert normalize_vietnamese_phone("+84 901 234 567") == "0901234567"
    assert normalize_vietnamese_phone("84901234567") == "0901234567"
    assert normalize_vietnamese_phone("090-123.45 67") == "0901234567"
    assert normalize_vietnamese_phone("090(123)4567") == "0901234567"
    assert normalize_vietnamese_phone("invalid") is None


def test_masked_phone_is_not_persisted():
    assert extract_phone_from_text("Liên hệ 0909 5** ***") is None


def test_blacklist_removes_hotline():
    from roombeacon_crawler.sources.common_html import extract_scoped_phone, parse_html
    root = parse_html('<div><a href="tel:19001234">Hotline</a></div>')
    assert extract_scoped_phone(root) is None
    
    root2 = parse_html('<div><a href="tel:0901234567">Seller</a></div>')
    assert extract_scoped_phone(root2) == "0901234567"


def test_blacklist_removes_hotline():
    from roombeacon_crawler.sources.common_html import extract_scoped_phone, parse_html
    root = parse_html('<div><a href="tel:19001234">Hotline</a></div>')
    assert extract_scoped_phone(root) is None
    
    root2 = parse_html('<div><a href="tel:0901234567">Seller</a></div>')
    assert extract_scoped_phone(root2) == "0901234567"


def test_bronze_mapper_preserves_seller_phone():
    detail = _PhoneDetailParser("test-source").parse(
        '<div class="contact-info"><a class="seller-call" href="tel:0901234567">Gọi ngay</a></div>',
        detail_url="https://example.test/listing-1",
    )

    bronze = BronzeMapper.map(_card(), detail, run_id="run-phone")

    assert bronze.seller_phone_raw == "0901234567"


def test_chothuephongtro_uses_listing_location_not_footer_office():
    detail = ChothuephongtroDetailParser("chothuephongtro").parse(
        """
        <section class="section">
          <div class="section-header">Vị trí phòng trọ</div>
          <div class="section-content">
            281/22 Đường Lý Thường Kiệt, Phường 15, Quận 11, Hồ Chí Minh
          </div>
        </section>
        <footer><p>Địa chỉ: Căn 02.34, The Sun Avenue, Thành phố Thủ Đức</p></footer>
        """,
        detail_url="https://chothuephongtro.me/ho-chi-minh/quan-11/126884.html",
    )

    assert detail is not None
    assert detail.address_raw == (
        "281/22 Đường Lý Thường Kiệt, Phường 15, Quận 11, Hồ Chí Minh"
    )


def test_tromoi_reads_public_full_phone_instead_of_masked_label():
    detail = TromoiDetailParser("tromoi").parse(
        """
        <a id="btn-call-host" href="tel:0909 1** ***">0909 1** ***</a>
        <script>const fullPhone = "0909123456";</script>
        """,
        detail_url="https://tromoi.com/phong-tro/example?id=1",
    )

    assert detail is not None
    assert detail.seller_phone_raw == "0909123456"
