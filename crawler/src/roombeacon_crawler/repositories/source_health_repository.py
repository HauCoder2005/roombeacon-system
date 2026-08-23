from abc import ABC, abstractmethod
from datetime import datetime

from roombeacon_crawler.models.source_health_state import (
    SourceHealthOutcome,
    SourceHealthState,
)


class SourceHealthRepository(ABC):
    """Giao diện trừu tượng quản lý trạng thái sức khỏe nguồn dữ liệu."""

    @abstractmethod
    def get_health(self, source: str, target_id: str) -> SourceHealthState | None:
        """Lấy trạng thái sức khỏe hiện tại của một target."""
        pass

    @abstractmethod
    def save_health(self, state: SourceHealthState) -> None:
        """Lưu trữ trạng thái sức khỏe an toàn (atomic)."""
        pass

    @abstractmethod
    def record_failure(
        self,
        source: str,
        target_id: str,
        outcome: SourceHealthOutcome,
        reason: str | None = None,
        http_status: int | None = None,
        current_time: datetime | None = None,
    ) -> SourceHealthState:
        """Ghi nhận một sự cố / rào cản và áp dụng cooldown tương ứng."""
        pass

    @abstractmethod
    def record_success(
        self,
        source: str,
        target_id: str,
        current_time: datetime | None = None,
    ) -> SourceHealthState:
        """Ghi nhận truy cập thành công và xóa bỏ cooldown."""
        pass
