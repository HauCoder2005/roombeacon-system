from datetime import datetime, timezone
import logging

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_action import FetchAction
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.metadata_collector import MetadataCollector
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.validators.listing_validator import ListingValidator

logger = logging.getLogger(__name__)


class ListingCrawlPipeline:
    """Pipeline xử lý việc thu thập và bóc tách một trang danh sách (Listing Page)."""

    def __init__(
        self,
        adapter: NhatotSourceAdapter,
        http_fetcher: HttpFetcher,
        browser_fetcher: BrowserFetcher,
        robots_policy: RobotsPolicy,
        rate_limit_policy: RateLimitPolicy,
        retry_policy: RetryPolicy,
        response_classifier: ResponseClassifier,
        fetch_policy: FetchPolicy,
    ) -> None:
        self.adapter = adapter
        self.http_fetcher = http_fetcher
        self.browser_fetcher = browser_fetcher
        self.robots_policy = robots_policy
        self.rate_limit_policy = rate_limit_policy
        self.retry_policy = retry_policy
        self.response_classifier = response_classifier
        self.fetch_policy = fetch_policy

    async def execute(
        self,
        target: CrawlTarget,
        run_id: str,
        limit_per_page: int = 50,
    ) -> tuple[list[ListingCardRaw], list[CrawlTarget], CrawlMetadata]:
        """Thực thi toàn bộ chu trình crawl một trang listing và sinh danh sách detail targets."""
        started_at = datetime.now(timezone.utc).isoformat()

        # 1. Kiểm tra Robots.txt
        if not self.robots_policy.is_allowed(target.url):
            meta = MetadataCollector.collect(
                target=target,
                response=None,
                run_id=run_id,
                crawl_status=CrawlStatus.ROBOTS_DENIED,
                started_at=started_at,
                robots_allowed=False,
            )
            return [], [], meta

        strategy = self.adapter.settings.default_strategy
        response: CapturedResponse | None = None
        attempt = 0
        crawl_status = CrawlStatus.UNKNOWN

        # 2. Fetch loop với RetryPolicy
        while True:
            attempt += 1
            await self.rate_limit_policy.throttle()

            try:
                if strategy == FetchStrategy.BROWSER:
                    response = await self.browser_fetcher.fetch(target.url)
                else:
                    response = await self.http_fetcher.fetch(target.url)

                crawl_status = self.response_classifier.classify(
                    status_code=response.status_code,
                    html=response.html,
                )
            except Exception as exc:
                logger.warning(
                    "Lỗi request listing (%s) lần thử %d: %s",
                    target.url,
                    attempt,
                    exc,
                )
                crawl_status = CrawlStatus.CONNECTION_ERROR

            if crawl_status == CrawlStatus.SUCCESS:
                break

            if not self.retry_policy.should_retry(crawl_status, attempt):
                break

            backoff = self.retry_policy.get_backoff_delay(attempt)
            logger.info("Listing retry sau %.1fs (lần %d)", backoff, attempt)
            import asyncio
            await asyncio.sleep(backoff)

        meta = MetadataCollector.collect(
            target=target,
            response=response,
            run_id=run_id,
            crawl_status=crawl_status,
            started_at=started_at,
            retry_count=attempt - 1,
            robots_allowed=True,
        )

        action = self.fetch_policy.decide(crawl_status)
        if action != FetchAction.PARSE or not response:
            return [], [], meta

        # 3. Extract Cards
        cards = self.adapter.listing_parser.parse(
            html=response.html,
            source_url=response.final_url,
            page_number=target.page_number,
            limit=limit_per_page,
        )

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

        return valid_cards, detail_targets, meta
