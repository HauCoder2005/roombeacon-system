from datetime import datetime, timedelta, timezone
import json
import os
import shutil
import tempfile
import unittest

from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.services.crawl_planner import CrawlPlanner


class TestCrawlPlannerAndStateRepository(unittest.TestCase):
    """Kiểm thử toàn diện cho CrawlPlanner và LocalCrawlStateRepository."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.repo = LocalCrawlStateRepository(base_data_dir=self.test_dir)
        self.planner = CrawlPlanner(state_repository=self.repo)
        self.now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_local_state_repository_save_and_retrieve_survives_restart(self) -> None:
        """Kiểm tra lưu vết checkpoint và seen listing IDs tồn tại bền vững qua các lần khởi động lại repo."""
        state = CrawlTargetState(
            source="nhatrovn",
            target_id="hcm_phongtro",
            last_success_at=self.now.isoformat(),
            last_watermark_at=self.now.isoformat(),
            last_status="success",
            last_records_created=25,
            consecutive_failures=0,
            next_run_at=(self.now + timedelta(minutes=30)).isoformat(),
        )
        self.repo.save_state(state)
        self.repo.record_seen_listing_ids("nhatrovn", "hcm_phongtro", ["id_101", "id_102"])

        # Khởi tạo instance repo mới từ cùng thư mục để mô phỏng tiến trình mới
        new_repo = LocalCrawlStateRepository(base_data_dir=self.test_dir)
        loaded_state = new_repo.get_state("nhatrovn", "hcm_phongtro")
        loaded_seen = new_repo.get_seen_listing_ids("nhatrovn", "hcm_phongtro")

        self.assertIsNotNone(loaded_state)
        self.assertEqual(loaded_state.source, "nhatrovn")
        self.assertEqual(loaded_state.target_id, "hcm_phongtro")
        self.assertEqual(loaded_state.last_records_created, 25)
        self.assertEqual(loaded_seen, {"id_101", "id_102"})

    def test_first_crawl_no_state_is_bootstrap_full(self) -> None:
        """Target chưa từng có state -> Chế độ BOOTSTRAP_FULL với lý do FIRST_SUCCESSFUL_CRAWL_NOT_FOUND."""
        seed = CrawlSeed(
            source="nhatrovn",
            target_id="hcm_phongtro",
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            enabled=True,
            interval_minutes=30,
        )

        plans = self.planner.plan_all([seed], current_time=self.now)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.source, "nhatrovn")
        self.assertEqual(plan.target_id, "hcm_phongtro")
        self.assertEqual(plan.mode, CrawlMode.BOOTSTRAP_FULL)
        self.assertEqual(plan.reason, "FIRST_SUCCESSFUL_CRAWL_NOT_FOUND")
        self.assertIsNone(plan.watermark_from)
        self.assertIsNone(plan.overlap_from)

    def test_successful_state_is_incremental_with_overlap(self) -> None:
        """Target đã có state thành công trước đó -> Chế độ INCREMENTAL và tính toán overlap window chuẩn xác."""
        last_success = self.now - timedelta(minutes=45)
        state = CrawlTargetState(
            source="nhatot",
            target_id="hcm_phongtro",
            last_success_at=last_success.isoformat(),
            last_watermark_at=last_success.isoformat(),
            next_run_at=(last_success + timedelta(minutes=30)).isoformat(),  # Due 15 mins ago
        )
        self.repo.save_state(state)

        seed = CrawlSeed(
            source="nhatot",
            target_id="hcm_phongtro",
            url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            enabled=True,
            interval_minutes=30,
            incremental_overlap_hours=24,
        )

        plans = self.planner.plan_all([seed], current_time=self.now)

        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.mode, CrawlMode.INCREMENTAL)
        self.assertEqual(plan.reason, "INCREMENTAL_SCHEDULED_DUE")
        self.assertEqual(plan.watermark_from, last_success.isoformat())
        expected_overlap = (last_success - timedelta(hours=24)).isoformat()
        self.assertEqual(plan.overlap_from, expected_overlap)

    def test_not_due_target_is_skipped(self) -> None:
        """Target chưa đến hạn chạy (next_run_at trong tương lai) -> Không sinh plan."""
        future_time = self.now + timedelta(minutes=20)
        state = CrawlTargetState(
            source="batdongsan",
            target_id="hcm_phongtro",
            last_success_at=(self.now - timedelta(minutes=10)).isoformat(),
            next_run_at=future_time.isoformat(),
        )
        self.repo.save_state(state)

        seed = CrawlSeed(
            source="batdongsan",
            target_id="hcm_phongtro",
            url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
            enabled=True,
            interval_minutes=120,
        )

        plans = self.planner.plan_all([seed], current_time=self.now)
        self.assertEqual(len(plans), 0)

    def test_disabled_target_is_ignored(self) -> None:
        """Seed bị vô hiệu hóa (enabled=False) -> Bị bỏ qua hoàn toàn."""
        seed = CrawlSeed(
            source="muaban",
            target_id="hcm_phongtro",
            url="https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm",
            enabled=False,
        )
        plans = self.planner.plan_all([seed], current_time=self.now)
        self.assertEqual(len(plans), 0)

    def test_force_full_override_bypasses_due_check_and_state(self) -> None:
        """Tham số override FORCE_FULL ép cào toàn bộ kể cả khi target chưa đến hạn."""
        future_time = self.now + timedelta(minutes=60)
        state = CrawlTargetState(
            source="nhatrovn",
            target_id="hcm_phongtro",
            last_success_at=self.now.isoformat(),
            next_run_at=future_time.isoformat(),
        )
        self.repo.save_state(state)

        seed = CrawlSeed(
            source="nhatrovn",
            target_id="hcm_phongtro",
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            enabled=True,
            interval_minutes=30,
        )

        plans = self.planner.plan_all([seed], current_time=self.now, override_mode="FORCE_FULL")
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].mode, CrawlMode.FORCE_FULL)
        self.assertEqual(plans[0].reason, "FORCE_FULL_OVERRIDE")

    def test_zero_due_targets_returns_empty_list(self) -> None:
        """Khi toàn bộ targets đều chưa đến hạn, planner trả về danh sách rỗng an toàn."""
        future_time = self.now + timedelta(hours=1)
        for s in ["nhatrovn", "nhatot", "phongtro123"]:
            state = CrawlTargetState(
                source=s,
                target_id="hcm_phongtro",
                last_success_at=self.now.isoformat(),
                next_run_at=future_time.isoformat(),
            )
            self.repo.save_state(state)

        seeds = [
            CrawlSeed(source="nhatrovn", target_id="hcm_phongtro", url="https://nhatrovn.vn/rooms"),
            CrawlSeed(source="nhatot", target_id="hcm_phongtro", url="https://nhatot.com/rooms"),
            CrawlSeed(source="phongtro123", target_id="hcm_phongtro", url="https://phongtro123.com/rooms"),
        ]

        plans = self.planner.plan_all(seeds, current_time=self.now)
        self.assertEqual(len(plans), 0)


if __name__ == "__main__":
    unittest.main()
