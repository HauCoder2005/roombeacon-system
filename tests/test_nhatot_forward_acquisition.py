import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import LocalStorageWriter
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.policies.robots_policy import (
    CachedRobotsEntry,
    RobotsDocument,
    RobotsPolicy,
)
from roombeacon_crawler.repositories.local_crawl_state_repository import LocalCrawlStateRepository
from roombeacon_crawler.services.crawl_planner import CrawlPlanner
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.sources.nhatot.parsers.detail_parser import NhatotDetailParser
from roombeacon_crawler.sources.nhatot.parsers.listing_parser import NhatotListingParser


class TestNhatotForwardOnlyAcquisition(unittest.TestCase):
    """Bộ kiểm thử xác thực quy trình thu thập dữ liệu Forward-Only cho Nhà Tốt (NhaTot)."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.state_dir = os.path.join(self.temp_dir, "state")
        self.bronze_dir = os.path.join(self.temp_dir, "bronze")
        self.manifest_dir = os.path.join(self.temp_dir, "manifests")
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.bronze_dir, exist_ok=True)
        os.makedirs(self.manifest_dir, exist_ok=True)

        self.state_repo = LocalCrawlStateRepository(base_data_dir=self.temp_dir)
        self.storage_writer = LocalStorageWriter(base_data_dir=self.temp_dir)
        self.planner = CrawlPlanner(state_repository=self.state_repo)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_nhatot_forward_only_planning_semantics(self) -> None:
        """Kiểm tra CrawlPlanner chọn FORWARD_ONLY_INCREMENTAL cho NhaTot với safety_max_pages=1."""
        seed = CrawlSeed(
            source="nhatot",
            target_id="hcm_phongtro",
            url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            enabled=True,
            interval_minutes=60,
        )

        plans = self.planner.plan_all([seed])
        self.assertEqual(len(plans), 1)
        plan = plans[0]

        self.assertEqual(plan.mode, CrawlMode.FORWARD_ONLY_INCREMENTAL)
        self.assertEqual(plan.reason, "FORWARD_ONLY_SEED_ACQUISITION")
        self.assertEqual(plan.safety_max_pages, 1)
        self.assertEqual(plan.start_page, 1)

    def test_pagination_forbidden_by_robots_never_fetches_network(self) -> None:
        """Kiểm tra đường dẫn ?page=2 bị robots.txt cấm và tuyệt đối không gửi request mạng."""
        policy = RobotsPolicy()
        nhatot_robots_txt = """User-agent: *
Disallow: /*page=
Allow: /
"""
        policy._cache["www.nhatot.com"] = CachedRobotsEntry(
            document=RobotsDocument.parse_text(nhatot_robots_txt),
            robots_state="OK",
            http_status=200,
            final_robots_url="https://www.nhatot.com/robots.txt",
            error_reason=None,
            cached_at=time.time(),
            ttl_seconds=3600.0,
        )

        # 1. Landing category seed -> Cho phép
        res_landing = policy.evaluate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh")
        self.assertEqual(res_landing.decision, "ALLOWED")

        # 2. Phân trang ?page=2 -> Bị cấm bởi Disallow: /*page=
        res_page2 = policy.evaluate("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2")
        self.assertEqual(res_page2.decision, "DENIED")
        self.assertEqual(res_page2.matched_rule, "Disallow: /*page=")
        self.assertFalse(policy.is_allowed("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh?page=2"))

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_first_and_second_run_deduplication_lifecycle(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm tra vòng đời thu thập:
        - Lần 1: Nhận 2 cards mới -> Phát sinh 2 Bronze records trên filesystem.
        - Lần 2 (giữ nguyên seen state): Nhận 2 cards cũ -> records_new=0, bronze_path=None, không tạo file bronze.
        - Lần 3: Nhận 1 card cũ + 1 card mới -> Chỉ tạo Bronze cho 1 card mới.
        """
        card_1 = ListingCardRaw(
            source="nhatot",
            listing_id="nt_1001",
            title_raw="Phòng trọ Quận 1",
            price_raw="5 triệu/tháng",
            area_raw="20 m2",
            location_raw="Quận 1",
            posted_at_raw="Hôm nay",
            detail_url="https://www.nhatot.com/phong-tro-1001.htm",
            page_number=1,
            card_position=1,
        )
        card_2 = ListingCardRaw(
            source="nhatot",
            listing_id="nt_1002",
            title_raw="Phòng trọ Bình Thạnh",
            price_raw="4 triệu/tháng",
            area_raw="25 m2",
            location_raw="Bình Thạnh",
            posted_at_raw="Hôm qua",
            detail_url="https://www.nhatot.com/phong-tro-1002.htm",
            page_number=1,
            card_position=2,
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        dummy_meta = CrawlMetadata(
            run_id="test_run",
            source="nhatot",
            target_type=CrawlTargetType.LISTING_PAGE,
            request_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            final_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            page_number=1,
            fetch_strategy=FetchStrategy.BROWSER,
            http_status=200,
            content_type="text/html",
            server=None,
            cf_ray=None,
            html_size=1024,
            started_at=now_iso,
            finished_at=now_iso,
            elapsed_ms=100.0,
            retry_count=0,
            robots_allowed=True,
            crawl_status=CrawlStatus.SUCCESS,
        )

        # LẦN 1: 2 cards mới
        mock_listing_exec.return_value = ([card_1, card_2], [], dummy_meta, "<html>valid</html>")

        runner1 = CrawlRunner(
            target_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            state_repository=self.state_repo,
            storage_writer=self.storage_writer,
        )

        records1, result1 = asyncio.run(
            runner1.run(crawl_details=False)
        )

        self.assertEqual(result1.records_seen, 2)
        self.assertEqual(result1.records_new, 2)
        self.assertEqual(result1.records_known, 0)
        self.assertEqual(result1.records_created, 2)
        self.assertIsNotNone(result1.bronze_path)
        self.assertTrue(Path(result1.bronze_path).exists())
        self.assertEqual(result1.stop_reason, "FORWARD_SCAN_COMPLETE")
        self.assertEqual(result1.pages_attempted, 1)
        self.assertEqual(result1.pages_success, 1)

        # Cập nhật danh sách seen IDs vào state repository như Airflow update_checkpoint thực hiện
        self.state_repo.record_seen_listing_ids("nhatot", "default", result1.observed_listing_ids)

        # LẦN 2: Cùng 2 cards cũ trên seed page -> records_new=0, không tạo Bronze dataset
        mock_listing_exec.return_value = ([card_1, card_2], [], dummy_meta, "<html>valid</html>")

        runner2 = CrawlRunner(
            target_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            state_repository=self.state_repo,
            storage_writer=self.storage_writer,
        )

        records2, result2 = asyncio.run(
            runner2.run(crawl_details=False)
        )

        self.assertEqual(result2.records_seen, 2)
        self.assertEqual(result2.records_new, 0)
        self.assertEqual(result2.records_known, 2)
        self.assertEqual(result2.records_created, 0)
        self.assertIsNone(result2.bronze_path)
        self.assertEqual(result2.stop_reason, "FORWARD_SCAN_COMPLETE")
        self.assertEqual(result2.pages_attempted, 1)
        self.assertEqual(result2.pages_success, 1)

        # LẦN 3: Xuất hiện 1 card mới nt_1003 và 1 card cũ nt_1001
        card_3 = ListingCardRaw(
            source="nhatot",
            listing_id="nt_1003",
            title_raw="Phòng trọ mới Quận 3",
            price_raw="6 triệu/tháng",
            area_raw="30 m2",
            location_raw="Quận 3",
            posted_at_raw="Vừa xong",
            detail_url="https://www.nhatot.com/phong-tro-1003.htm",
            page_number=1,
            card_position=1,
        )
        mock_listing_exec.return_value = ([card_3, card_1], [], dummy_meta, "<html>valid</html>")

        runner3 = CrawlRunner(
            target_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            state_repository=self.state_repo,
            storage_writer=self.storage_writer,
        )

        records3, result3 = asyncio.run(
            runner3.run(crawl_details=False)
        )

        self.assertEqual(result3.records_seen, 2)
        self.assertEqual(result3.records_new, 1)
        self.assertEqual(result3.records_known, 1)
        self.assertEqual(result3.records_created, 1)
        self.assertEqual(records3[0].listing_id, "nt_1003")
        self.assertIsNotNone(result3.bronze_path)
        self.assertEqual(result3.stop_reason, "FORWARD_SCAN_COMPLETE")
        self.assertEqual(result3.pages_attempted, 1)
        self.assertEqual(result3.pages_success, 1)
        self.assertTrue(Path(result3.bronze_path).exists())

    def test_nhatot_detail_parser_isolates_recommendations(self) -> None:
        """Kiểm tra Detail Parser chỉ bóc tách 1 ListingDetailRaw duy nhất và không biến related cards thành primary listings."""
        html_with_recommendations = """
        <html>
            <title>Cho thuê phòng trọ Quận 10</title>
            <div class="ad-price">4.5 triệu/tháng</div>
            <div class="ad-size">25 m2</div>
            <div class="ad-description">Phòng đẹp đầy đủ tiện nghi</div>
            <div class="recommended-ads">
                <a href="/phong-tro-rec1.htm">Tin liên quan 1</a>
                <a href="/phong-tro-rec2.htm">Tin liên quan 2</a>
            </div>
        </html>
        """
        parser = NhatotDetailParser(source_name="nhatot")
        detail = parser.parse(
            html=html_with_recommendations,
            detail_url="https://www.nhatot.com/phong-tro-main.htm",
            listing_id="nt_main",
        )

        self.assertIsNotNone(detail)
        self.assertEqual(detail.listing_id, "nt_main")
        self.assertEqual(detail.price_raw, "4.5 triệu/tháng")
        self.assertIsInstance(detail, ListingDetailRaw)

    @patch("roombeacon_crawler.pipeline.listing_crawl.ListingCrawlPipeline.execute")
    def test_forward_only_no_pagination_called_and_no_page_2_constructed(
        self, mock_listing_exec: AsyncMock
    ) -> None:
        """Kiểm tra chế độ FORWARD_ONLY_INCREMENTAL:
        - Fetch seed đúng 1 lần.
        - Parser thực thi.
        - Tuyệt đối không gọi has_next_page() hay build_page_url(page_number >= 2).
        - Không tạo/gửi URL ?page=2.
        - Kết thúc với status SUCCESS và stop_reason FORWARD_SCAN_COMPLETE.
        """
        card = ListingCardRaw(
            source="nhatot",
            listing_id="nt_seed_01",
            title_raw="Phòng trọ Seed Test",
            price_raw="3.5 triệu/tháng",
            area_raw="20 m2",
            location_raw="Quận 7",
            posted_at_raw="Hôm nay",
            detail_url="https://www.nhatot.com/phong-tro-seed-01.htm",
            page_number=1,
            card_position=1,
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        dummy_meta = CrawlMetadata(
            run_id="test_forward_run",
            source="nhatot",
            target_type=CrawlTargetType.LISTING_PAGE,
            request_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            final_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            page_number=1,
            fetch_strategy=FetchStrategy.BROWSER,
            http_status=200,
            content_type="text/html",
            server=None,
            cf_ray=None,
            html_size=1024,
            started_at=now_iso,
            finished_at=now_iso,
            elapsed_ms=100.0,
            retry_count=0,
            robots_allowed=True,
            crawl_status=CrawlStatus.SUCCESS,
        )
        mock_listing_exec.return_value = ([card], [], dummy_meta, "<html>valid</html>")

        runner = CrawlRunner(
            target_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
            state_repository=self.state_repo,
            storage_writer=self.storage_writer,
        )

        with patch.object(runner.adapter.pagination, "has_next_page", wraps=runner.adapter.pagination.has_next_page) as spy_has_next, \
             patch.object(runner.adapter.pagination, "build_page_url", wraps=runner.adapter.pagination.build_page_url) as spy_build_url:

            plan = CrawlPlan(
                source="nhatot",
                target_id="default",
                target_url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
                mode=CrawlMode.FORWARD_ONLY_INCREMENTAL,
                reason="FORWARD_ONLY_SEED_ACQUISITION",
                planned_at=now_iso,
            )
            records, result = asyncio.run(
                runner.run(
                    plan=plan,
                    crawl_details=False,
                )
            )

            # 1. Pipeline execute chỉ được gọi đúng 1 lần cho seed page
            self.assertEqual(mock_listing_exec.call_count, 1)
            first_call_target = mock_listing_exec.call_args_list[0].kwargs.get("target") or mock_listing_exec.call_args_list[0].args[0]
            self.assertEqual(first_call_target.url, "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh")
            self.assertNotIn("?page=2", first_call_target.url)

            # 2. Không bao giờ gọi has_next_page()
            self.assertEqual(spy_has_next.call_count, 0)

            # 3. Không bao giờ gọi build_page_url với page_number >= 2
            for call_item in spy_build_url.call_args_list:
                page_num = call_item.kwargs.get("page_number")
                if page_num is None and len(call_item.args) > 1:
                    page_num = call_item.args[1]
                if page_num is not None:
                    self.assertLessEqual(page_num, 1, f"build_page_url was illegally called for page {page_num}")

            # 4. Trạng thái kết thúc chuẩn mực
            self.assertEqual(result.status, CrawlStatus.SUCCESS)
            self.assertEqual(result.stop_reason, "FORWARD_SCAN_COMPLETE")
            self.assertEqual(result.pages_attempted, 1)
            self.assertEqual(result.pages_success, 1)
            self.assertEqual(result.pages_failed, 0)
            self.assertEqual(result.records_created, 1)
            self.assertIsNotNone(result.bronze_path)


if __name__ == "__main__":
    unittest.main()
