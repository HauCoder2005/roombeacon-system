from dataclasses import asdict, dataclass
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType


@dataclass(frozen=True, slots=True)
class CrawlSeed:
    """Mô hình dữ liệu bất biến đại diện cho một điểm vào (crawl seed / scheduled target)."""

    source: str
    url: str
    enabled: bool = True
    target_type_hint: CrawlTargetType = CrawlTargetType.LISTING_PAGE
    label: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "url": self.url,
            "enabled": self.enabled,
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

        return cls(
            source=data["source"],
            url=data["url"],
            enabled=data.get("enabled", True),
            target_type_hint=type_hint,
            label=data.get("label"),
        )
