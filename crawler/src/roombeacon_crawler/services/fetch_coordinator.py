import asyncio
from datetime import datetime, timezone
import logging

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
from roombeacon_crawler.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_target import CrawlTarget
from roombeacon_crawler.policies.rate_limit_policy import RateLimitPolicy
from roombeacon_crawler.policies.retry_policy import RetryPolicy
from roombeacon_crawler.services.metadata_collector import MetadataCollector
from roombeacon_crawler.services.response_classifier import ResponseClassifier
from roombeacon_crawler.services.strategy_selector import StrategySelector
from roombeacon_crawler.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class FetchCoordinator:
    """Điều phối viên tầng thu thập dữ liệu (Acquisition Layer) chung cho toàn bộ website nguồn.

    Chịu trách nhiệm:
    1. Lựa chọn chiến lược (Strategy Selection: HTTP vs Browser).
    2. Điều tiết tần suất gửi request (Rate Limiting).
    3. Thực thi fetch qua HttpFetcher hoặc BrowserFetcher.
    4. Phân loại phản hồi kỹ thuật (Response Classification).
    5. Quản lý retry với exponential backoff (Retry Policy).
    6. Thu thập technical metadata hoàn chỉnh (Metadata Collection).
    """

    def __init__(
        self,
        http_fetcher: HttpFetcher | None = None,
        browser_fetcher: BrowserFetcher | None = None,
        strategy_selector: StrategySelector | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
        response_classifier: ResponseClassifier | None = None,
    ) -> None:
        self.http_fetcher = http_fetcher or HttpFetcher()
        self.browser_fetcher = browser_fetcher or BrowserFetcher()
        self.strategy_selector = strategy_selector or StrategySelector()
        self.rate_limit_policy = rate_limit_policy or RateLimitPolicy()
        self.retry_policy = retry_policy or RetryPolicy()
        self.response_classifier = response_classifier or ResponseClassifier()

    async def fetch(
        self,
        target: CrawlTarget | str,
        adapter: BaseSourceAdapter | None = None,
        run_id: str = "",
        override_strategy: FetchStrategy | None = None,
        wait_selector: str | None = None,
        wait_timeout_ms: int = 5000,
    ) -> tuple[CapturedResponse | None, CrawlStatus, CrawlMetadata]:
        """Thực thi toàn bộ chu trình fetch độc lập với site nguồn."""
        if isinstance(target, str):
            target_obj = CrawlTarget(
                url=target,
                source=adapter.SOURCE_NAME if adapter else "unknown",
                target_type=CrawlTargetType.LISTING_PAGE,
            )
        else:
            target_obj = target

        started_at = datetime.now(timezone.utc).isoformat()
        strategy = self.strategy_selector.select(
            url=target_obj.url,
            adapter=adapter,
            override_strategy=override_strategy,
        )

        logger.info("FetchCoordinator: Bắt đầu fetch %s [Strategy: %s]", target_obj.url, strategy.value)

        response: CapturedResponse | None = None
        attempt = 0
        crawl_status = CrawlStatus.UNKNOWN

        while True:
            attempt += 1
            await self.rate_limit_policy.throttle()

            try:
                if strategy == FetchStrategy.BROWSER:
                    try:
                        response = await self.browser_fetcher.fetch(
                            url=target_obj.url,
                            wait_selector=wait_selector,
                            wait_timeout_ms=wait_timeout_ms,
                        )
                    except RuntimeError as re:
                        if "Playwright" in str(re):
                            logger.error(
                                "FetchCoordinator: Playwright không khả dụng (%s) khi fetch %s với chiến lược BROWSER",
                                re,
                                target_obj.url,
                            )
                            crawl_status = CrawlStatus.BROWSER_UNAVAILABLE
                            break
                        else:
                            raise
                else:
                    response = await self.http_fetcher.fetch(url=target_obj.url)

                if response is not None:
                    crawl_status = self.response_classifier.classify(
                        status_code=response.status_code,
                        html=response.html,
                    )
                    logger.info(
                        "FetchCoordinator: HTTP %d | Status: %s | Time: %.2fms",
                        response.status_code,
                        crawl_status.value,
                        response.elapsed_ms,
                    )
                else:
                    crawl_status = CrawlStatus.CONNECTION_ERROR
            except Exception as exc:
                logger.warning(
                    "FetchCoordinator: Lỗi fetch %s (lần thử %d): %s",
                    target_obj.url,
                    attempt,
                    exc,
                )
                crawl_status = CrawlStatus.CONNECTION_ERROR

            if crawl_status == CrawlStatus.SUCCESS:
                break

            if not self.retry_policy.should_retry(crawl_status, attempt):
                break

            backoff = self.retry_policy.get_backoff_delay(attempt)
            logger.info("FetchCoordinator: Retry sau %.1fs (lần %d)", backoff, attempt)
            await asyncio.sleep(backoff)

        meta = MetadataCollector.collect(
            target=target_obj,
            response=response,
            run_id=run_id,
            crawl_status=crawl_status,
            started_at=started_at,
            retry_count=attempt - 1,
            robots_allowed=True,
        )

        return response, crawl_status, meta
