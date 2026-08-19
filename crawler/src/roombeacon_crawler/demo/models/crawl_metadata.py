from dataclasses import dataclass
from datetime import datetime


@dataclass
class CrawlMetadata:
    source: str
    source_url: str
    run_id: str
    crawled_at: datetime
    status_code: int | None