from datetime import datetime
import logging

from roombeacon_crawler.enums.crawl_date_mode import CrawlDateMode

logger = logging.getLogger(__name__)


class DateCutoffPolicy:
    """Chính sách kiểm soát dừng phân trang theo thời gian đăng tin."""

    def __init__(
        self,
        mode: CrawlDateMode = CrawlDateMode.LATEST,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        max_pages_safety: int = 1000,
    ) -> None:
        self.mode = mode
        self.date_from = date_from
        self.date_to = date_to
        self.max_pages_safety = max_pages_safety

    def should_continue_pagination(
        self,
        oldest_item_dt: datetime | None,
        current_page: int,
        max_pages: int | None = None,
    ) -> bool:
        """Kiểm tra xem có nên tiếp tục sang trang tiếp theo hay dừng lại do vượt ngưỡng ngày."""
        effective_max = max_pages if max_pages is not None else self.max_pages_safety
        if current_page >= effective_max:
            return False

        if self.mode == CrawlDateMode.FULL_HISTORY:
            return True

        if self.mode == CrawlDateMode.DATE_RANGE and self.date_from is not None:
            if oldest_item_dt is not None and oldest_item_dt < self.date_from:
                return False

        return True

    def is_item_in_range(self, item_dt: datetime | None) -> bool:
        """Kiểm tra xem một tin đăng cụ thể có nằm trong khoảng thời gian cần crawl không."""
        if item_dt is None:
            return True

        if self.date_from is not None and item_dt < self.date_from:
            return False

        if self.date_to is not None and item_dt > self.date_to:
            return False

        return True
