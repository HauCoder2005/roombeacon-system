import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from roombeacon_crawler.application.crawl.deferred_details import DeferredDetailProcessor
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
        self.repo.record_failure(
            self.source, self.target_id, "fail_post", "Timeout",
            is_terminal=False, max_retries=3, retry_backoff_seconds=0,
        )
        backlog = self.repo.get_backlog(self.source, self.target_id)
        self.assertEqual(len(backlog), 1)
        self.assertEqual(backlog[0].attempt_count, 1)

        # Lần thử 2 thất bại
        self.repo.record_failure(
            self.source, self.target_id, "fail_post", "Timeout",
            is_terminal=False, max_retries=3, retry_backoff_seconds=0,
        )
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 1)

        # Lần thử 3 (đạt max_retries = 3) -> chuyển terminal
        self.repo.record_failure(
            self.source, self.target_id, "fail_post", "Timeout",
            is_terminal=False, max_retries=3, retry_backoff_seconds=0,
        )
        self.assertEqual(self.repo.count_backlog(self.source, self.target_id), 0)

    def test_fair_budget_scheduling_no_starvation(self):
        """6. Kiểm thử phân bổ ngân sách công bằng (No Starvation)."""
        scheduler = DeferredBudgetScheduler(min_deferred_slots=1)

        # Trường hợp A: Backlog 0 -> 100% cho New Discovery
        alloc_a = scheduler.allocate(total_budget=20, deferred_pending_count=0)
        self.assertEqual(alloc_a.deferred_quota, 0)
        self.assertEqual(alloc_a.immediate_quota, 20)

        # Backlog chưa enrich được ưu tiên trước immediate work trong source budget.
        alloc_b = scheduler.allocate(total_budget=20, deferred_pending_count=20)
        self.assertEqual(alloc_b.deferred_quota, 20)
        self.assertEqual(alloc_b.immediate_quota, 0)

        # Trường hợp C: Backlog nhỏ (3 items), Budget 20 -> 3 deferred, 17 immediate
        alloc_c = scheduler.allocate(total_budget=20, deferred_pending_count=3)
        self.assertEqual(alloc_c.deferred_quota, 3)
        self.assertEqual(alloc_c.immediate_quota, 17)

        # Backlog lớn dùng toàn bộ per-source budget, không ảnh hưởng source khác.
        alloc_d = scheduler.allocate(total_budget=20, deferred_pending_count=1000)
        self.assertEqual(alloc_d.deferred_quota, 20)
        self.assertEqual(alloc_d.immediate_quota, 0)

        # Trường hợp E: Dynamic Spillover (Deferred chỉ dùng 4/10 -> Còn lại 16 cho immediate)
        spillover = scheduler.spillover_immediate_quota(total_budget=20, actual_deferred_used=4)
        self.assertEqual(spillover, 16)

    def test_failed_retry_obeys_backoff_and_never_attempted_goes_first(self):
        now = datetime(2026, 8, 24, tzinfo=timezone.utc)
        failed = DeferredDetailItem(
            source=self.source,
            platform_post_id="failed_old",
            detail_url="https://nhatrovn.vn/detail/failed",
            origin_run_id="run_1",
            first_deferred_at="2026-08-20T00:00:00+00:00",
        )
        fresh = DeferredDetailItem(
            source=self.source,
            platform_post_id="never_attempted",
            detail_url="https://nhatrovn.vn/detail/fresh",
            origin_run_id="run_1",
            first_deferred_at="2026-08-21T00:00:00+00:00",
        )
        self.repo.enqueue(self.source, self.target_id, [failed, fresh])
        self.repo.record_failure(
            self.source, self.target_id, "failed_old", "Timeout",
            now=now, retry_backoff_seconds=900,
        )

        eligible_now = self.repo.get_backlog(self.source, self.target_id, now=now)
        self.assertEqual([item.platform_post_id for item in eligible_now], ["never_attempted"])
        eligible_later = self.repo.get_backlog(
            self.source, self.target_id, now=now + timedelta(minutes=16)
        )
        self.assertEqual(
            [item.platform_post_id for item in eligible_later],
            ["never_attempted", "failed_old"],
        )


class TestProgressiveDeferredCoverage(unittest.IsolatedAsyncioTestCase):
    async def test_http_success_without_expected_address_remains_retryable(self):
        source = "cafeland"
        target_id = "missing-address"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = LocalDeferredDetailRepository(base_data_dir=temp_dir)
            repo.enqueue(source, target_id, [
                DeferredDetailItem(
                    source=source,
                    platform_post_id="stable-post",
                    detail_url="https://example.test/detail/stable-post",
                    origin_run_id="run-1",
                    first_deferred_at="2026-08-26T00:00:00+00:00",
                )
            ])
            parsed_without_address = SimpleNamespace(address_raw=None)
            processor = DeferredDetailProcessor(
                adapter=SimpleNamespace(
                    SOURCE_NAME=source,
                    CAPABILITIES=SimpleNamespace(custom_flags={}),
                ),
                detail_pipeline=SimpleNamespace(
                    execute=AsyncMock(return_value=(
                        SimpleNamespace(source=source, listing_id="stable-post"),
                        parsed_without_address,
                        SimpleNamespace(status_code=200),
                    ))
                ),
                repository=repo,
                scheduler=DeferredBudgetScheduler(),
            )
            seen_meta = {}

            result = await processor.execute(
                run_id="run-2",
                target_id=target_id,
                now=datetime(2026, 8, 26, tzinfo=timezone.utc),
                crawl_details=True,
                max_details_per_run=1,
                bronze_records=[],
                detail_records=[],
                metadata=[],
                updated_seen_meta=seen_meta,
            )

            self.assertEqual(result.succeeded, 1)  # HTTP/parser success
            self.assertEqual(result.detail_address_parse_failed, 1)
            self.assertEqual(repo.count_backlog(source, target_id), 1)
            self.assertEqual(
                seen_meta["stable-post"]["detail_status"],
                "ADDRESS_MISSING_RETRY",
            )
            item = repo._load(source, target_id)["stable-post"]
            self.assertEqual(item["attempt_count"], 1)

    async def test_same_run_enrichment_replaces_lightweight_observation(self):
        source = "phongtro123"
        target_id = "discovery-first"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = LocalDeferredDetailRepository(base_data_dir=temp_dir)
            repo.enqueue(
                source,
                target_id,
                [
                    DeferredDetailItem(
                        source=source,
                        platform_post_id="post-1",
                        detail_url="https://example.test/detail/1",
                        origin_run_id="run-1",
                        first_deferred_at="2026-08-24T00:00:00+00:00",
                    )
                ],
            )
            lightweight = SimpleNamespace(
                source=source,
                listing_id="post-1",
                address_raw=None,
            )
            enriched = SimpleNamespace(
                source=source,
                listing_id="post-1",
                address_raw="1 Test Street",
            )
            detail = SimpleNamespace(address_raw="1 Test Street")
            pipeline = SimpleNamespace(
                execute=AsyncMock(
                    return_value=(
                        enriched,
                        detail,
                        SimpleNamespace(status_code=200),
                    )
                )
            )
            records = [lightweight]
            processor = DeferredDetailProcessor(
                adapter=SimpleNamespace(SOURCE_NAME=source),
                detail_pipeline=pipeline,
                repository=repo,
                scheduler=DeferredBudgetScheduler(),
            )

            result = await processor.execute(
                run_id="run-1",
                target_id=target_id,
                now=datetime(2026, 8, 24, tzinfo=timezone.utc),
                crawl_details=True,
                max_details_per_run=1,
                bronze_records=records,
                detail_records=[],
                metadata=[],
                updated_seen_meta={},
            )

            self.assertEqual(result.succeeded, 1)
            self.assertEqual(records, [enriched])
            self.assertEqual(repo.count_backlog(source, target_id), 0)

    async def test_fifty_items_progress_across_restart_with_no_overlap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = "phongtro123"
            target_id = "coverage"
            repo = LocalDeferredDetailRepository(base_data_dir=temp_dir)
            repo.enqueue(source, target_id, [
                DeferredDetailItem(
                    source=source,
                    platform_post_id=f"post_{index:02d}",
                    detail_url=f"https://phongtro123.com/detail/{index}",
                    origin_run_id="run_0",
                    first_deferred_at=f"2026-08-24T00:00:{index:02d}+00:00",
                )
                for index in range(50)
            ])
            attempted_runs: list[list[str]] = []

            for run_index in range(3):
                # Recreate both repository and processor to model a DAG/process restart.
                run_repo = LocalDeferredDetailRepository(base_data_dir=temp_dir)
                attempted: list[str] = []

                async def execute(*, target, card, run_id):
                    self.assertEqual(target.listing_id, card.listing_id)
                    attempted.append(card.listing_id)
                    detail = SimpleNamespace(address_raw="1 Test Street")
                    return SimpleNamespace(), detail, SimpleNamespace(status_code=200)

                pipeline = SimpleNamespace(execute=AsyncMock(side_effect=execute))
                processor = DeferredDetailProcessor(
                    adapter=SimpleNamespace(SOURCE_NAME=source),
                    detail_pipeline=pipeline,
                    repository=run_repo,
                    scheduler=DeferredBudgetScheduler(),
                )
                result = await processor.execute(
                    run_id=f"run_{run_index + 1}",
                    target_id=target_id,
                    now=datetime(2026, 8, 24, run_index + 1, tzinfo=timezone.utc),
                    crawl_details=True,
                    max_details_per_run=10,
                    bronze_records=[],
                    detail_records=[],
                    metadata=[],
                    updated_seen_meta={},
                )
                self.assertEqual(result.attempted, 10)
                attempted_runs.append(attempted)
                self.assertEqual(run_repo.count_backlog(source, target_id), 40 - run_index * 10)

            self.assertEqual(len(set().union(*map(set, attempted_runs))), 30)
            self.assertTrue(set(attempted_runs[0]).isdisjoint(attempted_runs[1]))
            self.assertTrue(set(attempted_runs[1]).isdisjoint(attempted_runs[2]))

    async def test_full_discovery_batch_does_not_starve_older_backlog(self):
        source = "phongtro123"
        target_id = "independent-budgets"
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = LocalDeferredDetailRepository(base_data_dir=temp_dir)
            repository.enqueue(
                source,
                target_id,
                [
                    DeferredDetailItem(
                        source=source,
                        platform_post_id=f"backlog-{index}",
                        detail_url=f"https://example.test/detail/{index}",
                        origin_run_id="older-run",
                        first_deferred_at=f"2026-08-24T00:00:0{index}+00:00",
                    )
                    for index in range(2)
                ],
            )
            discovery_records = [
                SimpleNamespace(source=source, listing_id=f"current-{index}")
                for index in range(1_000)
            ]

            async def execute(*, target, card, run_id):
                enriched = SimpleNamespace(
                    source=source,
                    listing_id=target.listing_id,
                    address_raw="1 Test Street",
                )
                detail = SimpleNamespace(address_raw="1 Test Street")
                return enriched, detail, SimpleNamespace(status_code=200)

            processor = DeferredDetailProcessor(
                adapter=SimpleNamespace(SOURCE_NAME=source),
                detail_pipeline=SimpleNamespace(execute=AsyncMock(side_effect=execute)),
                repository=repository,
                scheduler=DeferredBudgetScheduler(),
            )

            result = await processor.execute(
                run_id="current-run",
                target_id=target_id,
                now=datetime(2026, 8, 24, tzinfo=timezone.utc),
                crawl_details=True,
                max_details_per_run=2,
                bronze_records=discovery_records,
                detail_records=[],
                metadata=[],
                updated_seen_meta={},
            )

            self.assertEqual(result.attempted, 2)
            self.assertEqual(result.succeeded, 2)
            self.assertEqual(len(discovery_records), 1_002)
            self.assertEqual(repository.count_backlog(source, target_id), 0)


if __name__ == "__main__":
    unittest.main()
