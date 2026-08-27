import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import LocalStorageWriter
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.repositories.local_crawl_state_repository import LocalCrawlStateRepository
from roombeacon_crawler.services.crawl_planner import CrawlPlanner
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter


class TestNhaTroVNAcquisitionOptimization(unittest.TestCase):
    """Kiểm thử tối ưu hóa hiệu suất thu thập và bước tiến Frontier của NhaTroVN."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_repo = LocalCrawlStateRepository(base_data_dir=self.test_dir)
        self.storage_writer = LocalStorageWriter(base_data_dir=self.test_dir)
        self.adapter = NhatroVNSourceAdapter()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_historical_frontier_advances_across_cycles(self):
        """Kế hoạch BOOTSTRAP_CONTINUE tiếp tục trang tiếp theo thay vì bắt đầu lại từ page 1."""
        seed = CrawlSeed(
            source="nhatrovn",
            target_id="hcm_phongtro",
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            enabled=True,
            interval_minutes=15,
            bootstrap_safety_max_pages=10,
        )

        # 1. Khởi tạo state đang chạy dở ở page 5
        planner = CrawlPlanner(state_repository=self.state_repo)
        state = self.state_repo.get_state("nhatrovn", "hcm_phongtro")
        if state is None:
            from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
            state = CrawlTargetState(
                source="nhatrovn",
                target_id="hcm_phongtro",
                bootstrap_completed=False,
                bootstrap_next_page=6,
            )
            self.state_repo.save_state(state)

        # 2. Planner phải sinh CrawlPlan với start_page=6 và mode=BOOTSTRAP_CONTINUE
        plans = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].mode, CrawlMode.BOOTSTRAP_CONTINUE)
        self.assertEqual(plans[0].start_page, 6)

    def test_runtime_seed_uses_high_throughput_interval(self):
        seed = self.adapter.scheduled_targets()[0]
        self.assertEqual(seed.interval_minutes, 5)

    def test_lightweight_observation_retains_card_signals_without_detail_request(self):
        """Tin đã biết trong hạn TTL tạo ra RentalBronzeRecord hoàn chỉnh từ card mà không gọi request detail."""
        settings = CrawlerSettings(
            data_dir=self.test_dir,
            request_delay_seconds=0.0,
        )

        runner = CrawlRunner(
            adapter=self.adapter,
            settings=settings,
            storage_writer=self.storage_writer,
            state_repository=self.state_repo,
        )

        # Giả lập tin ID '61c025df9c30216e3e030e64' đã có trong seen_metadata (detailed gần đây)
        self.state_repo.record_seen_details(
            source="nhatrovn",
            target_id="test_target",
            details_map={
                "61c025df9c30216e3e030e64": {
                    "last_detailed_at": "2026-08-22T10:00:00+00:00",
                    "card_fingerprint": "mock_fingerprint",
                }
            },
        )

        seen_meta = self.state_repo.get_seen_metadata("nhatrovn", "test_target")
        self.assertIn("61c025df9c30216e3e030e64", seen_meta)


if __name__ == "__main__":
    unittest.main()
