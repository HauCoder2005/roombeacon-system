from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.fetch_action import FetchAction


class FetchPolicy:
    """Chính sách quyết định hành động tiếp theo dựa trên kết quả phân loại response."""

    ACTION_MAP: dict[CrawlStatus, FetchAction] = {
        CrawlStatus.SUCCESS: FetchAction.PARSE,
        CrawlStatus.RATE_LIMITED: FetchAction.COOLDOWN,
        CrawlStatus.SERVER_ERROR: FetchAction.RETRY_LATER,
        CrawlStatus.TIMEOUT: FetchAction.RETRY_LATER,
        CrawlStatus.CONNECTION_ERROR: FetchAction.RETRY_LATER,
        CrawlStatus.ACCESS_DENIED: FetchAction.STOP,
        CrawlStatus.CLOUDFLARE_CHALLENGE: FetchAction.STOP,
        CrawlStatus.ROBOTS_DENIED: FetchAction.STOP,
        CrawlStatus.NOT_FOUND: FetchAction.STOP,
        CrawlStatus.BAD_REQUEST: FetchAction.STOP,
        CrawlStatus.UNAUTHORIZED: FetchAction.STOP,
        CrawlStatus.PARSE_ERROR: FetchAction.STOP,
        CrawlStatus.UNKNOWN: FetchAction.STOP,
    }

    def decide(self, status: CrawlStatus) -> FetchAction:
        """Quyết định hành động (PARSE, COOLDOWN, RETRY_LATER, STOP) cho trạng thái crawl."""
        return self.ACTION_MAP.get(status, FetchAction.STOP)
