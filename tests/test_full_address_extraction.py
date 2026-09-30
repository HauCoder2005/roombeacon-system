"""Regression coverage for source-specific full-address extraction and merge."""

from pathlib import Path
import unittest

from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.sources.nhatot.parsers.detail_parser import NhatotDetailParser
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter
from roombeacon_crawler.sources.nhatrovn.parsers.detail_parser import NhatroVNDetailParser
from roombeacon_crawler.sources.phongtro123.adapter import Phongtro123SourceAdapter
from roombeacon_crawler.sources.phongtro123.parsers.detail_parser import Phongtro123DetailParser
from roombeacon_crawler.sources.batdongsan.adapter import BatDongSanSourceAdapter
from roombeacon_crawler.sources.muaban.adapter import MuabanSourceAdapter
from roombeacon_crawler.sources.tromoi.parsers.detail_parser import TromoiDetailParser


FIXTURES = Path(__file__).parent / "fixtures"


def _card(source: str, location: str = "Quận 12, Hồ Chí Minh") -> ListingCardRaw:
    return ListingCardRaw(
        source=source,
        listing_id="listing-1",
        detail_url="https://example.test/detail/listing-1",
        title_raw="Test",
        price_raw=None,
        area_raw=None,
        location_raw=location,
        posted_at_raw=None,
        page_number=1,
        card_position=1,
    )


class FullAddressExtractionTests(unittest.TestCase):
    def test_tromoi_extracts_box_address(self) -> None:
        detail = TromoiDetailParser("tromoi").parse(
            '<main><div class="box-address"><i></i>239, Cao Đạt, Phường Chợ Quán, Quận 5, Hồ Chí Minh</div></main>',
            detail_url="https://tromoi.com/phong-tro/ky-tuc-xa-239-cao-dat",
            listing_id="tromoi-contract-id",
        )

        self.assertIsNotNone(detail)
        self.assertEqual(detail.listing_id, "tromoi-contract-id")
        self.assertEqual(
            detail.address_raw,
            "239, Cao Đạt, Phường Chợ Quán, Quận 5, Hồ Chí Minh",
        )

    def test_address_sources_enable_detail_crawl_for_scheduled_targets(self) -> None:
        """Normal Airflow scheduling must execute the detail parsers."""
        for adapter_type in (
            Phongtro123SourceAdapter,
            NhatroVNSourceAdapter,
            NhatotSourceAdapter,
        ):
            with self.subTest(source=adapter_type.SOURCE_NAME):
                targets = adapter_type().scheduled_targets()
                self.assertTrue(targets)
                self.assertTrue(all(target.crawl_details for target in targets))

    def test_detail_throughput_budget_is_source_specific(self) -> None:
        expected = {
            Phongtro123SourceAdapter: 40,
            NhatroVNSourceAdapter: 40,
            NhatotSourceAdapter: 20,
            BatDongSanSourceAdapter: 20,
            MuabanSourceAdapter: 20,
        }
        for adapter_type, budget in expected.items():
            with self.subTest(source=adapter_type.SOURCE_NAME):
                targets = adapter_type().scheduled_targets()
                self.assertTrue(targets)
                self.assertTrue(
                    all(target.max_details_per_run == budget for target in targets)
                )

    def test_phongtro123_extracts_semantic_address_row(self) -> None:
        html = (FIXTURES / "phongtro123" / "detail_full_address.html").read_text()
        detail = Phongtro123DetailParser().parse(
            html,
            detail_url="https://phongtro123.com/example-pr688724.html",
        )
        expected = "814/5 Đường Sư Vạn Hạnh, Phường Hòa Hưng, Hồ Chí Minh"
        self.assertIsNotNone(detail)
        self.assertEqual(detail.address_raw, expected)
        self.assertEqual(detail.location_raw, expected)

    def test_phongtro123_missing_address_does_not_take_recommendation(self) -> None:
        html = '<main><h1>Test</h1></main><aside class="recommended"><div class="address">999 Đường Sai</div></aside>'
        detail = Phongtro123DetailParser().parse(html, detail_url="https://phongtro123.com/x-pr1.html")
        self.assertIsNotNone(detail)
        self.assertIsNone(detail.address_raw)

    def test_nhatrovn_extracts_residence_address_and_ignores_other_regions(self) -> None:
        html = (FIXTURES / "nhatrovn" / "detail_full_address.html").read_text()
        detail = NhatroVNDetailParser().parse(
            html,
            detail_url="https://nhatrovn.vn/chi-tiet/listing-1/",
            listing_id="listing-1",
        )
        expected = "83 Nguyễn Văn Quá, Phường Đông Hưng Thuận, Quận 12, Thành phố Hồ Chí Minh"
        self.assertEqual(detail.address_raw, expected)
        self.assertEqual(detail.location_raw, expected)
        self.assertNotIn("999 Đường Sai", detail.address_raw)

    def test_nhatrovn_scoped_dom_fallback_preserves_district_only_raw_value(self) -> None:
        html = '<main><section class="rn-room-card--standalone"><div class="rs-card-address">location_on Quận 10, Hồ Chí Minh</div></section></main>'
        detail = NhatroVNDetailParser().parse(html, detail_url="https://nhatrovn.vn/chi-tiet/x/")
        self.assertEqual(detail.address_raw, "Quận 10, Hồ Chí Minh")

    def test_nhatrovn_malformed_or_missing_address_remains_null(self) -> None:
        html = '<nav>Quận 12, Hồ Chí Minh</nav><section class="recommended-listings"><div class="rs-card-address">999 Đường Sai</div></section>'
        detail = NhatroVNDetailParser().parse(html, detail_url="https://nhatrovn.vn/chi-tiet/x/")
        self.assertIsNone(detail.address_raw)

    def test_detail_full_address_wins_over_card_coarse_location(self) -> None:
        html = (FIXTURES / "nhatrovn" / "detail_full_address.html").read_text()
        detail = NhatroVNDetailParser().parse(html, detail_url="https://nhatrovn.vn/chi-tiet/x/", listing_id="listing-1")
        bronze = BronzeMapper.map(_card("nhatrovn"), detail, run_id="run-address")
        self.assertEqual(bronze.address_raw, detail.address_raw)
        self.assertEqual(bronze.location_raw, detail.address_raw)

    def test_nhatot_full_address_uses_product_postal_address(self) -> None:
        html = (FIXTURES / "nhatot" / "detail_full_address.html").read_text()
        detail = NhatotDetailParser().parse(
            html,
            "https://www.nhatot.com/thue-phong-tro/123456.htm",
            "123456",
        )
        expected = "Hẻm 525, Đường Quang Trung, Phường 10, Quận Gò Vấp, TP Hồ Chí Minh"
        self.assertEqual(detail.address_raw, expected)
        self.assertEqual(detail.location_raw, expected)
        self.assertNotIn("999 Đường Sai", detail.address_raw)

        bronze = BronzeMapper.map(_card("nhatot"), detail, run_id="run-address")
        self.assertEqual(bronze.address_raw, expected)
        self.assertEqual(bronze.location_raw, expected)

    def test_nhatot_semantic_address_fallback_is_scoped(self) -> None:
        html = """
        <main><section><p>Địa chỉ bất động sản</p>
        <div><span>12 Đường Đúng, Phường 1, Quận 3, TP Hồ Chí Minh</span></div>
        </section></main>
        <section class='recommended'><div class='address'>999 Đường Sai</div></section>
        """
        detail = NhatotDetailParser().parse(html, "https://www.nhatot.com/a/123.htm", "123")
        self.assertEqual(detail.address_raw, "12 Đường Đúng, Phường 1, Quận 3, TP Hồ Chí Minh")

    def test_nhatot_coarse_or_missing_address_is_not_contaminated(self) -> None:
        parser = NhatotDetailParser()
        coarse = parser.parse(
            "<main><section><p>Địa chỉ bất động sản</p><div><span>Quận 10, TP Hồ Chí Minh</span></div></section></main>",
            "https://www.nhatot.com/a/123.htm",
            "123",
        )
    def test_cafeland_extracts_scoped_location_and_rejects_filter_menu(self) -> None:
        from roombeacon_crawler.sources.cafeland.parsers.detail_parser import CafelandDetailParser
        parser = CafelandDetailParser("cafeland")

        # Valid rental detail HTML snippet
        html_valid = """
        <html>
        <body>
            <div class="reales-location">
                <div class="col-left"><div class="infor">Vị trí: 123 Đường Số 1, Phường 2, Tân Bình TP. Hồ Chí Minh Lưu tin</div></div>
            </div>
            <div class="reals-description">Mô tả phòng trọ</div>
        </body>
        </html>
        """
        detail = parser.parse(html_valid, detail_url="https://nhadat.cafeland.vn/cho-thue-phong-tro-123.html")
        self.assertIsNotNone(detail)
        self.assertEqual(detail.address_raw, "123 Đường Số 1, Phường 2, Tân Bình TP. Hồ Chí Minh")

        # Sidebar navigation filter menu rejection
        html_filter = """
        <html>
        <body>
            <div class="infor">Lọc theo khu vực Toàn Quốc TP. Hà Nội TP. Hồ Chí Minh An Giang Bắc Ninh Cà Mau</div>
        </body>
        </html>
        """
        detail_filter = parser.parse(html_filter, detail_url="https://nhadat.cafeland.vn/cho-thue-phong-tro-124.html")
        self.assertIsNotNone(detail_filter)
        self.assertIsNone(detail_filter.address_raw)

        semantic = parser.parse(
            '<div class="infor"><span>Vị trí:</span> 18 Đường Số 4, Quận 7</div>',
            detail_url="https://nhadat.cafeland.vn/listing-125.html",
        )
        self.assertEqual(semantic.address_raw, "18 Đường Số 4, Quận 7")

        profile = parser.parse(
            '<div class="reales-location">Vị trí: 99 Đường Văn Phòng</div>',
            detail_url="https://nhadat.cafeland.vn/moi-gioi/profile.html",
        )
        self.assertIsNone(profile.address_raw)

    def test_chothuenha_extracts_property_address_and_rejects_corporate_footer(self) -> None:
        from roombeacon_crawler.sources.chothuenha.parsers.detail_parser import ChothuenhaDetailParser
        parser = ChothuenhaDetailParser("chothuenha")

        # HTML with property address and corporate footer/JSON-LD
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {"@type": "RealEstateAgent", "name": "ChoThueNha", "address": "Lầu 2, Tòa nhà 402 Huỳnh Văn Bánh, Phường 13, Quận Phú Nhuận"}
            </script>
            <script type="application/ld+json">
            {"@type": "House", "name": "Nhà thuê", "address": {"streetAddress": "7B/99 Đường Thành Thái, Phường 14, Quận 10, Hồ Chí Minh"}}
            </script>
        </head>
        <body>
            <p class="pd-map">7B/99 Đường Thành Thái, Phường 14, Quận 10, Hồ Chí Minh</p>
            <footer><div class="address">Lầu 2, Tòa nhà 402 Huỳnh Văn Bánh, Phường 13, Quận Phú Nhuận</div></footer>
        </body>
        </html>
        """
        detail = parser.parse(html, detail_url="https://chothuenha.com.vn/cho-thue-nha-123")
        self.assertIsNotNone(detail)
        self.assertEqual(detail.address_raw, "7B/99 Đường Thành Thái, Phường 14, Quận 10, Hồ Chí Minh")
        self.assertNotIn("402 Huỳnh Văn Bánh", detail.address_raw)

        company_only = parser.parse(
            '<script type="application/ld+json">'
            '{"@type":"Organization","address":{"streetAddress":"Office only"}}'
            '</script>',
            detail_url="https://chothuenha.com.vn/cho-thue-nha-124",
        )
        self.assertIsNone(company_only.address_raw)



    def test_chothuephongtro_extracts_semantic_address_and_rejects_footer(self) -> None:
        from roombeacon_crawler.sources.chothuephongtro.parsers.detail_parser import ChothuephongtroDetailParser
        parser = ChothuephongtroDetailParser("chothuephongtro")
        html = """
        <html>
            <body>
                <div class="section">
                    <div class="section-header"><h2>Vị trí phòng trọ</h2></div>
                    <div class="section-content">
                        Nhà Trọ An Bình hẻm 666 Nguyễn Văn Quá
                    </div>
                </div>
                <footer>
                    <div class="post-address">Footer Office Address</div>
                </footer>
            </body>
        </html>
        """
        detail = parser.parse(html, detail_url="https://chothuephongtro.me/x-pr1.html")
        self.assertEqual(detail.address_raw, "Nhà Trọ An Bình hẻm 666 Nguyễn Văn Quá")

    def test_chothuephongtro_ignores_other_headers(self) -> None:
        from roombeacon_crawler.sources.chothuephongtro.parsers.detail_parser import ChothuephongtroDetailParser
        parser = ChothuephongtroDetailParser("chothuephongtro")
        html = """
        <html>
            <body>
                <div class="section">
                    <div class="section-header"><h2>Thông tin khác</h2></div>
                    <div class="section-content">
                        Không lấy nội dung này
                    </div>
                </div>
                <div class="post-address">Địa chỉ đúng ở đây</div>
            </body>
        </html>
        """
        detail = parser.parse(html, detail_url="https://chothuephongtro.me/x-pr1.html")
        self.assertEqual(detail.address_raw, "Địa chỉ đúng ở đây")

    def test_cafeland_extracts_map_location(self) -> None:
        from roombeacon_crawler.sources.cafeland.parsers.detail_parser import CafelandDetailParser
        parser = CafelandDetailParser("cafeland")
        html_valid = """
        <html>
        <head>
            <script>
            var urlMapIframe = 'https://maps.google.com/maps?q=10.8452915,106.7795828&hl=es;z=12&output=embed';
            </script>
        </head>
        <body>
            <div class="reales-location">
                <div class="col-left"><div class="infor">Vị trí: 123 Đường Số 1, Phường 2, Tân Bình TP. Hồ Chí Minh Lưu tin</div></div>
            </div>
            <div class="reals-description">Mô tả phòng trọ</div>
        </body>
        </html>
        """
        detail = parser.parse(html_valid, detail_url="https://nhadat.cafeland.vn/cho-thue-phong-cao-cap-123.html")
        self.assertIsNotNone(detail)
        self.assertEqual(detail.address_raw, "123 Đường Số 1, Phường 2, Tân Bình TP. Hồ Chí Minh")
        self.assertIsNotNone(detail.map_location)
        self.assertEqual(detail.map_location.provider, "google_maps_embed")
        self.assertEqual(detail.map_location.latitude, 10.8452915)
        self.assertEqual(detail.map_location.longitude, 106.7795828)

    def test_cafeland_missing_map_location_is_safe(self) -> None:
        from roombeacon_crawler.sources.cafeland.parsers.detail_parser import CafelandDetailParser
        parser = CafelandDetailParser("cafeland")
        html_valid = """
        <html>
        <body>
            <div class="reales-location">
                <div class="col-left"><div class="infor">Vị trí: 123 Đường Số 1, Phường 2, Tân Bình TP. Hồ Chí Minh Lưu tin</div></div>
            </div>
        </body>
        </html>
        """
        detail = parser.parse(html_valid, detail_url="https://nhadat.cafeland.vn/cho-thue-phong-cao-cap-123.html")
        self.assertIsNotNone(detail)
        self.assertEqual(detail.address_raw, "123 Đường Số 1, Phường 2, Tân Bình TP. Hồ Chí Minh")
        self.assertIsNone(detail.map_location)

if __name__ == "__main__":
    unittest.main()
