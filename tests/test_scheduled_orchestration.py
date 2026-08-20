import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import airflow
from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.dags.crawler.roombeacon_crawler import (
    discover_scheduled_targets,
    qualify_and_crawl_target,
    summarize_crawl_results,
)
from roombeacon_crawler.enums.crawl_run_mode import CrawlRunMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.source_qualification_result import (
    AdapterStatus,
    QualificationOverallStatus,
    RobotsQualificationStatus,
    SourceQualificationResult,
    UrlSafetyStatus,
)
from roombeacon_crawler.services.target_provider import (
    AdapterScheduledTargetProvider,
    normalize_target_url,
)
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.registry import SourceRegistry, source_registry


class FakeMultiTargetAdapter(BaseSourceAdapter):
    """Test adapter cung cấp nhiều target định kỳ độc lập."""

    SOURCE_NAME = "fakemulti"
    DOMAINS = ("fakemulti.vn", "www.fakemulti.vn")
    DEFAULT_BASE_URL = "https://fakemulti.vn/hcm"

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        return (
            CrawlSeed(source=self.SOURCE_NAME, url="https://fakemulti.vn/hcm", label="hcm"),
            CrawlSeed(source=self.SOURCE_NAME, url="https://fakemulti.vn/hanoi", label="hanoi"),
            CrawlSeed(source=self.SOURCE_NAME, url="https://fakemulti.vn/danang", label="danang"),
        )


class FakeEmptyTargetAdapter(BaseSourceAdapter):
    """Test adapter hợp lệ nhưng không cấu hình scheduled targets."""

    SOURCE_NAME = "fakeempty"
    DOMAINS = ("fakeempty.vn",)

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        return ()


class TestScheduledMultiSourceOrchestration(unittest.TestCase):
    """Kiểm thử toàn diện tính năng Scheduled Multi-Source Crawl Orchestration."""

    def test_adapter_scheduled_target_provider_discovers_all_five_sources(self) -> None:
        """Provider tự động phát hiện targets định kỳ từ tất cả 5 nguồn production."""
        provider = AdapterScheduledTargetProvider(registry=source_registry)
        seeds = provider.get_scheduled_targets()

        discovered_sources = sorted(list(set(s.source for s in seeds)))
        self.assertEqual(
            discovered_sources,
            ["batdongsan", "muaban", "nhatot", "nhatrovn", "phongtro123"],
        )
        self.assertEqual(len(seeds), 5)

    def test_duplicate_scheduled_url_deduplication(self) -> None:
        """Kiểm tra deduplication URL định kỳ trùng lặp."""
        url_a = "https://example.com/rentals"
        url_b = "https://example.com/rentals/"
        self.assertEqual(normalize_target_url(url_a), normalize_target_url(url_b))

        class DuplicateSeedAdapter(BaseSourceAdapter):
            SOURCE_NAME = "duptest"
            DOMAINS = ("duptest.vn",)

            def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
                return (
                    CrawlSeed(source=self.SOURCE_NAME, url="https://duptest.vn/cho-thue/"),
                    CrawlSeed(source=self.SOURCE_NAME, url="https://duptest.vn/cho-thue"),
                )

        local_reg = SourceRegistry(auto_discover=False)
        local_reg.register(DuplicateSeedAdapter)

        provider = AdapterScheduledTargetProvider(registry=local_reg)
        seeds = provider.get_scheduled_targets()
        self.assertEqual(len(seeds), 1)

    def test_discover_scheduled_targets_single_target_mode(self) -> None:
        """Kiểm tra chế độ SINGLE_TARGET chỉ trả về đúng 1 target do user chỉ định."""
        # Valid single target
        targets = discover_scheduled_targets.function(
            params={
                "run_mode": CrawlRunMode.SINGLE_TARGET.value,
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            }
        )
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["source"], "nhatrovn")
        self.assertEqual(targets[0]["url"], "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/")

        # Empty target_url in SINGLE_TARGET mode raises error
        with self.assertRaises(AirflowException) as ctx:
            discover_scheduled_targets.function(
                params={
                    "run_mode": CrawlRunMode.SINGLE_TARGET.value,
                    "target_url": "",
                }
            )
        self.assertIn("Target URL is required", str(ctx.exception))

    def test_discover_scheduled_targets_scheduled_all_mode(self) -> None:
        """Kiểm tra chế độ SCHEDULED_ALL tự động nạp tất cả targets của các nguồn."""
        targets = discover_scheduled_targets.function(
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value}
        )
        self.assertEqual(len(targets), 5)
        sources = sorted(list(set(t["source"] for t in targets)))
        self.assertEqual(sources, ["batdongsan", "muaban", "nhatot", "nhatrovn", "phongtro123"])

    @patch("roombeacon_crawler.services.source_qualifier.SourceQualifier.qualify")
    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_scenario_1_one_ready_four_robots_denied(
        self, mock_execute_crawl: MagicMock, mock_qualify: MagicMock
    ) -> None:
        """Kịch bản 1: 1 nguồn ALLOWED (NhatroVN) và 4 nguồn ROBOTS_DENIED.

        Nguồn NhatroVN crawl thành công, 4 nguồn còn lại skip có kiểm soát, toàn bộ DAG thành công.
        """
        def qualify_side_effect(url: str, *args, **kwargs):
            if "nhatrovn.vn" in url:
                return SourceQualificationResult(
                    target_url=url,
                    hostname="nhatrovn.vn",
                    robots_url="https://nhatrovn.vn/robots.txt",
                    url_status=UrlSafetyStatus.VALID,
                    robots_status=RobotsQualificationStatus.ALLOWED,
                    adapter_status=AdapterStatus.REGISTERED,
                    overall_status=QualificationOverallStatus.READY,
                    source_name="nhatrovn",
                )
            else:
                return SourceQualificationResult(
                    target_url=url,
                    hostname="blocked.com",
                    robots_url="https://blocked.com/robots.txt",
                    url_status=UrlSafetyStatus.VALID,
                    robots_status=RobotsQualificationStatus.DENIED,
                    adapter_status=AdapterStatus.REGISTERED,
                    overall_status=QualificationOverallStatus.DENIED_BY_ROBOTS,
                    source_name="blocked",
                    reason="Robots policy denied",
                )

        mock_qualify.side_effect = qualify_side_effect
        mock_execute_crawl.return_value = (
            [object()] * 20,
            CrawlRunResult(
                run_id="run_nhatrovn_success",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                pages_success=1,
                records_created=20,
            ),
        )

        targets = discover_scheduled_targets.function(
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value}
        )

        results = []
        for target in targets:
            res = qualify_and_crawl_target.function(
                target=target,
                params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value, "max_pages": 1, "max_records": 20},
            )
            results.append(res)

        summary = summarize_crawl_results.function(results=results)

        self.assertEqual(summary["targets_discovered"], 5)
        self.assertEqual(summary["qualification_ready"], 1)
        self.assertEqual(summary["qualification_denied"], 4)
        self.assertEqual(summary["crawl_success"], 1)
        self.assertEqual(summary["crawl_skipped"], 4)
        self.assertEqual(summary["crawl_failed"], 0)
        self.assertEqual(summary["records_created"], 20)
        mock_execute_crawl.assert_called_once()

    @patch("roombeacon_crawler.services.source_qualifier.SourceQualifier.qualify")
    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_scenario_2_zero_ready_targets_all_robots_denied(
        self, mock_execute_crawl: MagicMock, mock_qualify: MagicMock
    ) -> None:
        """Kịch bản 2: Tất cả 5 nguồn đều ROBOTS_DENIED.

        Phiên điều phối hoàn thành thành công với 0 crawlable targets và không coi là lỗi kỹ thuật.
        """
        mock_qualify.return_value = SourceQualificationResult(
            target_url="https://any.vn/",
            hostname="any.vn",
            robots_url="https://any.vn/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.DENIED,
            adapter_status=AdapterStatus.REGISTERED,
            overall_status=QualificationOverallStatus.DENIED_BY_ROBOTS,
            source_name="any",
            reason="Denied by robots",
        )

        targets = discover_scheduled_targets.function(
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value}
        )

        results = []
        for target in targets:
            res = qualify_and_crawl_target.function(
                target=target,
                params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
            )
            results.append(res)

        summary = summarize_crawl_results.function(results=results)

        self.assertEqual(summary["targets_discovered"], 5)
        self.assertEqual(summary["qualification_ready"], 0)
        self.assertEqual(summary["qualification_denied"], 5)
        self.assertEqual(summary["crawl_success"], 0)
        self.assertEqual(summary["crawl_skipped"], 5)
        self.assertEqual(summary["crawl_failed"], 0)
        self.assertEqual(summary["records_created"], 0)
        mock_execute_crawl.assert_not_called()

    @patch("roombeacon_crawler.services.source_qualifier.SourceQualifier.qualify")
    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_scenario_3_access_changes_next_run_no_permanent_blocked_state(
        self, mock_execute_crawl: MagicMock, mock_qualify: MagicMock
    ) -> None:
        """Kịch bản 3: Không cache vĩnh viễn trạng thái chặn.

        Run A: BatDongSan ROBOTS_DENIED -> skip.
        Run B: BatDongSan ALLOWED -> được thẩm định lại và crawl thành công!
        """
        mock_execute_crawl.return_value = (
            [object()] * 10,
            CrawlRunResult(
                run_id="run_bds_success",
                source="batdongsan",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=10,
            ),
        )
        bds_target = {
            "source": "batdongsan",
            "url": "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            "enabled": True,
        }

        # Run A: Denied
        mock_qualify.return_value = SourceQualificationResult(
            target_url=bds_target["url"],
            hostname="batdongsan.com.vn",
            robots_url="https://batdongsan.com.vn/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.DENIED,
            adapter_status=AdapterStatus.REGISTERED,
            overall_status=QualificationOverallStatus.DENIED_BY_ROBOTS,
            source_name="batdongsan",
        )
        res_a = qualify_and_crawl_target.function(
            target=bds_target,
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
        )
        self.assertEqual(res_a["action"], "SKIPPED")
        mock_execute_crawl.assert_not_called()

        # Run B: Allowed (Website thay đổi chính sách)
        mock_qualify.return_value = SourceQualificationResult(
            target_url=bds_target["url"],
            hostname="batdongsan.com.vn",
            robots_url="https://batdongsan.com.vn/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.ALLOWED,
            adapter_status=AdapterStatus.REGISTERED,
            overall_status=QualificationOverallStatus.READY,
            source_name="batdongsan",
        )
        res_b = qualify_and_crawl_target.function(
            target=bds_target,
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
        )
        self.assertEqual(res_b["action"], "CRAWLED")
        self.assertEqual(res_b["records_created"], 10)
        mock_execute_crawl.assert_called_once()

    @patch("roombeacon_crawler.services.source_qualifier.SourceQualifier.qualify")
    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_scenario_4_reverse_access_change_allowed_becomes_denied(
        self, mock_execute_crawl: MagicMock, mock_qualify: MagicMock
    ) -> None:
        """Kịch bản 4: Nguồn trước đây ALLOWED chuyển sang ROBOTS_DENIED ở run tiếp theo.

        Run B phải thẩm định lại và skip, không được tái sử dụng trạng thái cũ.
        """
        target = {
            "source": "nhatrovn",
            "url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            "enabled": True,
        }

        # Run A: Allowed
        mock_qualify.return_value = SourceQualificationResult(
            target_url=target["url"],
            hostname="nhatrovn.vn",
            robots_url="https://nhatrovn.vn/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.ALLOWED,
            adapter_status=AdapterStatus.REGISTERED,
            overall_status=QualificationOverallStatus.READY,
            source_name="nhatrovn",
        )
        mock_execute_crawl.return_value = (
            [object()],
            CrawlRunResult(
                run_id="run_nhatro",
                source="nhatrovn",
                started_at="2026-08-19T00:00:00",
                finished_at="2026-08-19T00:00:01",
                status=CrawlStatus.SUCCESS,
                records_created=5,
            ),
        )
        res_a = qualify_and_crawl_target.function(
            target=target,
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
        )
        self.assertEqual(res_a["action"], "CRAWLED")

        # Run B: Denied
        mock_qualify.return_value = SourceQualificationResult(
            target_url=target["url"],
            hostname="nhatrovn.vn",
            robots_url="https://nhatrovn.vn/robots.txt",
            url_status=UrlSafetyStatus.VALID,
            robots_status=RobotsQualificationStatus.DENIED,
            adapter_status=AdapterStatus.REGISTERED,
            overall_status=QualificationOverallStatus.DENIED_BY_ROBOTS,
            source_name="nhatrovn",
        )
        res_b = qualify_and_crawl_target.function(
            target=target,
            params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
        )
        self.assertEqual(res_b["action"], "SKIPPED")

    def test_scenario_5_fake_source_plugin_with_multiple_scheduled_targets(self) -> None:
        """Kịch bản 5: Adapter mới cung cấp nhiều targets định kỳ độc lập được tự động phát hiện."""
        local_reg = SourceRegistry(auto_discover=False)
        local_reg.register(FakeMultiTargetAdapter)

        provider = AdapterScheduledTargetProvider(registry=local_reg)
        seeds = provider.get_scheduled_targets()

        self.assertEqual(len(seeds), 3)
        urls = [s.url for s in seeds]
        self.assertIn("https://fakemulti.vn/hcm", urls)
        self.assertIn("https://fakemulti.vn/hanoi", urls)
        self.assertIn("https://fakemulti.vn/danang", urls)

    def test_scenario_6_empty_scheduled_targets_adapter(self) -> None:
        """Kịch bản 6: Adapter hợp lệ nhưng không cấu hình scheduled targets không làm lỗi hệ thống."""
        local_reg = SourceRegistry(auto_discover=False)
        local_reg.register(FakeEmptyTargetAdapter)

        provider = AdapterScheduledTargetProvider(registry=local_reg)
        seeds = provider.get_scheduled_targets()

        self.assertEqual(len(seeds), 0)

    def test_scenario_7_mixed_outcomes_finalizer_aggregation(self) -> None:
        """Kịch bản 7: Finalizer tổng hợp chính xác khi các mapped targets có kết quả hỗn hợp (SUCCESS, SKIPPED, FAILED)."""
        mixed_results = [
            # Target 1: SUCCESS (NhatroVN)
            {
                "source": "nhatrovn",
                "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                "qualification_status": "READY",
                "crawl_status": "success",
                "records_created": 20,
                "pages_success": 1,
                "pages_failed": 0,
                "details_success": 3,
                "details_failed": 0,
                "action": "CRAWLED",
            },
            # Target 2: SKIPPED ROBOTS_DENIED (Nhatot)
            {
                "source": "nhatot",
                "target_url": "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
                "qualification_status": "DENIED_BY_ROBOTS",
                "crawl_status": "skipped",
                "records_created": 0,
                "pages_success": 0,
                "pages_failed": 0,
                "details_success": 0,
                "details_failed": 0,
                "action": "SKIPPED",
            },
            # Target 3: FAILED Technical Error (BatDongSan)
            {
                "source": "batdongsan",
                "target_url": "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
                "qualification_status": "READY",
                "crawl_status": "connection_error",
                "records_created": 0,
                "pages_success": 0,
                "pages_failed": 1,
                "details_success": 0,
                "details_failed": 0,
                "action": "CRAWLED",
            },
            # Target 4: SKIPPED ROBOTS_DENIED (Muaban)
            {
                "source": "muaban",
                "target_url": "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm",
                "qualification_status": "DENIED_BY_ROBOTS",
                "crawl_status": "skipped",
                "records_created": 0,
                "pages_success": 0,
                "pages_failed": 0,
                "details_success": 0,
                "details_failed": 0,
                "action": "SKIPPED",
            },
            # Target 5: SUCCESS (Phongtro123)
            {
                "source": "phongtro123",
                "target_url": "https://phongtro123.com/cho-thue-phong-tro",
                "qualification_status": "READY",
                "crawl_status": "success",
                "records_created": 15,
                "pages_success": 1,
                "pages_failed": 0,
                "details_success": 0,
                "details_failed": 0,
                "action": "CRAWLED",
            },
        ]

        summary = summarize_crawl_results.function(results=mixed_results)

        self.assertEqual(summary["targets_discovered"], 5)
        self.assertEqual(summary["sources_discovered"], 5)
        self.assertEqual(summary["qualification_ready"], 3)
        self.assertEqual(summary["qualification_denied"], 2)
        self.assertEqual(summary["crawl_success"], 2)
        self.assertEqual(summary["crawl_skipped"], 2)
        self.assertEqual(summary["crawl_failed"], 1)
        self.assertEqual(summary["records_created"], 35)
        self.assertEqual(summary["details_created"], 3)

    def test_xcom_payload_is_lightweight_without_raw_arrays_or_html(self) -> None:
        """Kiểm tra payload trả về qua XCom chỉ chứa metadata gọn nhẹ, không chứa HTML hay mảng dữ liệu thô."""
        with patch("roombeacon_crawler.services.source_qualifier.SourceQualifier.qualify") as mock_qualify:
            with patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl") as mock_crawl:
                mock_qualify.return_value = SourceQualificationResult(
                    target_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                    hostname="nhatrovn.vn",
                    robots_url="https://nhatrovn.vn/robots.txt",
                    url_status=UrlSafetyStatus.VALID,
                    robots_status=RobotsQualificationStatus.ALLOWED,
                    adapter_status=AdapterStatus.REGISTERED,
                    overall_status=QualificationOverallStatus.READY,
                    source_name="nhatrovn",
                )
                mock_crawl.return_value = (
                    [object()] * 10,
                    CrawlRunResult(
                        run_id="run_xcom_test",
                        source="nhatrovn",
                        started_at="2026-08-19T00:00:00",
                        finished_at="2026-08-19T00:00:01",
                        status=CrawlStatus.SUCCESS,
                        records_created=10,
                    ),
                )

                payload = qualify_and_crawl_target.function(
                    target={"source": "nhatrovn", "url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"},
                    params={"run_mode": CrawlRunMode.SCHEDULED_ALL.value},
                )

                # Payload must not contain heavy bodies
                self.assertNotIn("html", payload)
                self.assertNotIn("records", payload)
                self.assertNotIn("raw_html", payload)
                self.assertNotIn("listings", payload)
                self.assertNotIn("details", payload)
                self.assertIn("source", payload)
                self.assertIn("target_url", payload)
                self.assertIn("crawl_status", payload)
                self.assertIn("records_created", payload)


if __name__ == "__main__":
    unittest.main()

