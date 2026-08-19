from dataclasses import dataclass, field


@dataclass
class ListingDetailRaw:
    """Dữ liệu thô bóc tách đầy đủ từ trang chi tiết tin đăng."""

    source: str
    listing_id: str | None
    detail_url: str

    title_raw: str | None
    price_raw: str | None
    area_raw: str | None

    address_raw: str | None
    location_raw: str | None

    description_raw: str | None

    posted_at_raw: str | None
    updated_at_raw: str | None = None

    property_type_raw: str | None = None
    furnishing_raw: str | None = None
    deposit_raw: str | None = None

    seller_name_raw: str | None = None
    seller_type_raw: str | None = None

    image_urls_raw: list[str] = field(default_factory=list)
    amenities_raw: list[str] = field(default_factory=list)
