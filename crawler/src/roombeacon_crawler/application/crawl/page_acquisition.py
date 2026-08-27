"""Acquire and classify one source listing page.

This boundary builds the page target and invokes the existing listing pipeline.
It returns typed candidates and metrics but does not process cards or mutate the
historical frontier.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import TYPE_CHECKING

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.base import BaseSourceAdapter

if TYPE_CHECKING:
    from roombeacon_crawler.pipeline.listing_crawl import ListingCrawlPipeline


logger = logging.getLogger(__name__)


class PageAcquisitionOutcome(str, Enum):
    """Normalized page outcomes consumed by frontier decisions."""

    READY = "ready"
    ROBOTS_DENIED = "robots_denied"
    ACCESS_CHALLENGE = "access_challenge"
    FETCH_ERROR = "fetch_error"
    SOURCE_END = "source_end"


@dataclass(frozen=True)
class PageAcquisitionResult:
    """Cards, metadata and counter effects from one page acquisition attempt."""

    page_url: str
    cards: list[ListingCardRaw]
    metadata: CrawlMetadata
    raw_html: str | None
    outcome: PageAcquisitionOutcome
    counts_as_attempt: bool
    counts_as_success: bool
    counts_as_failure: bool


class PageAcquisitionProcessor:
    """Build, fetch, parse and classify one listing page.

    Fetch strategy, retries, robots evaluation and parser invocation remain in
    ``ListingCrawlPipeline``; this class defines the application-level boundary.
    """

    _FETCH_FAILURES = frozenset(
        {
            CrawlStatus.CONNECTION_ERROR,
            CrawlStatus.SERVER_ERROR,
            CrawlStatus.TIMEOUT,
            CrawlStatus.PARSE_ERROR,
        }
    )
    _ACCESS_FAILURES = frozenset(
        {CrawlStatus.ACCESS_DENIED, CrawlStatus.CLOUDFLARE_CHALLENGE}
    )

    def __init__(
        self,
        *,
        adapter: BaseSourceAdapter,
        listing_pipeline: ListingCrawlPipeline,
        limit_per_page: int,
    ) -> None:
        self._adapter = adapter
        self._listing_pipeline = listing_pipeline
        self._limit_per_page = limit_per_page

    async def execute(
        self,
        *,
        run_id: str,
        page_number: int,
        forward_only: bool,
    ) -> PageAcquisitionResult:
        """Acquire one page and return a typed outcome without frontier changes."""
        page_url = (
            self._adapter.base_url
            if forward_only
            else self._adapter.pagination.build_page_url(
                base_url=self._adapter.base_url,
                page_number=page_number,
            )
        )
        target = CrawlTarget(
            url=page_url,
            source=self._adapter.SOURCE_NAME,
            target_type=CrawlTargetType.LISTING_PAGE,
            page_number=page_number,
        )
        logger.info("Acquiring listing page %d: %s", page_number, page_url)
        cards, _detail_targets, metadata, raw_html = (
            await self._listing_pipeline.execute(
                target=target,
                run_id=run_id,
                limit_per_page=self._limit_per_page,
            )
        )

        if metadata.crawl_status == CrawlStatus.ROBOTS_DENIED:
            outcome = PageAcquisitionOutcome.ROBOTS_DENIED
        elif cards:
            outcome = PageAcquisitionOutcome.READY
        elif metadata.crawl_status in self._ACCESS_FAILURES:
            outcome = PageAcquisitionOutcome.ACCESS_CHALLENGE
        elif metadata.crawl_status in self._FETCH_FAILURES:
            outcome = PageAcquisitionOutcome.FETCH_ERROR
        else:
            outcome = PageAcquisitionOutcome.SOURCE_END

        return PageAcquisitionResult(
            page_url=page_url,
            cards=cards,
            metadata=metadata,
            raw_html=raw_html,
            outcome=outcome,
            counts_as_attempt=outcome != PageAcquisitionOutcome.ROBOTS_DENIED,
            counts_as_success=outcome == PageAcquisitionOutcome.READY,
            counts_as_failure=outcome
            in {
                PageAcquisitionOutcome.ACCESS_CHALLENGE,
                PageAcquisitionOutcome.FETCH_ERROR,
            },
        )
