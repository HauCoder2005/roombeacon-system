"""Decide whether a known listing requires detail refresh under its TTL.

The policy is pure: callers own detail acquisition, counters and deferred work.
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple


class RefreshDecision(NamedTuple):
    """Boolean refresh decision paired with its operational reason."""

    should_refresh: bool
    reason: str


class DetailRefreshPolicy:
    """Chính sách quyết định khi nào cần cào chi tiết (Detail Refresh) và khi nào ghi nhận quan sát nhẹ (Lightweight Observation)."""

    def __init__(self, default_ttl_hours: int = 24) -> None:
        self.default_ttl_hours = default_ttl_hours

    def evaluate(
        self,
        is_new: bool,
        card_changed: bool,
        last_detailed_at: datetime | str | None,
        current_time: datetime | None = None,
        custom_ttl_hours: int | None = None,
        detail_status: str | None = None,
    ) -> RefreshDecision:
        """Đánh giá xem một tin đăng có cần thực hiện request cào trang chi tiết (Detail Fetch) hay không.

        Quy tắc quyết định:
        1. NEW: Tin đăng mới chưa từng thấy -> BẮT BUỘC fetch detail.
        2. CARD_CHANGED: Tin đã biết nhưng trường nhẹ thay đổi -> BẮT BUỘC fetch detail (Forced refresh).
        3. ADDRESS_MISSING: Detail gần nhất không có address -> fetch lại có giới hạn.
        4. NO_PRIOR_DETAIL: Tin đã biết nhưng chưa từng có bản ghi detail -> fetch detail.
        5. TTL_EXPIRED: Đã quá hạn TTL kể từ lần fetch detail gần nhất -> fetch detail định kỳ.
        6. UNCHANGED_WITHIN_TTL: Đã biết, không đổi và còn trong hạn TTL -> BỎ QUA detail network request (Lightweight Observation).
        """
        if is_new:
            return RefreshDecision(should_refresh=True, reason="NEW_LISTING")

        if card_changed:
            return RefreshDecision(should_refresh=True, reason="CARD_CHANGED")

        if detail_status in {"SUCCESS_WITHOUT_ADDRESS", "ADDRESS_MISSING_RETRY"}:
            return RefreshDecision(should_refresh=True, reason="ADDRESS_MISSING")

        if last_detailed_at is None:
            return RefreshDecision(should_refresh=True, reason="NO_PRIOR_DETAIL")

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if isinstance(last_detailed_at, str):
            try:
                last_dt = datetime.fromisoformat(last_detailed_at)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
            except Exception:
                return RefreshDecision(should_refresh=True, reason="INVALID_TIMESTAMP")
        else:
            last_dt = last_detailed_at
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)

        effective_ttl = custom_ttl_hours if custom_ttl_hours is not None else self.default_ttl_hours
        ttl = timedelta(hours=effective_ttl)

        if (now - last_dt) >= ttl:
            return RefreshDecision(should_refresh=True, reason="TTL_EXPIRED")

        return RefreshDecision(should_refresh=False, reason="UNCHANGED_WITHIN_TTL")
