import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import airflow
from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.dags.crawler.roombeacon_crawler import (
    execute_crawl,
    load_crawl_targets,
    plan_crawls,
    qualify_target,
    summarize_run,
    update_checkpoint,
)
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
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
            CrawlSeed(source=self.SOURCE_NAME, target_id="hcm", url="https://fakemulti.vn/hcm", label="hcm"),
            CrawlSeed(source=self.SOURCE_NAME, target_id="hanoi", url="https://fakemulti.vn/hanoi", label="hanoi"),
            CrawlSeed(source=self.SOURCE_NAME, target_id="danang", url="https://fakemulti.vn/danang", label="danang"),
        )


class FakeEmptyTargetAdapter(BaseSourceAdapter):
    """Test adapter hợp lệ nhưng không cấu hình scheduled targets."""

    SOURCE_NAME = "fakeempty"
    DOMAINS = ("fakeempty.vn",)

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        return ()


class TestScheduledMultiSourceOrchestration(unittest.TestCase):
    """Kiểm thử toàn diện tính năng Scheduled Multi-Source Crawl Orchestration & 6-stage Flow."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.repo_patcher = patch(
            "airflow.dags.crawler.roombeacon_crawler.LocalCrawlStateRepository",
            lambda *args, **kwargs: LocalCrawlStateRepository(base_data_dir=self.test_dir),
        )
        self.repo_patcher.start()

    def tearDown(self) -> None:
        self.repo_patcher.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

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
                    CrawlSeed(source=self.SOURCE_NAME, target_id="target_1", url="https://duptest.vn/cho-thue/"),
                    CrawlSeed(source=self.SOURCE_NAME, target_id="target_2", url="https://duptest.vn/cho-thue"),
                )

        local_reg = SourceRegistry(auto_discover=False)
        local_reg.register(DuplicateSeedAdapter)

        provider = AdapterScheduledTargetProvider(registry=local_reg)
        seeds = provider.get_scheduled_targets()
        self.assertEqual(len(seeds), 1)

    def test_stage_1_load_targets_and_stage_2_plan_crawls_auto(self) -> None:
        """Kiểm tra Stage 1 & 2: Load targets và Plan crawls tự động ở chế độ AUTO."""
        raw_targets = load_crawl_targets.function()
        self.assertEqual(len(raw_targets), 5)

        plans = plan_crawls.function(targets=raw_targets, params={"execution_mode": "AUTO"})
        self.assertEqual(len(plans), 5)
        for p in plans:
            self.assertEqual(p["mode"], CrawlMode.BOOTSTRAP_FULL.value)
            self.assertEqual(p["reason"], "FIRST_SUCCESSFUL_CRAWL_NOT_FOUND")

    def test_stage_2_debug_single_target_mode(self) -> None:
        """Kiểm tra chế độ DEBUG_SINGLE_TARGET chỉ lập kế hoạch cho đúng 1 URL debug."""
        debug_url = "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/"
        plans = plan_crawls.function(
            targets=[],
            params={
                "execution_mode": "DEBUG_SINGLE_TARGET",
                "debug_target_url": debug_url,
                "debug_max_pages": 3,
                "debug_max_records": 50,
            },
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["target_url"], debug_url)
        self.assertEqual(plans[0]["safety_max_pages"], 3)
        self.assertEqual(plans[0]["safety_max_records"], 50)
        self.assertEqual(plans[0]["mode"], CrawlMode.FORCE_FULL.value)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    def test_stage_3_qualify_target_allowed_and_denied(self, mock_robots: MagicMock) -> None:
        """Kiểm tra Stage 3: Thẩm định target được phép cào hoặc bị cấm bởi robots.txt."""
        plan_allowed = {
            "source": "nhatrovn",
            "target_id": "hcm_phongtro",
            "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            "mode": "BOOTSTRAP_FULL",
        }
        plan_denied = {
            "source": "blocked_source",
            "target_id": "secret_rooms",
            "target_url": "https://blocked.test/secret",
            "mode": "BOOTSTRAP_FULL",
        }

        mock_robots.side_effect = lambda url: (
            ("ALLOWED", "https://nhatrovn.vn/robots.txt")
            if "nhatrovn" in url
            else ("DENIED", "https://blocked.test/robots.txt")
        )

        res_ok = qualify_target.function(plan=plan_allowed)
        res_denied = qualify_target.function(plan=plan_denied)

        self.assertEqual(res_ok["qualification_status"], "READY")
        self.assertEqual(res_ok["action"], "QUALIFIED")

        self.assertEqual(res_denied["qualification_status"], "DENIED_BY_ROBOTS")
        self.assertEqual(res_denied["action"], "SKIPPED")

    @patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl")
    def test_stage_4_execute_crawl_and_stage_5_update_checkpoint(
        self, mock_crawl: MagicMock
    ) -> None:
        """Kiểm tra Stage 4 & 5: Thực thi cào và cập nhật checkpoint vào State Repository."""
        plan = {
            "source": "nhatrovn",
            "target_id": "hcm_phongtro",
            "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            "mode": "BOOTSTRAP_FULL",
            "interval_minutes": 30,
        }
        qual_payload = {
            "plan": plan,
            "source": "nhatrovn",
            "target_id": "hcm_phongtro",
            "target_url": "https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            "qualification_status": "READY",
            "action": "QUALIFIED",
        }

        mock_crawl.return_value = (
            [object()] * 20,
            CrawlRunResult(
                run_id="run_test_stage4",
                source="nhatrovn",
                target_id="hcm_phongtro",
                started_at="2026-08-20T12:00:00",
                finished_at="2026-08-20T12:00:05",
                status=CrawlStatus.SUCCESS,
                pages_attempted=2,
                pages_success=2,
                pages_failed=0,
                records_created=20,
                observed_listing_ids=["id_1", "id_2", "id_3"],
            ),
        )

        crawl_result = execute_crawl.function(qual_payload=qual_payload)
        self.assertEqual(crawl_result["crawl_status"], "success")
        self.assertEqual(crawl_result["records_created"], 20)

        cp_result = update_checkpoint.function(result_payload=crawl_result)
        self.assertTrue(cp_result["checkpoint_updated"])
        self.assertIsNotNone(cp_result["last_success_at"])
        self.assertIsNotNone(cp_result["next_run_at"])

        # Kiểm tra repository đã ghi nhận
        repo = LocalCrawlStateRepository(base_data_dir=self.test_dir)
        saved_state = repo.get_state("nhatrovn", "hcm_phongtro")
        saved_seen = repo.get_seen_listing_ids("nhatrovn", "hcm_phongtro")
        self.assertIsNotNone(saved_state)
        self.assertEqual(saved_state.last_records_created, 20)
        self.assertEqual(saved_seen, {"id_1", "id_2", "id_3"})

    def test_stage_6_summarize_run(self) -> None:
        """Kiểm tra Stage 6: Tổng kết phiên cào toàn diện."""
        plans = [
            {"mode": "BOOTSTRAP_FULL"},
            {"mode": "INCREMENTAL"},
            {"mode": "INCREMENTAL"},
        ]
        qualifications = [
            {"qualification_status": "READY"},
            {"qualification_status": "READY"},
            {"qualification_status": "DENIED_BY_ROBOTS"},
        ]
        crawl_results = [
            {"crawl_status": "success", "records_created": 15, "details_success": 2, "action": "CRAWLED"},
            {"crawl_status": "cloudflare_challenge", "records_created": 0, "details_success": 0, "action": "ACCESS_CHALLENGE"},
            {"crawl_status": "skipped", "records_created": 0, "details_success": 0, "action": "SKIPPED"},
        ]
        checkpoints = [
            {"checkpoint_updated": True},
            {"checkpoint_updated": True},
            {"checkpoint_updated": True},
        ]

        summary = summarize_run.function(
            plans=plans,
            qualifications=qualifications,
            crawl_results=crawl_results,
            checkpoints=checkpoints,
        )

        self.assertEqual(summary["targets_due"], 3)
        self.assertEqual(summary["bootstrap_planned"], 1)
        self.assertEqual(summary["incremental_planned"], 2)
        self.assertEqual(summary["qualification_allowed"], 2)
        self.assertEqual(summary["robots_denied"], 1)
        self.assertEqual(summary["crawl_success"], 1)
        self.assertEqual(summary["access_challenge"], 1)
        self.assertEqual(summary["technical_failure"], 0)
        self.assertEqual(summary["records_created"], 15)
        self.assertEqual(summary["details_created"], 2)
        self.assertEqual(summary["checkpoints_updated"], 3)


if __name__ == "__main__":
    unittest.main()
