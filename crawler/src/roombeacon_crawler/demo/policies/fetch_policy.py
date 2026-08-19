from roombeacon_crawler.demo.enums.crawl_status import CrawlStatus
from roombeacon_crawler.demo.enums.fetch_action import FetchAction


class FetchPolicy:
    def decide(self, status: CrawlStatus) -> FetchAction:
        if status == CrawlStatus.SUCCESS:
            return FetchAction.PARSE

        if status == CrawlStatus.RATE_LIMITED:
            return FetchAction.COOLDOWN

        if status in (
            CrawlStatus.SERVER_ERROR,
            CrawlStatus.TIMEOUT,
            CrawlStatus.CONNECTION_ERROR,
        ):
            return FetchAction.RETRY_LATER

        if status in (
            CrawlStatus.CLOUDFLARE_CHALLENGE,
            CrawlStatus.ACCESS_DENIED,
            CrawlStatus.NOT_FOUND,
            CrawlStatus.BAD_REQUEST,
            CrawlStatus.UNAUTHORIZED,
            CrawlStatus.UNKNOWN,
        ):
            return FetchAction.STOP

        return FetchAction.STOP
