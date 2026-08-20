from dataclasses import asdict, dataclass


@dataclass
class CrawlTargetState:
    """Trạng thái lưu vết checkpoint của một crawl target."""

    source: str
    target_id: str
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    last_full_crawl_at: str | None = None
    last_watermark_at: str | None = None
    last_status: str | None = None
    last_stop_reason: str | None = None
    last_records_created: int = 0
    consecutive_failures: int = 0
    next_run_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlTargetState":
        return cls(
            source=data["source"],
            target_id=data["target_id"],
            last_started_at=data.get("last_started_at"),
            last_finished_at=data.get("last_finished_at"),
            last_success_at=data.get("last_success_at"),
            last_full_crawl_at=data.get("last_full_crawl_at"),
            last_watermark_at=data.get("last_watermark_at"),
            last_status=data.get("last_status"),
            last_stop_reason=data.get("last_stop_reason"),
            last_records_created=data.get("last_records_created", 0),
            consecutive_failures=data.get("consecutive_failures", 0),
            next_run_at=data.get("next_run_at"),
        )
