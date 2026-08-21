from abc import ABC, abstractmethod
from typing import Any
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation


class PlatformRepositoryPort(ABC):
    """Port giao tiếp quản lý danh mục nền tảng (Platform / Sources)."""

    @abstractmethod
    def get_or_create_platform(self, source_code: str, display_name: str, base_url: str) -> int:
        """Trả về platform_id trong cơ sở dữ liệu."""
        pass


class RentalPostRepositoryPort(ABC):
    """Port giao tiếp quản lý bảng gốc bài đăng bất động sản (rental_posts)."""

    @abstractmethod
    def upsert_post(self, observation: BronzeObservation, platform_id: int) -> int:
        """Thực hiện upsert rental_post và trả về post_id."""
        pass


class ObservationRepositoryPort(ABC):
    """Port giao tiếp ghi nhận bản ghi quan sát bất biến (raw_observations)."""

    @abstractmethod
    def insert_observation(self, observation: BronzeObservation, post_id: int) -> int:
        """Ghi nhận bản ghi quan sát theo phiên và trả về observation_id."""
        pass


class PostChildrenRepositoryPort(ABC):
    """Port giao tiếp lưu trữ các thông tin chi tiết con (giá, địa chỉ, tiện ích, hình ảnh)."""

    @abstractmethod
    def persist_children(
        self,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        """Lưu trữ dữ liệu con liên kết với observation."""
        pass


class TransactionManagerPort(ABC):
    """Port quản lý ranh giới giao dịch (Unit of Work / Transaction boundary)."""

    @abstractmethod
    def begin(self) -> Any:
        """Bắt đầu transaction."""
        pass

    @abstractmethod
    def commit(self) -> None:
        """Xác nhận transaction."""
        pass

    @abstractmethod
    def rollback(self) -> None:
        """Hủy transaction khi có lỗi."""
        pass
