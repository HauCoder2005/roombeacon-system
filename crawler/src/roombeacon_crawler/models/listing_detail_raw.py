from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ListingDetailRaw:
    """Dữ liệu thô bóc tách đầy đủ từ trang chi tiết tin đăng (Bronze Detail Layer)."""

    source: str
    listing_id: str | None
    detail_url: str

    title_raw: str | None = None
    price_raw: str | None = None
    area_raw: str | None = None
    address_raw: str | None = None
    location_raw: str | None = None
    description_raw: str | None = None
    posted_at_raw: str | None = None
    updated_at_raw: str | None = None

    property_type_raw: str | None = None
    room_type_raw: str | None = None
    position_raw: str | None = None
    furnishing_raw: str | None = None
    deposit_raw: str | None = None

    electricity_cost_raw: str | None = None
    water_cost_raw: str | None = None
    management_fee_raw: str | None = None
    parking_fee_raw: str | None = None
    internet_fee_raw: str | None = None

    available_rooms_raw: str | None = None
    total_rooms_raw: str | None = None
    verification_raw: str | None = None

    seller_name_raw: str | None = None
    seller_type_raw: str | None = None

    image_urls_raw: list[str] = field(default_factory=list)
    amenities_raw: list[str] = field(default_factory=list)

    crawl_run_id: str | None = None
    crawled_at: str | None = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
