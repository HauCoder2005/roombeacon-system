import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from airflow.exceptions import AirflowException, AirflowSkipException

from airflow.dags.crawler.roombeacon_crawler import (
    execute_crawl as airflow_execute_crawl,
    plan_crawls,
    qualify_target as airflow_qualify_target,
    roombeacon_crawler_dag,
)
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.validators.url_validator import URLValidator


class TestCrawlRunnerExecution(unittest.TestCase):
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

    def test_dag_structure(self) -> None:
        self.assertEqual(roombeacon_crawler_dag.dag_id, "roombeacon_crawler")
        self.assertIn("execution_mode", roombeacon_crawler_dag.params)
        self.assertIn("debug_target_url", roombeacon_crawler_dag.params)
        self.assertIn("debug_max_pages", roombeacon_crawler_dag.params)
        self.assertIn("debug_max_records", roombeacon_crawler_dag.params)
        self.assertIn("debug_crawl_details", roombeacon_crawler_dag.params)
        task_ids = [t.task_id for t in roombeacon_crawler_dag.tasks]
        self.assertIn("load_crawl_targets", task_ids)
        self.assertIn("plan_crawls", task_ids)
        self.assertIn("qualify_target", task_ids)
        self.assertIn("execute_crawl", task_ids)
        self.assertIn("update_checkpoint", task_ids)
        self.assertIn("summarize_run", task_ids)

    def test_invalid_target_url_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            CrawlRunner(target_url="ftp://invalid.com/file")

        with self.assertRaises(ValueError):
            CrawlRunner(target_url="http://localhost:8000")

    def test_unsupported_source_target_url_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            CrawlRunner(target_url="https://unknown-domain.com/listings")

    def test_url_validator_checks(self) -> None:
        valid_pt, _ = URLValidator.validate("https://phongtro123.com/tinh-thanh/ho-chi-minh")
        self.assertTrue(valid_pt)

        valid_nt, _ = URLValidator.validate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh")
        self.assertTrue(valid_nt)

        valid_nv, _ = URLValidator.validate("https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/")
        self.assertTrue(valid_nv)

        invalid_ssrf, reason = URLValidator.validate("http://127.0.0.1/admin")
        self.assertFalse(invalid_ssrf)
        self.assertIn("bảo mật", reason)

        invalid_proto, reason = URLValidator.validate("ftp://random-public-site.org/posts")
        self.assertFalse(invalid_proto)

    def test_runtime_parameter_propagation_debug_plan(self) -> None:
        """Kiểm tra truyền tham số debug từ Airflow Trigger UI vào CrawlPlan."""
        plans = plan_crawls.function(
            targets=[],
            params={
                "execution_mode": "DEBUG_SINGLE_TARGET",
                "debug_target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/",
                "debug_max_pages": 10,
                "debug_max_records": 200,
                "debug_crawl_details": False,
            },
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["target_url"], "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/")
        self.assertEqual(plans[0]["safety_max_pages"], 10)
        self.assertEqual(plans[0]["safety_max_records"], 200)
        self.assertFalse(plans[0]["crawl_details"])

    def test_runtime_parameter_propagation_debug_plan_b(self) -> None:
        """Kiểm tra truyền tham số debug Test B độc lập."""
        plans = plan_crawls.function(
            targets=[],
            params={
                "execution_mode": "DEBUG_SINGLE_TARGET",
                "debug_target_url": "https://phongtro123.com/tinh-thanh/da-nang",
                "debug_max_pages": 3,
                "debug_max_records": 45,
                "debug_crawl_details": True,
            },
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["target_url"], "https://phongtro123.com/tinh-thanh/da-nang")
        self.assertEqual(plans[0]["safety_max_pages"], 3)
        self.assertEqual(plans[0]["safety_max_records"], 45)
        self.assertTrue(plans[0]["crawl_details"])

    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_execute_crawl_facade_structure(
        self, mock_browser_fetch: AsyncMock, mock_http_fetch: AsyncMock
    ) -> None:
        sample_html = """
        <html>
            <body>
                <main data-testid="list-ads" class="ListAds_ListAds">
                    <div data-testid="ad-item" class="AdItem_adItemWrapper">
                        <a href="https://www.nhatot.com/132400185.htm">
                            <h3 class="AdItem_title">Phòng trọ quận 12 mới xây thoáng mát</h3>
                            <span class="AdItem_price">3.5 triệu/tháng</span>
                            <span class="AdItem_area">25 m2</span>
                            <span class="AdItem_location">Quận 12, TP.HCM</span>
                            <span class="AdItem_date">Hôm nay</span>
                        </a>
                    </div>
                </main>
            </body>
        </html>
        """
        mock_browser_fetch.return_value = CapturedResponse(
            request_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            final_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            status_code=200,
            html=sample_html,
            headers={},
            fetch_strategy=FetchStrategy.BROWSER,
        )

        records, result = CrawlRunner.execute_crawl(
            url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            max_pages=1,
            max_records=1,
            crawl_details=False,
        )

        self.assertIsInstance(result, CrawlRunResult)
        self.assertEqual(result.source, "nhatot")
        self.assertEqual(result.status, CrawlStatus.SUCCESS)
        self.assertEqual(result.pages_success, 1)
        self.assertEqual(result.records_created, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].listing_id, "132400185")
        self.assertIsNotNone(result.manifest_path)
        self.assertIsNotNone(result.bronze_path)
        self.assertTrue(os.path.isfile(result.manifest_path))
        self.assertTrue(os.path.isdir(result.bronze_path))

        with open(result.manifest_path, "r", encoding="utf-8") as f:
            manifest_json = json.load(f)
        self.assertEqual(manifest_json["manifest_path"], result.manifest_path)
        self.assertEqual(manifest_json["bronze_path"], result.bronze_path)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_execute_crawl_phongtro123_http_fetch(
        self,
        mock_browser_fetch: AsyncMock,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        mock_robots_eval.return_value = ("ALLOWED", "https://phongtro123.com/robots.txt")

        sample_phongtro123_html = """
        <html>
            <body>
                <ul class="post-listing">
                    <li class="post-item">
                        <h3 class="post-title">
                            <a href="https://phongtro123.com/phong-tro-quan-10-moi-xay-pr702593.html">
                                Phòng trọ Quận 10 mới xây sạch đẹp tiện nghi
                            </a>
                        </h3>
                        <span class="post-price">3.2 triệu/tháng</span>
                        <span class="post-acreage">22 m2</span>
                        <span class="post-location">Quận 10, Hồ Chí Minh</span>
                        <span class="post-time">2 giờ trước</span>
                    </li>
                </ul>
            </body>
        </html>
        """
        mock_http_fetch.return_value = CapturedResponse(
            request_url="https://phongtro123.com/tinh-thanh/ho-chi-minh",
            final_url="https://phongtro123.com/tinh-thanh/ho-chi-minh",
            status_code=200,
            html=sample_phongtro123_html,
            headers={},
            fetch_strategy=FetchStrategy.HTTP,
        )

        records, result = CrawlRunner.execute_crawl(
            url="https://phongtro123.com/tinh-thanh/ho-chi-minh",
            max_pages=1,
            max_records=1,
            crawl_details=False,
        )

        self.assertIsInstance(result, CrawlRunResult)
        self.assertEqual(result.source, "phongtro123")
        self.assertEqual(result.status, CrawlStatus.SUCCESS)
        self.assertEqual(result.pages_success, 1)
        self.assertEqual(result.records_created, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].listing_id, "702593")
        self.assertEqual(records[0].source, "phongtro123")
        self.assertIsNotNone(result.manifest_path)
        self.assertIsNotNone(result.bronze_path)
        self.assertTrue(os.path.isfile(result.manifest_path))
        self.assertTrue(os.path.isdir(result.bronze_path))

        with open(result.manifest_path, "r", encoding="utf-8") as f:
            manifest_json = json.load(f)
        self.assertEqual(manifest_json["manifest_path"], result.manifest_path)
        self.assertEqual(manifest_json["bronze_path"], result.bronze_path)
        mock_http_fetch.assert_called_once()
        mock_browser_fetch.assert_not_called()

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_execute_crawl_nhatrovn_http_fetch(
        self,
        mock_browser_fetch: AsyncMock,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        mock_robots_eval.return_value = ("ALLOWED", "https://nhatrovn.vn/robots.txt")

        fixtures_path = Path(__file__).parent / "fixtures" / "nhatrovn" / "listing_page.html"
        with open(fixtures_path, "r", encoding="utf-8") as f:
            sample_nhatrovn_html = f.read()

        mock_http_fetch.return_value = CapturedResponse(
            request_url="https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/",
            final_url="https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/",
            status_code=200,
            html=sample_nhatrovn_html,
            headers={},
            fetch_strategy=FetchStrategy.HTTP,
        )

        records, result = CrawlRunner.execute_crawl(
            url="https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/",
            max_pages=1,
            max_records=5,
            crawl_details=False,
        )

        self.assertIsInstance(result, CrawlRunResult)
        self.assertEqual(result.source, "nhatrovn")
        self.assertEqual(result.status, CrawlStatus.SUCCESS)
        self.assertEqual(result.pages_success, 1)
        self.assertEqual(result.records_created, 3)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].source, "nhatrovn")
        self.assertIsNotNone(result.manifest_path)
        self.assertIsNotNone(result.bronze_path)
        self.assertTrue(os.path.isfile(result.manifest_path))
        self.assertTrue(os.path.isdir(result.bronze_path))
        mock_http_fetch.assert_called_once()
        mock_browser_fetch.assert_not_called()

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    @patch("roombeacon_crawler.fetchers.http_fetcher.HttpFetcher.fetch")
    @patch("roombeacon_crawler.fetchers.browser_fetcher.BrowserFetcher.fetch")
    def test_robots_denied_preserves_status_and_avoids_fetch(
        self,
        mock_browser_fetch: AsyncMock,
        mock_http_fetch: AsyncMock,
        mock_robots_eval: MagicMock,
    ) -> None:
        mock_robots_eval.return_value = ("DENIED", "https://www.nhatot.com/robots.txt")

        records, result = CrawlRunner.execute_crawl(
            url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            max_pages=1,
            max_records=10,
        )

        self.assertEqual(result.status, CrawlStatus.ROBOTS_DENIED)
        self.assertEqual(result.stop_reason, CrawlStatus.ROBOTS_DENIED)
        self.assertEqual(result.records_created, 0)
        self.assertEqual(len(records), 0)
        self.assertIsNotNone(result.manifest_path)
        self.assertTrue(os.path.isfile(result.manifest_path))
        self.assertIsNone(result.bronze_path)

        with open(result.manifest_path, "r", encoding="utf-8") as f:
            manifest_json = json.load(f)
        self.assertEqual(manifest_json["manifest_path"], result.manifest_path)
        self.assertIsNone(manifest_json["bronze_path"])

        mock_browser_fetch.assert_not_called()
        mock_http_fetch.assert_not_called()

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    def test_airflow_task_semantics_robots_denied_returns_skipped(
        self, mock_robots: MagicMock
    ) -> None:
        mock_robots.return_value = ("DENIED", "https://nhatot.com/robots.txt")

        plan = {
            "source": "nhatot",
            "target_id": "hcm_phongtro",
            "target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            "mode": "BOOTSTRAP_FULL",
        }
        res = airflow_qualify_target.function(plan=plan)

        self.assertEqual(res["qualification_status"], "DENIED_BY_ROBOTS")
        self.assertEqual(res["action"], "SKIPPED")

    def test_airflow_task_semantics_unsupported_target_returns_invalid(self) -> None:
        plan = {
            "source": "nhatrovn",
            "target_id": "invalid",
            "target_url": "ftp://nhatrovn.vn/invalid",
            "mode": "BOOTSTRAP_FULL",
        }
        res = airflow_qualify_target.function(plan=plan)
        self.assertEqual(res["qualification_status"], "INVALID_URL")
        self.assertEqual(res["action"], "SKIPPED")

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_technical_error_raises_airflow_exception(
        self, mock_execute_crawl: MagicMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_test_fail",
                source="nhatot",
                target_id="hcm_phongtro",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.CONNECTION_ERROR,
                failure_reason="Connection refused by remote host",
                pages_failed=1,
                records_created=0,
            ),
        )

        qual_payload = {
            "plan": {
                "source": "nhatot",
                "target_id": "hcm_phongtro",
                "target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
                "mode": "BOOTSTRAP_FULL",
            },
            "source": "nhatot",
            "target_id": "hcm_phongtro",
            "target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            "qualification_status": "READY",
            "action": "QUALIFIED",
        }

        with self.assertRaises(AirflowException) as ctx:
            airflow_execute_crawl.function(qual_payload=qual_payload)

        self.assertIn("Connection refused", str(ctx.exception))

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_success_returns_summary(
        self, mock_execute_crawl: MagicMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [object()],
            CrawlRunResult(
                run_id="run_test_success",
                source="phongtro123",
                target_id="hcm_phongtro",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:02",
                status=CrawlStatus.SUCCESS,
                pages_success=1,
                records_created=1,
            ),
        )

        qual_payload = {
            "plan": {
                "source": "phongtro123",
                "target_id": "hcm_phongtro",
                "target_url": "https://phongtro123.com/tinh-thanh/ho-chi-minh",
                "mode": "BOOTSTRAP_FULL",
            },
            "source": "phongtro123",
            "target_id": "hcm_phongtro",
            "target_url": "https://phongtro123.com/tinh-thanh/ho-chi-minh",
            "qualification_status": "READY",
            "action": "QUALIFIED",
        }

        summary = airflow_execute_crawl.function(qual_payload=qual_payload)

        self.assertEqual(summary["run_id"], "run_test_success")
        self.assertEqual(summary["records_created"], 1)
        self.assertEqual(summary["crawl_status"], "success")


if __name__ == "__main__":
    unittest.main()
