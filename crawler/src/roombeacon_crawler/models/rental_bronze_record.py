from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RentalBronzeRecord:
    """Bản ghi hợp nhất dữ liệu thô (Bronze Layer) sau khi merge card + detail + metadata."""

    listing_id: str
    source: str
    url: str

    title_raw: str | None
    price_raw: str | None
    area_raw: str | None
    address_raw: str | None
    location_raw: str | None
    description_raw: str | None
    posted_at_raw: str | None

    property_type_raw: str | None = None
    furnishing_raw: str | None = None
    deposit_raw: str | None = None

    seller_name_raw: str | None = None
    seller_type_raw: str | None = None

    image_urls_raw: list[str] = field(default_factory=list)
    amenities_raw: list[str] = field(default_factory=list)

    crawl_run_id: str = ""
    crawled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
