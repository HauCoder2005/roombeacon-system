import json
import logging
from sqlalchemy import text
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.domain.ports.persistence_port import PostChildrenRepositoryPort
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
from roombeacon_crawler.infrastructure.mysql.mappers.bronze_mapper import MySQLBronzeMapper

logger = logging.getLogger(__name__)


class MySQLPostChildrenRepository(PostChildrenRepositoryPort):
    """Repository quản lý các bảng con liên kết: post_prices, post_addresses, post_details, post_images, post_amenities, post_fees, post_contacts, post_attributes."""

    def __init__(self, connection=None) -> None:
        self.connection = connection

    def persist_children(
        self,
        observation: BronzeObservation,
        post_id: int,
        observation_id: int,
    ) -> None:
        conn = self.connection or MySQLConnectionFactory.get_engine().connect()

        # 1. Bảng giá (post_prices)
        if observation.price_raw:
            num_price = MySQLBronzeMapper.parse_numeric_price(observation.price_raw)
            query_price = text(
                """
                INSERT INTO post_prices (rental_post_id, rental_post_version_id, price_raw, price_amount, currency, period, created_at)
                VALUES (:post_id, :version_id, :raw, :val, 'VND', 'MONTH', NOW())
                """
            )
            conn.execute(
                query_price,
                {"post_id": post_id, "version_id": observation_id, "raw": observation.price_raw, "val": num_price},
            )

        # 2. Bảng địa chỉ / khu vực (post_addresses)
        addr_text = observation.address_raw or observation.location_raw
        if addr_text:
            query_addr = text(
                """
                INSERT INTO post_addresses (rental_post_id, rental_post_version_id, full_address_text, created_at)
                VALUES (:post_id, :version_id, :addr, NOW())
                """
            )
            conn.execute(
                query_addr,
                {
                    "post_id": post_id,
                    "version_id": observation_id,
                    "addr": addr_text[:500] if isinstance(addr_text, str) else str(addr_text)[:500],
                },
            )

        # 3. Bảng chi tiết (post_details)
        num_area = MySQLBronzeMapper.parse_numeric_area(observation.area_raw)
        query_details = text(
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
        conn.execute(
            query_details,
            {
                "post_id": post_id,
                "version_id": observation_id,
                "area_raw": observation.area_raw,
                "area_val": num_area,
                "desc_raw": observation.description_raw,
                "prop_type": observation.property_type_raw,
                "furnishing": observation.furnishing_raw,
                "deposit": observation.deposit_raw,
                "posted_at": observation.posted_at_raw,
                "seller_name": observation.seller_name_raw,
                "seller_type": observation.seller_type_raw,
                "seller_phone": observation.seller_phone_raw,
                "attributes": json.dumps(observation.attributes or {}, ensure_ascii=False),
            },
        )

        # 4. Bảng hình ảnh (post_images)
        if observation.image_urls_raw:
            query_img = text(
                """
                INSERT INTO post_images (rental_post_id, rental_post_version_id, image_url, position, created_at)
                VALUES (:post_id, :version_id, :img_url, :pos, NOW())
                """
            )
            for idx, img in enumerate(observation.image_urls_raw):
                if img and isinstance(img, str) and img.strip():
                    conn.execute(
                        query_img,
                        {"post_id": post_id, "version_id": observation_id, "img_url": img.strip(), "pos": idx + 1},
                    )

        # 5. Bảng tiện ích (post_amenities)
        if observation.amenities_raw:
            query_amenity = text(
                """
                INSERT INTO post_amenities (rental_post_id, rental_post_version_id, amenity_name, created_at)
                VALUES (:post_id, :version_id, :amenity, NOW())
                """
            )
            for item in observation.amenities_raw:
                if item and isinstance(item, str) and item.strip():
                    conn.execute(
                        query_amenity,
                        {"post_id": post_id, "version_id": observation_id, "amenity": item.strip()},
                    )

        # 6. Bảng danh bạ người đăng (post_contacts)
        if observation.seller_phone_raw or observation.seller_name_raw:
            query_contact = text(
                """
                INSERT INTO post_contacts (rental_post_id, rental_post_version_id, contact_name, contact_phone, contact_type, created_at)
                VALUES (:post_id, :version_id, :name, :phone, :type, NOW())
                """
            )
            conn.execute(
                query_contact,
                {
                    "post_id": post_id,
                    "version_id": observation_id,
                    "name": observation.seller_name_raw,
                    "phone": observation.seller_phone_raw,
                    "type": observation.seller_type_raw,
                },
            )
