import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation

logger = logging.getLogger(__name__)


def compute_observation_content_hash(
    title_raw: str | None = None,
    price_raw: str | None = None,
    area_raw: str | None = None,
    location_raw: str | None = None,
    address_raw: str | None = None,
    description_raw: str | None = None,
    property_type_raw: str | None = None,
    furnishing_raw: str | None = None,
    deposit_raw: str | None = None,
    seller_phone_raw: str | None = None,
    image_urls: list[str] | None = None,
    amenities: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> str:
    """Tính toán chuỗi hash SHA-256 tất định trên các trường nội dung quan sát được.

    Tuyệt đối không bao gồm run_id, observed_at, crawled_at, timestamps để đảm bảo
    tính ổn định khi so sánh nội dung giữa các lần crawl khác nhau.
    """
    meaningful_data = {
        "title": (title_raw or "").strip(),
        "price": (price_raw or "").strip(),
        "area": (area_raw or "").strip(),
        "location": (location_raw or "").strip(),
        "address": (address_raw or "").strip(),
        "description": (description_raw or "").strip(),
        "property_type": (property_type_raw or "").strip(),
        "furnishing": (furnishing_raw or "").strip(),
        "deposit": (deposit_raw or "").strip(),
        "seller_phone": (seller_phone_raw or "").strip(),
        "image_urls": sorted(image_urls or []),
        "amenities": sorted(amenities or []),
        "attributes": sorted(attributes.items()) if attributes else [],
    }
    serialized = json.dumps(meaningful_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class BronzeObservationLoader:
    """Đọc các artifact Bronze (listings.json, details.json) và chuyển đổi thành BronzeObservation."""

    @classmethod
    def load_from_bronze_dir(cls, bronze_dir_path: str | Path, run_id: str | None = None) -> list[BronzeObservation]:
        """Nạp danh sách BronzeObservation từ thư mục Bronze artifact."""
        path = Path(bronze_dir_path)
        listings_file = path / "listings.json"
        if not listings_file.exists():
            logger.warning("Không tìm thấy file listings.json tại: %s", path)
            return []

        with open(listings_file, "r", encoding="utf-8") as f:
            raw_listings = json.load(f)

        details_file = path / "details.json"
        details_by_id: dict[str, dict[str, Any]] = {}
        if details_file.exists():
            with open(details_file, "r", encoding="utf-8") as f:
                raw_details = json.load(f)
                for d in raw_details:
                    d_id = str(d.get("source_listing_id") or d.get("listing_id") or "")
                    if d_id:
                        details_by_id[d_id] = d

        observations: list[BronzeObservation] = []
        for item in raw_listings:
            lid = str(item.get("source_listing_id") or item.get("listing_id") or "")
            source = str(item.get("source") or "")
            obs_run_id = str(run_id or item.get("crawl_run_id") or item.get("run_id") or path.name)
            url = str(item.get("url") or item.get("detail_url") or "")
            title_raw = item.get("title_raw") or item.get("title")
            price_raw = item.get("price_raw") or item.get("price")
            area_raw = item.get("area_raw") or item.get("area")
            location_raw = item.get("location_raw") or item.get("location")
            address_raw = item.get("address_raw") or item.get("address")
            posted_at_raw = item.get("posted_at_raw") or item.get("published_at_raw") or item.get("posted_at")
            property_type_raw = item.get("property_type_raw") or item.get("property_type")
            seller_name_raw = item.get("seller_name_raw") or item.get("seller_name")
            seller_type_raw = item.get("seller_type_raw") or item.get("seller_type")
            seller_phone_raw = item.get("seller_phone_raw") or item.get("seller_phone")
            observed_at = str(item.get("crawled_at") or item.get("observed_at") or "")

            image_urls_raw = list(item.get("image_urls_raw") or item.get("images") or [])
            amenities_raw = list(item.get("amenities_raw") or item.get("amenities") or [])
            attributes = dict(item.get("attributes") or {})
            description_raw = item.get("description_raw") or item.get("description")
            furnishing_raw = item.get("furnishing_raw") or item.get("furnishing")
            deposit_raw = item.get("deposit_raw") or item.get("deposit")

            # Merge thông tin từ details.json nếu có
            if lid in details_by_id:
                dt = details_by_id[lid]
                description_raw = dt.get("description_raw") or dt.get("description") or description_raw
                address_raw = dt.get("address_raw") or dt.get("address") or address_raw
                furnishing_raw = dt.get("furnishing_raw") or dt.get("furnishing") or furnishing_raw
                deposit_raw = dt.get("deposit_raw") or dt.get("deposit") or deposit_raw
                seller_phone_raw = dt.get("seller_phone_raw") or dt.get("seller_phone") or seller_phone_raw
                seller_name_raw = dt.get("seller_name_raw") or dt.get("seller_name") or seller_name_raw
                dt_images = dt.get("image_urls_raw") or dt.get("images") or []
                if dt_images:
                    image_urls_raw = list(dict.fromkeys(image_urls_raw + list(dt_images)))
                dt_amenities = dt.get("amenities_raw") or dt.get("amenities") or []
                if dt_amenities:
                    amenities_raw = list(dict.fromkeys(amenities_raw + list(dt_amenities)))
                dt_attrs = dt.get("attributes") or {}
                if dt_attrs:
                    attributes.update(dt_attrs)

            content_hash = compute_observation_content_hash(
                title_raw=title_raw,
                price_raw=price_raw,
                area_raw=area_raw,
                location_raw=location_raw,
                address_raw=address_raw,
                description_raw=description_raw,
                property_type_raw=property_type_raw,
                furnishing_raw=furnishing_raw,
                deposit_raw=deposit_raw,
                seller_phone_raw=seller_phone_raw,
                image_urls=image_urls_raw,
                amenities=amenities_raw,
                attributes=attributes,
            )

            obs = BronzeObservation(
                source=source,
                listing_id=lid,
                run_id=obs_run_id,
                url=url,
                observed_at=observed_at or None,
                title_raw=title_raw,
                price_raw=price_raw,
                area_raw=area_raw,
                location_raw=location_raw,
                address_raw=address_raw,
                description_raw=description_raw,
                posted_at_raw=posted_at_raw,
                property_type_raw=property_type_raw,
                furnishing_raw=furnishing_raw,
                deposit_raw=deposit_raw,
                seller_name_raw=seller_name_raw,
                seller_type_raw=seller_type_raw,
                seller_phone_raw=seller_phone_raw,
                image_urls_raw=image_urls_raw,
                amenities_raw=amenities_raw,
                attributes=attributes,
                source_payload=item,
            )
            # Lưu content_hash vào attributes hoặc trường riêng
            obs.attributes["content_hash"] = content_hash
            observations.append(obs)

        return observations
