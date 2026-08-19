from dataclasses import dataclass, field
from datetime import datetime, timezone

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType


@dataclass
class CrawlTarget:
    """Mô tả một URL mục tiêu cần được crawler xử lý."""

    url: str
    source: str
    target_type: CrawlTargetType
    page_number: int = 1
    parent_url: str | None = None
    listing_id: str | None = None
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
