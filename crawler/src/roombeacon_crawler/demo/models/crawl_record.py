from dataclasses import dataclass


@dataclass
class CrawlRecord:
    title: str | None
    price: str | None
    area: str | None
    location: str | None
    url: str