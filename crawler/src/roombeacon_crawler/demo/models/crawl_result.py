from dataclasses import dataclass

from roombeacon_crawler.demo.models.crawl_record import CrawlRecord


@dataclass
class CrawlResult:
    """Provide the demo-only CrawlResult contract used by the isolated example crawler."""
    records: list[CrawlRecord]
    total: int
    success: bool
