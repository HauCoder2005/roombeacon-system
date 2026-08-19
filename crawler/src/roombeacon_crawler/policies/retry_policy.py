from roombeacon_crawler.enums.crawl_status import CrawlStatus


class RetryPolicy:
    """Chính sách quyết định retry và tính toán thời gian backoff cho lỗi có thể phục hồi."""

    RETRYABLE_STATUSES = {
        CrawlStatus.TIMEOUT,
        CrawlStatus.CONNECTION_ERROR,
        CrawlStatus.SERVER_ERROR,
    }

    def __init__(
        self,
        max_retries: int = 3,
        base_delay_seconds: float = 2.0,
        max_delay_seconds: float = 30.0,
    ) -> None:
        self.max_retries = max(0, max_retries)
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds

    def should_retry(self, status: CrawlStatus, attempt: int) -> bool:
        """Kiểm tra xem có nên thực hiện retry lại request với status hiện tại không."""
        if attempt >= self.max_retries:
            return False
        return status in self.RETRYABLE_STATUSES

    def get_backoff_delay(self, attempt: int) -> float:
        """Tính toán thời gian delay lũy tiến (exponential backoff) trước lần thử tiếp theo."""
        delay = self.base_delay_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)
