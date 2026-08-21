import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter


class TestIncrementalCrawlAndKnownRegionStop(unittest.TestCase):
    """Kiểm thử chuyên sâu cho thuật toán cào dữ liệu INCREMENTAL và cơ chế dừng vùng đã biết (Known-Region Stop)."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.repo = LocalCrawlStateRepository(base_data_dir=self.test_dir)
        self.writer = LocalStorageWriter(base_data_dir=self.test_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_incremental_crawl_stops_after_consecutive_known_pages(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm tra INCREMENTAL crawl dừng ngay sau khi gặp 2 trang liên tiếp chỉ toàn tin đã biết."""
        # Chuẩn bị repo có sẵn 100 listing_ids đã thấy
        initial_seen = {f"item_{i}" for i in range(1, 101)}
        self.repo.record_seen_listing_ids("nhatrovn", "hcm_phongtro", initial_seen)

        # Mô phỏng:
        # Trang 1: Có 1 tin mới ("item_new_1") và 9 tin cũ ("item_1" .. "item_9") -> Streak = 0
        # Trang 2: Toàn tin cũ ("item_10" .. "item_19") -> Streak = 1
        # Trang 3: Toàn tin cũ ("item_20" .. "item_29") -> Streak = 2 -> DỪNG
        def make_card(lid: str, url: str) -> ListingCardRaw:
            return ListingCardRaw(
                source="nhatrovn",
                listing_id=lid,
                detail_url=url,
                title_raw=f"Tin đăng {lid}",
                price_raw="3 triệu/tháng",
                area_raw="25 m2",
                location_raw="Quận 1, TP.HCM",
                posted_at_raw="2026-08-20",
            )

        def make_meta(status=CrawlStatus.SUCCESS):
            return CrawlMetadata(
                run_id="run_test_inc",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                final_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                page_number=1,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-20T12:00:00",
                finished_at="2026-08-20T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=status,
            )

        cards_p1 = [make_card("item_new_1", "https://nhatrovn.vn/chi-tiet/new_1")] + [
            make_card(f"item_{i}", f"https://nhatrovn.vn/chi-tiet/{i}") for i in range(1, 10)
        ]
        cards_p2 = [
            make_card(f"item_{i}", f"https://nhatrovn.vn/chi-tiet/{i}") for i in range(10, 20)
        ]
        cards_p3 = [
            make_card(f"item_{i}", f"https://nhatrovn.vn/chi-tiet/{i}") for i in range(20, 30)
        ]
        cards_p4 = [
            make_card(f"item_{i}", f"https://nhatrovn.vn/chi-tiet/{i}") for i in range(30, 40)
        ]

        async def side_effect(target, run_id, limit_per_page):
            if target.page_number == 1:
                return cards_p1, [], make_meta(), "<html>page 1</html>"
            elif target.page_number == 2:
                return cards_p2, [], make_meta(), "<html>page 2</html>"
            elif target.page_number == 3:
                return cards_p3, [], make_meta(), "<html>page 3</html>"
            else:
                return cards_p4, [], make_meta(), "<html>page 4</html>"

        mock_listing_exec.side_effect = side_effect

        plan = CrawlPlan(
            source="nhatrovn",
            target_id="hcm_phongtro",
            target_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            mode=CrawlMode.INCREMENTAL,
            reason="INCREMENTAL_SCHEDULED_DUE",
            planned_at="2026-08-20T12:00:00",
            safety_max_pages=20,
            incremental_stop_after_known_pages=2,
            crawl_details=False,
        )

        runner = CrawlRunner(
            target_url=plan.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )

        records, result = asyncio.run(runner.run(plan=plan))

        # Phải dừng ở trang 3 sau khi streak đạt 2
        self.assertEqual(result.pages_attempted, 3)
        self.assertEqual(result.pages_success, 3)
        self.assertEqual(result.status, CrawlStatus.SUCCESS)
        self.assertEqual(result.new_listing_ids, ["item_new_1"])
        self.assertIn("item_new_1", result.observed_listing_ids)
        self.assertEqual(len(result.observed_listing_ids), 30)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_new_listing_resets_known_streak(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm tra khi gặp tin mới ở trang 2 thì streak bị reset về 0 và tiếp tục cào."""
        initial_seen = {f"item_{i}" for i in range(1, 101)}
        self.repo.record_seen_listing_ids("nhatrovn", "hcm_phongtro", initial_seen)

        def make_card(lid: str, url: str) -> ListingCardRaw:
            return ListingCardRaw(
                source="nhatrovn",
                listing_id=lid,
                detail_url=url,
                title_raw=f"Tin {lid}",
                price_raw="3 triệu/tháng",
                area_raw="25 m2",
                location_raw="Quận 1, TP.HCM",
                posted_at_raw="2026-08-20",
            )

        def make_meta():
            return CrawlMetadata(
                run_id="run_test",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url="https://nhatrovn.vn/rooms",
                final_url="https://nhatrovn.vn/rooms",
                page_number=1,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-20T12:00:00",
                finished_at="2026-08-20T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        # Trang 1: Toàn tin cũ -> Streak = 1
        # Trang 2: Có 1 tin mới -> Streak RESET về 0
        # Trang 3: Toàn tin cũ -> Streak = 1
        # Trang 4: Toàn tin cũ -> Streak = 2 -> DỪNG
        async def side_effect(target, run_id, limit_per_page):
            if target.page_number == 1:
                return [make_card(f"item_{i}", f"https://nhatrovn.vn/{i}") for i in range(1, 11)], [], make_meta(), "<html>p1</html>"
            elif target.page_number == 2:
                cards = [make_card("item_fresh_999", "https://nhatrovn.vn/fresh")] + [make_card(f"item_{i}", f"https://nhatrovn.vn/{i}") for i in range(11, 20)]
                return cards, [], make_meta(), "<html>p2</html>"
            elif target.page_number == 3:
                return [make_card(f"item_{i}", f"https://nhatrovn.vn/{i}") for i in range(21, 31)], [], make_meta(), "<html>p3</html>"
            elif target.page_number == 4:
                return [make_card(f"item_{i}", f"https://nhatrovn.vn/{i}") for i in range(31, 41)], [], make_meta(), "<html>p4</html>"
            else:
                return [], [], make_meta(), "<html>empty</html>"

        mock_listing_exec.side_effect = side_effect

        plan = CrawlPlan(
            source="nhatrovn",
            target_id="hcm_phongtro",
            target_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            mode=CrawlMode.INCREMENTAL,
            reason="INCREMENTAL_SCHEDULED_DUE",
            planned_at="2026-08-20T12:00:00",
            safety_max_pages=20,
            incremental_stop_after_known_pages=2,
            crawl_details=False,
        )

        runner = CrawlRunner(
            target_url=plan.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )

        records, result = asyncio.run(runner.run(plan=plan))

        # Dừng ở trang 4
        self.assertEqual(result.pages_attempted, 4)
        self.assertEqual(result.new_listing_ids, ["item_fresh_999"])
        self.assertEqual(result.records_created, 1)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_first_run_bootstrap_and_second_run_incremental_lifecycle(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm thử chu trình hoàn chỉnh: Lần 1 BOOTSTRAP_FULL -> Checkpoint lưu -> Lần 2 INCREMENTAL dừng sớm, 0 record mới."""
        from roombeacon_crawler.services.crawl_planner import CrawlPlanner
        from roombeacon_crawler.models.crawl_seed import CrawlSeed

        seed = CrawlSeed(
            source="nhatrovn",
            target_id="hcm_phongtro",
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            bootstrap_safety_max_pages=10,
            incremental_stop_after_known_pages=3,
        )

        def make_card(lid: str) -> ListingCardRaw:
            return ListingCardRaw(
                source="nhatrovn",
                listing_id=lid,
                detail_url=f"https://nhatrovn.vn/chi-tiet/{lid}",
                title_raw=f"Tin {lid}",
                price_raw="3 triệu/tháng",
                area_raw="25 m2",
                location_raw="Quận 1, TP.HCM",
                posted_at_raw="2026-08-21",
            )

        def make_meta():
            return CrawlMetadata(
                run_id="run_lifecycle",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url="https://nhatrovn.vn/rooms",
                final_url="https://nhatrovn.vn/rooms",
                page_number=1,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        # -------------------------------------------------------------
        # 1. RUN 1: Chưa có state -> Phải là BOOTSTRAP_FULL
        # -------------------------------------------------------------
        planner = CrawlPlanner(state_repository=self.repo)
        plans = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans), 1)
        plan_run_1 = plans[0]
        self.assertEqual(plan_run_1.mode, CrawlMode.BOOTSTRAP_FULL)
        self.assertEqual(plan_run_1.reason, "FIRST_SUCCESSFUL_CRAWL_NOT_FOUND")

        # Mock dữ liệu 2 trang cho run 1
        cards_p1 = [make_card(f"id_{i}") for i in range(1, 21)]
        cards_p2 = [make_card(f"id_{i}") for i in range(21, 41)]

        async def side_effect_run_1(target, run_id, limit_per_page):
            if target.page_number == 1:
                return cards_p1, [], make_meta(), "<html>p1</html>"
            elif target.page_number == 2:
                return cards_p2, [], make_meta(), "<html>p2</html>"
            else:
                return [], [], make_meta(), ""

        mock_listing_exec.side_effect = side_effect_run_1

        runner_1 = CrawlRunner(
            target_url=plan_run_1.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_1, result_1 = asyncio.run(runner_1.run(plan=plan_run_1))

        self.assertEqual(result_1.records_created, 40)
        self.assertEqual(result_1.status, CrawlStatus.SUCCESS)
        self.assertEqual(result_1.stop_reason, "SOURCE_END")

        # Mô phỏng task update_checkpoint lưu state
        state_1 = CrawlTargetState(
            source=result_1.source,
            target_id=result_1.target_id,
            last_success_at=result_1.finished_at,
            last_watermark_at=result_1.finished_at,
            last_status="success",
            last_stop_reason="SOURCE_END",
            last_records_created=result_1.records_created,
        )
        self.repo.save_state(state_1)
        self.repo.record_seen_listing_ids(result_1.source, result_1.target_id, result_1.observed_listing_ids)

        # Kiểm tra seen IDs đã lưu
        seen_after_run_1 = self.repo.get_seen_listing_ids("nhatrovn", "hcm_phongtro")
        self.assertEqual(len(seen_after_run_1), 40)

        # -------------------------------------------------------------
        # 2. RUN 2: Đã có checkpoint -> Phải là INCREMENTAL
        # -------------------------------------------------------------
        plans_run_2 = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans_run_2), 1)
        plan_run_2 = plans_run_2[0]
        self.assertEqual(plan_run_2.mode, CrawlMode.INCREMENTAL)
        self.assertEqual(plan_run_2.reason, "INCREMENTAL_SCHEDULED_DUE")

        # Mock dữ liệu toàn bộ là tin đã biết trên cả 3 trang đầu
        async def side_effect_run_2(target, run_id, limit_per_page):
            if target.page_number == 1:
                return cards_p1, [], make_meta(), "<html>p1</html>"
            elif target.page_number == 2:
                return cards_p2, [], make_meta(), "<html>p2</html>"
            elif target.page_number == 3:
                return cards_p1, [], make_meta(), "<html>p3</html>"
            else:
                return cards_p2, [], make_meta(), "<html>p4</html>"

        mock_listing_exec.side_effect = side_effect_run_2

        runner_2 = CrawlRunner(
            target_url=plan_run_2.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_2, result_2 = asyncio.run(runner_2.run(plan=plan_run_2))

        # Phải dừng chính xác sau 3 trang (threshold = 3)
        self.assertEqual(result_2.pages_attempted, 3)
        self.assertEqual(result_2.stop_reason, "KNOWN_REGION_REACHED")
        self.assertEqual(result_2.records_created, 0)
        self.assertEqual(len(records_2), 0)
        self.assertIsNone(result_2.bronze_path)  # Không ghi file rỗng vào Bronze
        self.assertIsNotNone(result_2.manifest_path)  # Nhưng vẫn lưu Manifest

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_duplicate_listing_id_within_same_page_or_consecutive_pages(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Đảm bảo cùng 1 listing_id xuất hiện lặp lại trong cùng 1 trang hoặc giữa các trang chỉ được tạo 1 record duy nhất."""
        def make_card(lid: str) -> ListingCardRaw:
            return ListingCardRaw(
                source="nhatrovn",
                listing_id=lid,
                detail_url=f"https://nhatrovn.vn/{lid}",
                title_raw=f"Tin {lid}",
                price_raw="3 triệu/tháng",
                area_raw="25 m2",
                location_raw="Quận 1, TP.HCM",
                posted_at_raw="2026-08-21",
            )

        def make_meta():
            return CrawlMetadata(
                run_id="run_dup",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url="https://nhatrovn.vn/rooms",
                final_url="https://nhatrovn.vn/rooms",
                page_number=1,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        # Trang 1: Chứa trùng lặp "item_dup" 2 lần
        # Trang 2: Lại chứa "item_dup" 1 lần nữa và "item_unique_2"
        cards_p1 = [make_card("item_dup"), make_card("item_dup"), make_card("item_unique_1")]
        cards_p2 = [make_card("item_dup"), make_card("item_unique_2")]

        async def side_effect(target, run_id, limit_per_page):
            if target.page_number == 1:
                return cards_p1, [], make_meta(), "<html>p1</html>"
            elif target.page_number == 2:
                return cards_p2, [], make_meta(), "<html>p2</html>"
            else:
                return [], [], make_meta(), ""

        mock_listing_exec.side_effect = side_effect

        plan = CrawlPlan(
            source="nhatrovn",
            target_id="hcm_phongtro",
            target_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            mode=CrawlMode.BOOTSTRAP_FULL,
            reason="TEST_DUP",
            planned_at="2026-08-21T12:00:00",
            safety_max_pages=5,
        )

        runner = CrawlRunner(
            target_url=plan.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records, result = asyncio.run(runner.run(plan=plan))

        # Tổng số record tạo phải là 3 ("item_dup", "item_unique_1", "item_unique_2"), không phải 5
        self.assertEqual(result.records_created, 3)
        self.assertEqual(result.duplicates_skipped, 2)
        self.assertEqual(sorted(result.new_listing_ids), ["item_dup", "item_unique_1", "item_unique_2"])

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_incremental_page_with_mix_of_new_and_known_emits_only_new(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm tra: State đã có [100, 99, 98, 97]. Trang 1 có [105, 104, 103, 102, 101, 100, 99] -> Chỉ emit 5 tin mới."""
        self.repo.record_seen_listing_ids("nhatrovn", "hcm_phongtro", {str(i) for i in range(1, 101)})

        def make_card(lid: str) -> ListingCardRaw:
            return ListingCardRaw(
                source="nhatrovn",
                listing_id=lid,
                detail_url=f"https://nhatrovn.vn/item/{lid}",
                title_raw=f"Tin {lid}",
                price_raw="3 triệu/tháng",
                area_raw="25 m2",
                location_raw="Quận 1, TP.HCM",
                posted_at_raw="2026-08-21",
            )

        def make_meta():
            return CrawlMetadata(
                run_id="run_mix",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url="https://nhatrovn.vn/rooms",
                final_url="https://nhatrovn.vn/rooms",
                page_number=1,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        # Trang 1: 5 tin mới (105..101) và 2 tin cũ (100, 99)
        cards_p1 = [make_card(str(i)) for i in (105, 104, 103, 102, 101, 100, 99)]
        # Trang 2: Toàn tin cũ (98..90) -> streak 1
        cards_p2 = [make_card(str(i)) for i in range(90, 99)]
        # Trang 3: Toàn tin cũ (80..89) -> streak 2 -> DỪNG
        cards_p3 = [make_card(str(i)) for i in range(80, 90)]

        async def side_effect(target, run_id, limit_per_page):
            if target.page_number == 1:
                return cards_p1, [], make_meta(), "<html>p1</html>"
            elif target.page_number == 2:
                return cards_p2, [], make_meta(), "<html>p2</html>"
            elif target.page_number == 3:
                return cards_p3, [], make_meta(), "<html>p3</html>"
            else:
                return [], [], make_meta(), ""

        mock_listing_exec.side_effect = side_effect

        plan = CrawlPlan(
            source="nhatrovn",
            target_id="hcm_phongtro",
            target_url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            mode=CrawlMode.INCREMENTAL,
            reason="INCREMENTAL_SCHEDULED_DUE",
            planned_at="2026-08-21T12:00:00",
            safety_max_pages=20,
            incremental_stop_after_known_pages=2,
            crawl_details=False,
        )

        runner = CrawlRunner(
            target_url=plan.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records, result = asyncio.run(runner.run(plan=plan))

        # Phải dừng ở trang 3
        self.assertEqual(result.pages_attempted, 3)
        self.assertEqual(result.stop_reason, "KNOWN_REGION_REACHED")
        # Chỉ emit đúng 5 record mới (105, 104, 103, 102, 101)
        self.assertEqual(result.records_created, 5)
        self.assertEqual(len(records), 5)
        self.assertEqual(sorted(result.new_listing_ids), ["101", "102", "103", "104", "105"])
        self.assertIsNotNone(result.bronze_path)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_multi_run_bootstrap_continuation_lifecycle_55_pages(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm thử chu trình tiếp diễn bootstrap nhiều chặng: 55 trang, safety_max_pages=20:
        - Run 1: BOOTSTRAP_FULL (trang 1-20) -> MAX_PAGES_REACHED -> next_page = 21, bootstrap_completed = False
        - Run 2: BOOTSTRAP_CONTINUE (trang 21-40) -> MAX_PAGES_REACHED -> next_page = 41, bootstrap_completed = False
        - Run 3: BOOTSTRAP_CONTINUE (trang 41-55) -> SOURCE_END -> next_page = None, bootstrap_completed = True
        - Run 4: INCREMENTAL (trang 1-3) -> KNOWN_REGION_REACHED
        """
        from roombeacon_crawler.services.crawl_planner import CrawlPlanner
        from roombeacon_crawler.models.crawl_seed import CrawlSeed

        seed = CrawlSeed(
            source="nhatrovn",
            target_id="hcm_phongtro",
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            bootstrap_safety_max_pages=20,
            incremental_stop_after_known_pages=2,
        )

        def make_card(page: int, idx: int) -> ListingCardRaw:
            return ListingCardRaw(
                source="nhatrovn",
                listing_id=f"p{page}_i{idx}",
                detail_url=f"https://nhatrovn.vn/chi-tiet/p{page}_i{idx}",
                title_raw=f"Tin P{page}-{idx}",
                price_raw="3 triệu/tháng",
                area_raw="25 m2",
                location_raw="Quận 1, TP.HCM",
                posted_at_raw="2026-08-21",
            )

        def make_meta(p: int):
            return CrawlMetadata(
                run_id=f"run_p{p}",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url=f"https://nhatrovn.vn/rooms?page={p}",
                final_url=f"https://nhatrovn.vn/rooms?page={p}",
                page_number=p,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        async def dynamic_side_effect(target, run_id, limit_per_page):
            p = target.page_number
            if p <= 55:
                cards = [make_card(p, i) for i in range(10)]
                html = f"<html><body>page {p} of 55</body></html>"
                return cards, [], make_meta(p), html
            else:
                return [], [], make_meta(p), "<html>empty</html>"

        mock_listing_exec.side_effect = dynamic_side_effect

        planner = CrawlPlanner(state_repository=self.repo)

        # -------------------------------------------------------------
        # RUN 1: Khởi tạo BOOTSTRAP_FULL (Trang 1 đến 20)
        # -------------------------------------------------------------
        plans_1 = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans_1), 1)
        plan_1 = plans_1[0]
        self.assertEqual(plan_1.mode, CrawlMode.BOOTSTRAP_FULL)
        self.assertEqual(plan_1.start_page, 1)

        runner_1 = CrawlRunner(
            target_url=plan_1.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_1, result_1 = asyncio.run(runner_1.run(plan=plan_1))

        self.assertEqual(result_1.pages_attempted, 20)
        self.assertEqual(result_1.records_created, 200)
        self.assertEqual(result_1.stop_reason, "MAX_PAGES_REACHED")
        self.assertFalse(result_1.bootstrap_completed)
        self.assertEqual(result_1.bootstrap_next_page, 21)

        # Update checkpoint sau Run 1
        state_1 = CrawlTargetState(
            source=result_1.source,
            target_id=result_1.target_id,
            last_success_at=result_1.finished_at,
            last_watermark_at=result_1.finished_at,
            last_status="success",
            last_stop_reason=result_1.stop_reason,
            last_records_created=result_1.records_created,
            bootstrap_completed=result_1.bootstrap_completed,
            bootstrap_next_page=result_1.bootstrap_next_page,
        )
        self.repo.save_state(state_1)
        self.repo.record_seen_listing_ids(result_1.source, result_1.target_id, result_1.observed_listing_ids)

        # -------------------------------------------------------------
        # RUN 2: Tiếp diễn BOOTSTRAP_CONTINUE (Trang 21 đến 40)
        # -------------------------------------------------------------
        plans_2 = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans_2), 1)
        plan_2 = plans_2[0]
        self.assertEqual(plan_2.mode, CrawlMode.BOOTSTRAP_CONTINUE)
        self.assertEqual(plan_2.reason, "BOOTSTRAP_INCOMPLETE_CONTINUATION")
        self.assertEqual(plan_2.start_page, 21)

        runner_2 = CrawlRunner(
            target_url=plan_2.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_2, result_2 = asyncio.run(runner_2.run(plan=plan_2))

        self.assertEqual(result_2.pages_attempted, 20)
        self.assertEqual(result_2.records_created, 200)
        self.assertEqual(result_2.stop_reason, "MAX_PAGES_REACHED")
        self.assertFalse(result_2.bootstrap_completed)
        self.assertEqual(result_2.bootstrap_next_page, 41)

        # Update checkpoint sau Run 2
        state_2 = CrawlTargetState(
            source=result_2.source,
            target_id=result_2.target_id,
            last_success_at=result_2.finished_at,
            last_watermark_at=result_2.finished_at,
            last_status="success",
            last_stop_reason=result_2.stop_reason,
            last_records_created=result_2.records_created,
            bootstrap_completed=result_2.bootstrap_completed,
            bootstrap_next_page=result_2.bootstrap_next_page,
        )
        self.repo.save_state(state_2)
        self.repo.record_seen_listing_ids(result_2.source, result_2.target_id, result_2.observed_listing_ids)

        # -------------------------------------------------------------
        # RUN 3: Hoàn tất BOOTSTRAP_CONTINUE (Trang 41 đến 55 -> SOURCE_END)
        # -------------------------------------------------------------
        plans_3 = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans_3), 1)
        plan_3 = plans_3[0]
        self.assertEqual(plan_3.mode, CrawlMode.BOOTSTRAP_CONTINUE)
        self.assertEqual(plan_3.start_page, 41)

        runner_3 = CrawlRunner(
            target_url=plan_3.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_3, result_3 = asyncio.run(runner_3.run(plan=plan_3))

        # Cào từ trang 41 đến 55 (15 trang có tin + 1 trang rỗng để phát hiện SOURCE_END)
        self.assertEqual(result_3.pages_attempted, 16)
        self.assertEqual(result_3.pages_success, 15)
        self.assertEqual(result_3.records_created, 150)
        self.assertEqual(result_3.stop_reason, "SOURCE_END")
        self.assertTrue(result_3.bootstrap_completed)
        self.assertIsNone(result_3.bootstrap_next_page)

        # Update checkpoint sau Run 3 (đánh dấu hoàn tất toàn bộ bootstrap)
        state_3 = CrawlTargetState(
            source=result_3.source,
            target_id=result_3.target_id,
            last_success_at=result_3.finished_at,
            last_watermark_at=result_3.finished_at,
            last_status="success",
            last_stop_reason=result_3.stop_reason,
            last_records_created=result_3.records_created,
            bootstrap_completed=result_3.bootstrap_completed,
            bootstrap_completed_at=result_3.finished_at,
            bootstrap_next_page=None,
            last_full_crawl_at=result_3.finished_at,
        )
        self.repo.save_state(state_3)
        self.repo.record_seen_listing_ids(result_3.source, result_3.target_id, result_3.observed_listing_ids)

        # Tổng số seen ids phải là 550
        seen_all = self.repo.get_seen_listing_ids("nhatrovn", "hcm_phongtro")
        self.assertEqual(len(seen_all), 550)

        # -------------------------------------------------------------
        # RUN 4: Đã hoàn tất bootstrap -> Chuyển sang INCREMENTAL
        # -------------------------------------------------------------
        plans_4 = planner.plan_all(seeds=[seed])
        self.assertEqual(len(plans_4), 1)
        plan_4 = plans_4[0]
        self.assertEqual(plan_4.mode, CrawlMode.INCREMENTAL)
        self.assertEqual(plan_4.reason, "INCREMENTAL_SCHEDULED_DUE")
        self.assertEqual(plan_4.start_page, 1)

        runner_4 = CrawlRunner(
            target_url=plan_4.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_4, result_4 = asyncio.run(runner_4.run(plan=plan_4))

        # Dừng sớm sau 2 trang liên tiếp đã biết
        self.assertEqual(result_4.pages_attempted, 2)
        self.assertEqual(result_4.stop_reason, "KNOWN_REGION_REACHED")
        self.assertEqual(result_4.records_created, 0)
        self.assertIsNone(result_4.bronze_path)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_max_records_reached_does_not_mark_bootstrap_completed(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm thử: Dừng do MAX_RECORDS_REACHED không được đánh dấu bootstrap_completed = True."""
        def make_card(page: int, idx: int) -> ListingCardRaw:
            return ListingCardRaw(
                source="phongtro123",
                listing_id=f"pt123_p{page}_i{idx}",
                detail_url=f"https://phongtro123.com/item/p{page}_i{idx}",
                title_raw=f"Tin {page}-{idx}",
                price_raw="4 triệu/tháng",
                area_raw="30 m2",
                location_raw="Quận Bình Thạnh, TP.HCM",
                posted_at_raw="2026-08-21",
            )

        def make_meta(p: int):
            return CrawlMetadata(
                run_id="run_max_rec",
                source="phongtro123",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url=f"https://phongtro123.com/rooms?page={p}",
                final_url=f"https://phongtro123.com/rooms?page={p}",
                page_number=p,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        async def dynamic_side_effect(target, run_id, limit_per_page):
            p = target.page_number
            cards = [make_card(p, i) for i in range(10)]
            html = f"<html><body>page {p} of 100</body></html>"
            return cards, [], make_meta(p), html

        mock_listing_exec.side_effect = dynamic_side_effect

        plan = CrawlPlan(
            source="phongtro123",
            target_id="hcm_phongtro",
            target_url="https://phongtro123.com/cho-thue-phong-tro-ho-chi-minh",
            mode=CrawlMode.BOOTSTRAP_FULL,
            reason="FIRST_SUCCESSFUL_CRAWL_NOT_FOUND",
            planned_at="2026-08-21T12:00:00",
            safety_max_pages=50,
            safety_max_records=25,  # 25 records limit
            crawl_details=False,
        )

        runner = CrawlRunner(
            target_url=plan.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records, result = asyncio.run(runner.run(plan=plan))

        # 3 trang hoàn chỉnh x 10 records = 30 records (không bị cắt vụn giữa chừng)
        self.assertEqual(result.records_created, 30)
        self.assertEqual(result.pages_attempted, 3)
        self.assertEqual(result.stop_reason, "MAX_RECORDS_REACHED")
        self.assertFalse(result.bootstrap_completed)
        self.assertEqual(result.bootstrap_next_page, 4)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_boundary_page_records_not_skipped_on_max_records_limit(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm thử hồi quy: Khi đạt max_records, toàn bộ các thẻ tin trên trang biên (boundary page)
        được xử lý trọn vẹn, không bị bỏ sót khi tiếp tục chặng sau từ current_page + 1.
        """
        def make_card(page: int, idx: int) -> ListingCardRaw:
            return ListingCardRaw(
                source="phongtro123",
                listing_id=f"item_p{page}_{idx}",
                detail_url=f"https://phongtro123.com/item/p{page}_{idx}",
                title_raw=f"Tin P{page}-{idx}",
                price_raw="3.5 triệu/tháng",
                area_raw="28 m2",
                location_raw="Quận 3, TP.HCM",
                posted_at_raw="2026-08-21",
            )

        def make_meta(p: int):
            return CrawlMetadata(
                run_id=f"run_boundary_p{p}",
                source="phongtro123",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url=f"https://phongtro123.com/rooms?page={p}",
                final_url=f"https://phongtro123.com/rooms?page={p}",
                page_number=p,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=200,
                content_type="text/html",
                server="nginx",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.SUCCESS,
            )

        # Giả lập nguồn có 3 trang, mỗi trang 10 tin = 30 tin
        async def boundary_side_effect(target, run_id, limit_per_page):
            p = target.page_number
            if p <= 3:
                cards = [make_card(p, i) for i in range(10)]
                return cards, [], make_meta(p), f"<html>page {p}</html>"
            return [], [], make_meta(p), "<html>empty</html>"

        mock_listing_exec.side_effect = boundary_side_effect

        # CHẶNG 1: safety_max_records = 15
        # Trang 1 có 10 tin -> total 10 < 15
        # Trang 2 có 10 tin -> total 20 >= 15 -> Hoàn tất cả 10 tin trang 2, dừng MAX_RECORDS_REACHED
        plan_1 = CrawlPlan(
            source="phongtro123",
            target_id="hcm_phongtro",
            target_url="https://phongtro123.com/cho-thue-phong-tro-ho-chi-minh",
            mode=CrawlMode.BOOTSTRAP_FULL,
            reason="FIRST_SUCCESSFUL_CRAWL_NOT_FOUND",
            planned_at="2026-08-21T12:00:00",
            safety_max_pages=50,
            safety_max_records=15,
            crawl_details=False,
            start_page=1,
        )

        runner_1 = CrawlRunner(
            target_url=plan_1.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_1, result_1 = asyncio.run(runner_1.run(plan=plan_1))

        # Phải thu thập đủ 20 tin (10 trang 1 + 10 trang 2), không bị cắt ở tin 15
        self.assertEqual(result_1.records_created, 20)
        self.assertEqual(result_1.pages_attempted, 2)
        self.assertEqual(result_1.stop_reason, "MAX_RECORDS_REACHED")
        self.assertFalse(result_1.bootstrap_completed)
        self.assertEqual(result_1.bootstrap_next_page, 3)

        # Lưu checkpoint chặng 1
        state_1 = CrawlTargetState(
            source="phongtro123",
            target_id="hcm_phongtro",
            last_success_at=result_1.finished_at,
            last_status="success",
            last_stop_reason=result_1.stop_reason,
            last_records_created=result_1.records_created,
            bootstrap_completed=False,
            bootstrap_next_page=3,
        )
        self.repo.save_state(state_1)
        self.repo.record_seen_listing_ids("phongtro123", "hcm_phongtro", result_1.observed_listing_ids)

        # CHẶNG 2: Tiếp diễn từ trang 3
        plan_2 = CrawlPlan(
            source="phongtro123",
            target_id="hcm_phongtro",
            target_url="https://phongtro123.com/cho-thue-phong-tro-ho-chi-minh",
            mode=CrawlMode.BOOTSTRAP_CONTINUE,
            reason="BOOTSTRAP_INCOMPLETE_CONTINUATION",
            planned_at="2026-08-21T12:30:00",
            safety_max_pages=50,
            safety_max_records=100,
            crawl_details=False,
            start_page=3,
        )

        runner_2 = CrawlRunner(
            target_url=plan_2.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records_2, result_2 = asyncio.run(runner_2.run(plan=plan_2))

        # Trang 3 thu thập 10 tin còn lại
        self.assertEqual(result_2.records_created, 10)
        self.assertEqual(result_2.stop_reason, "SOURCE_END")
        self.assertTrue(result_2.bootstrap_completed)

        self.repo.record_seen_listing_ids("phongtro123", "hcm_phongtro", result_2.observed_listing_ids)

        # Xác thực: Tổng 30 tin duy nhất được nạp đầy đủ vào seen_ids, 0 tin bị mất
        all_seen = self.repo.get_seen_listing_ids("phongtro123", "hcm_phongtro")
        self.assertEqual(len(all_seen), 30)
        expected_ids = {f"item_p{p}_{i}" for p in (1, 2, 3) for i in range(10)}
        self.assertEqual(set(all_seen), expected_ids)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_failure_during_continuation_preserves_previous_checkpoint(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm thử: Thất bại kỹ thuật giữa chặng không làm mất vị trí tiếp diễn hợp lệ đã lưu."""
        # Giả lập state đã commit từ Run 1: next_page = 21, bootstrap_completed = False
        initial_state = CrawlTargetState(
            source="nhatrovn",
            target_id="hcm_phongtro",
            last_success_at="2026-08-21T10:00:00+00:00",
            last_status="success",
            last_stop_reason="MAX_PAGES_REACHED",
            bootstrap_completed=False,
            bootstrap_next_page=21,
        )
        self.repo.save_state(initial_state)

        from roombeacon_crawler.services.crawl_planner import CrawlPlanner
        from roombeacon_crawler.models.crawl_seed import CrawlSeed

        seed = CrawlSeed(
            source="nhatrovn",
            target_id="hcm_phongtro",
            url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
            bootstrap_safety_max_pages=20,
        )
        planner = CrawlPlanner(state_repository=self.repo)
        plans = planner.plan_all(seeds=[seed])
        plan = plans[0]
        self.assertEqual(plan.mode, CrawlMode.BOOTSTRAP_CONTINUE)
        self.assertEqual(plan.start_page, 21)

        # Giả lập trang 21 gặp lỗi Access Challenge / Connection Error
        def make_error_meta(p: int):
            return CrawlMetadata(
                run_id="run_err",
                source="nhatrovn",
                target_type=CrawlTargetType.LISTING_PAGE,
                request_url=f"https://nhatrovn.vn/rooms?page={p}",
                final_url=f"https://nhatrovn.vn/rooms?page={p}",
                page_number=p,
                fetch_strategy=FetchStrategy.HTTP,
                http_status=403,
                content_type="text/html",
                server="cloudflare",
                cf_ray=None,
                html_size=1000,
                started_at="2026-08-21T12:00:00",
                finished_at="2026-08-21T12:00:01",
                elapsed_ms=100.0,
                retry_count=0,
                robots_allowed=True,
                crawl_status=CrawlStatus.ACCESS_DENIED,
            )

        async def error_side_effect(target, run_id, limit_per_page):
            return [], [], make_error_meta(target.page_number), "<html>403 Forbidden</html>"

        mock_listing_exec.side_effect = error_side_effect

        runner = CrawlRunner(
            target_url=plan.target_url,
            storage_writer=self.writer,
            state_repository=self.repo,
        )
        records, result = asyncio.run(runner.run(plan=plan))

        self.assertFalse(result.bootstrap_completed)
        self.assertEqual(result.status, CrawlStatus.ACCESS_DENIED)

        # Kiểm tra: Khi Airflow update_checkpoint ghi nhận access challenge, bootstrap_next_page cũ vẫn được bảo toàn (không bị ghi đè thành None hay sai lệch)
        saved_state = self.repo.get_state("nhatrovn", "hcm_phongtro")
        self.assertFalse(saved_state.bootstrap_completed)
        self.assertEqual(saved_state.bootstrap_next_page, 21)


if __name__ == "__main__":
    unittest.main()
