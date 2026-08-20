from enum import Enum


class CrawlRunMode(str, Enum):
    """Chế độ thực thi của phiên crawl trong DAG orchestration."""

    SINGLE_TARGET = "SINGLE_TARGET"
    SCHEDULED_ALL = "SCHEDULED_ALL"
