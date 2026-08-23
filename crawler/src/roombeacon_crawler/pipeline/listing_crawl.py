from datetime import datetime, timezone
import logging

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_action import FetchAction
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator
from roombeacon_crawler.services.metadata_collector import MetadataCollector
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.validators.listing_validator import ListingValidator

logger = logging.getLogger(__name__)


class ListingCrawlPipeline:
    """Pipeline xử lý việc thu thập và bóc tách một trang danh sách (Listing Page)."""

    def __init__(
        self,
        adapter,
        fetch_coordinator: FetchCoordinator | None = None,
        http_fetcher: HttpFetcher | None = None,
        browser_fetcher: BrowserFetcher | None = None,
        robots_policy: RobotsPolicy | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        response_classifier: ResponseClassifier | None = None,
        fetch_policy: FetchPolicy | None = None,
    ) -> None:
        self.adapter = adapter
        self.robots_policy = robots_policy or RobotsPolicy()
        self.fetch_policy = fetch_policy or FetchPolicy()

        if fetch_coordinator is not None:
            self.fetch_coordinator = fetch_coordinator
        else:
            self.fetch_coordinator = FetchCoordinator(
                http_fetcher=http_fetcher or HttpFetcher(),
                browser_fetcher=browser_fetcher or BrowserFetcher(),
                rate_limit_policy=rate_limit_policy or RateLimitPolicy(),
                retry_policy=retry_policy or RetryPolicy(),
                response_classifier=response_classifier or ResponseClassifier(),
            )

    async def execute(
        self,
        target: CrawlTarget,
        run_id: str,
        limit_per_page: int = 50,
    ) -> tuple[list[ListingCardRaw], list[CrawlTarget], CrawlMetadata, str | None]:
        """Thực thi toàn bộ chu trình crawl một trang listing và sinh danh sách detail targets cùng raw HTML."""
        started_at = datetime.now(timezone.utc).isoformat()

        # 1. Robots.txt Preflight Evaluation
        decision, robots_url = self.robots_policy.evaluate(target.url)
        logger.info("Source: %s", target.source)
        logger.info("Robots URL: %s", robots_url)
        logger.info("Robots Decision: %s", decision)

        if decision == "DENIED":
            logger.warning(
                "Crawl stopped by robots policy. Target was not fetched. No robots bypass was attempted. Target URL: %s",
                target.url,
            )
            meta = MetadataCollector.collect(
                target=target,
                response=None,
                run_id=run_id,
                crawl_status=CrawlStatus.ROBOTS_DENIED,
                started_at=started_at,
                robots_allowed=False,
            )
            return [], [], meta, None

        # 2. Generic Fetch via FetchCoordinator
        response, crawl_status, meta = await self.fetch_coordinator.fetch(
            target=target,
            adapter=self.adapter,
            run_id=run_id,
        )

        action = self.fetch_policy.decide(crawl_status)
        if action != FetchAction.PARSE or not response:
            return [], [], meta, None

        # 3. Extract Cards
        cards = self.adapter.listing_parser.parse(
            html=response.html,
            source_url=response.final_url,
            page_number=target.page_number,
            limit=limit_per_page,
        )
        logger.info("Parser Result: Extracted %d raw listing cards", len(cards))

        # 4. Validate and create Detail Crawl Targets
        valid_cards: list[ListingCardRaw] = []
        detail_targets: list[CrawlTarget] = []

        for card in cards:
            if ListingValidator.validate(card):
                valid_cards.append(card)
                detail_targets.append(
                    CrawlTarget(
                        url=card.detail_url,
                        source=target.source,
                        target_type=CrawlTargetType.DETAIL_PAGE,
                        page_number=target.page_number,
                        parent_url=target.url,
                        listing_id=card.listing_id,
                    )
                )

        logger.info("Listing Validator Result: %d/%d cards valid", len(valid_cards), len(cards))
        return valid_cards, detail_targets, meta, response.html
