from dataclasses import asdict, dataclass
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType


@dataclass(frozen=True, slots=True)
class CrawlSeed:
    """Mô hình cấu hình tĩnh bất biến đại diện cho một điểm vào (crawl seed / scheduled target)."""

    source: str
    target_id: str
    url: str
    enabled: bool = True
    interval_minutes: int = 60
    crawl_details: bool = False
    bootstrap_safety_max_pages: int = 50
    bootstrap_safety_max_records: int = 1000
    incremental_overlap_hours: int = 24
    incremental_stop_after_known_pages: int = 2
    max_details_per_run: int = 20
    target_type_hint: CrawlTargetType = CrawlTargetType.LISTING_PAGE
    label: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target_id": self.target_id,
            "url": self.url,
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "crawl_details": self.crawl_details,
            "bootstrap_safety_max_pages": self.bootstrap_safety_max_pages,
            "bootstrap_safety_max_records": self.bootstrap_safety_max_records,
            "incremental_overlap_hours": self.incremental_overlap_hours,
            "incremental_stop_after_known_pages": self.incremental_stop_after_known_pages,
            "max_details_per_run": self.max_details_per_run,
            "target_type_hint": (
                self.target_type_hint.value
                if isinstance(self.target_type_hint, CrawlTargetType)
                else str(self.target_type_hint)
            ),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlSeed":
        type_hint = data.get("target_type_hint")
        if isinstance(type_hint, str):
            try:
                type_hint = CrawlTargetType(type_hint)
            except ValueError:
                type_hint = CrawlTargetType.LISTING_PAGE
        elif not isinstance(type_hint, CrawlTargetType):
            type_hint = CrawlTargetType.LISTING_PAGE

        target_id = data.get("target_id") or data.get("label") or "default"

        return cls(
            source=data["source"],
            target_id=target_id,
            url=data["url"],
            enabled=data.get("enabled", True),
            interval_minutes=data.get("interval_minutes", 60),
            crawl_details=data.get("crawl_details", False),
            bootstrap_safety_max_pages=data.get("bootstrap_safety_max_pages", 50),
            bootstrap_safety_max_records=data.get("bootstrap_safety_max_records", 1000),
            incremental_overlap_hours=data.get("incremental_overlap_hours", 24),
            incremental_stop_after_known_pages=data.get("incremental_stop_after_known_pages", 2),
            max_details_per_run=data.get("max_details_per_run", 20),
            target_type_hint=type_hint,
            label=data.get("label"),
        )
