import json
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from airflow.exceptions import AirflowException, AirflowSkipException

from airflow.dags.crawler.roombeacon_crawler import (
    dag,
    task_execute_crawl,
    task_validate_url,
)
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner


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
        self.assertEqual(dag.dag_id, "roombeacon_crawler")
        self.assertTrue(dag.render_template_as_native_obj)
        self.assertIn("run_mode", dag.params)
        self.assertIn("target_url", dag.params)
        self.assertIn("max_pages", dag.params)
        self.assertIn("max_records", dag.params)
        self.assertIn("crawl_details", dag.params)
        self.assertIn("max_details_per_run", dag.params)
        task_ids = [t.task_id for t in dag.tasks]
        self.assertIn("discover_scheduled_targets", task_ids)
        self.assertIn("qualify_and_crawl_target", task_ids)
        self.assertIn("summarize_crawl_results", task_ids)

    def test_invalid_target_url_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            CrawlRunner(target_url="ftp://invalid.com/file")

        with self.assertRaises(ValueError):
            CrawlRunner(target_url="http://localhost:8000")

    def test_unsupported_source_target_url_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            CrawlRunner(target_url="https://unknown-domain.com/listings")

    def test_task_validate_url_success(self) -> None:
        result = task_validate_url(
            params={"target_url": "https://phongtro123.com/tinh-thanh/ho-chi-minh"}
        )
        self.assertEqual(result["source"], "phongtro123")

        result = task_validate_url(
            params={"target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"}
        )
        self.assertEqual(result["source"], "nhatot")

        result = task_validate_url(
            params={"target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/"}
        )
        self.assertEqual(result["source"], "nhatrovn")

    def test_task_validate_url_rejects_ssrf(self) -> None:
        with self.assertRaises(AirflowException) as ctx:
            task_validate_url(params={"target_url": "http://127.0.0.1/admin"})
        self.assertIn("validation failed", str(ctx.exception))

    def test_task_validate_url_rejects_unsupported_source(self) -> None:
        with self.assertRaises(AirflowException) as ctx:
            task_validate_url(params={"target_url": "https://random-public-site.org/posts"})
        self.assertIn("Unsupported source domain", str(ctx.exception))

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_runtime_parameter_propagation_test_a(
        self, mock_execute_crawl: MagicMock
    ) -> None:
        """Kiểm tra truyền tham số Test A từ Airflow Trigger UI xuống CrawlRunner."""
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_param_test_a",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=0,
            ),
        )

        task_execute_crawl(
            params={
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/",
                "max_pages": 10,
                "max_records": 200,
                "crawl_details": False,
                "max_details_per_run": 3,
            }
        )

        mock_execute_crawl.assert_called_once_with(
            url="https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/",
            max_pages=10,
            max_records=200,
            crawl_details=False,
            max_details_per_run=3,
        )

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_runtime_parameter_propagation_test_b(
        self, mock_execute_crawl: MagicMock
    ) -> None:
        """Kiểm tra truyền tham số Test B độc lập không bị ảnh hưởng bởi Run trước."""
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_param_test_b",
                source="phongtro123",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=0,
            ),
        )

        task_execute_crawl(
            params={
                "target_url": "https://phongtro123.com/tinh-thanh/da-nang",
                "max_pages": 3,
                "max_records": 45,
                "crawl_details": True,
                "max_details_per_run": 7,
            }
        )

        mock_execute_crawl.assert_called_once_with(
            url="https://phongtro123.com/tinh-thanh/da-nang",
            max_pages=3,
            max_records=45,
            crawl_details=True,
            max_details_per_run=7,
        )

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_boolean_type_parsing(self, mock_execute_crawl: MagicMock) -> None:
        """Kiểm tra xử lý đúng kiểu dữ liệu boolean (không bị stringify 'false' thành truthy)."""
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_bool_test",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=0,
            ),
        )

        # Chuỗi "false" phải được parse thành bool False
        task_execute_crawl(
            params={
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                "crawl_details": "false",
            }
        )
        self.assertIs(mock_execute_crawl.call_args[1]["crawl_details"], False)

        # Chuỗi "true" phải được parse thành bool True
        mock_execute_crawl.reset_mock()
        task_execute_crawl(
            params={
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                "crawl_details": "true",
            }
        )
        self.assertIs(mock_execute_crawl.call_args[1]["crawl_details"], True)

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_old_default_max_pages_regression(
        self, mock_execute_crawl: MagicMock
    ) -> None:
        """Kiểm tra input người dùng max_pages=10 không bị ghi đè bởi DAG default max_pages=1."""
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_default_override_test",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=0,
            ),
        )

        task_execute_crawl(
            params={
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                "max_pages": 10,
                "max_records": 200,
                "crawl_details": False,
                "max_details_per_run": None,
            }
        )

        args = mock_execute_crawl.call_args[1]
        self.assertEqual(args["max_pages"], 10)
        self.assertEqual(args["max_records"], 200)

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_runtime_43_pages_500_records_airflow_integration(
        self, mock_execute_crawl: MagicMock
    ) -> None:
        """Kiểm tra integration context params max_pages=43, max_records=500 chuyển nguyên vẹn."""
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_43_500_test",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=0,
            ),
        )

        task_execute_crawl(
            params={
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                "max_pages": 43,
                "max_records": 500,
                "crawl_details": False,
                "max_details_per_run": 3,
            }
        )

        mock_execute_crawl.assert_called_once_with(
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            max_pages=43,
            max_records=500,
            crawl_details=False,
            max_details_per_run=3,
        )

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

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_robots_denied_raises_skip(
        self, mock_execute_crawl: AsyncMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_test_robots",
                source="nhatot",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.ROBOTS_DENIED,
                stop_reason=CrawlStatus.ROBOTS_DENIED,
                records_created=0,
            ),
        )

        with self.assertRaises(AirflowSkipException):
            task_execute_crawl(
                params={"target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"}
            )

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_unsupported_target_raises_skip(
        self, mock_execute_crawl: AsyncMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_test_unsupported_target",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.UNSUPPORTED_TARGET,
                stop_reason=CrawlStatus.UNSUPPORTED_TARGET,
                records_created=0,
            ),
        )

        with self.assertRaises(AirflowSkipException):
            task_execute_crawl(
                params={"target_url": "https://nhatrovn.vn/chinh-sach-bao-mat/"}
            )

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_technical_error_raises_airflow_exception(
        self, mock_execute_crawl: AsyncMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_test_fail",
                source="nhatot",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.CONNECTION_ERROR,
                failure_reason="Connection refused by remote host",
                pages_failed=1,
                records_created=0,
            ),
        )

        with self.assertRaises(AirflowException) as ctx:
            task_execute_crawl(
                params={"target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"}
            )

        self.assertIn("Connection refused", str(ctx.exception))

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_success_returns_summary(
        self, mock_execute_crawl: AsyncMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [object()],
            CrawlRunResult(
                run_id="run_test_success",
                source="phongtro123",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:02",
                status=CrawlStatus.SUCCESS,
                pages_success=1,
                records_created=1,
            ),
        )

        summary = task_execute_crawl(
            params={"target_url": "https://phongtro123.com/tinh-thanh/ho-chi-minh"}
        )

        self.assertEqual(summary["run_id"], "run_test_success")
        self.assertEqual(summary["records_created"], 1)
        self.assertEqual(summary["status"], "success")

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_airflow_task_semantics_zero_records_no_error_success(
        self, mock_execute_crawl: AsyncMock
    ) -> None:
        mock_execute_crawl.return_value = (
            [],
            CrawlRunResult(
                run_id="run_test_empty",
                source="phongtro123",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:02",
                status=CrawlStatus.SUCCESS,
                pages_success=1,
                records_created=0,
            ),
        )

        summary = task_execute_crawl(
            params={"target_url": "https://phongtro123.com/tinh-thanh/ho-chi-minh"}
        )

        self.assertEqual(summary["records_created"], 0)
        self.assertEqual(summary["status"], "success")


if __name__ == "__main__":
    unittest.main()
