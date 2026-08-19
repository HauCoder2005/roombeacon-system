from dataclasses import dataclass

from roombeacon_crawler.demo.models.crawl_record import CrawlRecord


@dataclass
class CrawlResult:
    records: list[CrawlRecord]
    total: int
    success: bool