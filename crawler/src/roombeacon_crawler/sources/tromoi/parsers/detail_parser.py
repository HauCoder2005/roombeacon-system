"""Extract structured and scoped detail fields from TroMoi."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser, first_text

class TromoiDetailParser(SourceDetailParser):
    PRICE_CLASSES=("hostel-detail__price", "price"); AREA_CLASSES=("hostel-detail__area", "area")
    DESCRIPTION_CLASSES=("content-detail", "hostel__detail--content", "description"); ADDRESS_CLASSES=("hostel-detail__address", "address")
    SELLER_CLASSES=("hostel-owner__name", "owner-name")

    def _semantic_address(self, root):
        scoped = first_text(root, self.DESCRIPTION_CLASSES) or ""
        match = re.search(r"địa chỉ\s*:\s*(.*?)(?:\s+giá\s*:|$)", scoped, re.I)
        return (match.group(1).strip(" ,-\u2022") if match else None) or super()._semantic_address(root)
