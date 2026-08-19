from urllib.parse import urlparse

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw


class ListingValidator:
    """Kiểm tra tính hợp lệ về mặt cấu trúc của ListingCardRaw (không thực hiện data cleaning)."""

    @staticmethod
    def validate(card: ListingCardRaw) -> bool:
        """Xác thực đối tượng card có đủ điều kiện cấu trúc tối thiểu để tiếp tục xử lý không."""
        if not card.detail_url:
            return False

        parsed = urlparse(card.detail_url)
        if not parsed.scheme or not parsed.netloc:
            return False

        # Phải có ít nhất tiêu đề hoặc giá tiền để loại trừ các UI navigation / banner
        if not card.title_raw and not card.price_raw:
            return False

        return True
