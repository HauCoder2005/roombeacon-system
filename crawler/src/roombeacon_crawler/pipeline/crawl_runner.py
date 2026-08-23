import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import time
from typing import Any

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline
from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline
from roombeacon_crawler.policies.date_cutoff_policy import DateCutoffPolicy
from roombeacon_crawler.policies.detail_refresh_policy import DetailRefreshPolicy
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.repositories.crawl_state_repository import (
    CrawlStateRepository,
)
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem
from roombeacon_crawler.repositories.deferred_detail_repository import (
    DeferredDetailRepository,
)
from roombeacon_crawler.repositories.local_deferred_detail_repository import (
    LocalDeferredDetailRepository,
)
from roombeacon_crawler.policies.deferred_budget_scheduler import (
    DeferredBudgetScheduler,
)
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.services.strategy_selector import StrategySelector
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.resolver import SourceResolver

logger = logging.getLogger(__name__)


class CrawlRunner:
    """Entrypoint chính điều phối toàn bộ chu trình crawl của RoomBeacon Crawler."""

    def __init__(
        self,
        target_url: str | None = None,
        adapter: BaseSourceAdapter | None = None,
        settings: CrawlerSettings | None = None,
        storage_writer: LocalStorageWriter | None = None,
        state_repository: CrawlStateRepository | None = None,
        deferred_repository: DeferredDetailRepository | None = None,
    ) -> None:
        self.settings = settings or CrawlerSettings()
        self.storage_writer = storage_writer or LocalStorageWriter(base_data_dir=self.settings.data_dir)
        self.state_repository = state_repository or LocalCrawlStateRepository(base_data_dir=self.settings.data_dir)
        self.deferred_repository = deferred_repository or LocalDeferredDetailRepository(base_data_dir=self.settings.data_dir)
        self.deferred_scheduler = DeferredBudgetScheduler()

        # Phân giải Adapter từ URL nếu chưa được truyền vào
        if adapter is not None:
            self.adapter = adapter
        elif target_url:
            resolved = SourceResolver.resolve(target_url)
            if resolved is None:
                raise ValueError(
                    f"Không tìm thấy adapter cho target URL: '{target_url}'"
                )
            self.adapter = resolved
        else:
            raise ValueError("Cần cung cấp target_url hoặc adapter để khởi tạo CrawlRunner")

        # Khởi tạo các thành phần cốt lõi
        self.http_fetcher = HttpFetcher(
            timeout=self.settings.request_timeout,
            user_agent=self.settings.user_agent,
        )
        self.browser_fetcher = BrowserFetcher(
            timeout=self.settings.request_timeout,
            headless=self.settings.playwright_headless,
            user_agent=self.settings.user_agent,
            viewport={"width": 1280, "height": 800},
        )
        self.rate_limit_policy = RateLimitPolicy(
            delay_seconds=self.settings.request_delay_seconds,
            max_concurrency=self.settings.max_concurrency,
        )
        self.retry_policy = RetryPolicy(
            max_retries=self.settings.max_retries,
            base_delay_seconds=self.settings.request_delay_seconds,
        )
        self.response_classifier = ResponseClassifier()
        self.robots_policy = RobotsPolicy(
            user_agent=self.settings.user_agent,
        )
        self.fetch_policy = FetchPolicy()
        self.detail_refresh_policy = DetailRefreshPolicy(
            default_ttl_hours=int(os.environ.get("DETAIL_REFRESH_TTL_HOURS", "24"))
        )

        date_from_dt = (
            datetime.fromisoformat(self.settings.date_from)
            if self.settings.date_from
            else None
        )
        date_to_dt = (
            datetime.fromisoformat(self.settings.date_to)
            if self.settings.date_to
            else None
        )

        self.date_cutoff_policy = DateCutoffPolicy(
            mode=self.settings.crawl_date_mode,
            date_from=date_from_dt,
            date_to=date_to_dt,
            max_pages_safety=1000,
        )

        self.fetch_coordinator = FetchCoordinator(
            http_fetcher=self.http_fetcher,
            browser_fetcher=self.browser_fetcher,
            strategy_selector=StrategySelector(),
            rate_limit_policy=self.rate_limit_policy,
            retry_policy=self.retry_policy,
            response_classifier=self.response_classifier,
        )

        self.listing_pipeline = ListingCrawlPipeline(
            adapter=self.adapter,
            fetch_coordinator=self.fetch_coordinator,
            robots_policy=self.robots_policy,
            fetch_policy=self.fetch_policy,
        )

        self.detail_pipeline = DetailCrawlPipeline(
            adapter=self.adapter,
            fetch_coordinator=self.fetch_coordinator,
            robots_policy=self.robots_policy,
            fetch_policy=self.fetch_policy,
        )

    @classmethod
    def execute_crawl(
        cls,
        url: str | None = None,
        plan: CrawlPlan | dict | None = None,
        max_pages: int | None = None,
        max_records: int | None = None,
        crawl_details: bool | None = None,
        max_details_per_run: int | None = None,
        start_page: int | None = None,
        settings: CrawlerSettings | None = None,
        state_repository: CrawlStateRepository | None = None,
    ) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Public synchronous application entry point cho Airflow DAGs và scripts."""
        plan_obj: CrawlPlan | None = None
        if plan is not None:
            if isinstance(plan, dict):
                plan_obj = CrawlPlan.from_dict(plan)
            else:
                plan_obj = plan
            target_url = plan_obj.target_url
        else:
            target_url = url

        if not target_url:
            raise ValueError("Cần cung cấp target_url hoặc plan")

        runner = cls(
            target_url=target_url,
            settings=settings,
            state_repository=state_repository,
        )
        return asyncio.run(
            runner.run(
                plan=plan_obj,
                max_pages=max_pages,
                max_records=max_records,
                crawl_details=crawl_details,
                max_details_per_run=max_details_per_run,
                start_page=start_page,
            )
        )

    async def run(
        self,
        plan: CrawlPlan | None = None,
        max_pages: int | None = None,
        max_records: int | None = None,
        crawl_details: bool | None = None,
        max_details_per_run: int | None = None,
        start_page: int | None = None,
    ) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Thực thi phiên crawl hoàn chỉnh theo CrawlPlan hoặc thông số trực tiếp."""
        start_time = time.perf_counter()
        now = datetime.now(timezone.utc)
        run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"
        started_at = now.isoformat()

        target_id = plan.target_id if plan else "default"
        mode = (plan.mode.value if hasattr(plan.mode, "value") else str(plan.mode)) if plan else "BOOTSTRAP_FULL"

        caps = getattr(self.adapter, "CAPABILITIES", None)
        is_forward_only = (
            mode in (
                CrawlMode.FORWARD_ONLY_INCREMENTAL.value,
                "FORWARD_ONLY_INCREMENTAL",
            )
            or (
                caps is not None
                and not getattr(caps, "historical_backfill_supported", True)
            )
            or (
                caps is not None
                and not getattr(caps, "supports_pagination", True)
            )
        )

        if is_forward_only:
            mode = CrawlMode.FORWARD_ONLY_INCREMENTAL.value
            effective_max_pages = 1
            effective_start_page = 1
            effective_max_records = (
                max_records
                if max_records is not None
                else (plan.safety_max_records if plan else self.settings.max_total_records)
            )
            effective_crawl_details = (
                crawl_details
                if crawl_details is not None
                else (plan.crawl_details if plan else True)
            )
            effective_max_details = (
                max_details_per_run
                if max_details_per_run is not None
                else (plan.max_details_per_run if plan else self.settings.max_details_per_run)
            )
            stop_after_known_pages = 1
        elif plan:
            effective_max_pages = (
                max_pages
                if max_pages is not None
                else plan.safety_max_pages
            )
            effective_max_records = (
                max_records
                if max_records is not None
                else plan.safety_max_records
            )
            effective_crawl_details = (
                crawl_details if crawl_details is not None else plan.crawl_details
            )
            effective_max_details = (
                max_details_per_run
                if max_details_per_run is not None
                else plan.max_details_per_run
            )
            stop_after_known_pages = plan.incremental_stop_after_known_pages
            effective_start_page = start_page if start_page is not None else getattr(plan, "start_page", 1)
        else:
            effective_max_pages = (
                max_pages if max_pages is not None else self.settings.max_pages
            )
            effective_max_records = (
                max_records
                if max_records is not None
                else self.settings.max_total_records
            )
            effective_crawl_details = (
                crawl_details if crawl_details is not None else True
            )
            effective_max_details = (
                max_details_per_run
                if max_details_per_run is not None
                else self.settings.max_details_per_run
            )
            stop_after_known_pages = 2
            effective_start_page = start_page if start_page is not None else 1

        logger.info("=" * 60)
        logger.info("BẮT ĐẦU PHIÊN CRAWL: %s", run_id)
        logger.info("Target URL          : %s", self.adapter.base_url)
        logger.info("Source Name         : %s", self.adapter.SOURCE_NAME)
        logger.info("Target ID           : %s", target_id)
        logger.info("Crawl Mode          : %s", mode)
        logger.info("Start Page          : %d", effective_start_page)
        logger.info("Max Pages (Run)     : %d", effective_max_pages)
        logger.info("Max Records (Total) : %d", effective_max_records)
        logger.info("Crawl Details       : %s", effective_crawl_details)
        logger.info("Max Details per Run : %s", effective_max_details)
        logger.info("Stop After Known Pgs: %d", stop_after_known_pages)
        logger.info("=" * 60)

        # 0. Phân loại loại URL mục tiêu (Target Classification)
        target_type = self.adapter.classify_url(self.adapter.base_url)
        if target_type == CrawlTargetType.UNSUPPORTED:
            logger.warning(
                "Target URL '%s' không thuộc danh mục tin đăng hợp lệ của nguồn '%s'",
                self.adapter.base_url,
                self.adapter.SOURCE_NAME,
            )
            finished_at = datetime.now(timezone.utc).isoformat()
            result = CrawlRunResult(
                run_id=run_id,
                source=self.adapter.SOURCE_NAME,
                target_id=target_id,
                mode=mode,
                target_url=self.adapter.base_url,
                started_at=started_at,
                finished_at=finished_at,
                status=CrawlStatus.UNSUPPORTED_TARGET,
                stop_reason=CrawlStatus.UNSUPPORTED_TARGET,
                failure_reason=f"URL không thuộc danh mục phòng trọ hợp lệ của nguồn {self.adapter.SOURCE_NAME}",
                max_pages=effective_max_pages,
                max_records=effective_max_records,
                crawl_details=effective_crawl_details,
                pages_success=0,
                pages_failed=0,
                details_success=0,
                details_failed=0,
                records_created=0,
                duplicates_skipped=0,
                errors=[
                    f"Unsupported target URL pattern: {self.adapter.base_url}"
                ],
            )
            manifest_file = self.storage_writer.save_manifest(result)
            result.manifest_path = manifest_file
            return [], result

        return await self._run_async(
            run_id=run_id,
            started_at=started_at,
            start_time=start_time,
            target_id=target_id,
            mode=mode,
            effective_max_pages=effective_max_pages,
            effective_max_records=effective_max_records,
            crawl_details=effective_crawl_details,
            max_details_per_run=effective_max_details,
            stop_after_known_pages=stop_after_known_pages,
            start_page=effective_start_page,
        )

    @staticmethod
    def _extract_listing_identity(card: ListingCardRaw) -> str:
        """Trích xuất định danh duy nhất ổn định cho listing card: (source, source_listing_id) hoặc fallback canonical URL."""
        if card.listing_id and str(card.listing_id).strip():
            return str(card.listing_id).strip()
        if card.detail_url and str(card.detail_url).strip():
            return str(card.detail_url).strip()
        return f"{card.source}_pos_{card.card_position}_p_{card.page_number}"

    async def _run_async(
        self,
        run_id: str,
        started_at: str,
        start_time: float,
        target_id: str,
        mode: str,
        effective_max_pages: int,
        effective_max_records: int,
        crawl_details: bool,
        max_details_per_run: int,
        stop_after_known_pages: int,
        start_page: int = 1,
    ) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Thực thi chu trình crawl bất đồng bộ với cơ chế phân trang gia tăng và tiếp diễn bootstrap."""
        now = datetime.now(timezone.utc)
        all_bronze_records: list[RentalBronzeRecord] = []
        all_detail_records: list[ListingDetailRaw] = []
        all_metadata: list[CrawlMetadata] = []

        observed_listing_ids: list[str] = []
        new_listing_ids: list[str] = []
        seen_in_current_run: set[str] = set()

        # Tải danh sách listing_id đã từng thấy cho target này từ State Repository
        if hasattr(self.state_repository, "get_seen_metadata"):
            known_seen_meta = self.state_repository.get_seen_metadata(
                self.adapter.SOURCE_NAME, target_id
            )
        else:
            known_seen_meta = {
                lid: {"last_detailed_at": None, "card_fingerprint": None}
                for lid in self.state_repository.get_seen_listing_ids(
                    self.adapter.SOURCE_NAME, target_id
                )
            }
        known_seen_ids = set(known_seen_meta.keys())
        updated_seen_meta: dict[str, dict] = {}
        records_changed = 0
        detail_requests_forced_by_change = 0

        detail_required = 0
        detail_requested = 0
        detail_succeeded = 0
        detail_failed = 0
        detail_skipped = 0

        skipped_known_unchanged_ttl = 0
        skipped_no_detail_url = 0
        skipped_request_budget = 0
        skipped_source_policy = 0
        skipped_other = 0

        logger.info(
            "State Repository: Đã nạp %d known listing_ids cho %s/%s",
            len(known_seen_ids),
            self.adapter.SOURCE_NAME,
            target_id,
        )

        caps = getattr(self.adapter, "CAPABILITIES", None)
        is_forward_only = (
            mode in (
                CrawlMode.FORWARD_ONLY_INCREMENTAL.value,
                "FORWARD_ONLY_INCREMENTAL",
            )
            or (
                caps is not None
                and not getattr(caps, "historical_backfill_supported", True)
            )
            or (
                caps is not None
                and not getattr(caps, "supports_pagination", True)
            )
        )

        if is_forward_only:
            mode = CrawlMode.FORWARD_ONLY_INCREMENTAL.value
            is_incremental = False
            is_bootstrap = False
            effective_max_pages = 1
            effective_start_page = 1
            effective_end_page = 1
            current_page = 1
        else:
            is_incremental = mode in (
                CrawlMode.INCREMENTAL.value,
                CrawlMode.FORCE_INCREMENTAL.value,
            )
            is_bootstrap = mode in (
                CrawlMode.BOOTSTRAP_FULL.value,
                CrawlMode.BOOTSTRAP_CONTINUE.value,
                CrawlMode.FORCE_FULL.value,
            )
            current_page = start_page if is_bootstrap else 1
            effective_end_page = (start_page + effective_max_pages - 1) if is_bootstrap else effective_max_pages

        bootstrap_completed = False
        bootstrap_next_page: int | None = None

        pages_attempted = 0
        pages_success = 0
        pages_failed = 0
        details_success = 0
        details_failed = 0
        duplicates_skipped = 0
        details_crawled_count = 0
        known_page_streak = 0
        final_status = CrawlStatus.SUCCESS
        stop_reason: str | CrawlStatus | None = None
        failure_reason: str | None = None
        errors: list[str] = []

        # Khởi tạo metrics cho Deferred Detail Backlog
        deferred_backlog_before = (
            self.deferred_repository.count_backlog(self.adapter.SOURCE_NAME, target_id)
            if hasattr(self.deferred_repository, "count_backlog")
            else 0
        )
        deferred_added = 0
        deferred_attempted = 0
        deferred_succeeded = 0
        deferred_failed = 0
        deferred_terminal = 0

        # Phase 1: Xử lý Deferred Detail Backlog theo hạn ngạch Fair Budget Scheduling
        if (
            crawl_details
            and max_details_per_run is not None
            and max_details_per_run > 0
            and deferred_backlog_before > 0
            and hasattr(self.deferred_repository, "get_backlog")
        ):
            allocation = self.deferred_scheduler.allocate(
                total_budget=max_details_per_run,
                deferred_pending_count=deferred_backlog_before,
            )
            deferred_quota = allocation.deferred_quota
            logger.info(
                "Fair Budget Scheduling: Total=%d | Deferred Quota=%d (Backlog: %d) | Immediate Quota=%d",
                max_details_per_run,
                deferred_quota,
                deferred_backlog_before,
                allocation.immediate_quota,
            )

            backlog_items = self.deferred_repository.get_backlog(
                self.adapter.SOURCE_NAME, target_id
            )[:deferred_quota]

            for b_item in backlog_items:
                deferred_attempted += 1
                det_target = CrawlTarget(
                    url=b_item.detail_url,
                    source=self.adapter.SOURCE_NAME,
                    target_type=CrawlTargetType.DETAIL_PAGE,
                )
                fake_card = ListingCardRaw(
                    source=self.adapter.SOURCE_NAME,
                    listing_id=b_item.platform_post_id,
                    detail_url=b_item.detail_url,
                    title_raw=b_item.card_title or "",
                    price_raw=b_item.card_price,
                    area_raw=b_item.card_area,
                    location_raw=b_item.card_location,
                    posted_at_raw=None,
                    crawl_run_id=run_id,
                )
                det_bronze, det_raw, det_meta = await self.detail_pipeline.execute(
                    target=det_target,
                    card=fake_card,
                    run_id=run_id,
                )
                all_metadata.append(det_meta)

                if det_raw is not None:
                    deferred_succeeded += 1
                    all_detail_records.append(det_raw)
                    self.deferred_repository.record_success(
                        self.adapter.SOURCE_NAME, target_id, b_item.platform_post_id
                    )
                    updated_seen_meta[b_item.platform_post_id] = {
                        "last_detailed_at": now.isoformat(),
                        "card_fingerprint": b_item.card_fingerprint,
                    }
                    if det_bronze is not None:
                        all_bronze_records.append(det_bronze)
                else:
                    deferred_failed += 1
                    status_code = getattr(det_meta, "status_code", None)
                    is_term = status_code in (404, 410)
                    self.deferred_repository.record_failure(
                        self.adapter.SOURCE_NAME,
                        target_id,
                        b_item.platform_post_id,
                        error=f"HTTP status {status_code}",
                        is_terminal=is_term,
                    )
                    if is_term:
                        deferred_terminal += 1

            details_crawled_count += deferred_attempted

        while current_page <= effective_end_page:
            if is_forward_only:
                page_url = self.adapter.base_url
            else:
                page_url = self.adapter.pagination.build_page_url(
                    base_url=self.adapter.base_url,
                    page_number=current_page,
                )

            listing_target = CrawlTarget(
                url=page_url,
                source=self.adapter.SOURCE_NAME,
                target_type=CrawlTargetType.LISTING_PAGE,
                page_number=current_page,
            )

            logger.info(
                "--- [Trang %d/%d] Đang crawl listing: %s ---",
                current_page,
                effective_end_page,
                page_url,
            )
            cards, detail_targets, meta, raw_html = (
                await self.listing_pipeline.execute(
                    target=listing_target,
                    run_id=run_id,
                    limit_per_page=self.settings.max_records_per_page,
                )
            )
            all_metadata.append(meta)

            if meta.crawl_status == CrawlStatus.ROBOTS_DENIED:
                logger.warning(
                    "Crawl stopped by robots policy. Target was not fetched. No robots bypass was attempted. URL: %s",
                    page_url,
                )
                final_status = CrawlStatus.ROBOTS_DENIED
                stop_reason = CrawlStatus.ROBOTS_DENIED
                if is_bootstrap:
                    bootstrap_completed = False
                    bootstrap_next_page = current_page
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : ROBOTS_DENIED")
                logger.info("Current Page        : %d", current_page)
                logger.info("=" * 60)
                break

            # Fetch attempt was made over the wire
            pages_attempted += 1

            if not cards:
                if meta.crawl_status in (
                    CrawlStatus.ACCESS_DENIED,
                    CrawlStatus.CLOUDFLARE_CHALLENGE,
                ):
                    pages_failed += 1
                    final_status = meta.crawl_status
                    stop_reason = meta.crawl_status
                    if is_bootstrap:
                        bootstrap_completed = False
                        bootstrap_next_page = current_page
                    logger.warning(
                        "Controlled stop triggered by access policy/challenge: %s",
                        meta.crawl_status.value,
                    )
                    logger.info("=" * 60)
                    logger.info("PAGINATION STOP")
                    logger.info(
                        "Reason              : ACCESS_CHALLENGE (%s)",
                        meta.crawl_status.value,
                    )
                    logger.info("Current Page        : %d", current_page)
                    logger.info("=" * 60)
                    break
                elif meta.crawl_status in (
                    CrawlStatus.CONNECTION_ERROR,
                    CrawlStatus.SERVER_ERROR,
                    CrawlStatus.TIMEOUT,
                    CrawlStatus.PARSE_ERROR,
                ):
                    pages_failed += 1
                    final_status = meta.crawl_status
                    failure_reason = (
                        f"Lỗi fetch listing page: {meta.crawl_status.value}"
                    )
                    errors.append(failure_reason)
                    if is_bootstrap:
                        bootstrap_completed = False
                        bootstrap_next_page = current_page
                    logger.warning(
                        "Không lấy được card nào từ trang %d (CrawlStatus=%s)",
                        current_page,
                        meta.crawl_status.value,
                    )
                    logger.info("=" * 60)
                    logger.info("PAGINATION STOP")
                    logger.info(
                        "Reason              : FETCH_ERROR (%s)",
                        meta.crawl_status.value,
                    )
                    logger.info("Current Page        : %d", current_page)
                    logger.info("=" * 60)
                    break
                else:
                    # Trang rỗng không lỗi (hết danh mục tin từ phía nguồn)
                    logger.info("=" * 60)
                    logger.info("PAGINATION STOP")
                    logger.info("Reason              : SOURCE_END")
                    logger.info("Current Page        : %d", current_page)
                    logger.info("=" * 60)
                    stop_reason = "SOURCE_END"
                    final_status = CrawlStatus.SUCCESS
                    if is_bootstrap:
                        bootstrap_completed = True
                        bootstrap_next_page = None
                    else:
                        bootstrap_completed = True
                        bootstrap_next_page = None
                    break

            pages_success += 1
            page_records_count = len(cards)

            # Phân loại danh sách tin: NEW vs KNOWN (đã thấy trong lịch sử hoặc trong chính run này)
            page_new_count = 0
            page_known_count = 0

            for card in cards:
                lid = self._extract_listing_identity(card)
                if lid not in observed_listing_ids:
                    observed_listing_ids.append(lid)

                if lid in seen_in_current_run:
                    # Trùng lặp kỹ thuật trong cùng một run (ví dụ phân trang gối đầu) -> bỏ qua
                    page_known_count += 1
                    duplicates_skipped += 1
                    continue

                seen_in_current_run.add(lid)
                card.crawl_run_id = run_id

                # Tính toán fingerprint từ các trường nhẹ của Listing Card
                raw_fp_str = f"{card.title_raw or ''}|{card.price_raw or ''}|{card.area_raw or ''}|{card.location_raw or ''}"
                card_fp = hashlib.sha256(raw_fp_str.encode("utf-8")).hexdigest()[:16]

                is_new = (lid not in known_seen_ids)
                prev_info = known_seen_meta.get(lid, {})
                prev_fp = prev_info.get("card_fingerprint")
                last_detailed_at = prev_info.get("last_detailed_at")
                card_changed = (not is_new and prev_fp is not None and prev_fp != card_fp)

                decision = self.detail_refresh_policy.evaluate(
                    is_new=is_new,
                    card_changed=card_changed,
                    last_detailed_at=last_detailed_at,
                    current_time=now,
                )

                if is_new:
                    page_new_count += 1
                    new_listing_ids.append(lid)
                else:
                    page_known_count += 1

                if card_changed:
                    records_changed += 1

                has_detail_url = bool(card.detail_url and card.detail_url.strip())
                detail_required += 1

                if not crawl_details:
                    # Bỏ qua do chính sách nguồn/cấu hình tắt cào detail
                    detail_skipped += 1
                    skipped_source_policy += 1
                    record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                    all_bronze_records.append(record)
                    updated_seen_meta[lid] = {
                        "last_detailed_at": last_detailed_at,
                        "card_fingerprint": card_fp,
                    }
                elif not has_detail_url:
                    # Bỏ qua do không có URL chi tiết hợp lệ
                    detail_skipped += 1
                    skipped_no_detail_url += 1
                    record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                    all_bronze_records.append(record)
                    updated_seen_meta[lid] = {
                        "last_detailed_at": last_detailed_at,
                        "card_fingerprint": card_fp,
                    }
                elif not decision.should_refresh:
                    # Bỏ qua do tin đã biết và không đổi trong hạn TTL (Lightweight Observation)
                    detail_skipped += 1
                    skipped_known_unchanged_ttl += 1
                    record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                    all_bronze_records.append(record)
                    updated_seen_meta[lid] = {
                        "last_detailed_at": last_detailed_at,
                        "card_fingerprint": card_fp,
                    }
                elif (
                    max_details_per_run is not None
                    and details_crawled_count >= max_details_per_run
                ):
                    # Bỏ qua do đã chạm trần ngân sách request detail trong run (Request Budget Cap)
                    logger.info(
                        "Đã đạt giới hạn max_details_per_run (%d). Hoãn detail fetch cho %s.",
                        max_details_per_run,
                        lid,
                    )
                    detail_skipped += 1
                    skipped_request_budget += 1
                    record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                    all_bronze_records.append(record)
                    updated_seen_meta[lid] = {
                        "last_detailed_at": last_detailed_at,
                        "card_fingerprint": card_fp,
                    }
                    # Đưa vào Durable Deferred Detail Backlog để cào làm giàu ở chu kỳ sau
                    deferred_item = DeferredDetailItem(
                        source=self.adapter.SOURCE_NAME,
                        platform_post_id=lid,
                        detail_url=card.detail_url,
                        origin_run_id=run_id,
                        first_deferred_at=now.isoformat(),
                        reason="REQUEST_BUDGET_EXHAUSTED",
                        card_title=getattr(card, "title_raw", None) or getattr(card, "title", None),
                        card_price=getattr(card, "price_raw", None) or getattr(card, "price", None),
                        card_area=getattr(card, "area_raw", None) or getattr(card, "area", None),
                        card_location=getattr(card, "location_raw", None) or getattr(card, "location", None),
                        card_fingerprint=card_fp,
                    )
                    if hasattr(self.deferred_repository, "enqueue"):
                        added = self.deferred_repository.enqueue(
                            self.adapter.SOURCE_NAME, target_id, [deferred_item]
                        )
                        deferred_added += added
                else:
                    # Thực hiện network request cào trang chi tiết
                    detail_requested += 1
                    detail_target = CrawlTarget(
                        url=card.detail_url,
                        source=self.adapter.SOURCE_NAME,
                        target_type=CrawlTargetType.DETAIL_PAGE,
                    )
                    detail_bronze, detail_raw, detail_meta = (
                        await self.detail_pipeline.execute(
                            target=detail_target,
                            card=card,
                            run_id=run_id,
                        )
                    )
                    all_metadata.append(detail_meta)
                    details_crawled_count += 1
                    if card_changed:
                        detail_requests_forced_by_change += 1

                    if detail_raw is not None:
                        detail_succeeded += 1
                        all_detail_records.append(detail_raw)
                        updated_seen_meta[lid] = {
                            "last_detailed_at": now.isoformat(),
                            "card_fingerprint": card_fp,
                        }
                        if hasattr(self.deferred_repository, "record_success"):
                            self.deferred_repository.record_success(
                                self.adapter.SOURCE_NAME, target_id, lid
                            )
                    else:
                        detail_failed += 1
                        updated_seen_meta[lid] = {
                            "last_detailed_at": last_detailed_at,
                            "card_fingerprint": card_fp,
                        }

                    if detail_bronze is not None:
                        all_bronze_records.append(detail_bronze)
                    else:
                        record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                        all_bronze_records.append(record)

            if is_forward_only:
                fetch_strat = getattr(self.adapter.CAPABILITIES, "preferred_fetch_strategy", None)
                strat_name = fetch_strat.value if hasattr(fetch_strat, "value") else str(fetch_strat or "BROWSER")
                logger.info("=" * 60)
                logger.info("FORWARD-ONLY ACQUISITION COMPLETE")
                logger.info("Source          : %s", self.adapter.SOURCE_NAME)
                logger.info("Seed            : %s", self.adapter.base_url)
                logger.info("Robots          : ALLOWED")
                logger.info("Transport       : %s", strat_name)
                logger.info("Cards parsed    : %d", page_records_count)
                logger.info("Cards valid     : %d", page_records_count)
                logger.info("New             : %d", page_new_count)
                logger.info("Known           : %d", page_known_count)
                logger.info("Duplicates      : %d", duplicates_skipped)
                logger.info("Details fetched : %d", details_success)
                logger.info("Records created : %d", len(all_bronze_records))
                logger.info("=" * 60)

                stop_reason = "FORWARD_SCAN_COMPLETE"
                final_status = CrawlStatus.SUCCESS
                bootstrap_completed = False
                bootstrap_next_page = None
                break

            # Kiểm soát phân trang gia tăng (CHỈ áp dụng cho INCREMENTAL, KHÔNG áp dụng cho BOOTSTRAP)
            if is_incremental:
                effective_stop_after_known_pages = 1 if is_forward_only else stop_after_known_pages
                if page_new_count > 0:
                    # Có dữ liệu mới xuất hiện trên trang -> Reset streak về 0 ngay lập tức (chống promoted/pinned)
                    known_page_streak = 0
                    logger.info("=" * 60)
                    logger.info("INCREMENTAL PAGE %d", current_page)
                    logger.info("Records parsed : %d", page_records_count)
                    logger.info("New            : %d", page_new_count)
                    logger.info("Changed        : 0")
                    logger.info("Known          : %d", page_known_count)
                    logger.info("Known streak   : 0 (Reset by new data)")
                    logger.info("=" * 60)
                elif page_records_count > 0 and page_known_count == page_records_count:
                    # Toàn bộ thẻ tin trên trang đều là tin đã biết
                    known_page_streak += 1
                    logger.info("=" * 60)
                    logger.info("INCREMENTAL PAGE %d", current_page)
                    logger.info("Records parsed : %d", page_records_count)
                    logger.info("New            : 0")
                    logger.info("Changed        : 0")
                    logger.info("Known          : %d", page_known_count)
                    logger.info(
                        "Known streak   : %d/%d",
                        known_page_streak,
                        effective_stop_after_known_pages,
                    )
                    logger.info("=" * 60)

                    if known_page_streak >= effective_stop_after_known_pages:
                        logger.info("=" * 60)
                        logger.info("PAGINATION STOP")
                        logger.info("Reason              : KNOWN_REGION_REACHED")
                        logger.info("Current Page        : %d", current_page)
                        logger.info("Consecutive Streak  : %d", known_page_streak)
                        logger.info("=" * 60)
                        stop_reason = "KNOWN_REGION_REACHED"
                        final_status = CrawlStatus.SUCCESS
                        bootstrap_completed = False if is_forward_only else True
                        bootstrap_next_page = None
                        break
            else:
                logger.info(
                    "BOOTSTRAP PAGE %d: Parsed %d cards (New: %d, Known: %d)",
                    current_page,
                    page_records_count,
                    page_new_count,
                    page_known_count,
                )

            # Kiểm soát giới hạn an toàn số lượng bản ghi tại biên trang (Page Boundary Safety)
            if len(all_bronze_records) >= effective_max_records:
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : MAX_RECORDS_REACHED")
                logger.info("Current Page        : %d", current_page)
                logger.info("Configured Max Pages: %d", effective_max_pages)
                logger.info("Records Collected   : %d", len(all_bronze_records))
                logger.info("Configured Max Recs : %d", effective_max_records)
                logger.info("=" * 60)
                stop_reason = "MAX_RECORDS_REACHED"
                final_status = CrawlStatus.SUCCESS
                if is_bootstrap:
                    bootstrap_completed = False
                    bootstrap_next_page = current_page + 1
                else:
                    bootstrap_completed = True
                    bootstrap_next_page = None
                break

            # Kiểm tra phân trang từ phía nguồn
            has_next = self.adapter.pagination.has_next_page(
                current_page=current_page,
                max_pages=effective_end_page,
                current_items_count=page_records_count,
                raw_html=raw_html,
            )

            if not has_next:
                if current_page >= effective_end_page:
                    logger.info("=" * 60)
                    logger.info("PAGINATION STOP")
                    logger.info("Reason              : MAX_PAGES_REACHED")
                    logger.info("Current Page        : %d", current_page)
                    logger.info("Configured End Page : %d", effective_end_page)
                    logger.info("=" * 60)
                    stop_reason = "MAX_PAGES_REACHED"
                    final_status = CrawlStatus.SUCCESS
                    if is_bootstrap:
                        bootstrap_completed = False
                        bootstrap_next_page = current_page + 1
                    else:
                        bootstrap_completed = True
                        bootstrap_next_page = None
                else:
                    logger.info("=" * 60)
                    logger.info("PAGINATION STOP")
                    logger.info("Reason              : SOURCE_END")
                    logger.info("Current Page        : %d", current_page)
                    logger.info("Configured End Page : %d", effective_end_page)
                    logger.info("=" * 60)
                    stop_reason = "SOURCE_END"
                    final_status = CrawlStatus.SUCCESS
                    if is_bootstrap:
                        bootstrap_completed = True
                        bootstrap_next_page = None
                    else:
                        bootstrap_completed = True
                        bootstrap_next_page = None
                break

            current_page += 1

        if stop_reason is None and current_page > effective_end_page:
            if is_forward_only:
                stop_reason = "FORWARD_SCAN_COMPLETE"
                bootstrap_completed = False
                bootstrap_next_page = None
            elif is_bootstrap:
                stop_reason = "MAX_PAGES_REACHED"
                bootstrap_completed = False
                bootstrap_next_page = current_page
            else:
                stop_reason = "MAX_PAGES_REACHED"
                bootstrap_completed = True
                bootstrap_next_page = None

        if hasattr(self.state_repository, "record_seen_details") and updated_seen_meta:
            self.state_repository.record_seen_details(
                self.adapter.SOURCE_NAME, target_id, updated_seen_meta
            )

        elapsed_seconds = time.perf_counter() - start_time
        finished_at = datetime.now(timezone.utc).isoformat()
        records_seen = len(observed_listing_ids)
        records_new = len(new_listing_ids)
        records_known = max(0, records_seen - records_new)

        unique_yield = (
            (records_new / records_seen * 100.0) if records_seen > 0 else 0.0
        )
        change_rate = (
            (records_changed / records_known * 100.0) if records_known > 0 else 0.0
        )

        deferred_remaining = (
            self.deferred_repository.count_backlog(self.adapter.SOURCE_NAME, target_id)
            if hasattr(self.deferred_repository, "count_backlog")
            else 0
        )

        all_seen_meta_combined = {**known_seen_meta, **updated_seen_meta}
        total_unique_seen = len(all_seen_meta_combined)
        detailed_count = sum(
            1 for m in all_seen_meta_combined.values() if m.get("last_detailed_at")
        )
        detail_coverage = (
            (detailed_count / total_unique_seen * 100.0) if total_unique_seen > 0 else 0.0
        )
        lightweight_only_listings = max(0, total_unique_seen - detailed_count)

        result = CrawlRunResult(
            run_id=run_id,
            source=self.adapter.SOURCE_NAME,
            target_id=target_id,
            mode=mode,
            target_url=self.adapter.base_url,
            started_at=started_at,
            finished_at=finished_at,
            status=final_status,
            stop_reason=stop_reason,
            failure_reason=failure_reason,
            max_pages=effective_max_pages,
            max_records=effective_max_records,
            crawl_details=crawl_details,
            pages_attempted=pages_attempted,
            pages_success=pages_success,
            pages_failed=pages_failed,
            details_success=detail_succeeded + deferred_succeeded,
            details_failed=detail_failed + deferred_failed,
            detail_requests_skipped=detail_skipped,
            detail_requests_forced_by_change=detail_requests_forced_by_change,
            detail_required=detail_required,
            detail_requested=detail_requested,
            detail_succeeded=detail_succeeded,
            detail_failed=detail_failed,
            detail_skipped=detail_skipped,
            skipped_known_unchanged_ttl=skipped_known_unchanged_ttl,
            skipped_no_detail_url=skipped_no_detail_url,
            skipped_request_budget=skipped_request_budget,
            skipped_source_policy=skipped_source_policy,
            skipped_other=skipped_other,
            deferred_backlog_before=deferred_backlog_before,
            deferred_added=deferred_added,
            deferred_attempted=deferred_attempted,
            deferred_succeeded=deferred_succeeded,
            deferred_failed=deferred_failed,
            deferred_terminal=deferred_terminal,
            deferred_remaining=deferred_remaining,
            detail_coverage=round(detail_coverage, 2),
            lightweight_only_listings=lightweight_only_listings,
            unique_yield=round(unique_yield, 2),
            change_rate=round(change_rate, 2),
            records_created=len(new_listing_ids),
            observations_written=len(all_bronze_records),
            duplicates_skipped=duplicates_skipped,
            records_seen=records_seen,
            records_new=records_new,
            records_known=records_known,
            records_changed=records_changed,
            known_pages_streak_at_stop=known_page_streak,
            bootstrap_completed=bootstrap_completed,
            bootstrap_start_page=start_page if is_bootstrap else 1,
            bootstrap_next_page=bootstrap_next_page,
            observed_listing_ids=observed_listing_ids,
            new_listing_ids=new_listing_ids,
            errors=errors,
        )

        # 1. Ghi Bronze dataset CHỈ KHI có records thực tế (records_created > 0)
        bronze_dir = self.storage_writer.save_bronze_dataset(
            run_id=run_id,
            source=self.adapter.SOURCE_NAME,
            records=all_bronze_records,
            metadata=all_metadata,
            details=all_detail_records
            if (crawl_details and all_detail_records)
            else None,
        )
        result.bronze_path = bronze_dir

        # 2. Ghi Run Manifest đại diện cho trạng thái kết thúc hoàn chỉnh
        manifest_file = self.storage_writer.save_manifest(result)
        result.manifest_path = manifest_file

        logger.info("=" * 60)
        logger.info(
            "KẾT THÚC PHIÊN CRAWL: %s (Status: %s)", run_id, result.status.value
        )
        logger.info("Thời gian thực thi: %.2f giây", elapsed_seconds)
        logger.info(
            "Trang thành công: %d | Trang thất bại: %d",
            pages_success,
            pages_failed,
        )
        logger.info(
            "Detail thành công: %d | Detail thất bại: %d",
            details_success,
            details_failed,
        )
        logger.info(
            "Tổng số Bronze Records tạo: %d (Mới: %d, Quan sát: %d)",
            len(all_bronze_records),
            len(new_listing_ids),
            len(observed_listing_ids),
        )
        logger.info("Run Manifest: %s", manifest_file)
        if bronze_dir:
            logger.info("Bronze Dataset lưu tại: %s", bronze_dir)
        else:
            logger.info("Bronze Dataset: Không tạo (records_created=0)")
        logger.info("=" * 60)

        return all_bronze_records, result
