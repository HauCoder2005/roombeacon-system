from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ListingCardRaw:
    """Dữ liệu thô bóc tách từ một listing card trên trang danh sách (Bronze Listing Layer)."""

    source: str
    listing_id: str | None
    detail_url: str
    title_raw: str | None
    price_raw: str | None
    area_raw: str | None
    location_raw: str | None
    posted_at_raw: str | None
    seller_name_raw: str | None = None
    seller_type_raw: str | None = None
    thumbnail_url_raw: str | None = None
    card_position: int = 0
    page_number: int = 1
    crawl_run_id: str | None = None
    crawled_at: str | None = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
