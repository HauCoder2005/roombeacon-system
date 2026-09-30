"""Extract cards from CafeLand row-item containers."""
import re
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.sources.common_html import SourceListingParser

class CafelandListingParser(SourceListingParser):
    """Apply this source's listing-card HTML contract without semantic cleaning."""
    CARD_CLASSES=("row-item",); PRICE_CLASSES=("price", "reales-price"); AREA_CLASSES=("reales-area", "acreage")
    LOCATION_CLASSES=("reales-address", "location", "info-location"); DATE_CLASSES=("reales-date", "date"); IMAGE_CLASSES=("image-frame",)
    ID_PATTERN=re.compile(r"-(\d+)\.html", re.I)

    def _detail_link(self, card, source_url):
        """Exclude CafeLand broker profiles from rental-card identity selection."""
        candidates = []
        for class_name in self.LINK_CLASSES:
            candidates.extend(card.find_all(tag="a", class_token=class_name))
        candidates.extend(card.find_all(tag="a"))
        for node in candidates:
            href = node.attrs.get("href", "").strip()
            title = node.attrs.get("title", "").strip() or node.text()
            if "/moi-gioi/" in urlparse(href).path.casefold():
                continue
            if href and title and not href.startswith(
                ("#", "javascript:", "tel:", "mailto:")
            ):
                return node, urljoin(source_url, href)
        return None
