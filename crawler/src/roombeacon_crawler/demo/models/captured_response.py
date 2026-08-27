from dataclasses import dataclass

from roombeacon_crawler.demo.enums.fetch_strategy import FetchStrategy


@dataclass
class CapturedResponse:
    """Provide the demo-only CapturedResponse contract used by the isolated example crawler."""
    url: str
    final_url: str
    status_code: int
    html: str
    headers: dict[str, str]
    strategy: FetchStrategy
