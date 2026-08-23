from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DeferredDetailItem:
    """Đại diện cho một công việc cào chi tiết bị hoãn (Deferred Detail Work Item).

    Lưu trữ thông tin vận hành tối giản và bền vững để phục vụ việc cào bổ sung
    trong các chu kỳ Airflow tiếp theo mà không cần quét lại trang danh mục cũ.
    """

    source: str
    platform_post_id: str
    detail_url: str
    origin_run_id: str
    first_deferred_at: str
    last_attempt_at: str | None = None
    attempt_count: int = 0
    reason: str = "REQUEST_BUDGET_EXHAUSTED"
    # PENDING, IN_PROGRESS, COMPLETED, TERMINAL_FAILED
    status: str = "PENDING"  
    last_error: str | None = None
    card_title: str | None = None
    card_price: str | None = None
    card_area: str | None = None
    card_location: str | None = None
    card_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeferredDetailItem":
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)
