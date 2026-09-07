"""Extract semantic detail fields from ChoThuePhongTro posts."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser

class ChothuephongtroDetailParser(SourceDetailParser):
    PRICE_CLASSES=("post-price",); AREA_CLASSES=("acreage",); DESCRIPTION_CLASSES=("post-content", "description", "section-content")
    ADDRESS_CLASSES=("post-address", "location"); SELLER_CLASSES=("author-name", "user-name")
    ID_PATTERN=re.compile(r"-pr(\d+)\.html", re.I)

    def _extract_address(self, root):
        """Read the listing's location section without falling back to footer text."""
        for section in root.find_all(tag="section"):
            header = section.first(class_token="section-header")
            if not header or "vị trí" not in header.text().casefold():
                continue
            content = section.first(class_token="section-content")
            candidate = content.text().strip() if content else ""
            if candidate and not self._is_garbage_address(candidate):
                return candidate
        return super()._extract_address(root)
