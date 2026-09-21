"""Persist a batch of Bronze observations inside one application transaction.

The use case coordinates repository ports, idempotency and bounded deadlock
retries. It does not parse artifacts or own scheduler error translation.
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Sequence

from roombeacon_crawler.domain.errors.domain_error import PersistenceError
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.models.persistence_context import PersistenceContext
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
    transaction_begin_seconds: float = 0.0
    platform_seconds: float = 0.0
    rental_posts_seconds: float = 0.0
    rental_post_versions_seconds: float = 0.0
    children_seconds: float = 0.0
    commit_seconds: float = 0.0

    @property
    def successful_imports(self) -> int:
        """Count observations that were inserted or already safely persisted."""
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

    def execute(self, observations: Sequence[BronzeObservation], context: PersistenceContext | None = None) -> BronzeImportResult:
        """Thực thi persist danh sách BronzeObservation."""
        if not observations:
            return BronzeImportResult(total_observations=0)

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            result = BronzeImportResult(total_observations=len(observations))
            try:
                phase_started = time.perf_counter()
                self.transaction_mgr.begin()
                result.transaction_begin_seconds = time.perf_counter() - phase_started
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

                platform_ids: dict[str, int] = {}
                for obs in observations:
                    platform_id = platform_ids.get(obs.source)
                    if platform_id is None:
                        phase_started = time.perf_counter()
                        platform_id = self.platform_repo.get_or_create_platform(
                            source_code=obs.source,
                            display_name=obs.source.capitalize(),
                            base_url=obs.url,
                        )
                        result.platform_seconds += time.perf_counter() - phase_started
                        platform_ids[obs.source] = platform_id

                    phase_started = time.perf_counter()
                    post_id, is_new_post = self.rental_post_repo.upsert_post(
                        obs, platform_id=platform_id
                    )
                    result.rental_posts_seconds += time.perf_counter() - phase_started
                    if is_new_post:
                        result.posts_created += 1
                    else:
                        result.posts_existing += 1

                    phase_started = time.perf_counter()
                    version_id, is_inserted = self.observation_repo.insert_observation(
                        obs, post_id=post_id, context=context
                    )
                    result.rental_post_versions_seconds += time.perf_counter() - phase_started

                    if is_inserted:
                        result.observations_inserted += 1
                        phase_started = time.perf_counter()
                        self.children_repo.persist_children(
                            obs, post_id=post_id, observation_id=version_id
                        )
                        result.children_seconds += time.perf_counter() - phase_started
                    else:
                        result.technical_duplicates += 1

                phase_started = time.perf_counter()
                self.transaction_mgr.commit()
                result.commit_seconds = time.perf_counter() - phase_started
                logger.info(
                    "Persist Bronze hoàn tất: %d observations (Mới: %d, Trùng lặp kỹ thuật: %d, Posts mới: %d, Posts cũ: %d)",
                    len(observations),
                    result.observations_inserted,
                    result.technical_duplicates,
                    result.posts_created,
                    result.posts_existing,
                )
                return result
            except Exception as exc:
                self.transaction_mgr.rollback()
                is_deadlock = "1213" in str(exc) or "deadlock" in str(exc).lower()
                if is_deadlock and attempt < max_retries:
                    import random
                    sleep_time = (0.2 * (2 ** attempt)) + random.uniform(0.05, 0.15)
                    logger.warning(
                        "MySQL deadlock; retrying persistence (attempt=%d/%d, delay_seconds=%.2f, error_class=%s)",
                        attempt,
                        max_retries,
                        sleep_time,
                        type(exc).__name__,
                    )
                    time.sleep(sleep_time)
                    continue

                logger.error(
                    "Bronze persistence transaction failed (attempt=%d/%d, error_class=%s, deadlock=%s)",
                    attempt,
                    max_retries,
                    type(exc).__name__,
                    is_deadlock,
                )
                raise PersistenceError(
                    "Bronze persistence transaction failed"
                ) from None
            finally:
                for repo in (self.platform_repo, self.rental_post_repo, self.observation_repo, self.children_repo):
                    if hasattr(repo, "connection"):
                        repo.connection = None

        return result
