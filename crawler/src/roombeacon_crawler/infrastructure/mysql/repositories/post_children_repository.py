"""Persist version-scoped child observations in MySQL."""

import json
import logging
import math

from sqlalchemy import text

from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import PostChildrenRepositoryPort
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
from roombeacon_crawler.infrastructure.mysql.mappers.bronze_mapper import MySQLBronzeMapper

logger = logging.getLogger(__name__)


class MySQLPostChildrenRepository(PostChildrenRepositoryPort):
    """Persist price, address, detail, media, amenity and contact children."""

    def __init__(self, connection=None) -> None:
        self.connection = connection

    def persist_children(
        self,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        """Persist child rows in their established order and transaction."""
        connection = (
            self.connection or MySQLConnectionFactory.get_engine().connect()
        )
        self._persist_price(connection, observation, post_id, observation_id)
        self._persist_address(connection, observation, post_id, observation_id)
        self._persist_details(connection, observation, post_id, observation_id)
        self._persist_images(connection, observation, post_id, observation_id)
        self._persist_amenities(connection, observation, post_id, observation_id)
        self._persist_contact(connection, observation, post_id, observation_id)

    @staticmethod
    def _invalid_numeric_value(value, *, maximum: float) -> bool:
        return (
            not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            or value > maximum
        )

    @staticmethod
    def _has_detail_payload(observation: BronzeObservation) -> bool:
        """Return whether the observation contains a real detail-table value."""
        values = (
            observation.area_raw,
            observation.description_raw,
            observation.property_type_raw,
            observation.furnishing_raw,
            observation.deposit_raw,
            observation.posted_at_raw,
            observation.seller_name_raw,
            observation.seller_type_raw,
            observation.seller_phone_raw,
        )
        return any(
            value is not None and str(value).strip() for value in values
        )

    def _persist_price(
        self,
        connection,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        if not observation.price_raw:
            return

        normalized_price = MySQLBronzeMapper.parse_numeric_price(
            observation.price_raw
        )
        if (
            normalized_price is not None
            and self._invalid_numeric_value(
                normalized_price,
                maximum=999_999_999_999.99,
            )
        ):
            logger.warning(
                "Defensive guard: invalid price_amount %s rejected before insert, setting to NULL (price_raw=%s, post_id=%s)",
                normalized_price,
                str(observation.price_raw)[:50],
                post_id,
            )
            normalized_price = None

        insert_price = text(
            """
            INSERT INTO post_prices (rental_post_id, rental_post_version_id, price_raw, price_amount, currency, period, created_at)
            VALUES (:post_id, :version_id, :raw, :val, 'VND', 'MONTH', NOW())
            """
        )
        connection.execute(
            insert_price,
            {
                "post_id": post_id,
                "version_id": observation_id,
                "raw": observation.price_raw,
                "val": normalized_price,
            },
        )

    @staticmethod
    def _persist_address(
        connection,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        # ``location_raw`` is a coarse card label, not a confirmed address.
        observed_address = observation.address_raw
        lat = observation.latitude
        lng = observation.longitude

        if (
            isinstance(observed_address, str)
            and observed_address.lstrip().startswith("{")
        ):
            try:
                parsed = json.loads(observed_address)
                observed_address = parsed.get("address", observed_address)
                if lat is None and parsed.get("latitude") is not None:
                    lat = float(parsed.get("latitude"))
                if lng is None and parsed.get("longitude") is not None:
                    lng = float(parsed.get("longitude"))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning(
                    "Invalid structured address payload ignored (post_id=%s)",
                    post_id,
                )

        address_text = str(observed_address).strip() if observed_address else ""
        addr_val = address_text[:500] or None

        if (lat is not None and lng is None) or (lat is None and lng is not None):
            lat = None
            lng = None

        if addr_val is None and lat is None and lng is None:
            return

        insert_address = text(
            """
            INSERT INTO post_addresses (rental_post_id, rental_post_version_id, full_address_text, latitude, longitude, created_at)
            VALUES (:post_id, :version_id, :addr, :lat, :lng, NOW())
            """
        )
        connection.execute(
            insert_address,
            {
                "post_id": post_id,
                "version_id": observation_id,
                "addr": addr_val,
                "lat": lat,
                "lng": lng,
            },
        )

    def _persist_details(
        self,
        connection,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        if not self._has_detail_payload(observation):
            return

        normalized_area = MySQLBronzeMapper.parse_numeric_area(
            observation.area_raw
        )
        if (
            normalized_area is not None
            and self._invalid_numeric_value(
                normalized_area,
                maximum=99_999_999.99,
            )
        ):
            logger.warning(
                "Defensive guard: invalid area_value %s rejected before insert, setting to NULL (area_raw=%s, post_id=%s)",
                normalized_area,
                str(observation.area_raw)[:50] if observation.area_raw else "",
                post_id,
            )
            normalized_area = None

        insert_details = text(
            """
            INSERT INTO post_details (
                rental_post_id, rental_post_version_id, area_raw, area_value, description_raw, property_type_raw,
                furnishing_raw, deposit_raw, posted_at_raw, seller_name_raw, seller_type_raw,
                seller_phone_raw, attributes, created_at
            )
            VALUES (
                :post_id, :version_id, :area_raw, :area_val, :desc_raw, :prop_type, :furnishing, :deposit,
                :posted_at, :seller_name, :seller_type, :seller_phone, :attributes, NOW()
            )
            """
        )
        connection.execute(
            insert_details,
            {
                "post_id": post_id,
                "version_id": observation_id,
                "area_raw": observation.area_raw,
                "area_val": normalized_area,
                "desc_raw": observation.description_raw,
                "prop_type": observation.property_type_raw,
                "furnishing": observation.furnishing_raw,
                "deposit": observation.deposit_raw,
                "posted_at": observation.posted_at_raw,
                "seller_name": observation.seller_name_raw,
                "seller_type": observation.seller_type_raw,
                "seller_phone": observation.seller_phone_raw,
                "attributes": json.dumps(
                    observation.attributes or {},
                    ensure_ascii=False,
                ),
            },
        )

    @staticmethod
    def _persist_images(
        connection,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        if not observation.image_urls_raw:
            return

        image_rows = [
            {
                "post_id": post_id,
                "version_id": observation_id,
                "img_url": image_url.strip(),
                "pos": position,
            }
            for position, image_url in enumerate(
                observation.image_urls_raw,
                start=1,
            )
            if image_url
            and isinstance(image_url, str)
            and image_url.strip()
        ]
        if not image_rows:
            return

        insert_image = text(
            """
            INSERT INTO post_images (rental_post_id, rental_post_version_id, image_url, position, created_at)
            VALUES (:post_id, :version_id, :img_url, :pos, NOW())
            """
        )
        connection.execute(insert_image, image_rows)

    @staticmethod
    def _persist_amenities(
        connection,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        if not observation.amenities_raw:
            return

        amenity_rows = [
            {
                "post_id": post_id,
                "version_id": observation_id,
                "amenity": amenity.strip(),
            }
            for amenity in observation.amenities_raw
            if amenity and isinstance(amenity, str) and amenity.strip()
        ]
        if not amenity_rows:
            return

        insert_amenity = text(
            """
            INSERT INTO post_amenities (rental_post_id, rental_post_version_id, amenity_name, created_at)
            VALUES (:post_id, :version_id, :amenity, NOW())
            """
        )
        connection.execute(insert_amenity, amenity_rows)

    @staticmethod
    def _persist_contact(
        connection,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        if not observation.seller_phone_raw and not observation.seller_name_raw:
            return

        insert_contact = text(
            """
            INSERT INTO post_contacts (rental_post_id, rental_post_version_id, contact_name, contact_phone, contact_type, created_at)
            VALUES (:post_id, :version_id, :name, :phone, :type, NOW())
            """
        )
        connection.execute(
            insert_contact,
            {
                "post_id": post_id,
                "version_id": observation_id,
                "name": observation.seller_name_raw,
                "phone": observation.seller_phone_raw,
                "type": observation.seller_type_raw,
            },
        )
