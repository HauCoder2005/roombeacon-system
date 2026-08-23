import json
import logging
import math
import re
from typing import Any
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation

logger = logging.getLogger(__name__)


class MySQLBronzeMapper:
    """Mapper chuyển đổi BronzeObservation sang các tham số bảng MySQL."""

    # Plausibility bounds for Vietnamese rental market
    MIN_PLAUSIBLE_AREA_M2: float = 0.5
    MAX_PLAUSIBLE_AREA_M2: float = 100_000.0  # 10 ha max for rental listing / land / warehouse

    MIN_PLAUSIBLE_PRICE_VND: float = 1_000.0
    MAX_PLAUSIBLE_PRICE_VND: float = 100_000_000_000.0  # 100 billion VND max for rental price

    @classmethod
    def parse_numeric_price(cls, price_raw: str | None) -> float | None:
        """Trích xuất giá trị số từ chuỗi giá với plausibility guard."""
        if not price_raw:
            return None
        if not isinstance(price_raw, str):
            price_raw = str(price_raw)
            
        cleaned = price_raw.strip().lower()
        if not cleaned or cleaned in ("thỏa thuận", "thoa thuan", "thương lượng", "thuong luong", "liên hệ", "lien he", "n/a", "none", "null"):
            return None

        cleaned_num = cleaned.replace(",", ".").replace(" ", "")
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned_num)
        if not match:
            return None
            
        try:
            val = float(match.group(1))
            if "triệu" in cleaned or "tr" in cleaned:
                val = val * 1_000_000.0
            elif "nghìn" in cleaned or "k" in cleaned:
                val = val * 1_000.0
            elif "tỷ" in cleaned or "ty" in cleaned:
                val = val * 1_000_000_000.0

            if not math.isfinite(val) or val < cls.MIN_PLAUSIBLE_PRICE_VND or val > cls.MAX_PLAUSIBLE_PRICE_VND:
                logger.warning(
                    "Price normalization out of plausible range: raw=%s parsed=%s",
                    price_raw[:50],
                    val,
                )
                return None
            return round(val, 2)
        except (ValueError, TypeError):
            return None

    @classmethod
    def parse_numeric_area(cls, area_raw: str | None) -> float | None:
        """Trích xuất diện tích từ chuỗi với plausibility guard."""
        if not area_raw:
            return None
        if not isinstance(area_raw, str):
            area_raw = str(area_raw)

        cleaned = area_raw.strip().lower()
        if not cleaned or cleaned in ("liên hệ", "lien he", "thỏa thuận", "thoa thuan", "thương lượng", "thuong luong", "n/a", "none", "null"):
            return None

        cleaned_num = cleaned.replace(",", ".").replace(" ", "")
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned_num)
        if not match:
            return None

        try:
            val = float(match.group(1))
            if not math.isfinite(val) or val < cls.MIN_PLAUSIBLE_AREA_M2 or val > cls.MAX_PLAUSIBLE_AREA_M2:
                logger.warning(
                    "Area normalization out of plausible range: raw=%s parsed=%s",
                    area_raw[:50],
                    val,
                )
                return None
            return round(val, 2)
        except (ValueError, TypeError):
            return None

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
