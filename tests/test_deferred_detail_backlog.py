import shutil
import tempfile
import unittest
from pathlib import Path

from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem
from roombeacon_crawler.repositories.local_deferred_detail_repository import (
    LocalDeferredDetailRepository,
)
from roombeacon_crawler.policies.deferred_budget_scheduler import (
    DeferredBudgetScheduler,
)


class TestDeferredDetailBacklog(unittest.TestCase):
    """Kiểm thử toàn diện hàng đợi hoãn cào chi tiết (Deferred Detail Backlog)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.repo = LocalDeferredDetailRepository(base_data_dir=self.temp_dir)
        self.source = "nhatrovn"
        self.target_id = "test_target"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_enqueue_new_items_when_budget_exhausted(self):
        """1. NEW + budget exhausted -> Thêm thành công vào hàng đợi hoãn."""
        items = [
            DeferredDetailItem(
                source=self.source,
                platform_post_id=f"post_{i}",
                detail_url=f"https://nhatrovn.vn/detail/{i}",
                origin_run_id="run_1",
                first_deferred_at="2026-08-22T00:00:00Z",
                reason="REQUEST_BUDGET_EXHAUSTED",
                card_title=f"Phòng trọ {i}",
            )
            for i in range(1, 21)
        ]
        added = self.repo.enqueue(self.source, self.target_id, items)
        self.assertEqual(added, 20)
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 20)

    def test_deduplication_same_listing_queued_repeatedly(self):
        """2. Cùng một tin đăng bị đưa vào queue nhiều lần -> Chỉ giữ 1 active item duy nhất."""
        item = DeferredDetailItem(
            source=self.source,
            platform_post_id="duplicate_post",
            detail_url="https://nhatrovn.vn/detail/dup",
            origin_run_id="run_1",
            first_deferred_at="2026-08-22T00:00:00Z",
        )
        added_1 = self.repo.enqueue(self.source, self.target_id, [item])
        self.assertEqual(added_1, 1)

        # Enqueue lại tin này trong run khác
        item_again = DeferredDetailItem(
            source=self.source,
            platform_post_id="duplicate_post",
            detail_url="https://nhatrovn.vn/detail/dup",
            origin_run_id="run_2",
            first_deferred_at="2026-08-22T01:00:00Z",
        )
        added_2 = self.repo.enqueue(self.source, self.target_id, [item_again])
        self.assertEqual(added_2, 0)
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 1)

    def test_durable_disk_reload(self):
        """3. Khởi tạo repository mới từ cùng thư mục -> Backlog được phục hồi nguyên vẹn từ đĩa."""
        item = DeferredDetailItem(
            source=self.source,
            platform_post_id="persist_post",
            detail_url="https://nhatrovn.vn/detail/persist",
            origin_run_id="run_1",
            first_deferred_at="2026-08-22T00:00:00Z",
            card_title="Tin bền vững",
        )
        self.repo.enqueue(self.source, self.target_id, [item])

        # Tạo instance mới trỏ vào cùng data dir (mô phỏng container restart)
        new_repo = LocalDeferredDetailRepository(base_data_dir=self.temp_dir)
        backlog = new_repo.get_backlog(self.source, self.target_id)
        self.assertEqual(len(backlog), 1)
        self.assertEqual(backlog[0].platform_post_id, "persist_post")
        self.assertEqual(backlog[0].card_title, "Tin bền vững")

    def test_record_success_removes_from_backlog(self):
        """4. Cào chi tiết thành công ở chu kỳ sau -> Xóa khỏi backlog pending."""
        item = DeferredDetailItem(
            source=self.source,
            platform_post_id="success_post",
            detail_url="https://nhatrovn.vn/detail/success",
            origin_run_id="run_1",
            first_deferred_at="2026-08-22T00:00:00Z",
        )
        self.repo.enqueue(self.source, self.target_id, [item])
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 1)

        self.repo.record_success(self.source, self.target_id, "success_post")
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 0)

    def test_transient_failure_and_terminal_lifecycle(self):
        """5. Thất bại tạm thời giữ lại trong queue; quá số lần thử tối đa chuyển terminal."""
        item = DeferredDetailItem(
            source=self.source,
            platform_post_id="fail_post",
            detail_url="https://nhatrovn.vn/detail/fail",
            origin_run_id="run_1",
            first_deferred_at="2026-08-22T00:00:00Z",
        )
        self.repo.enqueue(self.source, self.target_id, [item])

        # Lần thử 1 thất bại
        self.repo.record_failure(self.source, self.target_id, "fail_post", "Timeout", is_terminal=False, max_retries=3)
        backlog = self.repo.get_backlog(self.source, self.target_id)
        self.assertEqual(len(backlog), 1)
        self.assertEqual(backlog[0].attempt_count, 1)

        # Lần thử 2 thất bại
        self.repo.record_failure(self.source, self.target_id, "fail_post", "Timeout", is_terminal=False, max_retries=3)
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 1)

        # Lần thử 3 (đạt max_retries = 3) -> chuyển terminal
        self.repo.record_failure(self.source, self.target_id, "fail_post", "Timeout", is_terminal=False, max_retries=3)
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 0)

    def test_fair_budget_scheduling_no_starvation(self):
        """6. Kiểm thử phân bổ ngân sách công bằng (No Starvation)."""
        scheduler = DeferredBudgetScheduler(deferred_share_ratio=0.5, min_deferred_slots=1)

        # Trường hợp A: Backlog 0 -> 100% cho New Discovery
        alloc_a = scheduler.allocate(total_budget=20, deferred_pending_count=0)
        self.assertEqual(alloc_a.deferred_quota, 0)
        self.assertEqual(alloc_a.immediate_quota, 20)

        # Trường hợp B: Backlog 20, Budget 20 -> 50/50 (10 deferred, 10 immediate)
        alloc_b = scheduler.allocate(total_budget=20, deferred_pending_count=20)
        self.assertEqual(alloc_b.deferred_quota, 10)
        self.assertEqual(alloc_b.immediate_quota, 10)

        # Trường hợp C: Backlog nhỏ (3 items), Budget 20 -> 3 deferred, 17 immediate
        alloc_c = scheduler.allocate(total_budget=20, deferred_pending_count=3)
        self.assertEqual(alloc_c.deferred_quota, 3)
        self.assertEqual(alloc_c.immediate_quota, 17)

        # Trường hợp D: Backlog lớn (1000 items), Budget 20 -> deferred không được chiếm quá quota (10), dành 10 cho tin mới
        alloc_d = scheduler.allocate(total_budget=20, deferred_pending_count=1000)
        self.assertEqual(alloc_d.deferred_quota, 10)
        self.assertEqual(alloc_d.immediate_quota, 10)

        # Trường hợp E: Dynamic Spillover (Deferred chỉ dùng 4/10 -> Còn lại 16 cho immediate)
        spillover = scheduler.spillover_immediate_quota(total_budget=20, actual_deferred_used=4)
        self.assertEqual(spillover, 16)


if __name__ == "__main__":
    unittest.main()
