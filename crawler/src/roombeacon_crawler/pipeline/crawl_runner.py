import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import time

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline
from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline
from roombeacon_crawler.policies.date_cutoff_policy import DateCutoffPolicy
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.services.strategy_selector import StrategySelector
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.resolver import SourceResolver
from roombeacon_crawler.validators.url_validator import URLValidator

logger = logging.getLogger(__name__)


class CrawlRunner:
    """Core Application Boundary chịu trách nhiệm điều phối toàn bộ chu trình crawl đa nguồn."""

    def __init__(
        self,
        target_url: str,
        settings: CrawlerSettings | None = None,
        storage_writer: LocalStorageWriter | None = None,
    ) -> None:
        self.target_url = target_url
        self.settings = settings or CrawlerSettings()

        # 1. URL & SSRF Validation
        is_valid, error_reason = URLValidator.validate(self.target_url)
        if not is_valid:
            raise ValueError(f"Target URL không hợp lệ: {error_reason}")

        # 2. Phân giải Source Adapter tương ứng
        self.adapter: BaseSourceAdapter = SourceResolver.resolve_adapter(self.target_url)
        if not self.adapter:
            supported = ", ".join(SourceResolver.get_supported_sources())
            raise ValueError(
                f"Không tìm thấy Adapter cho URL: {self.target_url}. Đang hỗ trợ: {supported}"
            )

        # 3. Khởi tạo Storage & Components
        self.storage_writer = storage_writer or LocalStorageWriter(
            base_data_dir=self.settings.data_dir
        )

        self.http_fetcher = HttpFetcher(
            timeout=self.settings.request_timeout,
            user_agent=self.settings.user_agent,
        )
        self.browser_fetcher = BrowserFetcher(
            headless=self.settings.playwright_headless,
            user_agent=self.settings.user_agent,
            timeout=self.settings.request_timeout,
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
        url: str,
        max_pages: int | None = None,
        max_records: int | None = None,
        crawl_details: bool = True,
        max_details_per_run: int | None = None,
        settings: CrawlerSettings | None = None,
    ) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Public synchronous application entry point cho Airflow DAGs và scripts."""
        runner = cls(target_url=url, settings=settings)
        return asyncio.run(
            runner.run(
                max_pages=max_pages,
                max_records=max_records,
                crawl_details=crawl_details,
                max_details_per_run=max_details_per_run,
            )
        )

    async def run(
        self,
        max_pages: int | None = None,
        max_records: int | None = None,
        crawl_details: bool = True,
        max_details_per_run: int | None = None,
    ) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Thực thi phiên crawl hoàn chỉnh."""
        start_time = time.perf_counter()
        now = datetime.now(timezone.utc)
        run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"
        started_at = now.isoformat()

        effective_max_pages = (
            max_pages if max_pages is not None else self.settings.max_pages
        )
        effective_max_records = (
            max_records
            if max_records is not None
            else self.settings.max_total_records
        )

        logger.info("=" * 60)
        logger.info("BẮT ĐẦU PHIÊN CRAWL: %s", run_id)
        logger.info("Target Base URL: %s", self.adapter.base_url)
        logger.info("Source Name: %s", self.adapter.SOURCE_NAME)
        logger.info("Headless Mode: %s", self.settings.playwright_headless)
        logger.info(
            "Max Pages: %d | Max Records: %d | Crawl Details: %s",
            effective_max_pages,
            effective_max_records,
            crawl_details,
        )
        logger.info("=" * 60)
        logger.info("CRAWLRUNNER LIMITS")
        logger.info("Max Pages   : %d", effective_max_pages)
        logger.info("Max Records : %d", effective_max_records)
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
                target_url=self.adapter.base_url,
                started_at=started_at,
                finished_at=finished_at,
                status=CrawlStatus.UNSUPPORTED_TARGET,
                stop_reason=CrawlStatus.UNSUPPORTED_TARGET,
                failure_reason=f"URL không thuộc danh mục phòng trọ hợp lệ của nguồn {self.adapter.SOURCE_NAME}",
                max_pages=effective_max_pages,
                max_records=effective_max_records,
                crawl_details=crawl_details,
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

        seen_detail_urls: set[str] = set()
        all_bronze_records: list[RentalBronzeRecord] = []
        all_detail_records: list[ListingDetailRaw] = []
        all_metadata: list[CrawlMetadata] = []

        current_page = 1
        pages_attempted = 0
        pages_success = 0
        pages_failed = 0
        details_success = 0
        details_failed = 0
        duplicates_skipped = 0
        details_crawled_count = 0
        final_status = CrawlStatus.SUCCESS
        stop_reason: CrawlStatus | None = None
        failure_reason: str | None = None
        errors: list[str] = []

        while current_page <= effective_max_pages:
            if len(all_bronze_records) >= effective_max_records:
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : MAX_RECORDS_REACHED")
                logger.info("Current Page        : %d", current_page)
                logger.info("Configured Max Pages: %d", effective_max_pages)
                logger.info("Records Collected   : %d", len(all_bronze_records))
                logger.info("Configured Max Recs : %d", effective_max_records)
                logger.info("=" * 60)
                break

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
                effective_max_pages,
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
                    # Trang rỗng không lỗi (ví dụ không còn tin)
                    logger.info("=" * 60)
                    logger.info("PAGINATION STOP")
                    logger.info("Reason              : EMPTY_LISTING_PAGE")
                    logger.info("Current Page        : %d", current_page)
                    logger.info("=" * 60)
                    break

            pages_success += 1
            page_records_count = len(cards)
            logger.info(
                "Trang %d: Thu thập được %d listing cards hợp lệ (Total Detail Targets: %d)",
                current_page,
                page_records_count,
                len(detail_targets),
            )
            card_by_url: dict[str, ListingCardRaw] = {
                c.detail_url: c for c in cards
            }

            # Detail Crawl
            for detail_target in detail_targets:
                if len(all_bronze_records) >= effective_max_records:
                    break

                if detail_target.url in seen_detail_urls:
                    duplicates_skipped += 1
                    continue

                seen_detail_urls.add(detail_target.url)
                card = card_by_url.get(detail_target.url)
                if card:
                    card.crawl_run_id = run_id

                if crawl_details:
                    if (
                        max_details_per_run is not None
                        and details_crawled_count >= max_details_per_run
                    ):
                        from roombeacon_crawler.mappers.bronze_mapper import (
                            BronzeMapper,
                        )

                        bronze_record = BronzeMapper.map(
                            card=card, detail=None, run_id=run_id
                        )
                        all_bronze_records.append(bronze_record)
                        continue

                    logger.info(
                        "Crawl detail: %s (ID: %s)",
                        detail_target.url,
                        detail_target.listing_id or "N/A",
                    )
                    bronze_record, detail_raw, d_meta = (
                        await self.detail_pipeline.execute(
                            target=detail_target,
                            card=card,
                            run_id=run_id,
                        )
                    )
                    all_metadata.append(d_meta)
                    details_crawled_count += 1

                    if detail_raw:
                        all_detail_records.append(detail_raw)
                        details_success += 1
                    else:
                        details_failed += 1

                    if bronze_record:
                        all_bronze_records.append(bronze_record)
                else:
                    from roombeacon_crawler.mappers.bronze_mapper import (
                        BronzeMapper,
                    )

                    bronze_record = BronzeMapper.map(
                        card=card, detail=None, run_id=run_id
                    )
                    all_bronze_records.append(bronze_record)

            # Kiểm tra xem max_records đã đạt được sau khi xử lý tin của trang hiện tại chưa
            if len(all_bronze_records) >= effective_max_records:
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : MAX_RECORDS_REACHED")
                logger.info("Current Page        : %d", current_page)
                logger.info("Configured Max Pages: %d", effective_max_pages)
                logger.info("Records Collected   : %d", len(all_bronze_records))
                logger.info("Configured Max Recs : %d", effective_max_records)
                logger.info("=" * 60)
                break

            # Check Date Cutoff for next page
            oldest_card_date = None
            for c in reversed(cards):
                if c.posted_at_raw:
                    oldest_card_date = self.adapter.date_interpreter.interpret(
                        c.posted_at_raw
                    )
                    if oldest_card_date:
                        break

            if not self.date_cutoff_policy.should_continue_pagination(
                oldest_item_dt=oldest_card_date,
                current_page=current_page,
                max_pages=effective_max_pages,
            ):
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : DATE_CUTOFF_REACHED")
                logger.info("Current Page        : %d", current_page)
                logger.info("Oldest Item Date    : %s", oldest_card_date)
                logger.info("=" * 60)
                break

            if current_page >= effective_max_pages:
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : MAX_PAGES_REACHED")
                logger.info("Current Page        : %d", current_page)
                logger.info("Configured Max Pages: %d", effective_max_pages)
                logger.info("=" * 60)
                break

            if not self.adapter.pagination.has_next_page(
                current_page=current_page,
                max_pages=effective_max_pages,
                current_items_count=len(cards),
                html=raw_html,
            ):
                logger.info("=" * 60)
                logger.info("PAGINATION STOP")
                logger.info("Reason              : SOURCE_HAS_NO_NEXT_PAGE")
                logger.info("Current Page        : %d", current_page)
                logger.info("Configured Max Pages: %d", effective_max_pages)
                logger.info("=" * 60)
                break

            current_page += 1

        elapsed_seconds = time.perf_counter() - start_time
        finished_at = datetime.now(timezone.utc).isoformat()
        result = CrawlRunResult(
            run_id=run_id,
            source=self.adapter.SOURCE_NAME,
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
            records_created=len(all_bronze_records),
            duplicates_skipped=duplicates_skipped,
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
        logger.info("Tổng số Bronze Records tạo: %d", len(all_bronze_records))
        logger.info("Run Manifest: %s", manifest_file)
        if bronze_dir:
            logger.info("Bronze Dataset lưu tại: %s", bronze_dir)
        else:
            logger.info("Bronze Dataset: Không tạo (records_created=0)")
        logger.info("=" * 60)

        return all_bronze_records, result
