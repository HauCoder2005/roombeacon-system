"""Extract cards from CafeLand row-item containers."""
import re
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.sources.common_html import SourceListingParser

class CafelandListingParser(SourceListingParser):
    """Apply this source's listing-card HTML contract without semantic cleaning."""
    CARD_CLASSES=("row-item-new",); PRICE_CLASSES=("price", "reals-price"); AREA_CLASSES=("reals-area", "acreage")
    LOCATION_CLASSES=("info-location", "location"); DATE_CLASSES=("reals-date", "date"); IMAGE_CLASSES=("image-frame",)
    ID_PATTERN=re.compile(r"-(\d+)\.html", re.I)
    DETAIL_PATH_PATTERN = re.compile(r"^/cho-thue-phong-tro-[^/]+-\d+\.html$", re.I)

    def _detail_link(self, card, source_url):
        """Select only CafeLand room-listing details, never broker profiles."""
        candidates = []
        for class_name in self.LINK_CLASSES:
            candidates.extend(card.find_all(tag="a", class_token=class_name))
        candidates.extend(card.find_all(tag="a"))

        source_host = (urlparse(source_url).hostname or "").removeprefix("www.")
        for node in candidates:
            href = node.attrs.get("href", "").strip()
            title = node.attrs.get("title", "").strip() or node.text()
            detail_url = urljoin(source_url, href)
            parsed = urlparse(detail_url)
            candidate_host = (parsed.hostname or "").removeprefix("www.")
            if (
                href
                and title
                and candidate_host == source_host
                and self.DETAIL_PATH_PATTERN.fullmatch(parsed.path)
            ):
                return node, detail_url
        return None
