from abc import ABC, abstractmethod
from typing import Any
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord
from roombeacon_crawler.models.source_health_state import SourceHealthState


class BronzeWriterPort(ABC):
    """Port giao tiếp lưu trữ dữ liệu thô Bronze (Filesystem / S3 / MinIO)."""

    @abstractmethod
    def save_bronze_dataset(
        self,
        source: str,
        run_id: str,
        listing_records: list[RentalBronzeRecord],
        metadata_list: list[CrawlMetadata],
    ) -> str | None:
        """Lưu trữ Bronze dataset và trả về URI/đường dẫn."""
        pass

    @abstractmethod
    def save_manifest(self, result: CrawlRunResult) -> str:
        """Lưu trữ Run Manifest và trả về đường dẫn."""
        pass


class CheckpointRepositoryPort(ABC):
    """Port giao tiếp quản lý vết trạng thái crawl (CrawlTargetState)."""

    @abstractmethod
    def get_state(self, source: str, target_id: str) -> CrawlTargetState | None:
        """Truy xuất state theo source và target_id."""
        pass

    @abstractmethod
    def save_state(self, state: CrawlTargetState) -> None:
        """Lưu trữ checkpoint state."""
        pass


class SeenListingRepositoryPort(ABC):
    """Port giao tiếp quản lý danh sách định danh tin đã thấy."""

    @abstractmethod
    def get_seen_listing_ids(self, source: str, target_id: str) -> set[str]:
        """Lấy tập hợp các listing ID đã thấy trong quá khứ."""
        pass

    @abstractmethod
    def record_seen_listing_ids(
        self, source: str, target_id: str, listing_ids: list[str] | set[str]
    ) -> None:
        """Ghi nhận thêm các listing ID đã thấy vào persistent storage."""
        pass


class SourceHealthRepositoryPort(ABC):
    """Port giao tiếp quản lý tình trạng sức khỏe nguồn (SourceHealthState)."""

    @abstractmethod
    def get_health(self, source: str, target_id: str) -> SourceHealthState | None:
        """Truy xuất health state."""
        pass

    @abstractmethod
    def save_health(self, health: SourceHealthState) -> None:
        """Lưu trữ health state."""
        pass
