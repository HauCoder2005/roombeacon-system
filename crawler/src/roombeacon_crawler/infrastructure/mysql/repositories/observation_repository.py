"""Implement idempotent MySQL persistence for Bronze observations."""

from datetime import datetime, timezone
import json
import logging
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import ObservationRepositoryPort
from roombeacon_crawler.models.persistence_context import PersistenceContext
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

logger = logging.getLogger(__name__)


class MySQLObservationRepository(ObservationRepositoryPort):
    """Repository quản lý bảng rental_post_versions (Bản ghi quan sát theo phiên)."""

    def __init__(self, connection=None) -> None:
        self.connection = connection

    def insert_observation(self, observation: BronzeObservation, post_id: int, context: PersistenceContext | None = None) -> tuple[int, bool]:
        """Ghi nhận bản ghi quan sát vào rental_post_versions.

        Trả về (version_id, is_inserted).
        Nếu (rental_post_id, crawl_run_id) đã tồn tại (Same-run retry) -> trả về (existing_id, False).
        """
        conn = self.connection or MySQLConnectionFactory.get_engine().connect()

        origin = context.ingestion_origin.value if context else 'UNKNOWN'

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

        insert_params = {
            "rental_post_id": post_id,
            "crawl_run_id": observation.run_id,
            "observed_at": obs_time,
            "url": observation.url,
            "title_raw": observation.title_raw[:500] if observation.title_raw else None,
            "content_hash": content_hash,
            "source_payload": json.dumps(observation.source_payload or {}, ensure_ascii=False),
            "ingestion_origin": origin,

        }
        query_insert = text(
            """
            INSERT INTO rental_post_versions (
                rental_post_id, crawl_run_id, observed_at, url, title_raw,
                content_hash, source_payload, ingestion_origin, created_at
            )
            VALUES (
                :rental_post_id, :crawl_run_id, :observed_at, :url, :title_raw,
                :content_hash, :source_payload, :ingestion_origin, NOW()
            )
            """
        )
        try:
            res = conn.execute(query_insert, insert_params)
        except IntegrityError as exc:
            error_args = getattr(exc.orig, "args", ())
            if not error_args or error_args[0] != 1062:
                raise
            existing = conn.execute(
                text(
                    """
                    SELECT id FROM rental_post_versions
                    WHERE rental_post_id = :rental_post_id
                      AND crawl_run_id = :crawl_run_id
                    LIMIT 1
                    """
                ),
                {
                    "rental_post_id": post_id,
                    "crawl_run_id": observation.run_id,
                },
            ).fetchone()
            if existing is None:
                raise
            return int(existing[0]), False
        return int(res.lastrowid or 0), True
