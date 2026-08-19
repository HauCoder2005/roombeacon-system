from dataclasses import dataclass, field


@dataclass
class CrawlRunResult:
    """Tổng kết thống kê toàn bộ một phiên crawl."""

    run_id: str
    source: str
    started_at: str
    finished_at: str
    pages_success: int = 0
    pages_failed: int = 0
    details_success: int = 0
    details_failed: int = 0
    records_created: int = 0
    duplicates_skipped: int = 0
    errors: list[str] = field(default_factory=list)
