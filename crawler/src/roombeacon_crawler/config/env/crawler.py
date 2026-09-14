from dataclasses import dataclass
from roombeacon_crawler.config.env.loader import get_bool, get_float, get_int, get_str


@dataclass(frozen=True, slots=True)
class CrawlerEnv:
    user_agent: str
    max_retries: int
    request_timeout_seconds: float
    obey_robots_txt: bool = True
    max_concurrency: int = 5
    request_delay_seconds: float = 1.0


def load_crawler_env() -> CrawlerEnv:
    return CrawlerEnv(
        user_agent=get_str("CRAWLER_USER_AGENT", default="RoomBeaconCrawler/0.1") or "RoomBeaconCrawler/0.1",
        max_retries=get_int("CRAWLER_MAX_RETRIES", default=3) or 3,
        request_timeout_seconds=get_float("CRAWLER_REQUEST_TIMEOUT_SECONDS", default=30.0) or 30.0,
        obey_robots_txt=get_bool("CRAWLER_OBEY_ROBOTS_TXT", default=True),
        max_concurrency=get_int("CRAWLER_MAX_CONCURRENCY", default=5) or 5,
        request_delay_seconds=get_float("CRAWLER_REQUEST_DELAY_SECONDS", default=1.0) or 1.0,
    )
