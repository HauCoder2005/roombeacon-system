import os
from dataclasses import dataclass, field

from roombeacon_crawler.enums.crawl_date_mode import CrawlDateMode


@dataclass
class CrawlerSettings:
    """Cấu hình vận hành toàn cục của RoomBeacon Crawler."""

    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "CRAWLER_USER_AGENT", "RoomBeaconCrawler/0.1"
        )
    )
    playwright_headless: bool = field(
        default_factory=lambda: os.getenv(
            "PLAYWRIGHT_HEADLESS", "true"
        ).lower()
        in ("1", "true", "yes")
    )
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT", "30.0"))
    )
    request_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("REQUEST_DELAY_SECONDS", "1.5"))
    )
    max_concurrency: int = field(
        default_factory=lambda: int(os.getenv("MAX_CONCURRENCY", "1"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "3"))
    )
    start_page: int = field(
        default_factory=lambda: int(os.getenv("START_PAGE", "1"))
    )
    max_pages: int = field(
        default_factory=lambda: int(os.getenv("MAX_PAGES", "5"))
    )
    max_records_per_page: int = field(
        default_factory=lambda: int(os.getenv("MAX_RECORDS_PER_PAGE", "50"))
    )
    max_total_records: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOTAL_RECORDS", "50"))
    )
    crawl_date_mode: CrawlDateMode = field(
        default_factory=lambda: CrawlDateMode(
            os.getenv("CRAWL_DATE_MODE", CrawlDateMode.LATEST.value)
        )
    )
    date_from: str | None = field(
        default_factory=lambda: os.getenv("DATE_FROM")
    )
    date_to: str | None = field(
        default_factory=lambda: os.getenv("DATE_TO")
    )
