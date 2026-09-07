"""Model page-loop frontier and stop transitions explicitly.

The processor mutates only frontier-related fields in ``CrawlSessionState``.
It does not fetch pages, process cards/details, persist data, or know Airflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from roombeacon_crawler.application.crawl.page_acquisition import (
    PageAcquisitionOutcome,
)
from roombeacon_crawler.application.crawl.session_state import CrawlSessionState
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.sources.base import BaseSourceAdapter

class FrontierAction(str, Enum):
    """Control signal returned to the CrawlRunner page loop."""

    CONTINUE = "continue"
    STOP = "stop"


class FrontierTransition(str, Enum):
    """Named frontier transitions preserving crawl stop semantics."""

    PAGE_READY = "page_ready"
    NEXT_PAGE = "next_page"
    ROBOTS_STOP = "robots_stop"
    ACCESS_STOP = "access_stop"
    FETCH_STOP = "fetch_stop"
    SOURCE_END = "source_end"
    FORWARD_COMPLETE = "forward_complete"
    KNOWN_REGION_REACHED = "known_region_reached"
    MAX_RECORDS_REACHED = "max_records_reached"
    MAX_PAGES_REACHED = "max_pages_reached"
    PAGE_RANGE_EXHAUSTED = "page_range_exhausted"


@dataclass(frozen=True)
class FrontierDecision:
    """Typed loop action paired with the transition that caused it."""

    action: FrontierAction
    transition: FrontierTransition

    @property
    def should_stop(self) -> bool:
        """Return whether the page loop must terminate after this transition."""
        return self.action == FrontierAction.STOP
        
    @property
    def allow_deferred_enrichment(self) -> bool:
        """Return whether deferred detail enrichment should proceed."""
        return self.transition in {
            FrontierTransition.PAGE_READY,
            FrontierTransition.NEXT_PAGE,
            FrontierTransition.FORWARD_COMPLETE,
            FrontierTransition.KNOWN_REGION_REACHED,
            FrontierTransition.MAX_RECORDS_REACHED,
            FrontierTransition.MAX_PAGES_REACHED,
            FrontierTransition.SOURCE_END,
        }


class FrontierDecisionProcessor:
    """Apply historical, incremental and forward-only frontier transitions."""

    def __init__(self, *, adapter: BaseSourceAdapter) -> None:
        self._adapter = adapter

    @staticmethod
    def _stop(
        transition: FrontierTransition,
    ) -> FrontierDecision:
        """Translate a page acquisition outcome into continue-or-stop state."""
        return FrontierDecision(FrontierAction.STOP, transition)

    def after_acquisition(
        self,
        *,
        state: CrawlSessionState,
        outcome: PageAcquisitionOutcome,
        crawl_status: CrawlStatus,
    ) -> FrontierDecision:
        """Apply post-card stop priority and advance the page when permitted."""
        if outcome == PageAcquisitionOutcome.READY:
            return FrontierDecision(
                FrontierAction.CONTINUE,
                FrontierTransition.PAGE_READY,
            )
        if outcome == PageAcquisitionOutcome.ROBOTS_DENIED:
            state.final_status = CrawlStatus.ROBOTS_DENIED
            state.stop_reason = CrawlStatus.ROBOTS_DENIED
            if state.is_bootstrap:
                state.bootstrap_completed = False
                state.bootstrap_next_page = state.current_page
            return self._stop(FrontierTransition.ROBOTS_STOP)
        if outcome == PageAcquisitionOutcome.ACCESS_CHALLENGE:
            state.final_status = crawl_status
            state.stop_reason = crawl_status
            if state.is_bootstrap:
                state.bootstrap_completed = False
                state.bootstrap_next_page = state.current_page
            return self._stop(FrontierTransition.ACCESS_STOP)
        if outcome == PageAcquisitionOutcome.FETCH_ERROR:
            state.final_status = crawl_status
            state.failure_reason = f"Lỗi fetch listing page: {crawl_status.value}"
            state.errors.append(state.failure_reason)
            if state.is_bootstrap:
                state.bootstrap_completed = False
                state.bootstrap_next_page = state.current_page
            return self._stop(FrontierTransition.FETCH_STOP)

        state.stop_reason = "SOURCE_END"
        state.final_status = CrawlStatus.SUCCESS
        state.bootstrap_completed = True
        state.bootstrap_next_page = None
        return self._stop(FrontierTransition.SOURCE_END)

    def after_cards(
        self,
        *,
        state: CrawlSessionState,
        page_records_count: int,
        page_new_count: int,
        page_known_count: int,
        effective_max_records: int,
        stop_after_known_pages: int,
        raw_html: str | None,
        record_cap_truncated_page: bool = False,
    ) -> FrontierDecision:
        """Evaluate post-card limits and advance to the next page when allowed."""
        if state.is_forward_only:
            state.stop_reason = "FORWARD_SCAN_COMPLETE"
            state.final_status = CrawlStatus.SUCCESS
            state.bootstrap_completed = False
            state.bootstrap_next_page = None
            return self._stop(FrontierTransition.FORWARD_COMPLETE)

        if state.is_incremental:
            if page_new_count > 0:
                state.known_page_streak = 0
            elif page_records_count > 0 and page_known_count == page_records_count:
                state.known_page_streak += 1
                if state.known_page_streak >= stop_after_known_pages:
                    state.stop_reason = "KNOWN_REGION_REACHED"
                    state.final_status = CrawlStatus.SUCCESS
                    state.bootstrap_completed = True
                    state.bootstrap_next_page = None
                    return self._stop(FrontierTransition.KNOWN_REGION_REACHED)

        if len(state.bronze_records) >= effective_max_records:
            state.stop_reason = "MAX_RECORDS_REACHED"
            state.final_status = CrawlStatus.SUCCESS
            if state.is_bootstrap:
                state.bootstrap_completed = False
                state.bootstrap_next_page = (
                    state.current_page
                    if record_cap_truncated_page
                    else state.current_page + 1
                )
            else:
                state.bootstrap_completed = True
                state.bootstrap_next_page = None
            return self._stop(FrontierTransition.MAX_RECORDS_REACHED)

        has_next = self._adapter.pagination.has_next_page(
            current_page=state.current_page,
            max_pages=state.effective_end_page,
            current_items_count=page_records_count,
            raw_html=raw_html,
        )
        if not has_next:
            state.final_status = CrawlStatus.SUCCESS
            if state.current_page >= state.effective_end_page:
                state.stop_reason = "MAX_PAGES_REACHED"
                if state.is_bootstrap:
                    state.bootstrap_completed = False
                    state.bootstrap_next_page = state.current_page + 1
                else:
                    state.bootstrap_completed = True
                    state.bootstrap_next_page = None
                return self._stop(FrontierTransition.MAX_PAGES_REACHED)

            state.stop_reason = "SOURCE_END"
            state.bootstrap_completed = True
            state.bootstrap_next_page = None
            return self._stop(FrontierTransition.SOURCE_END)

        # The frontier owns its transition.  Advancing here keeps the processor
        # self-contained and makes callers observe the next page immediately.
        state.current_page += 1
        return FrontierDecision(
            FrontierAction.CONTINUE,
            FrontierTransition.NEXT_PAGE,
        )

    @staticmethod
    def finalize(
        state: CrawlSessionState,
        exit_transition: FrontierTransition,
    ) -> None:
        """Finalize the state based on the explicit loop exit reason."""
        state.loop_exit_transition = exit_transition.value
        
        if state.stop_reason is None:
            state.stop_reason = exit_transition.value
            
        if exit_transition == FrontierTransition.PAGE_RANGE_EXHAUSTED:
            if state.is_forward_only:
                state.stop_reason = "FORWARD_SCAN_COMPLETE"
                state.bootstrap_completed = False
                state.bootstrap_next_page = None
            elif state.is_bootstrap:
                state.stop_reason = "MAX_PAGES_REACHED"
                state.bootstrap_completed = False
                state.bootstrap_next_page = state.current_page
            else:
                state.stop_reason = "MAX_PAGES_REACHED"
                state.bootstrap_completed = True
                state.bootstrap_next_page = None
