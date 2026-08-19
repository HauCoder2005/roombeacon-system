from datetime import datetime, timezone
import logging

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.fetch_action import FetchAction
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.metadata_collector import MetadataCollector
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.validators.detail_validator import DetailValidator

logger = logging.getLogger(__name__)


class DetailCrawlPipeline:
    """Pipeline xử lý việc thu thập, bóc tách trang chi tiết và ánh xạ thành bản ghi Bronze."""

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
        card: ListingCardRaw | None,
        run_id: str,
    ) -> tuple[RentalBronzeRecord | None, CrawlMetadata]:
        """Thực thi chu trình crawl trang chi tiết, bóc tách và map thành RentalBronzeRecord."""
        started_at = datetime.now(timezone.utc).isoformat()

        # 1. Robots check
        if not self.robots_policy.is_allowed(target.url):
            meta = MetadataCollector.collect(
                target=target,
                response=None,
                run_id=run_id,
                crawl_status=CrawlStatus.ROBOTS_DENIED,
                started_at=started_at,
                robots_allowed=False,
            )
            bronze = BronzeMapper.map(card=card, detail=None, run_id=run_id)
            return bronze, meta

        strategy = self.adapter.settings.default_strategy
        response: CapturedResponse | None = None
        attempt = 0
        crawl_status = CrawlStatus.UNKNOWN

        # 2. Fetch loop với Retry
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
                    "Lỗi request detail (%s) lần thử %d: %s",
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
            bronze = BronzeMapper.map(card=card, detail=None, run_id=run_id)
            return bronze, meta

        # 3. Extract Detail
        detail: ListingDetailRaw = self.adapter.detail_parser.parse(
            html=response.html,
            detail_url=response.final_url,
            listing_id=target.listing_id,
        )

        if not DetailValidator.validate(detail):
            logger.warning("Trang chi tiết %s không đạt validation cấu trúc", target.url)

        # 4. Map to Bronze
        bronze_record = BronzeMapper.map(
            card=card,
            detail=detail,
            run_id=run_id,
        )

        return bronze_record, meta
