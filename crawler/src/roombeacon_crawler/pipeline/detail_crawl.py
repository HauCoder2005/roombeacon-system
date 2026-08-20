from datetime import datetime, timezone
import logging

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.fetch_action import FetchAction
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.mappers.bronze_mapper import BronzeMapper
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator
from roombeacon_crawler.services.metadata_collector import MetadataCollector
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.validators.detail_validator import DetailValidator

logger = logging.getLogger(__name__)


class DetailCrawlPipeline:
    """Pipeline xử lý việc thu thập, bóc tách trang chi tiết và ánh xạ thành bản ghi Bronze."""

    def __init__(
        self,
        adapter: BaseSourceAdapter,
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
        card: ListingCardRaw | None,
        run_id: str,
    ) -> tuple[RentalBronzeRecord | None, ListingDetailRaw | None, CrawlMetadata]:
        """Thực thi chu trình crawl trang chi tiết, bóc tách ListingDetailRaw và map thành RentalBronzeRecord."""
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
            return bronze, None, meta

        # 2. Generic Fetch via FetchCoordinator
        response, crawl_status, meta = await self.fetch_coordinator.fetch(
            target=target,
            adapter=self.adapter,
            run_id=run_id,
        )

        action = self.fetch_policy.decide(crawl_status)
        if action != FetchAction.PARSE or not response:
            bronze = BronzeMapper.map(card=card, detail=None, run_id=run_id)
            return bronze, None, meta

        # 3. Extract Detail
        detail: ListingDetailRaw = self.adapter.detail_parser.parse(
            html=response.html,
            detail_url=response.final_url,
            listing_id=target.listing_id,
        )
        detail.crawl_run_id = run_id
        detail.crawled_at = datetime.now(timezone.utc).isoformat()

        if not DetailValidator.validate(detail):
            logger.warning("Trang chi tiết %s không đạt validation cấu trúc", target.url)

        # 4. Map to Bronze
        bronze_record = BronzeMapper.map(
            card=card,
            detail=detail,
            run_id=run_id,
        )

        return bronze_record, detail, meta
