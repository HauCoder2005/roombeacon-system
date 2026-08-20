import logging
import re
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.nhatrovn.dom import DOMNode, DOMTreeBuilder

logger = logging.getLogger(__name__)


class NhatroVNListingParser:
    """Parser bóc tách danh sách tin phòng trọ từ HTML trang listing của NhatroVN."""

    def __init__(self, source_name: str = "nhatrovn") -> None:
        self.source_name = source_name

    def parse(
        self,
        html: str,
        source_url: str,
        page_number: int = 1,
        limit: int = 50,
    ) -> list[ListingCardRaw]:
        """Bóc tách các thẻ listing card từ HTML của trang danh sách."""
        if not html:
            return []

        root = DOMTreeBuilder.parse(html)
        card_elements = root.find_all(class_contains="property-card")

        cards: list[ListingCardRaw] = []
        seen_urls: set[str] = set()

        for position, element in enumerate(card_elements, start=1):
            if len(cards) >= limit:
                break

            try:
                card = self._parse_card(
                    element=element,
                    source_url=source_url,
                    card_position=position,
                    page_number=page_number,
                )
                if card and card.detail_url not in seen_urls:
                    seen_urls.add(card.detail_url)
                    cards.append(card)
            except Exception as exc:
                logger.warning(
                    "Lỗi khi parse listing card thứ %d trên trang %s: %s",
                    position,
                    source_url,
                    exc,
                )
                continue

        return cards

    def _parse_card(
        self,
        element: DOMNode,
        source_url: str,
        card_position: int,
        page_number: int,
    ) -> ListingCardRaw | None:
        # 1. Tìm thẻ <a> chứa liên kết đến trang chi tiết
        parent_a = element.find_parent(tag="a")
        link_elem = parent_a or element.find(tag="a", attr_has=("href", "/chi-tiet/")) or element.find(tag="a")

        href = link_elem.get("href", "").strip() if link_elem else ""
        if not href or href.startswith("javascript:") or href.startswith("#"):
            return None

        detail_url = urljoin(source_url, href)
        parsed_url = urlparse(detail_url)
        if not parsed_url.hostname or "nhatrovn.vn" not in parsed_url.hostname.lower():
            return None

        # 2. Bóc tách listing_id
        listing_id = self._extract_listing_id(href, detail_url, element)

        # 3. Bóc tách hình ảnh & tiêu đề (từ thuộc tính alt hoặc address)
        img_elem = element.find(tag="img")
        thumbnail_url = None
        alt_title = None

        if img_elem:
            src = img_elem.get("src") or img_elem.get("data-src") or ""
            if src and not src.startswith("data:"):
                thumbnail_url = urljoin(source_url, src.strip())
            alt_title = img_elem.get("alt", "").strip() or None

        # 4. Bóc tách địa chỉ / location
        address_elem = element.find(class_contains="rn-property-address")
        address_raw = address_elem.get_text() if address_elem else None

        # Tiêu đề ưu tiên alt text nếu có, hoặc dùng địa chỉ
        title_raw = alt_title or address_raw or f"Phòng trọ NhatroVN {listing_id or ''}".strip()

        # 5. Bóc tách giá
        price_elem = element.find(class_contains="property-card-price")
        price_raw = price_elem.get_text() if price_elem else None

        return ListingCardRaw(
            source=self.source_name,
            listing_id=listing_id,
            detail_url=detail_url,
            title_raw=title_raw,
            price_raw=price_raw,
            area_raw=None,
            location_raw=address_raw,
            posted_at_raw=None,
            thumbnail_url_raw=thumbnail_url,
            card_position=card_position,
            page_number=page_number,
        )

    def _extract_listing_id(self, href: str, detail_url: str, element: DOMNode) -> str | None:
        """Trích xuất ID tin đăng từ URL hoặc thuộc tính."""
        match = re.search(r"/chi-tiet/([a-zA-Z0-9]+)/?", detail_url or href)
        if match:
            return match.group(1)

        img_elem = element.find(tag="img")
        if img_elem:
            src = img_elem.get("src", "")
            img_match = re.search(r"/images-room/([a-zA-Z0-9]+)/", src)
            if img_match:
                return img_match.group(1)

        return None
