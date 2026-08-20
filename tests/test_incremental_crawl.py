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


if __name__ == "__main__":
    unittest.main()
