import json
import os
from pathlib import Path
import re
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter
from roombeacon_crawler.sources.nhatrovn.discovery.pagination import NhatroVNPagination
from roombeacon_crawler.sources.nhatrovn.parsers.detail_parser import NhatroVNDetailParser
from roombeacon_crawler.sources.nhatrovn.parsers.listing_parser import NhatroVNListingParser
from roombeacon_crawler.sources.registry import source_registry
from roombeacon_crawler.sources.resolver import SourceResolver

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "nhatrovn"


class TestNhatroVNSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(FIXTURES_DIR / "listing_page.html", "r", encoding="utf-8") as f:
            cls.listing_html = f.read()
        with open(FIXTURES_DIR / "detail_page.html", "r", encoding="utf-8") as f:
            cls.detail_html = f.read()

    def test_adapter_domain_support(self) -> None:
        """Kiểm tra nhận diện domain của NhatroVNSourceAdapter."""
        self.assertTrue(
            NhatroVNSourceAdapter.supports("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/")
        )
        self.assertTrue(
            NhatroVNSourceAdapter.supports("https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/")
        )
        self.assertTrue(
            NhatroVNSourceAdapter.supports("https://www.nhatrovn.vn/cho-thue-phong-tro/")
        )
        self.assertTrue(
            NhatroVNSourceAdapter.supports("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/quan-10/chi-tiet/123456/")
        )
        self.assertFalse(
            NhatroVNSourceAdapter.supports("https://nhatot.com/thue-phong-tro")
        )
        self.assertFalse(
            NhatroVNSourceAdapter.supports("https://unrelated-domain.com/rentals")
        )

    def test_url_classification(self) -> None:
        """Kiểm tra phân loại URL mục tiêu của NhatroVN (Listing, Detail, Unsupported)."""
        adapter = NhatroVNSourceAdapter()

        # Root listing
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/"),
            CrawlTargetType.LISTING_PAGE,
        )
        # Multiple cities
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"),
            CrawlTargetType.LISTING_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/"),
            CrawlTargetType.LISTING_PAGE,
        )
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/da-nang/"),
            CrawlTargetType.LISTING_PAGE,
        )
        # District / Filter
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/quan-10/"),
            CrawlTargetType.LISTING_PAGE,
        )
        # Detail URL
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/thanh-pho-thu-duc/chi-tiet/6a83dc4ccb235d6c3c150348/"),
            CrawlTargetType.DETAIL_PAGE,
        )
        # Unsupported paths on known domain
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/huong-dan/"),
            CrawlTargetType.UNSUPPORTED,
        )
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/about-us"),
            CrawlTargetType.UNSUPPORTED,
        )
        self.assertEqual(
            adapter.classify_url("https://nhatrovn.vn/chinh-sach-bao-mat/"),
            CrawlTargetType.UNSUPPORTED,
        )

    def test_registry_and_resolver_integration(self) -> None:
        """Kiểm tra đăng ký trong SourceRegistry và phân giải qua SourceResolver."""
        self.assertTrue(source_registry.is_supported("https://nhatrovn.vn/cho-thue-phong-tro/"))
        self.assertEqual(
            source_registry.resolve_source_name("https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"),
            "nhatrovn",
        )
        self.assertEqual(
            source_registry.resolve_source_name("https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/"),
            "nhatrovn",
        )

        adapter = SourceResolver.resolve_adapter("https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/")
        self.assertIsInstance(adapter, NhatroVNSourceAdapter)
        self.assertEqual(adapter.SOURCE_NAME, "nhatrovn")
        self.assertEqual(adapter.base_url, "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/")
        self.assertEqual(adapter.settings.default_strategy, FetchStrategy.HTTP)

    def test_listing_parser_extracts_cards_and_deduplicates(self) -> None:
        """Kiểm tra parser trang danh sách bóc tách chính xác các card và khử trùng lặp."""
        parser = NhatroVNListingParser(source_name="nhatrovn")
        cards = parser.parse(
            html=self.listing_html,
            source_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            page_number=1,
            limit=10,
        )

        # Fixture có 4 cards (trong đó card 3 trùng card 1) -> kết quả 3 cards duy nhất
        self.assertEqual(len(cards), 3)

        # Card 1
        card1 = cards[0]
        self.assertEqual(card1.source, "nhatrovn")
        self.assertEqual(card1.listing_id, "6a83dc4ccb235d6c3c150348")
        self.assertEqual(
            card1.detail_url,
            "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/thanh-pho-thu-duc/chi-tiet/6a83dc4ccb235d6c3c150348/",
        )
        self.assertEqual(card1.title_raw, "1110/B13 PHẠM VĂN ĐỒNG")
        self.assertEqual(card1.price_raw, "Giá: 5 triệu")
        self.assertIn("Linh Đông", card1.location_raw or "")
        self.assertEqual(
            card1.thumbnail_url_raw,
            "https://api.nhatrovn.vn/api/common/img/test/6a83dc4ccb235d6c3c150348/thumb1.jpg",
        )

        # Card 2
        card2 = cards[1]
        self.assertEqual(card2.listing_id, "7b94ed5ddc346e7d4d261459")
        self.assertEqual(card2.price_raw, "Giá: 6.5 triệu")

        # Card 4 (Missing image/price)
        card3 = cards[2]
        self.assertEqual(card3.listing_id, "8c05fe6eeb457f8e5e372560")
        self.assertIsNone(card3.price_raw)
        self.assertIsNone(card3.thumbnail_url_raw)

    def test_pagination_url_and_next_page_check(self) -> None:
        """Kiểm tra cơ chế phân trang động và tính độc lập theo URL của NhatroVN."""
        pagination = NhatroVNPagination()

        # HCMC base URL
        hcm_url = "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"
        self.assertEqual(
            pagination.build_page_url(base_url=hcm_url, page_number=1),
            "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
        )
        self.assertEqual(
            pagination.build_page_url(base_url=hcm_url, page_number=2),
            "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/?page=2",
        )

        # Hanoi base URL (Không bị ép về HCMC)
        hn_url = "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/"
        self.assertEqual(
            pagination.build_page_url(base_url=hn_url, page_number=2),
            "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/?page=2",
        )

        # Query filter preservation
        filtered_url = "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/?price_min=3000000&sort=newest"
        self.assertEqual(
            pagination.build_page_url(base_url=filtered_url, page_number=3),
            "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/?price_min=3000000&sort=newest&page=3",
        )

        # has_next_page
        self.assertTrue(
            pagination.has_next_page(
                current_page=1,
                max_pages=10,
                current_items_count=3,
                html=self.listing_html,
            )
        )
        self.assertFalse(
            pagination.has_next_page(
                current_page=42,
                max_pages=50,
                current_items_count=3,
                html=self.listing_html,
            )
        )
        self.assertFalse(
            pagination.has_next_page(
                current_page=1,
                max_pages=1,
                current_items_count=3,
                html=self.listing_html,
            )
        )

    def test_detail_parser_extracts_all_rich_attributes(self) -> None:
        """Kiểm tra detail parser trích xuất đầy đủ các trường giàu dữ liệu từ fixture."""
        parser = NhatroVNDetailParser(source_name="nhatrovn")
        detail = parser.parse(
            html=self.detail_html,
            detail_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/thanh-pho-thu-duc/chi-tiet/6a83dc4ccb235d6c3c150348/",
        )

        self.assertEqual(detail.source, "nhatrovn")
        self.assertEqual(detail.listing_id, "6a83dc4ccb235d6c3c150348")
        self.assertEqual(detail.title_raw, "Duplex G01")
        self.assertEqual(detail.price_raw, "5,000,000")
        self.assertEqual(detail.area_raw, "20m2")
        self.assertEqual(detail.position_raw, "Trệt")
        self.assertIn("Linh Đông", detail.address_raw or "")
        self.assertIn("Thủ Đức", detail.address_raw or "")
        self.assertEqual(len(detail.image_urls_raw), 2)

        # Amenities: chỉ lấy active, loại bỏ inactive
        self.assertIn("Nệm", detail.amenities_raw)
        self.assertIn("Máy lạnh", detail.amenities_raw)
        self.assertIn("Wifi", detail.amenities_raw)
        self.assertNotIn("Giường", detail.amenities_raw)

        # Fees
        self.assertEqual(detail.electricity_cost_raw, "Điện: 4k/kWh")
        self.assertEqual(detail.water_cost_raw, "Nước: 100k/ng")
        self.assertEqual(detail.internet_fee_raw, "Wifi: Free")

        # Description
        self.assertIsNotNone(detail.description_raw)
        self.assertIn("Phòng trọ Thủ Đức ngay mặt tiền Phạm Văn Đồng", detail.description_raw or "")
        self.assertIn("Gigamall Thủ Đức", detail.description_raw or "")

    def test_detail_parser_without_description_returns_none(self) -> None:
        """Kiểm tra trường hợp trang không có mô tả trả về description_raw = None không crash."""
        minimal_html = """
        <html>
            <body>
                <h1 class="room-code">Phòng Test 101</h1>
                <div class="rs-card-address">Quận 1, TP.HCM</div>
            </body>
        </html>
        """
        parser = NhatroVNDetailParser(source_name="nhatrovn")
        detail = parser.parse(
            html=minimal_html,
            detail_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/quan-1/chi-tiet/123456/",
        )
        self.assertEqual(detail.title_raw, "Phòng Test 101")
        self.assertIsNone(detail.description_raw)
        self.assertIsNone(detail.electricity_cost_raw)
        self.assertEqual(len(detail.amenities_raw), 0)

    def test_null_detail_does_not_overwrite_listing_data(self) -> None:
        """Kiểm tra nguyên tắc hợp nhất: detail null không được ghi đè dữ liệu tốt từ card."""
        card = ListingCardRaw(
            source="nhatrovn",
            listing_id="6a83dc4ccb235d6c3c150348",
            detail_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/thanh-pho-thu-duc/chi-tiet/6a83dc4ccb235d6c3c150348/",
            title_raw="1110/B13 PHẠM VĂN ĐỒNG",
            price_raw="Giá: 5 triệu",
            area_raw=None,
            location_raw="Thành phố Thủ Đức",
            posted_at_raw="Hôm nay",
            thumbnail_url_raw="https://img.test/thumb.jpg",
        )
        # Detail với price_raw = None, location_raw = None
        empty_detail = ListingDetailRaw(
            source="nhatrovn",
            listing_id="6a83dc4ccb235d6c3c150348",
            detail_url=card.detail_url,
            title_raw=None,
            price_raw=None,
            location_raw=None,
        )

        merged = BronzeMapper.map(card=card, detail=empty_detail, run_id="run_merge_test")
        self.assertEqual(merged.price_raw, "Giá: 5 triệu")
        self.assertEqual(merged.location_raw, "Thành phố Thủ Đức")
        self.assertEqual(merged.title_raw, "1110/B13 PHẠM VĂN ĐỒNG")

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_detail_limit_and_persistence_separation(
        self,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        """Kiểm tra crawl_details=True với max_details_per_run=2 lưu đúng listings.json và details.json."""
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        # Mock fetch listing page first, then detail pages
        async def fetch_side_effect(url=None, *args, **kwargs):
            target_url = url or kwargs.get("url") or (args[0] if args else "")
            if "/chi-tiet/" in str(target_url):
                return CapturedResponse(
                    request_url=str(target_url),
                    final_url=str(target_url),
                    status_code=200,
                    html=self.detail_html,
                    headers={},
                    fetch_strategy=FetchStrategy.HTTP,
                )
            else:
                return CapturedResponse(
                    request_url=str(target_url),
                    final_url=str(target_url),
                    status_code=200,
                    html=self.listing_html,
                    headers={},
                    fetch_strategy=FetchStrategy.HTTP,
                )

        mock_http_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir)
            records, result = CrawlRunner.execute_crawl(
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                max_pages=1,
                max_records=10,
                crawl_details=True,
                max_details_per_run=2,
                settings=settings,
            )

            self.assertEqual(result.status, CrawlStatus.SUCCESS)
            self.assertEqual(result.pages_success, 1)
            self.assertEqual(result.details_success, 2)
            self.assertEqual(result.records_created, 3)
            self.assertEqual(len(records), 3)

            # Kiểm tra file artifacts trong thư mục bronze
            self.assertIsNotNone(result.bronze_path)
            bronze_dir = Path(result.bronze_path)
            listings_file = bronze_dir / "listings.json"
            details_file = bronze_dir / "details.json"
            metadata_file = bronze_dir / "metadata.json"

            self.assertTrue(listings_file.exists())
            self.assertTrue(details_file.exists())
            self.assertTrue(metadata_file.exists())

            with open(listings_file, "r", encoding="utf-8") as f:
                saved_listings = json.load(f)
            with open(details_file, "r", encoding="utf-8") as f:
                saved_details = json.load(f)

            self.assertEqual(len(saved_listings), 3)
            self.assertEqual(len(saved_details), 2)
            self.assertEqual(saved_details[0]["source"], "nhatrovn")
            self.assertEqual(saved_details[0]["title_raw"], "Duplex G01")
            self.assertEqual(saved_details[0]["electricity_cost_raw"], "Điện: 4k/kWh")

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_detail_failure_isolation(
        self,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        """Kiểm tra lỗi ở 1 trang detail không làm huỷ toàn bộ kết quả crawl."""
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        call_count = 0

        async def fetch_side_effect(url=None, *args, **kwargs):
            nonlocal call_count
            target_url = url or kwargs.get("url") or (args[0] if args else "")
            if "/chi-tiet/" in str(target_url):
                call_count += 1
                if call_count == 1:
                    # Lần fetch detail 1 thành công
                    return CapturedResponse(
                        request_url=str(target_url),
                        final_url=str(target_url),
                        status_code=200,
                        html=self.detail_html,
                        headers={},
                        fetch_strategy=FetchStrategy.HTTP,
                    )
                else:
                    # Lần fetch detail 2 bị lỗi 500
                    return CapturedResponse(
                        request_url=str(target_url),
                        final_url=str(target_url),
                        status_code=500,
                        html="",
                        headers={},
                        fetch_strategy=FetchStrategy.HTTP,
                    )
            else:
                return CapturedResponse(
                    request_url=str(target_url),
                    final_url=str(target_url),
                    status_code=200,
                    html=self.listing_html,
                    headers={},
                    fetch_strategy=FetchStrategy.HTTP,
                )

        mock_http_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir)
            records, result = CrawlRunner.execute_crawl(
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                max_pages=1,
                max_records=10,
                crawl_details=True,
                max_details_per_run=2,
                settings=settings,
            )

            self.assertEqual(result.details_success, 1)
            self.assertEqual(result.details_failed, 1)
            self.assertEqual(result.records_created, 3)
            self.assertEqual(len(records), 3)

            bronze_dir = Path(result.bronze_path)
            with open(bronze_dir / "details.json", "r", encoding="utf-8") as f:
                saved_details = json.load(f)
            self.assertEqual(len(saved_details), 1)

    def test_pagination_page_5_of_42_has_next_page(self) -> None:
        """Regression test: Trang 5 / 42 với max_pages=43 phải trả về has_next_page=True."""
        pagination = NhatroVNPagination()
        html_page_5 = """
        <html>
            <body>
                <div id="paginationContainer">
                    <span class="pagination-btn">1</span>
                    <span class="pagination-btn">2</span>
                    <span class="pagination-btn">3</span>
                    <span class="pagination-btn">4</span>
                    <span class="pagination-btn active">5</span>
                    <span class="pagination-ellipsis">...</span>
                    <span class="pagination-btn">42</span>
                    <a href="?page=6" class="pagination-btn pagination-arrow">&gt;</a>
                </div>
                <small class="text-muted">Trang 5 / 42</small>
            </body>
        </html>
        """
        self.assertTrue(
            pagination.has_next_page(
                current_page=5,
                max_pages=43,
                current_items_count=20,
                html=html_page_5,
            )
        )
        next_url = pagination.build_page_url(
            base_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/?page=5",
            page_number=6,
        )
        self.assertEqual(
            next_url,
            "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/?page=6",
        )

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_multipage_crawl_stops_at_25_pages_for_500_records(
        self, mock_http_fetch: AsyncMock, mock_robots_eval: MagicMock
    ) -> None:
        """Regression test: max_pages=43, max_records=500 với nguồn 42 trang (20 records/trang)

        phải crawl chính xác 25 trang và thu thập 500 records rồi dừng với MAX_RECORDS_REACHED.
        """
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        def make_page_html(page_num: int, total_pages: int = 42) -> str:
            cards = "\n".join([
                f"""<div class="col-6 col-lg-3 mb-4">
                    <a href="/cho-thue-phong-tro/ho-chi-minh/quan-1/chi-tiet/p{page_num}_i{i}/">
                        <div class="property-card">
                            <div class="rn-property-address">Địa chỉ P{page_num}-{i}</div>
                            <div class="property-card-price">Giá: 5 triệu</div>
                        </div>
                    </a>
                </div>""" for i in range(20)
            ])
            return f"""<html><body><div class="row">{cards}</div>
            <small class="text-muted">Trang {page_num} / {total_pages}</small></body></html>"""

        async def fetch_side_effect(url=None, *args, **kwargs):
            target_url = str(url or kwargs.get("url") or "")
            match = re.search(r"page=(\d+)", target_url)
            page_num = int(match.group(1)) if match else 1
            return CapturedResponse(
                request_url=target_url,
                final_url=target_url,
                status_code=200,
                html=make_page_html(page_num, total_pages=42),
                headers={},
                fetch_strategy=FetchStrategy.HTTP,
            )

        mock_http_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir, request_delay_seconds=0.0)
            records, result = CrawlRunner.execute_crawl(
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                max_pages=43,
                max_records=500,
                crawl_details=False,
                settings=settings,
            )

            self.assertEqual(result.status, CrawlStatus.SUCCESS)
            self.assertEqual(result.pages_success, 25)
            self.assertEqual(result.records_created, 500)
            self.assertEqual(len(records), 500)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_multipage_crawl_stops_at_5_pages_when_max_pages_is_5(
        self, mock_http_fetch: AsyncMock, mock_robots_eval: MagicMock
    ) -> None:
        """Regression test: max_pages=5, max_records=500 phải dừng tại đúng 5 trang."""
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        def make_page_html(page_num: int, total_pages: int = 42) -> str:
            cards = "\n".join([
                f"""<div class="col-6 col-lg-3 mb-4">
                    <a href="/cho-thue-phong-tro/ho-chi-minh/quan-1/chi-tiet/p{page_num}_i{i}/">
                        <div class="property-card">
                            <div class="rn-property-address">Địa chỉ P{page_num}-{i}</div>
                            <div class="property-card-price">Giá: 5 triệu</div>
                        </div>
                    </a>
                </div>""" for i in range(20)
            ])
            return f"""<html><body><div class="row">{cards}</div>
            <small class="text-muted">Trang {page_num} / {total_pages}</small></body></html>"""

        async def fetch_side_effect(url=None, *args, **kwargs):
            target_url = str(url or kwargs.get("url") or "")
            match = re.search(r"page=(\d+)", target_url)
            page_num = int(match.group(1)) if match else 1
            return CapturedResponse(
                request_url=target_url,
                final_url=target_url,
                status_code=200,
                html=make_page_html(page_num, total_pages=42),
                headers={},
                fetch_strategy=FetchStrategy.HTTP,
            )

        mock_http_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir, request_delay_seconds=0.0)
            records, result = CrawlRunner.execute_crawl(
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                max_pages=5,
                max_records=500,
                crawl_details=False,
                settings=settings,
            )

            self.assertEqual(result.status, CrawlStatus.SUCCESS)
            self.assertEqual(result.pages_success, 5)
            self.assertEqual(result.records_created, 100)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_multipage_crawl_stops_at_5_pages_when_max_records_is_100(
        self, mock_http_fetch: AsyncMock, mock_robots_eval: MagicMock
    ) -> None:
        """Regression test: max_pages=43, max_records=100 phải dừng tại đúng 5 trang (100 records)."""
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        def make_page_html(page_num: int, total_pages: int = 42) -> str:
            cards = "\n".join([
                f"""<div class="col-6 col-lg-3 mb-4">
                    <a href="/cho-thue-phong-tro/ho-chi-minh/quan-1/chi-tiet/p{page_num}_i{i}/">
                        <div class="property-card">
                            <div class="rn-property-address">Địa chỉ P{page_num}-{i}</div>
                            <div class="property-card-price">Giá: 5 triệu</div>
                        </div>
                    </a>
                </div>""" for i in range(20)
            ])
            return f"""<html><body><div class="row">{cards}</div>
            <small class="text-muted">Trang {page_num} / {total_pages}</small></body></html>"""

        async def fetch_side_effect(url=None, *args, **kwargs):
            target_url = str(url or kwargs.get("url") or "")
            match = re.search(r"page=(\d+)", target_url)
            page_num = int(match.group(1)) if match else 1
            return CapturedResponse(
                request_url=target_url,
                final_url=target_url,
                status_code=200,
                html=make_page_html(page_num, total_pages=42),
                headers={},
                fetch_strategy=FetchStrategy.HTTP,
            )

        mock_http_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir, request_delay_seconds=0.0)
            records, result = CrawlRunner.execute_crawl(
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                max_pages=43,
                max_records=100,
                crawl_details=False,
                settings=settings,
            )

            self.assertEqual(result.status, CrawlStatus.SUCCESS)
            self.assertEqual(result.pages_success, 5)
            self.assertEqual(result.records_created, 100)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_multipage_crawl_stops_at_source_end_page_42(
        self, mock_http_fetch: AsyncMock, mock_robots_eval: MagicMock
    ) -> None:
        """Regression test: max_pages=43, max_records=1000 với nguồn 42 trang phải dừng tại trang 42

        và KHÔNG request trang 43.
        """
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        requested_pages: list[int] = []

        def make_page_html(page_num: int, total_pages: int = 42) -> str:
            cards = "\n".join([
                f"""<div class="col-6 col-lg-3 mb-4">
                    <a href="/cho-thue-phong-tro/ho-chi-minh/quan-1/chi-tiet/p{page_num}_i{i}/">
                        <div class="property-card">
                            <div class="rn-property-address">Địa chỉ P{page_num}-{i}</div>
                            <div class="property-card-price">Giá: 5 triệu</div>
                        </div>
                    </a>
                </div>""" for i in range(20)
            ])
            return f"""<html><body><div class="row">{cards}</div>
            <small class="text-muted">Trang {page_num} / {total_pages}</small></body></html>"""

        async def fetch_side_effect(url=None, *args, **kwargs):
            target_url = str(url or kwargs.get("url") or "")
            match = re.search(r"page=(\d+)", target_url)
            page_num = int(match.group(1)) if match else 1
            requested_pages.append(page_num)
            return CapturedResponse(
                request_url=target_url,
                final_url=target_url,
                status_code=200,
                html=make_page_html(page_num, total_pages=42),
                headers={},
                fetch_strategy=FetchStrategy.HTTP,
            )

        mock_http_fetch.side_effect = fetch_side_effect

        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir, request_delay_seconds=0.0)
            records, result = CrawlRunner.execute_crawl(
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                max_pages=43,
                max_records=1000,
                crawl_details=False,
                settings=settings,
            )

            self.assertEqual(result.status, CrawlStatus.SUCCESS)
            self.assertEqual(result.pages_success, 42)
            self.assertEqual(result.records_created, 840)
            self.assertNotIn(43, requested_pages)
            self.assertEqual(max(requested_pages), 42)

    def test_unsupported_path_on_known_domain_controlled_stop(self) -> None:
        """Kiểm tra đường dẫn không thuộc danh mục phòng trọ trên domain NhatroVN dừng có kiểm soát."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = CrawlerSettings(data_dir=tmp_dir)
            runner = CrawlRunner(
                target_url="https://nhatrovn.vn/chinh-sach-bao-mat/",
                settings=settings,
            )
            records, result = runner.execute_crawl(
                url="https://nhatrovn.vn/chinh-sach-bao-mat/",
                settings=settings,
            )
            self.assertEqual(result.status, CrawlStatus.UNSUPPORTED_TARGET)
            self.assertEqual(result.records_created, 0)
            self.assertEqual(len(records), 0)
            self.assertIsNotNone(result.manifest_path)
            self.assertIsNone(result.bronze_path)


if __name__ == "__main__":
    unittest.main()

