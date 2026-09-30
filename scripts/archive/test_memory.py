from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class MapLocation:
    address: str
    latitude: float
    longitude: float

@dataclass
class RentalBronzeRecord:
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
    latitude: float | None = None
    longitude: float | None = None
    property_type_raw: str | None = None
    furnishing_raw: str | None = None
    deposit_raw: str | None = None
    seller_name_raw: str | None = None
    seller_type_raw: str | None = None
    seller_phone_raw: str | None = None
    image_urls_raw: list[str] = field(default_factory=list)
    amenities_raw: list[str] = field(default_factory=list)
    map_location: "MapLocation | None" = None
    crawl_run_id: str = ""
    crawled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

records = []
for i in range(25000):
    rec = RentalBronzeRecord(
        listing_id=f"pt123_{i}",
        source="phongtro123",
        url=f"https://phongtro123.com/thue-phong-{i}.html",
        title_raw="Cho thuê phòng trọ giá rẻ sạch sẽ an ninh" * 2,
        price_raw="2.5 triệu/tháng",
        area_raw="20m2",
        address_raw="Quận Gò Vấp, Hồ Chí Minh" * 2,
        location_raw="Gò Vấp, Hồ Chí Minh",
        description_raw="Phòng mới xây, có gác lửng, ban công thoáng mát..." * 20,
        posted_at_raw="Hôm nay",
        image_urls_raw=[f"img_{j}.jpg" for j in range(5)],
        amenities_raw=["Wifi", "Chỗ để xe", "Tự do"]
    )
    records.append(rec)
