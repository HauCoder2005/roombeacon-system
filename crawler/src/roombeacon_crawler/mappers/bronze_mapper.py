from datetime import datetime, timezone

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord


class BronzeMapper:
    """Hợp nhất dữ liệu thô từ ListingCardRaw, ListingDetailRaw thành RentalBronzeRecord chuẩn lớp Bronze."""

    @staticmethod
    def map(
        card: ListingCardRaw | None,
        detail: ListingDetailRaw | None,
        run_id: str = "",
    ) -> RentalBronzeRecord:
        """Merge thông tin card và detail, ưu tiên dữ liệu chi tiết nếu có."""
        listing_id = (
            (detail.listing_id if detail else None)
            or (card.listing_id if card else None)
            or ""
        )
        source = (
            (detail.source if detail else None)
            or (card.source if card else None)
            or "unknown"
        )
        url = (
            (detail.detail_url if detail else None)
            or (card.detail_url if card else None)
            or ""
        )

        title_raw = (detail.title_raw if detail and detail.title_raw else None) or (
            card.title_raw if card else None
        )
        price_raw = (detail.price_raw if detail and detail.price_raw else None) or (
            card.price_raw if card else None
        )
        area_raw = (detail.area_raw if detail and detail.area_raw else None) or (
            card.area_raw if card else None
        )
        address_raw = detail.address_raw if detail else None
        location_raw = (detail.location_raw if detail and detail.location_raw else None) or (
            card.location_raw if card else None
        )
        description_raw = detail.description_raw if detail else None
        posted_at_raw = (detail.posted_at_raw if detail and detail.posted_at_raw else None) or (
            card.posted_at_raw if card else None
        )

        property_type_raw = detail.property_type_raw if detail else None
        furnishing_raw = detail.furnishing_raw if detail else None
        deposit_raw = detail.deposit_raw if detail else None

        seller_name_raw = (
            (detail.seller_name_raw if detail and detail.seller_name_raw else None)
            or (card.seller_name_raw if card else None)
        )
        seller_type_raw = (
            (detail.seller_type_raw if detail and detail.seller_type_raw else None)
            or (card.seller_type_raw if card else None)
        )

        image_urls_raw = detail.image_urls_raw if detail else []
        if not image_urls_raw and card and card.thumbnail_url_raw:
            image_urls_raw = [card.thumbnail_url_raw]

        amenities_raw = detail.amenities_raw if detail else []

        return RentalBronzeRecord(
            listing_id=listing_id,
            source=source,
            url=url,
            title_raw=title_raw,
            price_raw=price_raw,
            area_raw=area_raw,
            address_raw=address_raw,
            location_raw=location_raw,
            description_raw=description_raw,
            posted_at_raw=posted_at_raw,
            property_type_raw=property_type_raw,
            furnishing_raw=furnishing_raw,
            deposit_raw=deposit_raw,
            seller_name_raw=seller_name_raw,
            seller_type_raw=seller_type_raw,
            image_urls_raw=image_urls_raw,
            amenities_raw=amenities_raw,
            crawl_run_id=run_id,
            crawled_at=datetime.now(timezone.utc).isoformat(),
        )
