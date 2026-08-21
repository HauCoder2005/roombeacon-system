import asyncio
from datetime import datetime, timezone
import logging
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
    ) -> None:
        self.settings = settings or CrawlerSettings()
        self.storage_writer = storage_writer or LocalStorageWriter()
        self.state_repository = state_repository or LocalCrawlStateRepository()

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
        all_bronze_records: list[RentalBronzeRecord] = []
        all_detail_records: list[ListingDetailRaw] = []
        all_metadata: list[CrawlMetadata] = []

        observed_listing_ids: list[str] = []
        new_listing_ids: list[str] = []
        seen_in_current_run: set[str] = set()

        # Tải danh sách listing_id đã từng thấy cho target này từ State Repository
        known_seen_ids = set(
            self.state_repository.get_seen_listing_ids(
                self.adapter.SOURCE_NAME, target_id
            )
        )
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

                if lid not in known_seen_ids:
                    # Tin mới (NEW)
                    page_new_count += 1
                    new_listing_ids.append(lid)

                    if crawl_details:
                        if (
                            max_details_per_run is not None
                            and details_crawled_count >= max_details_per_run
                        ):
                            logger.info(
                                "Đã đạt giới hạn max_details_per_run (%d). Bỏ qua các detail còn lại.",
                                max_details_per_run,
                            )
                            record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                            all_bronze_records.append(record)
                            continue

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

                        if detail_raw is not None:
                            details_success += 1
                            all_detail_records.append(detail_raw)
                        else:
                            details_failed += 1

                        if detail_bronze is not None:
                            all_bronze_records.append(detail_bronze)
                        else:
                            record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                            all_bronze_records.append(record)
                    else:
                        record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                        all_bronze_records.append(record)
                else:
                    # Tin đã biết trong lịch sử (KNOWN) -> không cào detail để tiết kiệm mạng nhưng VẪN ghi nhận vào Bronze Observation
                    page_known_count += 1
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

        elapsed_seconds = time.perf_counter() - start_time
        finished_at = datetime.now(timezone.utc).isoformat()
        records_seen = len(observed_listing_ids)
        records_new = len(new_listing_ids)
        records_known = max(0, records_seen - records_new)

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
            details_success=details_success,
            details_failed=details_failed,
            records_created=len(new_listing_ids),
            observations_written=len(all_bronze_records),
            duplicates_skipped=duplicates_skipped,
            records_seen=records_seen,
            records_new=records_new,
            records_known=records_known,
            records_changed=0,
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
