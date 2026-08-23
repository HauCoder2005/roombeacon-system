from dataclasses import dataclass

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy


@dataclass
class SourceSettings:
    """Cấu hình chi tiết cho từng website nguồn cụ thể."""

    source_name: str
    domain: str
    base_url: str
    default_strategy: FetchStrategy
    request_delay_seconds: float = env.crawler.request_delay_seconds
    max_concurrency: int = env.crawler.max_concurrency
    timeout: float = env.crawler.request_timeout_seconds
    robots_url: str | None = None
