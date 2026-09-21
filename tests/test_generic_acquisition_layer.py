import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.services.strategy_selector import StrategySelector
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.registry import SourceRegistry, source_registry
from roombeacon_crawler.sources.muaban.adapter import MuabanSourceAdapter
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.application.orchestration.persistence import (
    persist_bronze_mysql,
)


# --------------------------------------------------------------------------
# Test-Only Fake Source Adapter & Parsers
# --------------------------------------------------------------------------

class FakeListingParser:
    def parse(self, html: str, source_url: str, page_number: int = 1, limit: int = 50) -> list[ListingCardRaw]:
        if "item-101" in html:
            return [
                ListingCardRaw(
                    listing_id="fake-101",
                    source="fake_test_source",
                    title_raw="Phòng trọ test chất lượng cao",
                    price_raw="3 triệu/tháng",
                    area_raw="20 m2",
                    location_raw="Quận 1, TP.HCM",
                    detail_url="https://rentals.test/listings/fake-101",
                    posted_at_raw="Hôm nay",
                )
            ]
        return []


class FakeDetailParser:
    def parse(self, html: str, detail_url: str, listing_id: str | None = None) -> ListingDetailRaw:
        return ListingDetailRaw(
            listing_id=listing_id or "fake-101",
            source="fake_test_source",
            detail_url=detail_url,
            title_raw="Phòng trọ test chất lượng cao chi tiết",
            price_raw="3 triệu/tháng",
            area_raw="20 m2",
            address_raw="123 Đường Test, Quận 1",
            location_raw="Quận 1, TP.HCM",
            description_raw="Mô tả chi tiết phòng trọ test",
            posted_at_raw="Hôm nay",
        )


class FakePagination:
    def build_page_url(self, page_number: int = 1, base_url: str = "") -> str:
        base = base_url or "https://rentals.test/search"
        return f"{base}?page={page_number}"

    def has_next_page(
        self,
        current_page: int = 1,
        max_pages: int = 1,
        current_items_count: int = 0,
        *args,
        **kwargs,
    ) -> bool:
        return False


class FakeDateInterpreter:
    def is_within_range(self, date_str: str | None, *args, **kwargs) -> bool:
        return True

    def interpret(self, date_str: str | None) -> datetime | None:
        return datetime.now(timezone.utc)


class FakeSourceAdapter(BaseSourceAdapter):
    """Fake adapter dành riêng cho kiểm thử generic acquisition layer."""

    SOURCE_NAME = "fake_test_source"
    DOMAINS = ("rentals.test", "www.rentals.test")
    DEFAULT_BASE_URL = "https://rentals.test/search"

    def __init__(
        self,
        base_url: str | None = None,
        request_delay_seconds: float = 0.0,
        max_concurrency: int = 1,
    ) -> None:
        super().__init__(
            base_url=base_url,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )
        self.settings = SourceSettings(
            source_name=self.SOURCE_NAME,
            domain="rentals.test",
            base_url=self.base_url,
            default_strategy=FetchStrategy.HTTP,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )
        self.listing_parser = FakeListingParser()
        self.detail_parser = FakeDetailParser()
        self.metadata_parser = None
        self.pagination = FakePagination()
        self.date_interpreter = FakeDateInterpreter()


# --------------------------------------------------------------------------
# Test Suite: Generic Acquisition Layer
# --------------------------------------------------------------------------

class TestGenericAcquisitionLayer(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        source_registry.register(FakeSourceAdapter)

    def tearDown(self) -> None:
        source_registry.unregister(FakeSourceAdapter.SOURCE_NAME)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_muaban_parse_failure_retains_raw_evidence(self) -> None:
        html = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{}}}'
            "</script></html>"
        )
        response = CapturedResponse(
            request_url="https://muaban.net/bat-dong-san/rentals",
            final_url="https://muaban.net/bat-dong-san/rentals",
            status_code=200,
            html=html,
            headers={"content-type": "text/html"},
            fetch_strategy=FetchStrategy.HTTP,
            fetched_at="2026-09-15T00:00:00+00:00",
        )
        metadata = CrawlMetadata(
            run_id="run-schema-drift",
            source="muaban",
            target_type=CrawlTargetType.LISTING_PAGE,
            request_url=response.request_url,
            final_url=response.final_url,
            page_number=1,
            fetch_strategy=FetchStrategy.HTTP,
            http_status=200,
            content_type="text/html",
            server=None,
            cf_ray=None,
            html_size=len(html),
            started_at="2026-09-15T00:00:00+00:00",
            finished_at="2026-09-15T00:00:01+00:00",
            elapsed_ms=1.0,
            retry_count=0,
            robots_allowed=True,
            crawl_status=CrawlStatus.SUCCESS,
        )
        coordinator = MagicMock()
        coordinator.fetch = AsyncMock(
            return_value=(response, CrawlStatus.SUCCESS, metadata)
        )
        robots_policy = MagicMock()
        robots_policy.evaluate.return_value = (
            "ALLOWED",
            "https://muaban.net/robots.txt",
        )
        writer = LocalStorageWriter(base_data_dir=self.test_dir)
        pipeline = ListingCrawlPipeline(
            adapter=MuabanSourceAdapter(),
            fetch_coordinator=coordinator,
            robots_policy=robots_policy,
            failure_artifact_writer=writer,
        )
        target = CrawlTarget(
            url=response.request_url,
            source="muaban",
            target_type=CrawlTargetType.LISTING_PAGE,
            page_number=1,
        )

        cards, detail_targets, result_meta, raw_html = asyncio.run(
            pipeline.execute(target=target, run_id="run-schema-drift")
        )

        self.assertEqual(cards, [])
        self.assertEqual(detail_targets, [])
        self.assertEqual(result_meta.crawl_status, CrawlStatus.PARSE_ERROR)
        self.assertEqual(raw_html, html)
        failure_dir = (
            Path(self.test_dir)
            / "quarantine"
            / "muaban"
            / "2026-09-15"
            / "run-schema-drift"
            / "page-1"
        )
        self.assertEqual((failure_dir / "response.html").read_text(), html)
        failure_metadata = json.loads(
            (failure_dir / "metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(failure_metadata["source"], "muaban")
        self.assertEqual(failure_metadata["url"], response.final_url)
        self.assertEqual(failure_metadata["crawl_run_id"], "run-schema-drift")
        self.assertEqual(failure_metadata["failure_reason"], "SCHEMA_OR_PARSE_FAILURE")

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_muaban_confirmed_empty_first_page_completes_cleanly(
        self,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        target_url = (
            "https://muaban.net/bat-dong-san/"
            "cho-thue-nha-tro-phong-tro-ho-chi-minh"
        )
        mock_robots_eval.return_value = (
            "ALLOWED",
            "https://muaban.net/robots.txt",
        )
        mock_http_fetch.return_value = CapturedResponse(
            request_url=target_url,
            final_url=target_url,
            status_code=200,
            html=(
                '<html><script id="__NEXT_DATA__" type="application/json">'
                '{"props":{"pageProps":{"classified":{"items":[]}}}}'
                "</script></html>"
            ),
            headers={"content-type": "text/html"},
            fetch_strategy=FetchStrategy.HTTP,
        )
        settings = CrawlerSettings(
            data_dir=self.test_dir,
            request_delay_seconds=0.0,
        )

        records, crawl_result = CrawlRunner.execute_crawl(
            url=target_url,
            max_pages=1,
            max_records=20,
            crawl_details=False,
            settings=settings,
        )

        self.assertEqual(records, [])
        self.assertEqual(crawl_result.status, CrawlStatus.SUCCESS)
        self.assertEqual(crawl_result.stop_reason, "SOURCE_END")
        self.assertTrue(crawl_result.source_end_confirmed)
        self.assertIsNone(crawl_result.bronze_path)
        persistence = persist_bronze_mysql(
            {
                "source": crawl_result.source,
                "target_id": crawl_result.target_id,
                "run_id": crawl_result.run_id,
                "action": "CRAWLED",
                "crawl_status": crawl_result.status.value,
                "stop_reason": crawl_result.stop_reason,
                "source_end_confirmed": crawl_result.source_end_confirmed,
                "bronze_path": crawl_result.bronze_path,
                "observations_written": crawl_result.observations_written,
            }
        )
        self.assertEqual(persistence["status"], "SUCCESS")

    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_fetch_coordinator_http_flow(self, mock_http_fetch: AsyncMock) -> None:
        """Kiểm thử FetchCoordinator gọi HTTPFetcher và trả về CapturedResponse chuẩn."""
        mock_http_fetch.return_value = CapturedResponse(
            request_url="https://rentals.test/search",
            final_url="https://rentals.test/search",
            status_code=200,
            html="<div id='item-101'>Test item</div>",
            headers={"content-type": "text/html"},
            fetch_strategy=FetchStrategy.HTTP,
            elapsed_ms=45.0,
        )

        coordinator = FetchCoordinator(
            rate_limit_policy=RateLimitPolicy(delay_seconds=0.0),
        )
        adapter = FakeSourceAdapter()

        response, crawl_status, meta = asyncio.run(
            coordinator.fetch(
                target="https://rentals.test/search",
                adapter=adapter,
                run_id="run_coord_test",
            )
        )

        self.assertIsNotNone(response)
        self.assertEqual(crawl_status, CrawlStatus.SUCCESS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.fetch_strategy, FetchStrategy.HTTP)
        self.assertEqual(meta.crawl_status, CrawlStatus.SUCCESS)
        self.assertEqual(meta.source, "fake_test_source")
        mock_http_fetch.assert_called_once_with(url="https://rentals.test/search")

    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_fetch_coordinator_browser_flow(
        self, mock_http_fetch: AsyncMock, mock_browser_fetch: AsyncMock
    ) -> None:
        """Kiểm thử FetchCoordinator gọi BrowserFetcher khi strategy là BROWSER."""
        mock_browser_fetch.return_value = CapturedResponse(
            request_url="https://rentals.test/search",
            final_url="https://rentals.test/search",
            status_code=200,
            html="<div id='item-101'>Test dynamic item</div>",
            headers={"content-type": "text/html"},
            fetch_strategy=FetchStrategy.BROWSER,
            elapsed_ms=120.0,
        )

        coordinator = FetchCoordinator(
            rate_limit_policy=RateLimitPolicy(delay_seconds=0.0),
        )
        adapter = FakeSourceAdapter()
        # Override strategy to BROWSER
        adapter.settings.default_strategy = FetchStrategy.BROWSER

        response, crawl_status, meta = asyncio.run(
            coordinator.fetch(
                target="https://rentals.test/search",
                adapter=adapter,
                run_id="run_coord_browser_test",
            )
        )

        self.assertIsNotNone(response)
        self.assertEqual(crawl_status, CrawlStatus.SUCCESS)
        self.assertEqual(response.fetch_strategy, FetchStrategy.BROWSER)
        mock_browser_fetch.assert_called_once_with(
            url="https://rentals.test/search",
            wait_selector=None,
            wait_timeout_ms=5000,
        )
        mock_http_fetch.assert_not_called()

    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_fetch_coordinator_retry_exhaustion_on_transient_error(
        self, mock_http_fetch: AsyncMock
    ) -> None:
        """Kiểm thử RetryPolicy dừng lại sau số lần retry tối đa và bảo toàn status kỹ thuật."""
        mock_http_fetch.side_effect = TimeoutError("Connection timed out")

        coordinator = FetchCoordinator(
            rate_limit_policy=RateLimitPolicy(delay_seconds=0.0),
            retry_policy=RetryPolicy(max_retries=2, base_delay_seconds=0.01),
        )

        response, crawl_status, meta = asyncio.run(
            coordinator.fetch(
                target="https://rentals.test/search",
                adapter=FakeSourceAdapter(),
                run_id="run_retry_test",
            )
        )

        self.assertIsNone(response)
        self.assertEqual(crawl_status, CrawlStatus.CONNECTION_ERROR)
        self.assertEqual(meta.crawl_status, CrawlStatus.CONNECTION_ERROR)
        self.assertEqual(meta.retry_count, 2)
        # Should attempt initial (1) + 2 retries = 3 attempts total
        self.assertEqual(mock_http_fetch.call_count, 3)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_end_to_end_fake_source_crawl(
        self,
        mock_browser_fetch: AsyncMock,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        """Kiểm thử end-to-end phiên crawl hoàn chỉnh với FakeSourceAdapter."""
        mock_robots_eval.return_value = ("ALLOWED", "https://rentals.test/robots.txt")

        mock_http_fetch.side_effect = [
            # Listing page response
            CapturedResponse(
                request_url="https://rentals.test/search",
                final_url="https://rentals.test/search",
                status_code=200,
                html="<div id='item-101'>Listing Card Content</div>",
                headers={},
                fetch_strategy=FetchStrategy.HTTP,
            ),
            # Detail page response
            CapturedResponse(
                request_url="https://rentals.test/listings/fake-101",
                final_url="https://rentals.test/listings/fake-101",
                status_code=200,
                html="<div>Detail page content for fake-101</div>",
                headers={},
                fetch_strategy=FetchStrategy.HTTP,
            ),
        ]

        settings = CrawlerSettings(
            data_dir=self.test_dir,
            request_delay_seconds=0.0,
        )

        records, result = CrawlRunner.execute_crawl(
            url="https://rentals.test/search",
            max_pages=1,
            max_records=1,
            crawl_details=True,
            settings=settings,
        )

        self.assertEqual(result.status, CrawlStatus.SUCCESS)
        self.assertEqual(result.source, "fake_test_source")
        self.assertEqual(result.records_created, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].listing_id, "fake-101")
        self.assertEqual(records[0].source, "fake_test_source")

        # Verify Manifest and Bronze persisted properly
        self.assertIsNotNone(result.manifest_path)
        self.assertIsNotNone(result.bronze_path)
        self.assertTrue(os.path.isfile(result.manifest_path))
        self.assertTrue(os.path.isdir(result.bronze_path))

        with open(result.manifest_path, "r", encoding="utf-8") as f:
            manifest_json = json.load(f)
        self.assertEqual(manifest_json["manifest_path"], result.manifest_path)
        self.assertEqual(manifest_json["bronze_path"], result.bronze_path)
        self.assertEqual(manifest_json["records_created"], 1)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_robots_denied_aborts_before_fetch(
        self,
        mock_browser_fetch: AsyncMock,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        """Kiểm thử khi RobotsPolicy trả về DENIED, không có bất kỳ fetcher/parser nào được gọi."""
        mock_robots_eval.return_value = ("DENIED", "https://rentals.test/robots.txt")

        settings = CrawlerSettings(
            data_dir=self.test_dir,
            request_delay_seconds=0.0,
        )

        records, result = CrawlRunner.execute_crawl(
            url="https://rentals.test/search",
            max_pages=1,
            max_records=10,
            settings=settings,
        )

        self.assertEqual(result.status, CrawlStatus.ROBOTS_DENIED)
        self.assertEqual(result.records_created, 0)
        self.assertEqual(len(records), 0)
        self.assertIsNotNone(result.manifest_path)
        self.assertIsNone(result.bronze_path)

        mock_http_fetch.assert_not_called()
        mock_browser_fetch.assert_not_called()

    def test_unsupported_source_rejection(self) -> None:
        """Kiểm thử URL an toàn nhưng chưa có Adapter nào đăng ký."""
        with self.assertRaises(ValueError) as ctx:
            CrawlRunner(target_url="https://unsupported-public-domain.vn/listings")
        self.assertIn("chưa được hỗ trợ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
