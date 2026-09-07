"""Validate parsed listing-detail fields before Bronze mapping."""

from urllib.parse import urlparse

from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw


class DetailValidator:
    """Kiểm tra tính hợp lệ về mặt cấu trúc của ListingDetailRaw (không thực hiện data cleaning)."""

    @staticmethod
    def validate(detail: ListingDetailRaw) -> bool:
        """Xác thực đối tượng detail hợp lệ về mặt cấu trúc trang chi tiết."""
        if not detail.detail_url:
            return False

        parsed = urlparse(detail.detail_url)
        if not parsed.scheme or not parsed.netloc:
            return False

        enrichment_fields = (
            detail.title_raw,
            detail.price_raw,
            detail.area_raw,
            detail.address_raw,
            detail.location_raw,
            detail.description_raw,
            detail.posted_at_raw,
            detail.property_type_raw,
            detail.furnishing_raw,
            detail.deposit_raw,
            detail.seller_name_raw,
            detail.seller_phone_raw,
        )
        return any(value for value in enrichment_fields) or bool(
            detail.image_urls_raw or detail.amenities_raw
        )
