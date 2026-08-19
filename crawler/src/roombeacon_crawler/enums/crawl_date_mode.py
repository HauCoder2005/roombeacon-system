from enum import Enum


class CrawlDateMode(str, Enum):
    """Chế độ quét dữ liệu theo thời gian đăng tin."""

    LATEST = "latest"
    DATE_RANGE = "date_range"
    FULL_HISTORY = "full_history"
