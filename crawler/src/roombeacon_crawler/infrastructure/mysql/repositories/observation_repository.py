from datetime import datetime, timezone
import json
import logging
from sqlalchemy import text
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import ObservationRepositoryPort
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

logger = logging.getLogger(__name__)


class MySQLObservationRepository(ObservationRepositoryPort):
    """Repository quản lý bảng rental_post_versions (Bản ghi quan sát theo phiên)."""

    def __init__(self, connection=None) -> None:
        self.connection = connection

    def insert_observation(self, observation: BronzeObservation, post_id: int) -> tuple[int, bool]:
        """Ghi nhận bản ghi quan sát vào rental_post_versions.

        Trả về (version_id, is_inserted).
        Nếu (rental_post_id, crawl_run_id) đã tồn tại (Same-run retry) -> trả về (existing_id, False).
        """
        conn = self.connection or MySQLConnectionFactory.get_engine().connect()

        # Kiểm tra tính lũy đẳng: Unique(rental_post_id, crawl_run_id)
        query_check = text(
            """
            SELECT id FROM rental_post_versions
            WHERE rental_post_id = :post_id AND crawl_run_id = :run_id
            LIMIT 1
            """
        )
        existing = conn.execute(
            query_check, {"post_id": post_id, "run_id": observation.run_id}
        ).fetchone()
        if existing:
            return int(existing[0]), False

        obs_time = observation.observed_at or datetime.now(timezone.utc).isoformat()
        content_hash = observation.attributes.get("content_hash", "")
        if not content_hash:
            from roombeacon_crawler.mappers.bronze_observation_loader import compute_observation_content_hash
            content_hash = compute_observation_content_hash(
                title_raw=observation.title_raw,
                price_raw=observation.price_raw,
                area_raw=observation.area_raw,
                location_raw=observation.location_raw,
                address_raw=observation.address_raw,
                description_raw=observation.description_raw,
                property_type_raw=observation.property_type_raw,
                furnishing_raw=observation.furnishing_raw,
                deposit_raw=observation.deposit_raw,
                seller_phone_raw=observation.seller_phone_raw,
                image_urls=observation.image_urls_raw,
                amenities=observation.amenities_raw,
                attributes=observation.attributes,
            )

        query_insert = text(
            """
            INSERT INTO rental_post_versions (
                rental_post_id, crawl_run_id, observed_at, url, title_raw,
                content_hash, source_payload, created_at
            )
            VALUES (
                :rental_post_id, :crawl_run_id, :observed_at, :url, :title_raw,
                :content_hash, :source_payload, NOW()
            )
            """
        )
        res = conn.execute(
            query_insert,
            {
                "rental_post_id": post_id,
                "crawl_run_id": observation.run_id,
                "observed_at": obs_time,
                "url": observation.url,
                "title_raw": observation.title_raw,
                "content_hash": content_hash,
                "source_payload": json.dumps(observation.source_payload or {}, ensure_ascii=False),
            },
        )
        version_id = int(res.lastrowid) if hasattr(res, "lastrowid") and res.lastrowid else 0
        if version_id == 0:
            row_new = conn.execute(
                query_check, {"post_id": post_id, "run_id": observation.run_id}
            ).fetchone()
            version_id = int(row_new[0]) if row_new else 0
        return version_id, True
