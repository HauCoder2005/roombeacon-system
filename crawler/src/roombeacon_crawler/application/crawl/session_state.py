"""Typed mutable state owned by one crawl-run lifecycle.

This module contains data only. It does not create clients, access persistence,
perform acquisition, or make orchestration decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from roombeacon_crawler.enums.crawl_status import CrawlStatus

if TYPE_CHECKING:
    from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
    from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
    from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord


SeenMetadata = dict[str, str | None]


@dataclass
class CrawlSessionState:
    """Collect mutable counters, identities, frontier fields and run outputs.

    A fresh instance belongs to exactly one crawl run. Mutable fields use
    isolated factories so state cannot leak between runs.
    """

    bronze_records: list[RentalBronzeRecord] = field(default_factory=list)
    detail_records: list[ListingDetailRaw] = field(default_factory=list)
    metadata: list[CrawlMetadata] = field(default_factory=list)
    observed_listing_ids: list[str] = field(default_factory=list)
    new_listing_ids: list[str] = field(default_factory=list)
    seen_in_current_run: set[str] = field(default_factory=set)
    known_seen_meta: dict[str, SeenMetadata] = field(default_factory=dict)
    known_seen_ids: set[str] = field(default_factory=set)
    updated_seen_meta: dict[str, SeenMetadata] = field(default_factory=dict)

    records_changed: int = 0
    detail_requests_forced_by_change: int = 0
    detail_required: int = 0
    detail_requested: int = 0
    detail_succeeded: int = 0
    detail_failed: int = 0
    detail_skipped: int = 0
    skipped_known_unchanged_ttl: int = 0
    skipped_no_detail_url: int = 0
    skipped_request_budget: int = 0
    skipped_deferred_for_discovery: int = 0
    skipped_source_policy: int = 0
    skipped_other: int = 0
    full_address_present: int = 0
    full_address_missing: int = 0
    coarse_only_address: int = 0
    detail_address_extracted: int = 0
    detail_address_parse_failed: int = 0
    
    run_started_at: float | None = None
    discovery_started_at: float | None = None
    discovery_finished_at: float | None = None

    is_forward_only: bool = False
    is_incremental: bool = False
    is_bootstrap: bool = False
    current_page: int = 1
    effective_end_page: int = 1
    bootstrap_completed: bool = False
    bootstrap_next_page: int | None = None
    
    loop_exit_transition: str | None = None

    pages_attempted: int = 0
    pages_success: int = 0
    pages_failed: int = 0
    details_success: int = 0
    details_failed: int = 0
    duplicates_skipped: int = 0
    details_crawled_count: int = 0
    known_page_streak: int = 0
    final_status: CrawlStatus = CrawlStatus.SUCCESS
    stop_reason: str | CrawlStatus | None = None
    failure_reason: str | None = None
    errors: list[str] = field(default_factory=list)

    deferred_backlog_before: int = 0
    deferred_added: int = 0
    deferred_attempted: int = 0
    deferred_succeeded: int = 0
    deferred_failed: int = 0
    deferred_terminal: int = 0

    page_acquisition_seconds: float = 0.0
    listing_parse_seconds: float = 0.0
    card_processing_seconds: float = 0.0
    detail_fetch_seconds: float = 0.0
    deferred_detail_seconds: float = 0.0
    frontier_seconds: float = 0.0
    discovery_seconds: float = 0.0
