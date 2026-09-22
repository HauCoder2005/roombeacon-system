"""Compose and orchestrate one RoomBeacon crawl run.

The runner coordinates typed application processors and publishes local Bronze
artifacts. Page, card, deferred-detail and frontier rules live in their dedicated
components; this module has no Airflow or MySQL persistence responsibility.
"""

import asyncio
from datetime import datetime, timezone
import logging
import os
import time

from roombeacon_crawler.application.crawl.execution_options import CrawlExecutionOptions
from roombeacon_crawler.application.crawl.deferred_details import DeferredDetailProcessor
from roombeacon_crawler.application.crawl.card_processing import CardProcessingProcessor
from roombeacon_crawler.application.crawl.frontier_decision import (
    FrontierDecisionProcessor,
)
from roombeacon_crawler.application.crawl.page_acquisition import (
    PageAcquisitionOutcome,
    PageAcquisitionProcessor,
)
from roombeacon_crawler.application.crawl.session_state import CrawlSessionState
from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import (
    LocalStorageWriter,
)
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline
from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline
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
    """Orchestrate one crawl from resolved options through artifact publication.

    A runner instance is bound to one source adapter and composes acquisition,
    card, deferred-detail and frontier processors. Running it performs network
    acquisition and local state/artifact writes; MySQL and Airflow remain outside
    this boundary.
    """

    def __init__(
        self,
        target_url: str | None = None,
        adapter: BaseSourceAdapter | None = None,
        settings: CrawlerSettings | None = None,
        storage_writer: LocalStorageWriter | None = None,
        state_repository: CrawlStateRepository | None = None,
        deferred_repository: DeferredDetailRepository | None = None,
    ) -> None:
        """Compose runtime dependencies for the supplied URL or source adapter.

        Raises:
            ValueError: If no adapter can be resolved for the requested target.
        """
        self.settings = settings or CrawlerSettings()
        self.storage_writer = storage_writer or LocalStorageWriter(base_data_dir=self.settings.data_dir)
        self.state_repository = state_repository or LocalCrawlStateRepository(base_data_dir=self.settings.data_dir)
        self.deferred_repository = deferred_repository or LocalDeferredDetailRepository(base_data_dir=self.settings.data_dir)
        self.deferred_scheduler = DeferredBudgetScheduler()

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
            failure_artifact_writer=self.storage_writer,
        )
        self.page_acquisition_processor = PageAcquisitionProcessor(
            adapter=self.adapter,
            listing_pipeline=self.listing_pipeline,
            limit_per_page=self.settings.max_records_per_page,
        )

        self.detail_pipeline = DetailCrawlPipeline(
            adapter=self.adapter,
            fetch_coordinator=self.fetch_coordinator,
            robots_policy=self.robots_policy,
            fetch_policy=self.fetch_policy,
        )
        self.card_processing_processor = CardProcessingProcessor(
            adapter=self.adapter,
            detail_pipeline=self.detail_pipeline,
            detail_refresh_policy=self.detail_refresh_policy,
            deferred_repository=self.deferred_repository,
        )
        self.frontier_decision_processor = FrontierDecisionProcessor(
            adapter=self.adapter,
        )
        self.deferred_detail_processor = DeferredDetailProcessor(
            adapter=self.adapter,
            detail_pipeline=self.detail_pipeline,
            repository=self.deferred_repository,
            scheduler=self.deferred_scheduler,
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
        """Execute a complete crawl from a plan or explicit option overrides.

        Returns:
            Bronze observations and the manifest-ready run result.
        """
        start_time = time.perf_counter()
        now = datetime.now(timezone.utc)
        run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"
        started_at = now.isoformat()

        target_id = plan.target_id if plan else "default"
        caps = getattr(self.adapter, "CAPABILITIES", None)
        options = CrawlExecutionOptions.resolve(
            plan=plan,
            settings=self.settings,
            capabilities=caps,
            max_pages=max_pages,
            max_records=max_records,
            crawl_details=crawl_details,
            max_details_per_run=max_details_per_run,
            start_page=start_page,
        )
        mode = options.mode
        effective_max_pages = options.max_pages
        effective_max_records = options.max_records
        effective_crawl_details = options.crawl_details
        effective_max_details = options.max_details_per_run
        stop_after_known_pages = options.stop_after_known_pages
        effective_start_page = options.start_page

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

        try:
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
        finally:
            await self.http_fetcher.close()
            await self.browser_fetcher.close()

    async def _run_async(self, run_id: str, started_at: str, start_time: float, target_id: str, mode: str, effective_max_pages: int, effective_max_records: int, crawl_details: bool, max_details_per_run: int, stop_after_known_pages: int, start_page: int=1) -> tuple[list[RentalBronzeRecord], CrawlRunResult]:
        """Coordinate session initialization, processors and final publication."""
        deadline = time.monotonic() + self.settings.max_run_seconds
        state = CrawlSessionState()
        now = datetime.now(timezone.utc)
        if hasattr(self.state_repository, 'get_seen_metadata'):
            state.known_seen_meta = self.state_repository.get_seen_metadata(self.adapter.SOURCE_NAME, target_id)
        else:
            state.known_seen_meta = {lid: {'last_detailed_at': None, 'card_fingerprint': None} for lid in self.state_repository.get_seen_listing_ids(self.adapter.SOURCE_NAME, target_id)}
        state.known_seen_ids = set(state.known_seen_meta.keys())
        logger.info('State Repository: Đã nạp %d known listing_ids cho %s/%s', len(state.known_seen_ids), self.adapter.SOURCE_NAME, target_id)
        caps = getattr(self.adapter, 'CAPABILITIES', None)
        state.is_forward_only = mode in (CrawlMode.FORWARD_ONLY_INCREMENTAL.value, 'FORWARD_ONLY_INCREMENTAL') or (caps is not None and (not getattr(caps, 'historical_backfill_supported', True))) or (caps is not None and (not getattr(caps, 'supports_pagination', True)))
        if state.is_forward_only:
            mode = CrawlMode.FORWARD_ONLY_INCREMENTAL.value
            state.is_incremental = False
            state.is_bootstrap = False
            effective_max_pages = 1
            state.effective_end_page = 1
            state.current_page = 1
        else:
            state.is_incremental = mode in (CrawlMode.INCREMENTAL.value, CrawlMode.FORCE_INCREMENTAL.value)
            state.is_bootstrap = mode in (CrawlMode.BOOTSTRAP_FULL.value, CrawlMode.BOOTSTRAP_CONTINUE.value, CrawlMode.FORCE_FULL.value)
            state.current_page = start_page if state.is_bootstrap else 1
            state.effective_end_page = start_page + effective_max_pages - 1 if state.is_bootstrap else effective_max_pages
        state.deferred_backlog_before = (
            self.deferred_repository.count_backlog(
                self.adapter.SOURCE_NAME, target_id
            )
            if hasattr(self.deferred_repository, "count_backlog")
            else 0
        )
        exit_transition = None
        while state.current_page <= state.effective_end_page:
            # Finish the current page before yielding, so no card is skipped.
            if state.pages_success > 0 and time.monotonic() >= deadline:
                state.stop_reason = "TIME_BUDGET_REACHED"
                if state.is_bootstrap:
                    state.bootstrap_completed = False
                    state.bootstrap_next_page = state.current_page
                break
            page_started = time.perf_counter()
            page = await self.page_acquisition_processor.execute(
                run_id=run_id,
                page_number=state.current_page,
                forward_only=state.is_forward_only,
            )
            page_elapsed = time.perf_counter() - page_started
            fetch_elapsed = page.metadata.elapsed_ms / 1000.0
            state.page_acquisition_seconds += min(page_elapsed, fetch_elapsed)
            state.listing_parse_seconds += max(0.0, page_elapsed - fetch_elapsed)
            cards = page.cards
            meta = page.metadata
            raw_html = page.raw_html
            if page.outcome == PageAcquisitionOutcome.SOURCE_END:
                state.source_end_confirmed = page.source_end_confirmed
            state.metadata.append(meta)
            state.pages_attempted += int(page.counts_as_attempt)
            state.pages_success += int(page.counts_as_success)
            state.pages_failed += int(page.counts_as_failure)
            frontier_started = time.perf_counter()
            acquisition_decision = self.frontier_decision_processor.after_acquisition(
                state=state,
                outcome=page.outcome,
                crawl_status=meta.crawl_status,
            )
            state.frontier_seconds += time.perf_counter() - frontier_started
            if acquisition_decision.should_stop:
                logger.info(
                    "Frontier stop after acquisition: transition=%s page=%d status=%s",
                    acquisition_decision.transition.value,
                    state.current_page,
                    meta.crawl_status.value,
                )
                exit_transition = acquisition_decision.transition
                break
            page_records_count = len(cards)
            page_new_count = 0
            page_known_count = 0
            for card in cards:
                card_started = time.perf_counter()
                metadata_start = len(state.metadata)
                card_result = await self.card_processing_processor.execute(
                    card=card,
                    state=state,
                    run_id=run_id,
                    target_id=target_id,
                    now=now,
                    crawl_details=crawl_details,
                    max_details_per_run=max_details_per_run,
                    defer_details_for_discovery=True,
                )
                card_elapsed = time.perf_counter() - card_started
                detail_elapsed = sum(
                    item.elapsed_ms for item in state.metadata[metadata_start:]
                ) / 1000.0
                state.detail_fetch_seconds += detail_elapsed
                state.card_processing_seconds += max(0.0, card_elapsed - detail_elapsed)
                page_new_count += int(card_result.is_new)
                page_known_count += int(card_result.counts_as_known)
            frontier_started = time.perf_counter()
            frontier_decision = self.frontier_decision_processor.after_cards(
                state=state,
                page_records_count=page_records_count,
                page_new_count=page_new_count,
                page_known_count=page_known_count,
                effective_max_records=effective_max_records,
                stop_after_known_pages=stop_after_known_pages,
                raw_html=raw_html,
            )
            state.frontier_seconds += time.perf_counter() - frontier_started
            logger.info(
                "Frontier transition: transition=%s page=%d new=%d known=%d",
                frontier_decision.transition.value,
                state.current_page,
                page_new_count,
                page_known_count,
            )
            if frontier_decision.should_stop:
                exit_transition = frontier_decision.transition
                break
        frontier_started = time.perf_counter()
        
        if exit_transition is None:
            from roombeacon_crawler.application.crawl.frontier_decision import FrontierTransition
            exit_transition = FrontierTransition.PAGE_RANGE_EXHAUSTED
            
        self.frontier_decision_processor.finalize(state, exit_transition)
        state.frontier_seconds += time.perf_counter() - frontier_started
        state.discovery_seconds = time.perf_counter() - start_time
        # Discovery and frontier progression complete before bounded enrichment.
        # The durable queue preserves unconsumed work for later NORMAL runs.
        deferred_started = time.perf_counter()
        metadata_start = len(state.metadata)
        deferred = await self.deferred_detail_processor.execute(
            deadline=deadline,
            run_id=run_id,
            target_id=target_id,
            now=now,
            crawl_details=crawl_details,
            max_details_per_run=max_details_per_run,
            bronze_records=state.bronze_records,
            detail_records=state.detail_records,
            metadata=state.metadata,
            updated_seen_meta=state.updated_seen_meta,
        )
        state.deferred_detail_seconds += time.perf_counter() - deferred_started
        state.detail_fetch_seconds += sum(
            item.elapsed_ms for item in state.metadata[metadata_start:]
        ) / 1000.0
        state.deferred_attempted = deferred.attempted
        state.deferred_succeeded = deferred.succeeded
        state.deferred_failed = deferred.failed
        state.deferred_terminal = deferred.terminal
        state.full_address_present += deferred.full_address_present
        state.full_address_missing += deferred.full_address_missing
        state.coarse_only_address += deferred.coarse_only_address
        state.detail_address_extracted += deferred.detail_address_extracted
        state.detail_address_parse_failed += deferred.detail_address_parse_failed
        state.details_crawled_count = deferred.attempted
        elapsed_seconds = time.perf_counter() - start_time
        finished_at = datetime.now(timezone.utc).isoformat()
        records_seen = len(state.observed_listing_ids)
        records_new = len(state.new_listing_ids)
        records_known = max(0, records_seen - records_new)
        unique_yield = records_new / records_seen * 100.0 if records_seen > 0 else 0.0
        change_rate = state.records_changed / records_known * 100.0 if records_known > 0 else 0.0
        deferred_remaining = self.deferred_repository.count_backlog(self.adapter.SOURCE_NAME, target_id) if hasattr(self.deferred_repository, 'count_backlog') else 0
        all_seen_meta_combined = {**state.known_seen_meta, **state.updated_seen_meta}
        total_unique_seen = len(all_seen_meta_combined)
        detailed_count = sum((1 for m in all_seen_meta_combined.values() if m.get('last_detailed_at')))
        detail_coverage = detailed_count / total_unique_seen * 100.0 if total_unique_seen > 0 else 0.0
        lightweight_only_listings = max(0, total_unique_seen - detailed_count)
        result = CrawlRunResult(run_id=run_id, source=self.adapter.SOURCE_NAME, target_id=target_id, mode=mode, target_url=self.adapter.base_url, started_at=started_at, finished_at=finished_at, status=state.final_status, stop_reason=state.stop_reason, source_end_confirmed=state.source_end_confirmed, failure_reason=state.failure_reason, max_pages=effective_max_pages, max_records=effective_max_records, crawl_details=crawl_details, pages_attempted=state.pages_attempted, pages_success=state.pages_success, pages_failed=state.pages_failed, details_success=state.detail_succeeded + state.deferred_succeeded, details_failed=state.detail_failed + state.deferred_failed, detail_requests_skipped=state.detail_skipped, detail_requests_forced_by_change=state.detail_requests_forced_by_change, detail_required=state.detail_required, detail_requested=state.detail_requested, detail_succeeded=state.detail_succeeded, detail_failed=state.detail_failed, detail_skipped=state.detail_skipped, skipped_known_unchanged_ttl=state.skipped_known_unchanged_ttl, skipped_no_detail_url=state.skipped_no_detail_url, skipped_request_budget=state.skipped_request_budget, skipped_deferred_for_discovery=state.skipped_deferred_for_discovery, skipped_source_policy=state.skipped_source_policy, skipped_other=state.skipped_other, full_address_present=state.full_address_present, full_address_missing=state.full_address_missing, coarse_only_address=state.coarse_only_address, detail_address_extracted=state.detail_address_extracted, detail_address_parse_failed=state.detail_address_parse_failed, deferred_backlog_before=state.deferred_backlog_before, deferred_added=state.deferred_added, deferred_attempted=state.deferred_attempted, deferred_succeeded=state.deferred_succeeded, deferred_failed=state.deferred_failed, deferred_terminal=state.deferred_terminal, deferred_remaining=deferred_remaining, detail_coverage=round(detail_coverage, 2), lightweight_only_listings=lightweight_only_listings, unique_yield=round(unique_yield, 2), change_rate=round(change_rate, 2), records_created=len(state.new_listing_ids), observations_written=len(state.bronze_records), duplicates_skipped=state.duplicates_skipped, records_seen=records_seen, records_new=records_new, records_known=records_known, records_changed=state.records_changed, known_pages_streak_at_stop=state.known_page_streak, bootstrap_completed=state.bootstrap_completed, bootstrap_start_page=start_page if state.is_bootstrap else 1, bootstrap_next_page=state.bootstrap_next_page, observed_listing_ids=state.observed_listing_ids, new_listing_ids=state.new_listing_ids, seen_metadata_updates=state.updated_seen_meta, errors=state.errors, page_acquisition_seconds=state.page_acquisition_seconds, listing_parse_seconds=state.listing_parse_seconds, card_processing_seconds=state.card_processing_seconds, detail_fetch_seconds=state.detail_fetch_seconds, deferred_detail_seconds=state.deferred_detail_seconds, frontier_seconds=state.frontier_seconds, discovery_seconds=state.discovery_seconds, http_client_count=self.http_fetcher.client_count, browser_launch_count=self.browser_fetcher.launch_count, browser_context_count=self.browser_fetcher.context_count, browser_page_count=self.browser_fetcher.page_count)
        if hasattr(self.deferred_repository, "flush"):
            try:
                self.deferred_repository.flush()
            except Exception as e:
                logger.error("Error flushing deferred repository: %s", e)

        bronze_started = time.perf_counter()

        bronze_dir = self.storage_writer.save_bronze_dataset(run_id=run_id, source=self.adapter.SOURCE_NAME, records=state.bronze_records, metadata=state.metadata, details=state.detail_records if crawl_details and state.detail_records else None)
        result.bronze_serialization_seconds = time.perf_counter() - bronze_started
        result.total_crawl_seconds = time.perf_counter() - start_time
        result.bronze_path = bronze_dir
        manifest_file = self.storage_writer.save_manifest(result)
        result.manifest_path = manifest_file
        logger.info('=' * 60)
        logger.info('KẾT THÚC PHIÊN CRAWL: %s (Status: %s)', run_id, result.status.value)
        logger.info('Thời gian thực thi: %.2f giây', elapsed_seconds)
        logger.info(
            'Crawl timing seconds: discovery=%.3f page=%.3f parse=%.3f cards=%.3f details=%.3f deferred=%.3f frontier=%.3f bronze=%.3f total=%.3f',
            result.discovery_seconds,
            result.page_acquisition_seconds,
            result.listing_parse_seconds,
            result.card_processing_seconds,
            result.detail_fetch_seconds,
            result.deferred_detail_seconds,
            result.frontier_seconds,
            result.bronze_serialization_seconds,
            result.total_crawl_seconds,
        )
        logger.info(
            'Transport lifecycle: http_clients=%d browser_launches=%d browser_contexts=%d browser_pages=%d',
            result.http_client_count,
            result.browser_launch_count,
            result.browser_context_count,
            result.browser_page_count,
        )
        logger.info('Trang thành công: %d | Trang thất bại: %d', state.pages_success, state.pages_failed)
        # The run total includes backlog work completed before page acquisition.
        # Immediate-only counters remain separate for page-card conservation metrics.
        logger.info(
            'Detail thành công: %d | Detail thất bại: %d',
            result.details_success,
            result.details_failed,
        )
        logger.info('Tổng số Bronze Records tạo: %d (Mới: %d, Quan sát: %d)', len(state.bronze_records), len(state.new_listing_ids), len(state.observed_listing_ids))
        logger.info('Run Manifest: %s', manifest_file)
        if bronze_dir:
            logger.info('Bronze Dataset lưu tại: %s', bronze_dir)
        else:
            logger.info('Bronze Dataset: Không tạo (records_created=0)')
        logger.info('=' * 60)
        return (state.bronze_records, result)
