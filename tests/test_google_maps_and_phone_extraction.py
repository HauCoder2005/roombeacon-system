"""Test Google Maps coordinate & address extraction, phone extraction, and persistence."""

from unittest.mock import MagicMock
import pytest

from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import (
    MySQLPostChildrenRepository,
)
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.sources.common_html import (
    SourceDetailParser,
    extract_google_maps_info,
    extract_phone_from_text,
    extract_scoped_phone,
    parse_html,
)


def test_extract_phone_from_various_vietnamese_formats():

    assert extract_phone_from_text("Liên hệ: 0901234567 gặp anh Nam") == "0901234567"
    assert extract_phone_from_text("Call ngay +84 987 654 321") == "+84 987 654 321"
    assert extract_phone_from_text("Hotline: 028.3822.1234") == "028.3822.1234"
    assert extract_phone_from_text("SĐT: 035 123 4567") == "035 123 4567"
    assert extract_phone_from_text("Số không hợp lệ 12345") is None


def test_extract_scoped_phone_from_tel_and_data_attributes():

    html = """
    <div class="contact-box">
        <a href="tel:0912345678" class="btn-call">Gọi ngay</a>
        <button data-phone="0988776655" class="btn-show-phone">Hiện số</button>
    </div>
    """
    root = parse_html(html)
    phone = extract_scoped_phone(root)
    assert phone == "0912345678"

    html_data_attr = """
    <div class="contact-box">
        <span data-mobile="0933445566">Bấm để xem số</span>
    </div>
    """
    root2 = parse_html(html_data_attr)
    phone2 = extract_scoped_phone(root2)
    assert phone2 == "0933445566"


def test_extract_google_maps_from_iframe_with_coords():
    html = """
    <div class="map-wrapper">
        <iframe src="https://maps.google.com/maps?q=10.776889,106.700806&hl=vi&z=14&output=embed"></iframe>
    </div>
    """
    root = parse_html(html)
    cand = extract_google_maps_info(root, html)
    assert cand.latitude == pytest.approx(10.776889)
    assert cand.longitude == pytest.approx(106.700806)


def test_extract_google_maps_from_iframe_with_address():
    html = """
    <div class="map-wrapper">
        <iframe src="https://www.google.com/maps/embed?q=123+Nguyen+Thi+Minh+Khai,+Quan+3,+TP+HCM&output=embed"></iframe>
    </div>
    """
    root = parse_html(html)
    cand = extract_google_maps_info(root, html)
    assert cand.address == "123 Nguyen Thi Minh Khai, Quan 3, TP HCM"


def test_extract_google_maps_from_data_attributes():
    html = """
    <div id="map-container" data-lat="10.823099" data-lng="106.629664" data-address="456 Phan Van Tri, Go Vap">
    </div>
    """
    root = parse_html(html)
    cand = extract_google_maps_info(root, html)
    assert cand.latitude == pytest.approx(10.823099)
    assert cand.longitude == pytest.approx(106.629664)
    assert cand.address == "456 Phan Van Tri, Go Vap"


def test_extract_google_maps_from_json_ld():
    html = """
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "Place",
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 10.762622,
            "longitude": 106.660172
        }
    }
    </script>
    """
    root = parse_html(html)
    cand = extract_google_maps_info(root, html)
    assert cand.latitude == pytest.approx(10.762622)
    assert cand.longitude == pytest.approx(106.660172)


def test_source_detail_parser_with_google_maps_fallback():
    class TestDetailParser(SourceDetailParser):
        TITLE_CLASSES = ("post-title",)
        PRICE_CLASSES = ("post-price",)
        AREA_CLASSES = ("post-area",)
        DESCRIPTION_CLASSES = ("post-desc",)
        MAP_CLASSES = ("map-wrapper",)

    parser = TestDetailParser("test_source")
    html = """
    <html>
        <h1 class="post-title">Cho thuê phòng trọ giá rẻ</h1>
        <span class="post-price">3.5 triệu/tháng</span>
        <span class="post-area">25 m2</span>
        <div class="post-desc">Phòng đẹp, liên hệ 0909123456</div>
        <div class="map-wrapper">
            <iframe src="https://maps.google.com/maps?q=10.776889,106.700806&output=embed"></iframe>
        </div>
    </html>
    """
    detail = parser.parse(html, detail_url="https://example.com/post-123.html")
    assert detail is not None
    assert detail.title_raw == "Cho thuê phòng trọ giá rẻ"
    assert detail.price_raw == "3.5 triệu/tháng"
    assert detail.area_raw == "25 m2"
    assert detail.seller_phone_raw == "0909123456"
    assert detail.latitude == pytest.approx(10.776889)
    assert detail.longitude == pytest.approx(106.700806)


def test_persist_address_with_coordinates():
    connection = MagicMock()
    repo = MySQLPostChildrenRepository(connection=connection)

    obs = BronzeObservation(
        source="phongtro123",
        listing_id="12345",
        run_id="run-001",
        url="https://example.com/12345",
        address_raw="123 Nguyen Trai, Q5",
        latitude=10.758,
        longitude=106.674,
    )

    repo._persist_address(connection, obs, post_id=10, observation_id=100)

    assert connection.execute.called
    call_args = connection.execute.call_args
    sql_text = str(call_args[0][0])
    params = call_args[0][1]

    assert "INSERT INTO post_addresses" in sql_text
    assert "latitude" in sql_text
    assert "longitude" in sql_text
    assert params["lat"] == 10.758
    assert params["lng"] == 106.674
    assert params["addr"] == "123 Nguyen Trai, Q5"

def test_mogi_iframe_lat_lng_extraction():
    from roombeacon_crawler.sources.mogi.parsers.detail_parser import MogiDetailParser
    html = """
    <html>
        <div class="map-content clearfix">
            <iframe title="map" frameborder="0" class="lozad" data-src="https://www.google.com/maps/embed/v1/place?key=AIza&language=vi&q=10.78656292,106.6701507549999" allowfullscreen></iframe>
        </div>
    </html>
    """
    parser = MogiDetailParser("mogi")
    detail = parser.parse(html, detail_url="https://mogi.vn/test")
    assert detail.latitude == pytest.approx(10.78656292)
    assert detail.longitude == pytest.approx(106.6701507549999)

def test_chothuenha_iframe_lat_lng_extraction():
    from roombeacon_crawler.sources.chothuenha.parsers.detail_parser import ChothuenhaDetailParser
    html = """
    <html>
        <div class="dv-bds-bd">
            <iframe width="100%" height="100%" frameborder="0" style="border:0" src="https://www.google.com/maps/embed/v1/place?key=AIza&q=86/52 Đường Tân Chánh Hiệp 36, Phường Trung Mỹ Tây, Quận 12, Hồ Chí Minh&zoom=14" allowfullscreen=""></iframe>
        </div>
    </html>
    """
    parser = ChothuenhaDetailParser("chothuenha")
    detail = parser.parse(html, detail_url="https://chothuenha.com/test")
    assert detail.latitude is None
    assert detail.longitude is None
    assert "Tân Chánh Hiệp 36" in detail.address_raw

def test_cafeland_js_latitude_longitude_extraction():
    from roombeacon_crawler.sources.cafeland.parsers.detail_parser import CafelandDetailParser
    html = """
    <html>
        <script>
            _latitude = 10.822818;
            _longitude = 106.679570;
        </script>
    </html>
    """
    parser = CafelandDetailParser("cafeland")
    detail = parser.parse(html, detail_url="https://nhadat.cafeland.vn/test")
    assert detail.latitude == pytest.approx(10.822818)
    assert detail.longitude == pytest.approx(106.679570)

def test_footer_office_map_not_selected_if_fixture_exists():
    from roombeacon_crawler.sources.mogi.parsers.detail_parser import MogiDetailParser
    html = """
    <html>
        <div class="map-content clearfix">
            <iframe title="map" data-src="https://www.google.com/maps/embed/v1/place?q=10.7865,106.6701"></iframe>
        </div>
        <div class="footer">
            <iframe src="https://www.google.com/maps/embed/v1/place?q=10.1111,106.1111"></iframe>
        </div>
    </html>
    """
    parser = MogiDetailParser("mogi")
    detail = parser.parse(html, detail_url="https://mogi.vn/test")
    assert detail.latitude == pytest.approx(10.7865)
    assert detail.longitude == pytest.approx(106.6701)

def test_organization_geo_not_used_instead_of_listing_geo():
    from roombeacon_crawler.sources.cafeland.parsers.detail_parser import CafelandDetailParser
    html = """
    <html>
        <script>
            _latitude = 10.822818;
            _longitude = 106.679570;
        </script>
        <script type="application/ld+json">
        {
            "@type": "Organization",
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": 10.1111,
                "longitude": 106.1111
            }
        }
        </script>
    </html>
    """
    parser = CafelandDetailParser("cafeland")
    detail = parser.parse(html, detail_url="https://nhadat.cafeland.vn/test")
    assert detail.latitude == pytest.approx(10.822818)
    assert detail.longitude == pytest.approx(106.679570)

