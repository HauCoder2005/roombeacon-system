"""Process one listing card inside the current crawl session.

Identity, deduplication, detail-refresh policy, immediate detail acquisition and
budget deferral belong here. The module does not fetch listing pages, choose
frontier transitions, persist MySQL data, or depend on Airflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import logging
from typing import TYPE_CHECKING

from roombeacon_crawler.application.crawl.session_state import CrawlSessionState
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.policies.detail_refresh_policy import DetailRefreshPolicy
from roombeacon_crawler.repositories.deferred_detail_repository import (
    DeferredDetailRepository,
)
from roombeacon_crawler.sources.base import BaseSourceAdapter

if TYPE_CHECKING:
    from roombeacon_crawler.pipeline.detail_crawl import DetailCrawlPipeline


logger = logging.getLogger(__name__)


class CardProcessingOutcome(str, Enum):
    """Observable terminal outcomes for processing one listing card."""

    DUPLICATE = "duplicate"
    LIGHTWEIGHT = "lightweight"
    DEFERRED = "deferred"
    DETAIL_SUCCEEDED = "detail_succeeded"
    DETAIL_FAILED = "detail_failed"


@dataclass(frozen=True)
class CardProcessingResult:
    """Typed card outcome and the flags needed for page-level aggregation."""

    listing_id: str
    outcome: CardProcessingOutcome
    is_new: bool
    counts_as_known: bool
    content_changed: bool


class CardProcessingProcessor:
    """Process one card and update caller-owned session observations.

    The supplied detail pipeline and deferred repository are the only external
    side-effect boundaries. Page position and stop state are never modified.
    """

    def __init__(
        self,
        *,
        adapter: BaseSourceAdapter,
        detail_pipeline: DetailCrawlPipeline,
        detail_refresh_policy: DetailRefreshPolicy,
        deferred_repository: DeferredDetailRepository,
    ) -> None:
        self._adapter = adapter
        self._detail_pipeline = detail_pipeline
        self._detail_refresh_policy = detail_refresh_policy
        self._deferred_repository = deferred_repository

    @staticmethod
    def resolve_identity(card: ListingCardRaw) -> str:
        """Return the stable source ID, canonical URL, or positional fallback."""
        if card.listing_id and str(card.listing_id).strip():
            return str(card.listing_id).strip()
        if card.detail_url and str(card.detail_url).strip():
            return str(card.detail_url).strip()
        return f"{card.source}_pos_{card.card_position}_p_{card.page_number}"

    @staticmethod
    def _fingerprint(card: ListingCardRaw) -> str:
        raw = (
            f"{card.title_raw or ''}|{card.price_raw or ''}|"
            f"{card.area_raw or ''}|{card.location_raw or ''}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _append_lightweight(
        *,
        card: ListingCardRaw,
        state: CrawlSessionState,
        run_id: str,
        listing_id: str,
        last_detailed_at: str | None,
        fingerprint: str,
        previous_metadata: dict[str, str | None],
    ) -> None:
        state.bronze_records.append(
            BronzeMapper.map(card=card, detail=None, run_id=run_id)
        )
        state.updated_seen_meta[listing_id] = {
            **previous_metadata,
            "last_detailed_at": last_detailed_at,
            "card_fingerprint": fingerprint,
        }

    @staticmethod
    def _record_address_outcome(
        *,
        card: ListingCardRaw,
        state: CrawlSessionState,
        detail_raw=None,
        detail_was_parsed: bool = False,
    ) -> None:
        """Record address quality without treating coarse card text as full address."""
        full_address = getattr(detail_raw, "address_raw", None)
        if full_address and str(full_address).strip():
            state.full_address_present += 1
            state.detail_address_extracted += 1
            return

        state.full_address_missing += 1
        if card.location_raw and str(card.location_raw).strip():
            state.coarse_only_address += 1
        if detail_was_parsed:
            state.detail_address_parse_failed += 1

    async def execute(
        self,
        *,
        card: ListingCardRaw,
        state: CrawlSessionState,
        run_id: str,
        target_id: str,
        now: datetime,
        crawl_details: bool,
        max_details_per_run: int | None,
        defer_details_for_discovery: bool = False,
    ) -> CardProcessingResult:
        """Apply deduplication and detail policy, then return the card outcome."""
        listing_id = self.resolve_identity(card)
        if listing_id not in state.observed_listing_ids:
            state.observed_listing_ids.append(listing_id)
        if listing_id in state.seen_in_current_run:
            state.duplicates_skipped += 1
            return CardProcessingResult(
                listing_id=listing_id,
                outcome=CardProcessingOutcome.DUPLICATE,
                is_new=False,
                counts_as_known=True,
                content_changed=False,
            )

        state.seen_in_current_run.add(listing_id)
        card.crawl_run_id = run_id
        fingerprint = self._fingerprint(card)
        is_new = listing_id not in state.known_seen_ids
        # Deferred work runs before page acquisition. Prefer its same-run update so
        # the listing page cannot erase a successful detail timestamp and requeue it.
        previous = state.updated_seen_meta.get(
            listing_id,
            state.known_seen_meta.get(listing_id, {}),
        )
        previous_fingerprint = previous.get("card_fingerprint")
        last_detailed_at = previous.get("last_detailed_at")
        content_changed = (
            not is_new
            and previous_fingerprint is not None
            and previous_fingerprint != fingerprint
        )
        decision = self._detail_refresh_policy.evaluate(
            is_new=is_new,
            card_changed=content_changed,
            last_detailed_at=last_detailed_at,
            current_time=now,
        )
        if is_new:
            state.new_listing_ids.append(listing_id)
        if content_changed:
            state.records_changed += 1

        state.detail_required += 1
        has_detail_url = bool(card.detail_url and card.detail_url.strip())
        if not crawl_details:
            state.detail_skipped += 1
            state.skipped_source_policy += 1
            self._append_lightweight(
                card=card,
                state=state,
                run_id=run_id,
                listing_id=listing_id,
                last_detailed_at=last_detailed_at,
                fingerprint=fingerprint,
                previous_metadata=previous,
            )
            outcome = CardProcessingOutcome.LIGHTWEIGHT
        elif not has_detail_url:
            state.detail_skipped += 1
            state.skipped_no_detail_url += 1
            self._append_lightweight(
                card=card,
                state=state,
                run_id=run_id,
                listing_id=listing_id,
                last_detailed_at=last_detailed_at,
                fingerprint=fingerprint,
                previous_metadata=previous,
            )
            outcome = CardProcessingOutcome.LIGHTWEIGHT
        elif not decision.should_refresh:
            state.detail_skipped += 1
            state.skipped_known_unchanged_ttl += 1
            self._append_lightweight(
                card=card,
                state=state,
                run_id=run_id,
                listing_id=listing_id,
                last_detailed_at=last_detailed_at,
                fingerprint=fingerprint,
                previous_metadata=previous,
            )
            outcome = CardProcessingOutcome.LIGHTWEIGHT
        elif defer_details_for_discovery:
            state.detail_skipped += 1
            state.skipped_deferred_for_discovery += 1
            self._append_lightweight(
                card=card,
                state=state,
                run_id=run_id,
                listing_id=listing_id,
                last_detailed_at=last_detailed_at,
                fingerprint=fingerprint,
                previous_metadata=previous,
            )
            item = DeferredDetailItem(
                source=self._adapter.SOURCE_NAME,
                platform_post_id=listing_id,
                detail_url=card.detail_url,
                origin_run_id=run_id,
                first_deferred_at=now.isoformat(),
                reason="DISCOVERY_FIRST_ENRICHMENT",
                card_title=getattr(card, "title_raw", None)
                or getattr(card, "title", None),
                card_price=getattr(card, "price_raw", None)
                or getattr(card, "price", None),
                card_area=getattr(card, "area_raw", None)
                or getattr(card, "area", None),
                card_location=getattr(card, "location_raw", None)
                or getattr(card, "location", None),
                card_fingerprint=fingerprint,
            )
            if hasattr(self._deferred_repository, "enqueue"):
                state.deferred_added += self._deferred_repository.enqueue(
                    self._adapter.SOURCE_NAME,
                    target_id,
                    [item],
                )
            outcome = CardProcessingOutcome.DEFERRED
        elif (
            max_details_per_run is not None
            and state.details_crawled_count >= max_details_per_run
        ):
            logger.info(
                "Detail request budget exhausted; deferring listing %s",
                listing_id,
            )
            state.detail_skipped += 1
            state.skipped_request_budget += 1
            self._append_lightweight(
                card=card,
                state=state,
                run_id=run_id,
                listing_id=listing_id,
                last_detailed_at=last_detailed_at,
                fingerprint=fingerprint,
                previous_metadata=previous,
            )
            item = DeferredDetailItem(
                source=self._adapter.SOURCE_NAME,
                platform_post_id=listing_id,
                detail_url=card.detail_url,
                origin_run_id=run_id,
                first_deferred_at=now.isoformat(),
                reason="REQUEST_BUDGET_EXHAUSTED",
                card_title=getattr(card, "title_raw", None)
                or getattr(card, "title", None),
                card_price=getattr(card, "price_raw", None)
                or getattr(card, "price", None),
                card_area=getattr(card, "area_raw", None)
                or getattr(card, "area", None),
                card_location=getattr(card, "location_raw", None)
                or getattr(card, "location", None),
                card_fingerprint=fingerprint,
            )
            if hasattr(self._deferred_repository, "enqueue"):
                state.deferred_added += self._deferred_repository.enqueue(
                    self._adapter.SOURCE_NAME,
                    target_id,
                    [item],
                )
            outcome = CardProcessingOutcome.DEFERRED
        else:
            state.detail_requested += 1
            target = CrawlTarget(
                url=card.detail_url,
                source=self._adapter.SOURCE_NAME,
                target_type=CrawlTargetType.DETAIL_PAGE,
                listing_id=listing_id,
            )
            detail_bronze, detail_raw, detail_meta = (
                await self._detail_pipeline.execute(
                    target=target,
                    card=card,
                    run_id=run_id,
                )
            )
            state.metadata.append(detail_meta)
            state.details_crawled_count += 1
            if content_changed:
                state.detail_requests_forced_by_change += 1
            if detail_raw is not None:
                state.detail_succeeded += 1
                state.detail_records.append(detail_raw)
                state.updated_seen_meta[listing_id] = {
                    "last_detailed_at": now.isoformat(),
                    "card_fingerprint": fingerprint,
                    "detail_status": (
                        "SUCCESS_WITH_ADDRESS"
                        if detail_raw.address_raw and str(detail_raw.address_raw).strip()
                        else "SUCCESS_WITHOUT_ADDRESS"
                    ),
                }
                if hasattr(self._deferred_repository, "record_success"):
                    self._deferred_repository.record_success(
                        self._adapter.SOURCE_NAME,
                        target_id,
                        listing_id,
                    )
                outcome = CardProcessingOutcome.DETAIL_SUCCEEDED
            else:
                state.detail_failed += 1
                state.updated_seen_meta[listing_id] = {
                    "last_detailed_at": last_detailed_at,
                    "card_fingerprint": fingerprint,
                    "detail_status": "FAILED",
                }
                outcome = CardProcessingOutcome.DETAIL_FAILED
            state.bronze_records.append(
                detail_bronze
                if detail_bronze is not None
                else BronzeMapper.map(card=card, detail=None, run_id=run_id)
            )

        if outcome in (CardProcessingOutcome.LIGHTWEIGHT, CardProcessingOutcome.DEFERRED):
            self._record_address_outcome(card=card, state=state)
        elif outcome == CardProcessingOutcome.DETAIL_SUCCEEDED:
            self._record_address_outcome(
                card=card,
                state=state,
                detail_raw=detail_raw,
                detail_was_parsed=True,
            )
        elif outcome == CardProcessingOutcome.DETAIL_FAILED:
            self._record_address_outcome(card=card, state=state)

        return CardProcessingResult(
            listing_id=listing_id,
            outcome=outcome,
            is_new=is_new,
            counts_as_known=not is_new,
            content_changed=content_changed,
        )
