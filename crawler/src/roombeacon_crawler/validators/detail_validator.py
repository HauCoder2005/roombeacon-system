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

        # Trang chi tiết hợp lệ cần có tiêu đề, giá tiền hoặc nội dung mô tả
        if not detail.title_raw and not detail.price_raw and not detail.description_raw:
            return False

        return True
