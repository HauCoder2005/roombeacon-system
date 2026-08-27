from dataclasses import dataclass
from datetime import datetime


@dataclass
class CrawlMetadata:
    """Provide the demo-only CrawlMetadata contract used by the isolated example crawler."""
    source: str
    source_url: str
    run_id: str
    crawled_at: datetime
    status_code: int | None
