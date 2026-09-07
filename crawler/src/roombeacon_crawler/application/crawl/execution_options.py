"""Resolve immutable execution options for a crawl request.

This pure application helper combines an optional plan, explicit overrides and
source capabilities. It performs no acquisition, persistence or environment
bootstrap.
"""

from dataclasses import dataclass

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.source_capabilities import SourceCapabilities


@dataclass(frozen=True)
class CrawlExecutionOptions:
    """Resolved, side-effect-free limits for one crawl execution."""

    mode: str
    max_pages: int
    max_records: int
    crawl_details: bool
    max_details_per_run: int
    stop_after_known_pages: int
    start_page: int

    @classmethod
    def resolve(
        cls,
        *,
        plan: CrawlPlan | None,
        settings: CrawlerSettings,
        capabilities,
        max_pages: int | None,
        max_records: int | None,
        crawl_details: bool | None,
        max_details_per_run: int | None,
        start_page: int | None,
    ) -> "CrawlExecutionOptions":
        """Resolve plan and explicit overrides while enforcing source limits."""
        mode = (
            plan.mode.value if plan and hasattr(plan.mode, "value") else
            str(plan.mode) if plan else CrawlMode.BOOTSTRAP_FULL.value
        )
        
        caps = capabilities if capabilities is not None else SourceCapabilities()
        
        # A source that cannot backfill must never construct historical page
        # URLs.  Coerce every entry point (including direct/manual execution)
        # to the safe seed-page acquisition contract.
        if not caps.historical_backfill_supported:
            mode = CrawlMode.FORWARD_ONLY_INCREMENTAL.value

        is_forward_only_mode = mode == CrawlMode.FORWARD_ONLY_INCREMENTAL.value

        if is_forward_only_mode:
            return cls(
                mode=mode,
                max_pages=1,
                max_records=max_records if max_records is not None else (
                    plan.safety_max_records if plan else settings.max_total_records
                ),
                crawl_details=crawl_details if crawl_details is not None else (
                    plan.crawl_details if plan else True
                ),
                max_details_per_run=(
                    max_details_per_run if max_details_per_run is not None else
                    plan.max_details_per_run if plan else settings.max_details_per_run
                ),
                stop_after_known_pages=1,
                start_page=1,
            )

        if plan:
            return cls(
                mode=mode,
                max_pages=max_pages if max_pages is not None else plan.safety_max_pages,
                max_records=max_records if max_records is not None else plan.safety_max_records,
                crawl_details=crawl_details if crawl_details is not None else plan.crawl_details,
                max_details_per_run=(
                    max_details_per_run if max_details_per_run is not None else plan.max_details_per_run
                ),
                stop_after_known_pages=plan.incremental_stop_after_known_pages,
                start_page=start_page if start_page is not None else getattr(plan, "start_page", 1),
            )

        return cls(
            mode=mode,
            max_pages=max_pages if max_pages is not None else settings.max_pages,
            max_records=max_records if max_records is not None else settings.max_total_records,
            crawl_details=crawl_details if crawl_details is not None else True,
            max_details_per_run=(
                max_details_per_run if max_details_per_run is not None else settings.max_details_per_run
            ),
            stop_after_known_pages=2,
            start_page=start_page if start_page is not None else 1,
        )
