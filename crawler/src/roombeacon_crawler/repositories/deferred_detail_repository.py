"""Define the persistence contract for deferred listing-detail work."""

from abc import ABC, abstractmethod
from datetime import datetime
from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem


class DeferredDetailRepository(ABC):
    """Interface trừu tượng quản lý hàng đợi hoãn cào chi tiết (Deferred Detail Backlog)."""

    @abstractmethod
    def get_backlog(
        self, source: str, target_id: str, *, now: datetime | None = None
    ) -> list[DeferredDetailItem]:
        """Lấy danh sách các công việc cào chi tiết đang chờ xử lý (PENDING)."""
        ...

    @abstractmethod
    def count_backlog(self, source: str, target_id: str) -> int:
        """Đếm số lượng công việc cào chi tiết đang chờ xử lý."""
        ...

    @abstractmethod
    def enqueue(
        self, source: str, target_id: str, items: list[DeferredDetailItem]
    ) -> int:
        """Thêm các công việc mới vào backlog. Trả về số lượng công việc thực sự được thêm mới (loại trừ trùng lặp)."""
        ...

    @abstractmethod
    def record_success(
        self, source: str, target_id: str, platform_post_id: str
    ) -> None:
        """Đánh dấu công việc đã cào chi tiết thành công và hoàn tất."""
        ...

    @abstractmethod
    def record_failure(
        self,
        source: str,
        target_id: str,
        platform_post_id: str,
        error: str,
        is_terminal: bool = False,
        max_retries: int = 3,
        now: datetime | None = None,
        retry_backoff_seconds: int = 900,
    ) -> None:
        """Ghi nhận thất bại cho một công việc; đánh dấu terminal nếu đạt tối đa số lần thử."""
        ...
