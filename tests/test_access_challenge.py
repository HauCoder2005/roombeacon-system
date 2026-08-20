import asyncio
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import airflow
from airflow.exceptions import AirflowException, AirflowSkipException

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.sources.batdongsan.adapter import (
    BatDongSanSourceAdapter,
)
from airflow.dags.crawler.roombeacon_crawler import (
    qualify_and_crawl_target,
    summarize_crawl_results,
)
from roombeacon_crawler.enums.crawl_run_mode import CrawlRunMode
from roombeacon_crawler.models.source_qualification_result import (
    AdapterStatus,
    QualificationOverallStatus,
    RobotsQualificationStatus,
    SourceQualificationResult,
    UrlSafetyStatus,
)


class TestAccessChallengeHandling(unittest.TestCase):
    """Kiểm thử toàn diện việc xử lý Cloudflare Challenge và Access Denied như first-class runtime status."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.writer_patcher = patch(
            "roombeacon_crawler.pipeline.crawl_runner.LocalStorageWriter",
            lambda *args, **kwargs: LocalStorageWriter(base_data_dir=self.test_dir),
        )
        self.writer_patcher.start()

    def tearDown(self) -> None:
        self.writer_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_response_classifier_identifies_cloudflare_challenge(self) -> None:
        """ResponseClassifier nhận diện chính xác trang Cloudflare challenge (403 và 200)."""
        classifier = ResponseClassifier()

        cf_html_1 = "<html><title>Just a moment...</title><body>Please wait while we verify your browser.</body></html>"
        self.assertEqual(classifier.classify(403, cf_html_1), CrawlStatus.CLOUDFLARE_CHALLENGE)
        self.assertEqual(classifier.classify(200, cf_html_1), CrawlStatus.CLOUDFLARE_CHALLENGE)

        cf_html_2 = "<html><body><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script></body></html>"
        self.assertEqual(classifier.classify(403, cf_html_2), CrawlStatus.CLOUDFLARE_CHALLENGE)
        self.assertEqual(classifier.classify(200, cf_html_2), CrawlStatus.CLOUDFLARE_CHALLENGE)

        normal_403 = "<html><title>403 Forbidden</title><body>Access Denied</body></html>"
        self.assertEqual(classifier.classify(403, normal_403), CrawlStatus.ACCESS_DENIED)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    def test_listing_pipeline_stops_before_parser_on_challenge(
        self, mock_fetch: AsyncMock, mock_robots: MagicMock
    ) -> None:
        """Khi gặp Cloudflare Challenge, pipeline phải dừng ngay và TUYỆT ĐỐI KHÔNG chuyển HTML cho parser bóc tách."""
        mock_robots.return_value = ("ALLOWED", "https://batdongsan.com.vn/robots.txt")

        challenge_html = "<html><title>Just a moment...</title><body>Checking your browser before accessing batdongsan.com.vn</body></html>"
        mock_fetch.return_value = CapturedResponse(
            request_url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            final_url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            status_code=403,
            html=challenge_html,
            headers={},
            fetch_strategy=FetchStrategy.HTTP,
        )

        adapter = BatDongSanSourceAdapter()
        adapter.listing_parser = MagicMock()

        pipeline = ListingCrawlPipeline(adapter=adapter)
        target = CrawlTarget(
            url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            source="batdongsan",
            target_type=CrawlTargetType.LISTING_PAGE,
            page_number=1,
        )

        cards, detail_targets, meta, raw_html = asyncio.run(
            pipeline.execute(target=target, run_id="run_cf_test")
        )

        self.assertEqual(len(cards), 0)
        self.assertEqual(len(detail_targets), 0)
        self.assertEqual(meta.crawl_status, CrawlStatus.CLOUDFLARE_CHALLENGE)
        # Parser must not be called
        adapter.listing_parser.parse.assert_not_called()

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_crawl_runner_honest_accounting_on_challenge(
        self,
        mock_browser_fetch: AsyncMock,
        mock_http_fetch: AsyncMock,
        mock_robots: MagicMock,
    ) -> None:
        """Kiểm tra CrawlRunner cập nhật số liệu trung thực khi gặp Cloudflare Challenge:
        - pages_attempted: 1
        - pages_success: 0
        - pages_failed: 1
        - records_created: 0
        - status: CrawlStatus.CLOUDFLARE_CHALLENGE
        - stop_reason: CrawlStatus.CLOUDFLARE_CHALLENGE
        - bronze_path: None
        - manifest_path: Lưu đầy đủ
        """
        mock_robots.return_value = ("ALLOWED", "https://batdongsan.com.vn/robots.txt")

        challenge_html = "<html><title>Just a moment...</title><body>Cloudflare Challenge</body></html>"
        mock_http_fetch.return_value = CapturedResponse(
            request_url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            final_url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            status_code=200,
            html=challenge_html,
            headers={},
            fetch_strategy=FetchStrategy.HTTP,
        )

        records, result = CrawlRunner.execute_crawl(
            url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            max_pages=1,
            max_records=20,
        )

        self.assertEqual(result.source, "batdongsan")
        self.assertEqual(result.status, CrawlStatus.CLOUDFLARE_CHALLENGE)
        self.assertEqual(result.stop_reason, CrawlStatus.CLOUDFLARE_CHALLENGE)
        self.assertEqual(result.pages_attempted, 1)
        self.assertEqual(result.pages_success, 0)
        self.assertEqual(result.pages_failed, 1)
        self.assertEqual(result.records_created, 0)
        self.assertEqual(len(records), 0)
        self.assertIsNone(result.bronze_path)
        self.assertIsNotNone(result.manifest_path)
        self.assertTrue(os.path.isfile(result.manifest_path))

        with open(result.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["status"], "cloudflare_challenge")
        self.assertEqual(manifest["stop_reason"], "cloudflare_challenge")
        self.assertEqual(manifest["pages_attempted"], 1)
        self.assertEqual(manifest["pages_failed"], 1)
        self.assertEqual(manifest["pages_success"], 0)
        self.assertEqual(manifest["records_created"], 0)

    @patch("roombeacon_crawler.services.source_qualifier.SourceQualifier.qualify")
    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_scheduled_isolation_challenge_does_not_block_normal_target(
        self, mock_crawl: MagicMock, mock_qualify: MagicMock
    ) -> None:
        """Kiểm tra trong scheduled execution: Target gặp Cloudflare Challenge không chặn các target bình thường khác."""
        mock_qualify.return_value = SourceQualificationResult(
            target_url="https://any.com/",
            hostname="any.com",
            robots_url="https://any.com/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.ALLOWED,
            adapter_status=AdapterStatus.REGISTERED,
            overall_status=QualificationOverallStatus.READY,
            source_name="any",
        )

        # Target 1: BatDongSan -> Cloudflare challenge
        # Target 2: NhatroVN -> Success
        def crawl_side_effect(url: str, *args, **kwargs):
            if "batdongsan" in url:
                return [], CrawlRunResult(
                    run_id="run_bds_cf",
                    source="batdongsan",
                    started_at="2026-08-20T00:00:00",
                    finished_at="2026-08-20T00:00:01",
                    status=CrawlStatus.CLOUDFLARE_CHALLENGE,
                    stop_reason=CrawlStatus.CLOUDFLARE_CHALLENGE,
                    pages_attempted=1,
                    pages_success=0,
                    pages_failed=1,
                    records_created=0,
                )
            else:
                return [object()] * 15, CrawlRunResult(
                    run_id="run_nhatrovn_ok",
                    source="nhatrovn",
                    started_at="2026-08-20T00:00:00",
                    finished_at="2026-08-20T00:00:01",
                    status=CrawlStatus.SUCCESS,
                    pages_attempted=1,
                    pages_success=1,
                    pages_failed=0,
                    records_created=15,
                )

        mock_crawl.side_effect = crawl_side_effect

        target_bds = {"source": "batdongsan", "url": "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm"}
        target_nhatrovn = {"source": "nhatrovn", "url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"}

        res_bds = qualify_and_crawl_target.function(
            target=target_bds,
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
        )
        res_nhatro = qualify_and_crawl_target.function(
            target=target_nhatrovn,
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
        )

        self.assertEqual(res_bds["crawl_status"], "cloudflare_challenge")
        self.assertEqual(res_bds["action"], "ACCESS_CHALLENGE")
        self.assertEqual(res_bds["records_created"], 0)
        self.assertEqual(res_bds["pages_failed"], 1)

        self.assertEqual(res_nhatro["crawl_status"], "success")
        self.assertEqual(res_nhatro["action"], "CRAWLED")
        self.assertEqual(res_nhatro["records_created"], 15)

        summary = summarize_crawl_results.function(results=[res_bds, res_nhatro])

        self.assertEqual(summary["targets_discovered"], 2)
        self.assertEqual(summary["crawl_success"], 1)
        self.assertEqual(summary["access_challenge"], 1)
        self.assertEqual(summary["crawl_failed"], 0)
        self.assertEqual(summary["records_created"], 15)

    def test_mixed_fleet_five_targets_summary(self) -> None:
        """Kiểm thử tổng kết kịch bản 5 targets hỗn hợp:
        A: SUCCESS (20 records)
        B: ACCESS_CHALLENGE (0 records)
        C: ROBOTS_DENIED (0 records)
        D: Technical FAILED (0 records)
        E: SUCCESS (15 records)
        """
        results = [
            {
                "source": "source_a",
                "target_url": "https://a.test/listings",
                "qualification_status": "READY",
                "crawl_status": "success",
                "records_created": 20,
                "pages_attempted": 1,
                "pages_success": 1,
                "pages_failed": 0,
                "action": "CRAWLED",
            },
            {
                "source": "source_b",
                "target_url": "https://b.test/listings",
                "qualification_status": "READY",
                "crawl_status": "cloudflare_challenge",
                "records_created": 0,
                "pages_attempted": 1,
                "pages_success": 0,
                "pages_failed": 1,
                "action": "ACCESS_CHALLENGE",
            },
            {
                "source": "source_c",
                "target_url": "https://c.test/listings",
                "qualification_status": "DENIED_BY_ROBOTS",
                "crawl_status": "skipped",
                "records_created": 0,
                "pages_attempted": 0,
                "pages_success": 0,
                "pages_failed": 0,
                "action": "SKIPPED",
            },
            {
                "source": "source_d",
                "target_url": "https://d.test/listings",
                "qualification_status": "READY",
                "crawl_status": "connection_error",
                "records_created": 0,
                "pages_attempted": 1,
                "pages_success": 0,
                "pages_failed": 1,
                "action": "CRAWLED",
            },
            {
                "source": "source_e",
                "target_url": "https://e.test/listings",
                "qualification_status": "READY",
                "crawl_status": "success",
                "records_created": 15,
                "pages_attempted": 1,
                "pages_success": 1,
                "pages_failed": 0,
                "action": "CRAWLED",
            },
        ]

        summary = summarize_crawl_results.function(results=results)

        self.assertEqual(summary["targets_discovered"], 5)
        self.assertEqual(summary["sources_discovered"], 5)
        self.assertEqual(summary["qualification_ready"], 4)
        self.assertEqual(summary["qualification_denied"], 1)
        self.assertEqual(summary["crawl_success"], 2)
        self.assertEqual(summary["access_challenge"], 1)
        self.assertEqual(summary["crawl_skipped"], 1)
        self.assertEqual(summary["crawl_failed"], 1)
        self.assertEqual(summary["records_created"], 35)


if __name__ == "__main__":
    unittest.main()

