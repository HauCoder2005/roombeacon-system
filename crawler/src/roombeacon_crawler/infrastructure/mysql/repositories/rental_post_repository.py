"""Implement canonical rental-post identity and version writes in MySQL."""

from datetime import datetime, timezone
import logging
from sqlalchemy import text
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import RentalPostRepositoryPort
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

logger = logging.getLogger(__name__)


class MySQLRentalPostRepository(RentalPostRepositoryPort):
    """Repository quản lý bảng rental_posts (Bảng định danh bài đăng gốc)."""

    def __init__(self, connection=None) -> None:
        self.connection = connection

    def upsert_post(self, observation: BronzeObservation, platform_id: int) -> tuple[int, bool]:
        """Upsert bài đăng. Trả về (post_id, is_new)."""
        conn = self.connection or MySQLConnectionFactory.get_engine().connect()
        obs_time = observation.observed_at or datetime.now(timezone.utc).isoformat()
        query = text(
            """
            INSERT INTO rental_posts (
                platform_id, platform_post_id, url, title_raw,
                first_observed_at, last_observed_at, created_at, updated_at
            )
            VALUES (
                :platform_id, :platform_post_id, :url, :title_raw,
                :first_observed_at, :last_observed_at, NOW(), NOW()
            )
            ON DUPLICATE KEY UPDATE
                id = LAST_INSERT_ID(id),
                url = VALUES(url),
                title_raw = COALESCE(VALUES(title_raw), title_raw),
                last_observed_at = VALUES(last_observed_at),
                updated_at = NOW()
            """
        )
        res = conn.execute(
            query,
            {
                "platform_id": platform_id,
                "platform_post_id": observation.listing_id,
                "url": observation.url,
                "title_raw": observation.title_raw,
                "first_observed_at": obs_time,
                "last_observed_at": obs_time,
            },
        )
        return int(res.lastrowid or 0), res.rowcount == 1
