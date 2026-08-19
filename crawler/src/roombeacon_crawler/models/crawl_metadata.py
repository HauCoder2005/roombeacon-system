from dataclasses import dataclass

from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy


@dataclass
class CrawlMetadata:
    """Metadata kỹ thuật thực tế thu thập được trong quá trình thực hiện request."""

    run_id: str
    source: str
    target_type: CrawlTargetType
    request_url: str
    final_url: str
    page_number: int
    fetch_strategy: FetchStrategy
    http_status: int
    content_type: str | None
    server: str | None
    cf_ray: str | None
    html_size: int
    started_at: str
    finished_at: str
    elapsed_ms: float
    retry_count: int
    robots_allowed: bool
    crawl_status: CrawlStatus
