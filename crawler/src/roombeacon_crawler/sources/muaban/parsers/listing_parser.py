import logging
import re
from urllib.parse import urljoin

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.nhatrovn.dom import DOMNode, DOMTreeBuilder

logger = logging.getLogger(__name__)


class MuabanListingParser:
    """Parser bóc tách danh sách tin đăng từ HTML trang listing của Muaban."""

    def __init__(self, source_name: str = "muaban") -> None:
        self.source_name = source_name

    def parse(
        self,
        html: str,
        source_url: str,
        page_number: int = 1,
        limit: int = 50,
    ) -> list[ListingCardRaw]:
        """Bóc tách các thẻ listing card từ HTML."""
        if not html:
            return []

        root = DOMTreeBuilder.parse(html)
        # Muaban listing card items
        card_elements = root.find_all(class_contains="list-item") or root.find_all(class_contains="item-listing") or root.find_all(class_contains="mb-card")

        cards: list[ListingCardRaw] = []
        seen_urls: set[str] = set()

        for position, element in enumerate(card_elements, start=1):
            if len(cards) >= limit:
                break

            try:
                card = self._parse_card(element, source_url, position, page_number)
                if card and card.detail_url not in seen_urls:
                    seen_urls.add(card.detail_url)
                    cards.append(card)
            except Exception as exc:
                logger.warning("Lỗi parse card thứ %d trên Muaban: %s", position, exc)
                continue

        return cards

    def _parse_card(
        self,
        element: DOMNode,
        source_url: str,
        card_position: int,
        page_number: int,
    ) -> ListingCardRaw | None:
        link_elem = element.find(tag="a")
        href = link_elem.get("href", "").strip() if link_elem else ""
        if not href or href.startswith("javascript:") or href.startswith("#"):
            return None

        detail_url = urljoin(source_url, href)

        match = re.search(r"-id(\d+)", href) or re.search(r"/id(\d+)", href)
        listing_id = match.group(1) if match else None

        title_elem = element.find(class_contains="title") or link_elem
        title_raw = title_elem.get_text() if title_elem else None

        price_elem = element.find(class_contains="price")
        price_raw = price_elem.get_text() if price_elem else None

        location_elem = element.find(class_contains="location") or element.find(class_contains="address")
        location_raw = location_elem.get_text() if location_elem else None

        date_elem = element.find(class_contains="date") or element.find(class_contains="time")
        posted_at_raw = date_elem.get_text() if date_elem else None

        img_elem = element.find(tag="img")
        thumbnail_url = None
        if img_elem:
            src = img_elem.get("src") or img_elem.get("data-src")
            if src and not src.startswith("data:"):
                thumbnail_url = urljoin(source_url, src.strip())

        return ListingCardRaw(
            source=self.source_name,
            listing_id=listing_id,
            detail_url=detail_url,
            title_raw=title_raw,
            price_raw=price_raw,
            area_raw=None,
            location_raw=location_raw,
            posted_at_raw=posted_at_raw,
            thumbnail_url_raw=thumbnail_url,
            card_position=card_position,
            page_number=page_number,
        )
