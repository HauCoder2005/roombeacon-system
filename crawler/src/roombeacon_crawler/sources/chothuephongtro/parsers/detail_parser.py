"""Extract semantic detail fields from ChoThuePhongTro posts."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser

class ChothuephongtroDetailParser(SourceDetailParser):
    PRICE_CLASSES=("post-price",); AREA_CLASSES=("acreage",); DESCRIPTION_CLASSES=("post-content", "description")
    ADDRESS_CLASSES=("post-address", "location"); SELLER_CLASSES=("author-name", "user-name")
    ID_PATTERN=re.compile(r"-pr(\d+)\.html", re.I)

    def _semantic_address(self, root):
        section_headers = root.find_all(class_token="section-header")
        for heading_tag in ("h2", "h3", "h4"):
            section_headers.extend(root.find_all(tag=heading_tag))
        for heading in section_headers:
            if heading.text().strip().casefold() != "vị trí phòng trọ":
                continue
            section = heading.parent
            content = section.first(class_token="section-content") if section else None
            candidate = content.text().strip() if content else ""
            if candidate and not self._is_garbage_address(candidate):
                return candidate
        return super()._semantic_address(root)

    def _extract_scoped_address(self, root):
        for class_name in self.ADDRESS_CLASSES:
            for address_node in root.find_all(class_token=class_name):
                ancestor = address_node.parent
                inside_footer = False
                while ancestor:
                    if ancestor.tag == "footer":
                        inside_footer = True
                        break
                    ancestor = ancestor.parent
                if inside_footer:
                    continue
                address_candidate = address_node.text().replace(
                    "Xem trên bản đồ", ""
                ).strip()
                if not self._is_garbage_address(address_candidate):
                    return address_candidate
        return None
