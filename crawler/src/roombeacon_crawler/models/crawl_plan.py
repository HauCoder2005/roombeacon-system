from dataclasses import dataclass
from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.discovery.strategy_resolver import DiscoveryStrategy


@dataclass(frozen=True, slots=True)
class CrawlPlan:
    """Kế hoạch thực thi cào dữ liệu được tính toán bởi CrawlPlanner."""

    source: str
    target_id: str
    target_url: str
    mode: CrawlMode
    reason: str
    planned_at: str
    watermark_from: str | None = None
    overlap_from: str | None = None
    crawl_details: bool = False
    safety_max_pages: int = 50
    safety_max_records: int = 1000
    incremental_stop_after_known_pages: int = 2
    max_details_per_run: int = 20
    discovery_strategy: DiscoveryStrategy = DiscoveryStrategy.STANDARD
    start_page: int = 1

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target_id": self.target_id,
            "target_url": self.target_url,
            "mode": self.mode.value if isinstance(self.mode, CrawlMode) else str(self.mode),
            "reason": self.reason,
            "planned_at": self.planned_at,
            "watermark_from": self.watermark_from,
            "overlap_from": self.overlap_from,
            "crawl_details": self.crawl_details,
            "safety_max_pages": self.safety_max_pages,
            "safety_max_records": self.safety_max_records,
            "incremental_stop_after_known_pages": self.incremental_stop_after_known_pages,
            "max_details_per_run": self.max_details_per_run,
            "discovery_strategy": (
                self.discovery_strategy.value
                if isinstance(self.discovery_strategy, DiscoveryStrategy)
                else str(self.discovery_strategy)
            ),
            "start_page": self.start_page,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlPlan":
        mode_val = data["mode"]
        if isinstance(mode_val, str):
            try:
                mode_enum = CrawlMode(mode_val)
            except ValueError:
                mode_enum = CrawlMode.BOOTSTRAP_FULL
        else:
            mode_enum = mode_val

        strategy_val = data.get("discovery_strategy", DiscoveryStrategy.STANDARD)
        if isinstance(strategy_val, str):
            try:
                strategy_enum = DiscoveryStrategy(strategy_val)
            except ValueError:
                strategy_enum = DiscoveryStrategy.STANDARD
        else:
            strategy_enum = strategy_val

        return cls(
            source=data["source"],
            target_id=data.get("target_id", "default"),
            target_url=data["target_url"],
            mode=mode_enum,
            reason=data.get("reason", ""),
            planned_at=data["planned_at"],
            watermark_from=data.get("watermark_from"),
            overlap_from=data.get("overlap_from"),
            crawl_details=data.get("crawl_details", False),
            safety_max_pages=data.get("safety_max_pages", 50),
            safety_max_records=data.get("safety_max_records", 1000),
            incremental_stop_after_known_pages=data.get("incremental_stop_after_known_pages", 2),
            max_details_per_run=data.get("max_details_per_run", 20),
            discovery_strategy=strategy_enum,
            start_page=int(data.get("start_page", 1) or 1),
        )
