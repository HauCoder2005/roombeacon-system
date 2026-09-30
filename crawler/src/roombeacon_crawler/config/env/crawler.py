from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_bool, get_float, get_int, get_str


@dataclass(frozen=True, slots=True)
class CrawlerEnv:
    data_dir: str = "/data"
    user_agent: str = "RoomBeaconCrawler/0.1"
    playwright_headless: bool = True
    obey_robots_txt: bool = True
    request_timeout_seconds: float = 30.0
    request_delay_seconds: float = 3.0
    max_concurrency: int = 1
    max_run_seconds: float = 2700.0
    max_retries: int = 1
    retry_backoff_seconds: float = 5.0
    start_page: int = 1
    max_pages: int = 5
    max_records_per_page: int = 50
    max_total_records: int = 250
    date_mode: str = "LATEST"
    date_from: str | None = None
    date_to: str | None = None


def load_crawler_env() -> CrawlerEnv:
    return CrawlerEnv(
        data_dir=get_str("CRAWLER_DATA_DIR", default="/data") or "/data",
        user_agent=get_str("CRAWLER_USER_AGENT", default="RoomBeaconCrawler/0.1") or "RoomBeaconCrawler/0.1",
        playwright_headless=get_bool("PLAYWRIGHT_HEADLESS", default=get_bool("CRAWLER_PLAYWRIGHT_HEADLESS", default=True)),
        obey_robots_txt=get_bool("CRAWLER_OBEY_ROBOTS_TXT", default=True),
        request_timeout_seconds=get_float("CRAWLER_REQUEST_TIMEOUT_SECONDS", default=30.0) or 30.0,
        request_delay_seconds=get_float("CRAWLER_REQUEST_DELAY_SECONDS", default=3.0) or 3.0,
        max_concurrency=get_int("CRAWLER_MAX_CONCURRENCY", default=1) or 1,
        max_run_seconds=2700.0,
        max_retries=get_int("CRAWLER_MAX_RETRIES", default=1) or 1,
        retry_backoff_seconds=get_float("CRAWLER_RETRY_BACKOFF_SECONDS", default=5.0) or 5.0,
        start_page=get_int("CRAWLER_START_PAGE", default=1) or 1,
        max_pages=get_int("CRAWLER_MAX_PAGES", default=5) or 5,
        max_records_per_page=get_int("CRAWLER_MAX_RECORDS_PER_PAGE", default=50) or 50,
        max_total_records=get_int("CRAWLER_MAX_TOTAL_RECORDS", default=250) or 250,
        date_mode=get_str("CRAWLER_DATE_MODE", default="LATEST") or "LATEST",
        date_from=get_str("CRAWLER_DATE_FROM", default=None),
        date_to=get_str("CRAWLER_DATE_TO", default=None),
    )
