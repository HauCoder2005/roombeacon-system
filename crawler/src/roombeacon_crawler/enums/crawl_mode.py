from enum import Enum


class CrawlMode(str, Enum):
    """Chế độ thực thi cào dữ liệu cho từng crawl target."""

    BOOTSTRAP_FULL = "BOOTSTRAP_FULL"
    BOOTSTRAP_CONTINUE = "BOOTSTRAP_CONTINUE"
    INCREMENTAL = "INCREMENTAL"
    FORWARD_ONLY_INCREMENTAL = "FORWARD_ONLY_INCREMENTAL"
    FORCE_FULL = "FORCE_FULL"
    FORCE_INCREMENTAL = "FORCE_INCREMENTAL"
