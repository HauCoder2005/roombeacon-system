from abc import ABC, abstractmethod
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState


class CrawlStateRepository(ABC):
    """Interface trừu tượng quản lý lưu vết checkpoint và danh sách listing đã thấy."""

    @abstractmethod
    def get_state(self, source: str, target_id: str) -> CrawlTargetState | None:
        """Lấy trạng thái checkpoint của một crawl target."""
        ...

    @abstractmethod
    def save_state(self, state: CrawlTargetState) -> None:
        """Lưu cập nhật trạng thái checkpoint an toàn."""
        ...

    @abstractmethod
    def get_seen_listing_ids(self, source: str, target_id: str) -> set[str]:
        """Lấy tập hợp các listing_id đã từng thu thập cho target này."""
        ...

    @abstractmethod
    def record_seen_listing_ids(
        self, source: str, target_id: str, listing_ids: set[str] | list[str]
    ) -> None:
        """Ghi nhận thêm danh sách listing_id mới vào tập seen."""
        ...
