from dataclasses import dataclass, field

from roombeacon_crawler.enums.crawl_status import CrawlStatus


@dataclass
class CrawlRunResult:
    """Tổng kết thống kê và manifest phi vụ của một phiên crawl."""

    run_id: str
    source: str
    started_at: str
    finished_at: str
    target_url: str | None = None
    status: CrawlStatus = CrawlStatus.SUCCESS
    stop_reason: CrawlStatus | None = None
    failure_reason: str | None = None
    max_pages: int = 1
    max_records: int = 50
    crawl_details: bool = False
    pages_attempted: int = 0
    pages_success: int = 0
    pages_failed: int = 0
    details_success: int = 0
    details_failed: int = 0
    records_created: int = 0
    duplicates_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    manifest_path: str | None = None
    bronze_path: str | None = None
