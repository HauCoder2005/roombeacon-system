from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum


class SourceHealthOutcome(str, Enum):
    """Phân loại kết quả sức khỏe và rào cản kỹ thuật của nguồn dữ liệu."""

    HEALTHY = "HEALTHY"
    ACCESS_CHALLENGE = "ACCESS_CHALLENGE"
    ROBOTS_FETCH_ERROR = "ROBOTS_FETCH_ERROR"
    ROBOTS_UNAVAILABLE = "ROBOTS_UNAVAILABLE"
    ROBOTS_DENIED = "ROBOTS_DENIED"
    BROWSER_UNAVAILABLE = "BROWSER_UNAVAILABLE"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    HTTP_SERVER_ERROR = "HTTP_SERVER_ERROR"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    PARSER_FAILURE = "PARSER_FAILURE"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass
class SourceHealthState:
    """Trạng thái sức khỏe và năng lực kết nối mạng của nguồn (Source Health State).

    Hoàn toàn tách biệt khỏi CrawlTargetState (tiến độ đồng bộ dữ liệu / watermark).
    Chịu trách nhiệm theo dõi:
    - Nguồn có đang khỏe mạnh (HEALTHY) hay đang gặp sự cố/challenge?
    - Số lần thất bại liên tiếp (consecutive_failures)
    - Thời điểm hết hạn cooldown (cooldown_until) để Health Gate chặn request mạng không cần thiết.
    """

    source: str
    target_id: str = "default"
    last_outcome: SourceHealthOutcome = SourceHealthOutcome.HEALTHY
    last_failure_reason: str | None = None
    consecutive_failures: int = 0
    last_checked_at: str | None = None
    last_failure_at: str | None = None
    last_access_success_at: str | None = None
    cooldown_until: str | None = None
    last_http_status: int | None = None
    updated_at: str | None = None

    def is_in_cooldown(self, current_time: datetime | None = None) -> bool:
        """Kiểm tra xem target có đang trong thời gian nghỉ giãn cách (cooldown) hay không."""
        if not self.cooldown_until:
            return False
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        try:
            cd_dt = datetime.fromisoformat(self.cooldown_until)
            if cd_dt.tzinfo is None:
                cd_dt = cd_dt.replace(tzinfo=timezone.utc)
            return now < cd_dt
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Chuyển đổi sang dict an toàn cho JSON serialization."""
        d = asdict(self)
        if isinstance(self.last_outcome, Enum):
            d["last_outcome"] = self.last_outcome.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SourceHealthState":
        """Khởi tạo từ dict JSON."""
        outcome_raw = data.get("last_outcome", "HEALTHY")
        try:
            outcome = SourceHealthOutcome(outcome_raw)
        except Exception:
            outcome = SourceHealthOutcome.UNKNOWN
        return cls(
            source=data.get("source", "unknown"),
            target_id=data.get("target_id", "default"),
            last_outcome=outcome,
            last_failure_reason=data.get("last_failure_reason"),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            last_checked_at=data.get("last_checked_at"),
            last_failure_at=data.get("last_failure_at"),
            last_access_success_at=data.get("last_access_success_at"),
            cooldown_until=data.get("cooldown_until"),
            last_http_status=data.get("last_http_status"),
            updated_at=data.get("updated_at"),
        )
