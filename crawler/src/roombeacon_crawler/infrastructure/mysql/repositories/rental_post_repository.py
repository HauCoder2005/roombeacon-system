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
        query_find = text(
            """
            SELECT id FROM rental_posts
            WHERE platform_id = :platform_id AND platform_post_id = :platform_post_id
            LIMIT 1
            """
        )
        row = conn.execute(
            query_find,
            {"platform_id": platform_id, "platform_post_id": observation.listing_id},
        ).fetchone()

        obs_time = observation.observed_at or datetime.now(timezone.utc).isoformat()

        if row:
            post_id = int(row[0])
            query_update = text(
                """
                UPDATE rental_posts
                SET url = :url,
                    title_raw = COALESCE(:title_raw, title_raw),
                    last_observed_at = :last_observed_at,
                    updated_at = NOW()
                WHERE id = :id
                """
            )
            conn.execute(
                query_update,
                {
                    "id": post_id,
                    "url": observation.url,
                    "title_raw": observation.title_raw,
                    "last_observed_at": obs_time,
                },
            )
            return post_id, False
        else:
            query_insert = text(
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
                    url = VALUES(url),
                    title_raw = COALESCE(VALUES(title_raw), title_raw),
                    last_observed_at = VALUES(last_observed_at),
                    updated_at = NOW()
                """
            )
            res = conn.execute(
                query_insert,
                {
                    "platform_id": platform_id,
                    "platform_post_id": observation.listing_id,
                    "url": observation.url,
                    "title_raw": observation.title_raw,
                    "first_observed_at": obs_time,
                    "last_observed_at": obs_time,
                },
            )
            is_new = (res.rowcount == 1)
            row_new = conn.execute(
                query_find,
                {"platform_id": platform_id, "platform_post_id": observation.listing_id},
            ).fetchone()
            post_id = int(row_new[0]) if row_new else int(res.lastrowid or 0)
            return post_id, is_new
