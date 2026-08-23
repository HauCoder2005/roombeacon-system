from enum import Enum


class CrawlDateMode(str, Enum):
    """Chế độ quét dữ liệu theo thời gian đăng tin."""

    LATEST = "latest"
    DATE_RANGE = "date_range"
    FULL_HISTORY = "full_history"

    @classmethod
    def from_str(cls, value: str | None) -> "CrawlDateMode":
        """Chuyển đổi chuỗi (không phân biệt hoa thường) thành CrawlDateMode."""
        if not value:
            return cls.LATEST
        val_clean = value.strip().lower()
        for item in cls:
            if item.value == val_clean or item.name.lower() == val_clean:
                return item
        return cls.LATEST
