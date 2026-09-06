"""Extract listing cards from the audited ChoThueNha card DOM."""
import re
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.sources.common_html import SourceListingParser

class ChothuenhaListingParser(SourceListingParser):
    CARD_CLASSES = ("dv-bds",)
    PRICE_CLASSES = ("price",)
    AREA_CLASSES = ("area", "dientich")
    LOCATION_CLASSES = ("location", "address")
    DATE_CLASSES = ("date", "time")
    IMAGE_CLASSES = ("home-thumb",)
    ID_PATTERN = re.compile(r"-(\d+)(?:$|[/?#])")
    DETAIL_PATH_PATTERN = re.compile(r"^/(?:phong-tro|nha-tro)-[^/]+-\d+$", re.I)

    def _detail_link(self, card, source_url):
        """Select room-listing details and skip other rental-property links."""
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
                and self.DETAIL_PATH_PATTERN.fullmatch(parsed.path.rstrip("/"))
            ):
                return node, detail_url
        return None

    def parse(self, html: str, source_url: str, page_number: int = 1, limit: int = 50):
        from roombeacon_crawler.sources.common_html import parse_html
        cards_raw = super().parse(html, source_url, page_number, limit)
        if not cards_raw:
            return cards_raw

        root = parse_html(html)
        dom_cards = root.find_all(class_token="dv-bds")
        url_to_card = {}
        for dom_card in dom_cards:
            linked = self._detail_link(dom_card, source_url)
            if linked:
                url_to_card[linked[1]] = dom_card

        for card in cards_raw:
            dom = url_to_card.get(card.detail_url)
            if dom:
                auth = dom.find_all(class_token="dv-bds-autho")
                if auth:
                    a_tags = auth[0].find_all(tag="a")
                    for a in a_tags:
                        href = a.attrs.get("href", "")
                        if "cho-thue-nha-" in href or "ho-chi-minh" in href:
                            card.location_raw = a.text().strip()
                            break
        return cards_raw
