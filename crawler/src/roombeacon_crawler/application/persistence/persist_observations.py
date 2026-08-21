from dataclasses import dataclass, field
import logging
from typing import Sequence

from roombeacon_crawler.domain.errors.domain_error import PersistenceError
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import (
    ObservationRepositoryPort,
    PlatformRepositoryPort,
    PostChildrenRepositoryPort,
    RentalPostRepositoryPort,
    TransactionManagerPort,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BronzeImportResult:
    """Kết quả tổng hợp phiên import Bronze Observations vào Database."""

    total_observations: int = 0
    posts_created: int = 0
    posts_existing: int = 0
    observations_inserted: int = 0
    technical_duplicates: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def successful_imports(self) -> int:
        return self.observations_inserted + self.technical_duplicates


class PersistBronzeObservationsUseCase:
    """Use-case nghiệp vụ: Nhập dữ liệu quan sát Bronze vào MySQL Database.

    Đảm bảo nguyên tắc Clean Architecture:
    1. Không chứa câu lệnh SQL trực tiếp.
    2. Giao dịch được bao bọc bởi một Transaction Boundary duy nhất (Unit of Work).
    3. Hỗ trợ tính lũy đẳng (Idempotency): Khi import lại cùng một run_id, không sinh duplicate records.
    4. Hoàn tác (Rollback) toàn bộ nếu xảy ra lỗi trong quá trình lưu trữ.
    """

    def __init__(
        self,
        platform_repo: PlatformRepositoryPort,
        rental_post_repo: RentalPostRepositoryPort,
        observation_repo: ObservationRepositoryPort,
        children_repo: PostChildrenRepositoryPort,
        transaction_mgr: TransactionManagerPort,
    ) -> None:
        self.platform_repo = platform_repo
        self.rental_post_repo = rental_post_repo
        self.observation_repo = observation_repo
        self.children_repo = children_repo
        self.transaction_mgr = transaction_mgr

    def execute(self, observations: Sequence[BronzeObservation]) -> BronzeImportResult:
        """Thực thi persist danh sách BronzeObservation."""
        result = BronzeImportResult(total_observations=len(observations))
        if not observations:
            return result

        try:
            self.transaction_mgr.begin()
            conn = getattr(self.transaction_mgr, "connection", None)
            if conn is not None:
                if hasattr(self.platform_repo, "connection"):
                    self.platform_repo.connection = conn
                if hasattr(self.rental_post_repo, "connection"):
                    self.rental_post_repo.connection = conn
                if hasattr(self.observation_repo, "connection"):
                    self.observation_repo.connection = conn
                if hasattr(self.children_repo, "connection"):
                    self.children_repo.connection = conn

            for obs in observations:
                # 1. Quản lý Platform
                platform_id = self.platform_repo.get_or_create_platform(
                    source_code=obs.source,
                    display_name=obs.source.capitalize(),
                    base_url=obs.url,
                )

                # 2. Quản lý Rental Post Identity (Stable entity)
                post_id, is_new_post = self.rental_post_repo.upsert_post(
                    obs, platform_id=platform_id
                )
                if is_new_post:
                    result.posts_created += 1
                else:
                    result.posts_existing += 1

                # 3. Quản lý Phiên bản Quan sát (rental_post_versions)
                version_id, is_inserted = self.observation_repo.insert_observation(
                    obs, post_id=post_id
                )

                # 4. Quản lý dữ liệu con liên kết (chỉ khi là observation mới)
                if is_inserted:
                    result.observations_inserted += 1
                    self.children_repo.persist_children(
                        obs, post_id=post_id, observation_id=version_id
                    )
                else:
                    result.technical_duplicates += 1

            self.transaction_mgr.commit()
            logger.info(
                "Persist Bronze hoàn tất: %d observations (Mới: %d, Trùng lặp kỹ thuật: %d, Posts mới: %d, Posts cũ: %d)",
                len(observations),
                result.observations_inserted,
                result.technical_duplicates,
                result.posts_created,
                result.posts_existing,
            )
        except Exception as exc:
            self.transaction_mgr.rollback()
            err_msg = f"Lỗi transaction khi persist Bronze observations: {exc}"
            logger.exception(err_msg)
            raise PersistenceError(err_msg) from exc
        finally:
            for repo in (self.platform_repo, self.rental_post_repo, self.observation_repo, self.children_repo):
                if hasattr(repo, "connection"):
                    repo.connection = None

        return result
