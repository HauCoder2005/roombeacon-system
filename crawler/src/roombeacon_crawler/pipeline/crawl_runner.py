from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline
from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline
from roombeacon_crawler.policies.date_cutoff_policy import DateCutoffPolicy
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter

logger = logging.getLogger(__name__)


class CrawlRunner:
    """Orchestrator điều phối toàn bộ một phiên crawl (run) độc lập từ listing đến detail và xuất Bronze."""

    def __init__(
        self,
        adapter: NhatotSourceAdapter | None = None,
        settings: CrawlerSettings | None = None,
    ) -> None:
        self.settings = settings or CrawlerSettings()
        self.adapter = adapter or NhatotSourceAdapter(
            request_delay_seconds=self.settings.request_delay_seconds,
            max_concurrency=self.settings.max_concurrency,
        )

        self.robots_policy = RobotsPolicy(user_agent=self.settings.user_agent)
        self.rate_limit_policy = RateLimitPolicy(
            delay_seconds=self.settings.request_delay_seconds,
            max_concurrency=self.settings.max_concurrency,
        )
        self.retry_policy = RetryPolicy(max_retries=self.settings.max_retries)
        self.fetch_policy = FetchPolicy()
        self.response_classifier = ResponseClassifier()

        self.http_fetcher = HttpFetcher(
            timeout=self.settings.request_timeout,
            user_agent=self.settings.user_agent,
        )
        self.browser_fetcher = BrowserFetcher(
            timeout=self.settings.request_timeout,
            headless=self.settings.playwright_headless,
            user_agent=self.settings.user_agent,
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
            max_pages_safety=self.settings.max_pages,
        )

        self.listing_pipeline = ListingCrawlPipeline(
            adapter=self.adapter,
            http_fetcher=self.http_fetcher,
            browser_fetcher=self.browser_fetcher,
            robots_policy=self.robots_policy,
            rate_limit_policy=self.rate_limit_policy,
            retry_policy=self.retry_policy,
            response_classifier=self.response_classifier,
            fetch_policy=self.fetch_policy,
        )

        self.detail_pipeline = DetailCrawlPipeline(
            adapter=self.adapter,
            http_fetcher=self.http_fetcher,
            browser_fetcher=self.browser_fetcher,
            robots_policy=self.robots_policy,
            rate_limit_policy=self.rate_limit_policy,
            retry_policy=self.retry_policy,
            response_classifier=self.response_classifier,
            fetch_policy=self.fetch_policy,
        )

    async def run(
        self,
        max_pages: int | None = None,
        max_records: int | None = None,
        crawl_details: bool = True,
        max_details_per_run: int | None = None,
    ) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Thực thi phiên crawl hoàn chỉnh."""
        now = datetime.now(timezone.utc)
        run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"
        started_at = now.isoformat()

        effective_max_pages = max_pages or self.settings.max_pages
        effective_max_records = max_records or self.settings.max_total_records

        logger.info(
            "Bắt đầu phiên crawl %s cho nguồn %s (max_pages=%d, max_records=%d)",
            run_id,
            self.adapter.SOURCE_NAME,
            effective_max_pages,
            effective_max_records,
        )

        seen_detail_urls: set[str] = set()
        all_bronze_records: list[RentalBronzeRecord] = []
        all_metadata: list[CrawlMetadata] = []

        pages_success = 0
        pages_failed = 0
        details_success = 0
        details_failed = 0
        duplicates_skipped = 0
        errors: list[str] = []

        current_page = self.settings.start_page
        details_crawled_count = 0

        while current_page <= effective_max_pages:
            if len(all_bronze_records) >= effective_max_records:
                logger.info("Đã đạt giới hạn tối đa %d records. Dừng pagination.", effective_max_records)
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

            logger.info("Đang crawl listing page %d: %s", current_page, page_url)
            cards, detail_targets, meta = await self.listing_pipeline.execute(
                target=listing_target,
                run_id=run_id,
                limit_per_page=self.settings.max_records_per_page,
            )
            all_metadata.append(meta)

            if not cards:
                pages_failed += 1
                logger.warning("Không lấy được card nào từ trang %d", current_page)
                break

            pages_success += 1
            card_by_url: dict[str, ListingCardRaw] = {c.detail_url: c for c in cards}

            # Detail Crawl
            for detail_target in detail_targets:
                if len(all_bronze_records) >= effective_max_records:
                    break

                if detail_target.url in seen_detail_urls:
                    duplicates_skipped += 1
                    continue

                seen_detail_urls.add(detail_target.url)
                card = card_by_url.get(detail_target.url)

                if crawl_details:
                    if (
                        max_details_per_run is not None
                        and details_crawled_count >= max_details_per_run
                    ):
                        # Map directly from card if details limit reached
                        bronze = self.adapter.detail_parser.parse(
                            html="",
                            detail_url=detail_target.url,
                            listing_id=detail_target.listing_id,
                        )
                        from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
                        bronze_record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                        all_bronze_records.append(bronze_record)
                        continue

                    logger.info("Đang crawl detail tin: %s", detail_target.url)
                    bronze_record, d_meta = await self.detail_pipeline.execute(
                        target=detail_target,
                        card=card,
                        run_id=run_id,
                    )
                    all_metadata.append(d_meta)
                    details_crawled_count += 1

                    if bronze_record:
                        all_bronze_records.append(bronze_record)
                        details_success += 1
                    else:
                        details_failed += 1
                else:
                    # Direct mapping from card without detail fetch
                    from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
                    bronze_record = BronzeMapper.map(card=card, detail=None, run_id=run_id)
                    all_bronze_records.append(bronze_record)

            # Check Date Cutoff for next page
            oldest_card_date = None
            for c in reversed(cards):
                if c.posted_at_raw:
                    oldest_card_date = self.adapter.date_interpreter.interpret(c.posted_at_raw)
                    if oldest_card_date:
                        break

            if not self.date_cutoff_policy.should_continue_pagination(
                oldest_item_dt=oldest_card_date,
                current_page=current_page,
            ):
                logger.info("DateCutoffPolicy yêu cầu dừng phân trang tại trang %d", current_page)
                break

            if not self.adapter.pagination.has_next_page(
                current_page=current_page,
                max_pages=effective_max_pages,
                current_items_count=len(cards),
            ):
                break

            current_page += 1

        finished_at = datetime.now(timezone.utc).isoformat()
        result = CrawlRunResult(
            run_id=run_id,
            source=self.adapter.SOURCE_NAME,
            started_at=started_at,
            finished_at=finished_at,
            pages_success=pages_success,
            pages_failed=pages_failed,
            details_success=details_success,
            details_failed=details_failed,
            records_created=len(all_bronze_records),
            duplicates_skipped=duplicates_skipped,
            errors=errors,
        )

        # Commit Bronze datasets to local storage contract
        self._commit_local_bronze(run_id, all_bronze_records, all_metadata, result)

        return all_bronze_records, result

    def _commit_local_bronze(
        self,
        run_id: str,
        records: list[RentalBronzeRecord],
        metadata: list[CrawlMetadata],
        result: CrawlRunResult,
    ) -> str:
        """Ghi kết quả crawl thành local Bronze dataset theo cấu trúc storage contract."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_dir = os.path.join(
            "data", "bronze", self.adapter.SOURCE_NAME, date_str, run_id
        )
        os.makedirs(output_dir, exist_ok=True)

        listings_path = os.path.join(output_dir, "listings.json")
        metadata_path = os.path.join(output_dir, "metadata.json")
        manifest_path = os.path.join(output_dir, "manifest.json")

        with open(listings_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in records], f, ensure_ascii=False, indent=2)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in metadata], f, ensure_ascii=False, indent=2)

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(asdict(result), f, ensure_ascii=False, indent=2)

        logger.info("Đã lưu Bronze dataset tại: %s", output_dir)
        return output_dir
