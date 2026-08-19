from dataclasses import dataclass

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy


@dataclass
class SourceSettings:
    """Cấu hình chi tiết cho từng website nguồn cụ thể."""

    source_name: str
    domain: str
    base_url: str
    default_strategy: FetchStrategy
    request_delay_seconds: float = 1.5
    max_concurrency: int = 1
    timeout: float = 30.0
    robots_url: str | None = None
