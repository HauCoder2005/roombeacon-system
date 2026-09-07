"""Consume previously deferred detail work within the current request budget.

The processor handles backlog scheduling and detail outcomes. It does not
acquire listing pages, decide the crawl frontier, or persist run checkpoints.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw


@dataclass(frozen=True)
class DeferredDetailResult:
    """Immutable counters produced while consuming the deferred backlog."""

    backlog_before: int = 0
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    terminal: int = 0
    full_address_present: int = 0
    full_address_missing: int = 0
    coarse_only_address: int = 0
    detail_address_extracted: int = 0
    detail_address_parse_failed: int = 0


@dataclass(frozen=True)
class _DeferredDetailOutcome:
    """Typed interpretation of one fetch and address-enrichment attempt."""

    pending_detail: DeferredDetailItem
    listing_card: ListingCardRaw
    bronze_record: Any | None
    parsed_detail: Any | None
    fetch_metadata: Any
    fetch_succeeded: bool
    address_extracted: bool
    address_expected: bool
    enrichment_completed: bool
    coarse_only_address: bool
    terminal_failure: bool

    @property
    def detail_status(self) -> str:
        """Expose the stable status label consumed by run reporting."""
        if self.address_extracted:
            return "SUCCESS_WITH_ADDRESS"
        if not self.address_expected:
            return "SUCCESS_WITHOUT_ADDRESS"
        return "ADDRESS_MISSING_RETRY"


@dataclass
class _DeferredDetailMetrics:
    """Mutable counters internal to a single deferred-detail execution."""

    attempted: int = 0
    fetch_succeeded: int = 0
    fetch_failed: int = 0
    terminal: int = 0
    full_address_present: int = 0
    full_address_missing: int = 0
    coarse_only_address: int = 0
    address_extracted: int = 0
    address_parse_failed: int = 0

    def record(self, outcome: _DeferredDetailOutcome) -> None:
        """Fold one detail outcome into the run-local counters."""
        if outcome.fetch_succeeded:
            self.fetch_succeeded += 1
        else:
            self.fetch_failed += 1
        if outcome.terminal_failure:
            self.terminal += 1
        if outcome.address_extracted:
            self.full_address_present += 1
            self.address_extracted += 1
        else:
            self.full_address_missing += 1
            if outcome.fetch_succeeded:
                self.address_parse_failed += 1
        if outcome.coarse_only_address:
            self.coarse_only_address += 1

    def build_result(self, *, backlog_before: int) -> DeferredDetailResult:
        """Freeze mutable counters into the processor's public result contract."""
        return DeferredDetailResult(
            backlog_before=backlog_before,
            attempted=self.attempted,
            succeeded=self.fetch_succeeded,
            failed=self.fetch_failed,
            terminal=self.terminal,
            full_address_present=self.full_address_present,
            full_address_missing=self.full_address_missing,
            coarse_only_address=self.coarse_only_address,
            detail_address_extracted=self.address_extracted,
            detail_address_parse_failed=self.address_parse_failed,
        )


class DeferredDetailProcessor:
    """Consume the fair-scheduled deferred quota after page acquisition."""

    def __init__(self, *, adapter, detail_pipeline, repository, scheduler) -> None:
        self.adapter = adapter
        self.detail_pipeline = detail_pipeline
        self.repository = repository
        self.scheduler = scheduler

    @staticmethod
    def _merge_bronze_record(bronze_records: list, enriched_record) -> None:
        """Replace a same-run lightweight card or append older backlog enrichment."""
        listing_id = getattr(enriched_record, "listing_id", None)
        record_source = getattr(enriched_record, "source", None)
        for index, existing_record in enumerate(bronze_records):
            if (
                getattr(existing_record, "listing_id", None) == listing_id
                and getattr(existing_record, "source", None) == record_source
            ):
                bronze_records[index] = enriched_record
                return
        bronze_records.append(enriched_record)

    def _select_pending_details(
        self,
        *,
        target_id: str,
        now: datetime,
        crawl_details: bool,
        max_details_per_run: int | None,
    ) -> tuple[int, list[DeferredDetailItem]]:
        backlog_before = self.repository.count_backlog(self.adapter.SOURCE_NAME, target_id)
        
        can_process_backlog = (
            crawl_details
            and max_details_per_run is not None
            and max_details_per_run > 0
            and backlog_before > 0
        )
        if not can_process_backlog:
            return backlog_before, []

        budget_allocation = self.scheduler.allocate(
            total_budget=max_details_per_run,
            deferred_pending_count=backlog_before,
        )
        pending_details = self.repository.get_backlog(
            self.adapter.SOURCE_NAME,
            target_id,
            now=now,
        )[: budget_allocation.deferred_quota]
        return backlog_before, pending_details

    def _address_expected(self) -> bool:
        capabilities = getattr(self.adapter, "CAPABILITIES", None)
        custom_flags = getattr(capabilities, "custom_flags", None)
        if not isinstance(custom_flags, dict):
            return True
        return bool(custom_flags.get("detail_address_expected", True))

    async def _fetch_pending_detail(
        self,
        *,
        pending_detail: DeferredDetailItem,
        run_id: str,
    ) -> _DeferredDetailOutcome:
        detail_target = CrawlTarget(
            url=pending_detail.detail_url,
            source=self.adapter.SOURCE_NAME,
            target_type=CrawlTargetType.DETAIL_PAGE,
            listing_id=pending_detail.platform_post_id,
        )
        listing_card = ListingCardRaw(
            source=self.adapter.SOURCE_NAME,
            listing_id=pending_detail.platform_post_id,
            detail_url=pending_detail.detail_url,
            title_raw=pending_detail.card_title or "",
            price_raw=pending_detail.card_price,
            area_raw=pending_detail.card_area,
            location_raw=pending_detail.card_location,
            posted_at_raw=None,
            crawl_run_id=run_id,
        )
        bronze_record, parsed_detail, fetch_metadata = (
            await self.detail_pipeline.execute(
                target=detail_target,
                card=listing_card,
                run_id=run_id,
            )
        )

        fetch_succeeded = parsed_detail is not None
        address_extracted = bool(
            fetch_succeeded
            and parsed_detail.address_raw
            and str(parsed_detail.address_raw).strip()
        )
        address_expected = self._address_expected() if fetch_succeeded else True
        return _DeferredDetailOutcome(
            pending_detail=pending_detail,
            listing_card=listing_card,
            bronze_record=bronze_record,
            parsed_detail=parsed_detail,
            fetch_metadata=fetch_metadata,
            fetch_succeeded=fetch_succeeded,
            address_extracted=address_extracted,
            address_expected=address_expected,
            enrichment_completed=(
                fetch_succeeded
                and (address_extracted or not address_expected)
            ),
            coarse_only_address=bool(
                listing_card.location_raw
                and str(listing_card.location_raw).strip()
                and not address_extracted
            ),
            terminal_failure=(
                not fetch_succeeded
                and getattr(fetch_metadata, "status_code", None) in (404, 410)
            ),
        )

    def _apply_outcome(
        self,
        *,
        outcome: _DeferredDetailOutcome,
        target_id: str,
        now: datetime,
        bronze_records: list,
        detail_records: list,
        metadata: list,
        updated_seen_meta: dict[str, dict],
    ) -> None:
        metadata.append(outcome.fetch_metadata)
        pending_detail = outcome.pending_detail

        if not outcome.fetch_succeeded:
            status_code = getattr(outcome.fetch_metadata, "status_code", None)
            self.repository.record_failure(
                self.adapter.SOURCE_NAME,
                target_id,
                pending_detail.platform_post_id,
                error=f"HTTP status {status_code}",
                is_terminal=outcome.terminal_failure,
                now=now,
            )
            return

        detail_records.append(outcome.parsed_detail)
        if outcome.enrichment_completed:
            self.repository.record_success(
                self.adapter.SOURCE_NAME,
                target_id,
                pending_detail.platform_post_id,
            )
        else:
            self.repository.record_failure(
                self.adapter.SOURCE_NAME,
                target_id,
                pending_detail.platform_post_id,
                error="ADDRESS_EXTRACTION_MISSING",
                is_terminal=False,
                now=now,
            )

        updated_seen_meta[pending_detail.platform_post_id] = {
            "last_detailed_at": (
                now.isoformat() if outcome.address_extracted else None
            ),
            "card_fingerprint": pending_detail.card_fingerprint,
            "detail_status": outcome.detail_status,
        }
        if outcome.bronze_record is not None:
            self._merge_bronze_record(bronze_records, outcome.bronze_record)

    async def execute(
        self,
        *,
        run_id: str,
        target_id: str,
        now: datetime,
        crawl_details: bool,
        max_details_per_run: int | None,
        bronze_records: list,
        detail_records: list,
        metadata: list,
        updated_seen_meta: dict[str, dict],
    ) -> DeferredDetailResult:
        """Process a bounded backlog slice independently of discovery output.

        ``max_details_per_run`` is the network/enrichment safety bound.  The
        listing discovery record cap must not filter older queue items because
        those items intentionally belong to earlier discovery runs.
        """
        backlog_before, pending_details = self._select_pending_details(
            target_id=target_id,
            now=now,
            crawl_details=crawl_details,
            max_details_per_run=max_details_per_run,
        )

        metrics = _DeferredDetailMetrics(attempted=len(pending_details))

        for pending_detail in pending_details:
            outcome = await self._fetch_pending_detail(
                pending_detail=pending_detail,
                run_id=run_id,
            )
            self._apply_outcome(
                outcome=outcome,
                target_id=target_id,
                now=now,
                bronze_records=bronze_records,
                detail_records=detail_records,
                metadata=metadata,
                updated_seen_meta=updated_seen_meta,
            )
            metrics.record(outcome)

        return metrics.build_result(backlog_before=backlog_before)
