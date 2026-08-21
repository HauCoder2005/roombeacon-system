from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class BronzeObservation:
    """Mô hình dữ liệu quan sát chuẩn hóa (Canonical Domain Representation) của tầng Bronze.

    Mọi crawler output hoặc raw data đều được chuẩn hóa thành BronzeObservation
    trước khi được chuyển tiếp cho tầng Database Persistence (MySQL) xử lý.
    """

    source: str
    listing_id: str
    run_id: str
    url: str
    observed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    title_raw: str | None = None
    price_raw: str | None = None
    area_raw: str | None = None
    location_raw: str | None = None
    address_raw: str | None = None
    description_raw: str | None = None
    posted_at_raw: str | None = None
    property_type_raw: str | None = None
    furnishing_raw: str | None = None
    deposit_raw: str | None = None
    seller_name_raw: str | None = None
    seller_type_raw: str | None = None
    seller_phone_raw: str | None = None
    image_urls_raw: list[str] = field(default_factory=list)
    amenities_raw: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    source_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "listing_id": self.listing_id,
            "run_id": self.run_id,
            "url": self.url,
            "observed_at": self.observed_at,
            "title_raw": self.title_raw,
            "price_raw": self.price_raw,
            "area_raw": self.area_raw,
            "location_raw": self.location_raw,
            "address_raw": self.address_raw,
            "description_raw": self.description_raw,
            "posted_at_raw": self.posted_at_raw,
            "property_type_raw": self.property_type_raw,
            "furnishing_raw": self.furnishing_raw,
            "deposit_raw": self.deposit_raw,
            "seller_name_raw": self.seller_name_raw,
            "seller_type_raw": self.seller_type_raw,
            "seller_phone_raw": self.seller_phone_raw,
            "image_urls_raw": self.image_urls_raw,
            "amenities_raw": self.amenities_raw,
            "attributes": self.attributes,
            "source_payload": self.source_payload,
        }
