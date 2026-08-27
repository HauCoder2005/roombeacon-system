from dataclasses import dataclass


@dataclass
class CrawlRecord:
    """Provide the demo-only CrawlRecord contract used by the isolated example crawler."""
    title: str | None
    price: str | None
    area: str | None
    location: str | None
    url: str
