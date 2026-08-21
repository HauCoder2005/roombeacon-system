import json
import re
from typing import Any
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation


class MySQLBronzeMapper:
    """Mapper chuyển đổi BronzeObservation sang các tham số bảng MySQL."""

    @staticmethod
    def parse_numeric_price(price_raw: str | None) -> float | None:
        """Trích xuất giá trị số từ chuỗi giá."""
        if not price_raw:
            return None
        cleaned = price_raw.lower().replace(",", ".").replace(" ", "")
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if not match:
            return None
        val = float(match.group(1))
        if "triệu" in cleaned or "tr" in cleaned:
            return val * 1_000_000.0
        elif "nghìn" in cleaned or "k" in cleaned:
            return val * 1_000.0
        elif "tỷ" in cleaned:
            return val * 1_000_000_000.0
        return val

    @staticmethod
    def parse_numeric_area(area_raw: str | None) -> float | None:
        """Trích xuất diện tích từ chuỗi."""
        if not area_raw:
            return None
        cleaned = area_raw.lower().replace(",", ".").replace(" ", "")
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if not match:
            return None
        return float(match.group(1))

    @classmethod
    def to_rental_post_params(cls, obs: BronzeObservation, platform_id: int) -> dict[str, Any]:
        """Chuẩn bị tham số cho câu lệnh upsert bảng rental_posts."""
        return {
            "platform_id": platform_id,
            "source_listing_id": obs.listing_id,
            "url": obs.url,
            "title_raw": obs.title_raw,
            "first_observed_at": obs.observed_at,
            "last_observed_at": obs.observed_at,
        }

    @classmethod
    def to_observation_params(cls, obs: BronzeObservation, post_id: int) -> dict[str, Any]:
        """Chuẩn bị tham số cho bảng raw_observations."""
        return {
            "post_id": post_id,
            "run_id": obs.run_id,
            "observed_at": obs.observed_at,
            "url": obs.url,
            "title_raw": obs.title_raw,
            "price_raw": obs.price_raw,
            "area_raw": obs.area_raw,
            "location_raw": obs.location_raw,
            "address_raw": obs.address_raw,
            "description_raw": obs.description_raw,
            "posted_at_raw": obs.posted_at_raw,
            "property_type_raw": obs.property_type_raw,
            "furnishing_raw": obs.furnishing_raw,
            "deposit_raw": obs.deposit_raw,
            "seller_name_raw": obs.seller_name_raw,
            "seller_type_raw": obs.seller_type_raw,
            "seller_phone_raw": obs.seller_phone_raw,
            "image_urls_raw": json.dumps(obs.image_urls_raw, ensure_ascii=False),
            "amenities_raw": json.dumps(obs.amenities_raw, ensure_ascii=False),
            "attributes": json.dumps(obs.attributes, ensure_ascii=False),
            "source_payload": json.dumps(obs.source_payload, ensure_ascii=False),
        }
