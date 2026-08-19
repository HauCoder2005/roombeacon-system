from dataclasses import dataclass, field
from datetime import datetime, timezone

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy


@dataclass
class CapturedResponse:
    """Kết quả thu thập phản hồi thô sau khi gửi HTTP request hoặc render Browser."""

    request_url: str
    final_url: str
    status_code: int
    html: str
    headers: dict[str, str]
    fetch_strategy: FetchStrategy
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    elapsed_ms: float = 0.0
