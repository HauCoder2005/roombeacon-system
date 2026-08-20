from enum import Enum


class CrawlTargetType(str, Enum):
    """Phân loại trang hoặc tài nguyên mục tiêu cần crawl."""

    LISTING_PAGE = "listing_page"
    DETAIL_PAGE = "detail_page"
    ASSET = "asset"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
