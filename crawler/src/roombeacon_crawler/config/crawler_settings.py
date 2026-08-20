from dataclasses import dataclass, field

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.enums.crawl_date_mode import CrawlDateMode


@dataclass
class CrawlerSettings:
    """Cấu hình vận hành toàn cục của RoomBeacon Crawler."""

    data_dir: str = field(default_factory=lambda: env.crawler.data_dir)
    user_agent: str = field(default_factory=lambda: env.crawler.user_agent)
    playwright_headless: bool = field(
        default_factory=lambda: env.crawler.playwright_headless
    )
    obey_robots_txt: bool = field(
        default_factory=lambda: env.crawler.obey_robots_txt
    )
    request_timeout: float = field(
        default_factory=lambda: env.crawler.request_timeout_seconds
    )
    request_delay_seconds: float = field(
        default_factory=lambda: env.crawler.request_delay_seconds
    )
    max_concurrency: int = field(
        default_factory=lambda: env.crawler.max_concurrency
    )
    max_retries: int = field(default_factory=lambda: env.crawler.max_retries)
    start_page: int = field(default_factory=lambda: env.crawler.start_page)
    max_pages: int = field(default_factory=lambda: env.crawler.max_pages)
    max_records_per_page: int = field(
        default_factory=lambda: env.crawler.max_records_per_page
    )
    max_total_records: int = field(
        default_factory=lambda: env.crawler.max_total_records
    )
    crawl_date_mode: CrawlDateMode = field(
        default_factory=lambda: CrawlDateMode.from_str(env.crawler.date_mode)
    )
    date_from: str | None = field(default_factory=lambda: env.crawler.date_from)
    date_to: str | None = field(default_factory=lambda: env.crawler.date_to)
