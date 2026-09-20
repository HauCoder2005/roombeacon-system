"""Extract MuaBan rental cards from the source listing-page structure."""

import json
import logging
import re
from urllib.parse import urljoin

from roombeacon_crawler.domain.errors.domain_error import ParseError
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.nhatrovn.dom import DOMNode, DOMTreeBuilder

logger = logging.getLogger(__name__)


class MuabanListingParser:
    """Parser bóc tách danh sách tin đăng từ HTML trang listing của Muaban."""

    validates_source_structure = True

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
            raise ParseError("Muaban listing response is empty")

        root = DOMTreeBuilder.parse(html)
        next_data = root.find(
            tag="script",
            predicate=lambda node: node.get("id") == "__NEXT_DATA__",
        )
        if next_data:
            try:
                payload = json.loads(next_data.get_text(separator=""))
                if not isinstance(payload, dict):
                    raise TypeError("Muaban __NEXT_DATA__ must be an object")
                props = payload.get("props")
                page_props = props.get("pageProps") if isinstance(props, dict) else None
                classified = (
                    page_props.get("classified")
                    if isinstance(page_props, dict)
                    else None
                )
                if not isinstance(classified, dict) or "items" not in classified:
                    raise TypeError("Muaban classified.items path is missing")
                items = classified["items"]
                if not isinstance(items, list):
                    raise TypeError("Muaban classified.items must be a list")
                cards = self._parse_embedded_items(
                    items,
                    source_url=source_url,
                    page_number=page_number,
                    limit=limit,
                )
                if items and not cards:
                    raise TypeError("Muaban listing items have no usable records")
                return cards
            except (TypeError, ValueError, AttributeError) as exc:
                logger.warning(
                    "Muaban embedded listing parse failed (error_class=%s)",
                    type(exc).__name__,
                )
                raise ParseError("Muaban listing schema is missing or incompatible") from None

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
                logger.warning("Muaban card parse failed (position=%d, error_class=%s)", position, type(exc).__name__)
                continue

        if cards:
            return cards
        raise ParseError("Muaban listing structure could not be validated")

    def _parse_embedded_items(
        self,
        items: list[dict],
        *,
        source_url: str,
        page_number: int,
        limit: int,
    ) -> list[ListingCardRaw]:
        """Map the stable Next.js listing payload exposed by current MuaBan pages."""
        cards: list[ListingCardRaw] = []
        seen_urls: set[str] = set()
        for position, item in enumerate(items, start=1):
            if len(cards) >= limit:
                break
            if not isinstance(item, dict):
                continue
            href = str(item.get("url") or "").strip()
            detail_url = urljoin(source_url, href)
            if not href or detail_url in seen_urls:
                continue
            listing_id = str(item.get("id") or "").strip() or None
            covers = item.get("covers") or []
            thumbnail = (
                urljoin(source_url, covers[0])
                if covers and isinstance(covers[0], str)
                else None
            )
            cards.append(
                ListingCardRaw(
                    source=self.source_name,
                    listing_id=listing_id,
                    detail_url=detail_url,
                    title_raw=item.get("title"),
                    price_raw=item.get("price_display"),
                    area_raw=None,
                    location_raw=item.get("location"),
                    posted_at_raw=item.get("publish_display"),
                    thumbnail_url_raw=thumbnail,
                    card_position=position,
                    page_number=page_number,
                )
            )
            seen_urls.add(detail_url)
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
