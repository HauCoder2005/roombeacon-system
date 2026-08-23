from datetime import datetime, timedelta, timezone
from typing import ClassVar

from roombeacon_crawler.models.source_health_state import SourceHealthOutcome


class SourceHealthPolicy:
    """Chính sách tính toán thời gian nghỉ hồi phục (Adaptive Cooldown / Backoff Policy).

    Quy định:
    1. Thất bại do Access Challenge hoặc Lỗi tải Robots: Áp dụng chuỗi giãn cách tăng dần (15m, 30m, 60m, 6h, 12h, 24h).
    2. Thất bại do Network Timeout / HTTP 5xx: Áp dụng chuỗi ngắn hơn (5m, 15m, 30m, 60m).
    3. Thất bại do Browser Runtime: Bounded retry (15m, 30m, 60m) tránh quá tải cục bộ.
    4. Robots Denied: Là chính sách từ chối của website, không áp dụng retry liên tục cố chấp.
    5. Thành công (HEALTHY): Reset chuỗi, không áp dụng cooldown.
    """

    DEFAULT_BACKOFF_MINUTES: ClassVar[tuple[int, ...]] = (15, 30, 60, 360, 720, 1440)
    NETWORK_BACKOFF_MINUTES: ClassVar[tuple[int, ...]] = (5, 15, 30, 60)
    BROWSER_BACKOFF_MINUTES: ClassVar[tuple[int, ...]] = (15, 30, 60)

    def __init__(
        self,
        backoff_minutes: tuple[int, ...] | list[int] | None = None,
    ) -> None:
        self.backoff_minutes = tuple(backoff_minutes) if backoff_minutes else self.DEFAULT_BACKOFF_MINUTES

    def get_backoff_duration_minutes(
        self,
        outcome: SourceHealthOutcome,
        consecutive_failures: int,
    ) -> int:
        """Tính toán số phút cần nghỉ dựa trên loại kết quả và số lần thất bại liên tiếp."""
        if consecutive_failures <= 0 or outcome == SourceHealthOutcome.HEALTHY:
            return 0

        if outcome in (
            SourceHealthOutcome.ACCESS_CHALLENGE,
            SourceHealthOutcome.ROBOTS_FETCH_ERROR,
            SourceHealthOutcome.ROBOTS_UNAVAILABLE,
            SourceHealthOutcome.TECHNICAL_FAILURE,
            SourceHealthOutcome.PARSER_FAILURE,
            SourceHealthOutcome.STORAGE_FAILURE,
        ):
            idx = min(consecutive_failures - 1, len(self.backoff_minutes) - 1)
            return self.backoff_minutes[idx]

        if outcome in (
            SourceHealthOutcome.NETWORK_TIMEOUT,
            SourceHealthOutcome.HTTP_SERVER_ERROR,
        ):
            idx = min(consecutive_failures - 1, len(self.NETWORK_BACKOFF_MINUTES) - 1)
            return self.NETWORK_BACKOFF_MINUTES[idx]

        if outcome == SourceHealthOutcome.BROWSER_UNAVAILABLE:
            idx = min(consecutive_failures - 1, len(self.BROWSER_BACKOFF_MINUTES) - 1)
            return self.BROWSER_BACKOFF_MINUTES[idx]

        if outcome == SourceHealthOutcome.ROBOTS_DENIED:
            return 0

        # Mặc định
        idx = min(consecutive_failures - 1, len(self.backoff_minutes) - 1)
        return self.backoff_minutes[idx]

    def calculate_cooldown(
        self,
        outcome: SourceHealthOutcome,
        consecutive_failures: int,
        current_time: datetime | None = None,
    ) -> datetime | None:
        """Tính toán mốc thời gian UTC (cooldown_until) target được phép thử lại mạng."""
        duration_minutes = self.get_backoff_duration_minutes(outcome, consecutive_failures)
        if duration_minutes <= 0:
            return None

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        return now + timedelta(minutes=duration_minutes)
