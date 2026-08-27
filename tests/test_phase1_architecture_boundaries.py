import ast
from pathlib import Path
import unittest

from roombeacon_crawler.application.crawl.execution_options import CrawlExecutionOptions
from roombeacon_crawler.application.crawl.session_state import CrawlSessionState
from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.models.crawl_plan import CrawlPlan


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TestPhase1ArchitectureBoundaries(unittest.TestCase):
    def test_crawl_session_state_mutable_defaults_are_isolated(self):
        first = CrawlSessionState()
        second = CrawlSessionState()

        first.observed_listing_ids.append("listing-1")
        first.seen_in_current_run.add("listing-1")
        first.errors.append("safe failure")

        self.assertEqual(second.observed_listing_ids, [])
        self.assertEqual(second.seen_in_current_run, set())
        self.assertEqual(second.errors, [])

    def test_application_orchestration_has_no_airflow_import(self):
        root = PROJECT_ROOT / "crawler/src/roombeacon_crawler/application/orchestration"
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            self.assertFalse(
                any(name == "airflow" or name.startswith("airflow.") for name in imported),
                path,
            )

    def test_domain_has_no_infrastructure_import(self):
        root = PROJECT_ROOT / "crawler/src/roombeacon_crawler/domain"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(
                        node.module.startswith("roombeacon_crawler.infrastructure"), path
                    )

    def test_execution_options_preserve_forward_only_invariants(self):
        class ForwardOnlyCapabilities:
            historical_backfill_supported = False
            supports_pagination = False

        plan = CrawlPlan(
            source="nhatot",
            target_id="hcm",
            target_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            mode=CrawlMode.BOOTSTRAP_CONTINUE,
            reason="phase1_boundary_test",
            planned_at="2026-08-24T00:00:00+00:00",
            safety_max_pages=50,
            safety_max_records=125,
            start_page=22,
        )
        options = CrawlExecutionOptions.resolve(
            plan=plan,
            settings=CrawlerSettings(),
            capabilities=ForwardOnlyCapabilities(),
            max_pages=None,
            max_records=None,
            crawl_details=None,
            max_details_per_run=None,
            start_page=None,
        )
        self.assertEqual(options.mode, CrawlMode.FORWARD_ONLY_INCREMENTAL.value)
        self.assertEqual(options.max_pages, 1)
        self.assertEqual(options.start_page, 1)
        self.assertEqual(options.stop_after_known_pages, 1)
        self.assertEqual(options.max_records, 125)

    def test_dag_keeps_documented_task_ids_and_schedule(self):
        from airflow.dags.crawler.roombeacon_crawler import roombeacon_crawler_dag

        self.assertEqual(roombeacon_crawler_dag.schedule, "*/5 * * * *")
        self.assertEqual(roombeacon_crawler_dag.max_active_runs, 1)
        self.assertEqual(
            {task.task_id for task in roombeacon_crawler_dag.tasks},
            {
                "01_config_load_sources",
                "02_config_plan_crawls",
                "03_crawl_check_eligibility",
                "04_crawl_execute_source",
                "05_storage_save_bronze",
                "06_state_update_checkpoint",
                "07_analytics_refresh_duckdb",
                "08_assets_sync_minio",
                "09_report_run_summary",
            },
        )


if __name__ == "__main__":
    unittest.main()
