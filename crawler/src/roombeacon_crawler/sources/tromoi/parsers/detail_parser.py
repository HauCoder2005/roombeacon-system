"""Extract structured and scoped detail fields from TroMoi."""
import re
from roombeacon_crawler.sources.common_html import SourceDetailParser, first_text

class TromoiDetailParser(SourceDetailParser):
    PRICE_CLASSES=("hostel-detail__price", "price"); AREA_CLASSES=("hostel-detail__area", "area")
    DESCRIPTION_CLASSES=("content-detail", "hostel__detail--content", "description"); ADDRESS_CLASSES=("hostel-detail__address", "box-address", "address")
    SELLER_CLASSES=("hostel-owner__name", "owner-name")

    def _semantic_address(self, root):
        scoped = first_text(root, self.DESCRIPTION_CLASSES) or ""
        match = re.search(r"địa chỉ\s*:\s*(.*?)(?:\s+giá\s*:|$)", scoped, re.I)
        return (match.group(1).strip(" ,-\u2022") if match else None) or super()._semantic_address(root)


    def parse(self, html: str, detail_url: str = "", **kwargs):
        detail = super().parse(html, detail_url=detail_url, **kwargs)
        if detail and not detail.seller_phone_raw:
            from roombeacon_crawler.sources.common_html import parse_html
            import re
            root = parse_html(html)
            for script in root.find_all(tag="script"):
                text = script.text()
                if text:
                    match = re.search(r'(?:phone|mobile|hotline|fullPhone)["\']?\s*[:=]\s*["\']([0-9\s\.\+]+)["\']', text, re.I)
                    if match:
                        phone = match.group(1).strip()
                        if len(re.sub(r'[\s\.\-\((\)]', '', phone)) >= 9:
                            detail.seller_phone_raw = phone
                            break
        return detail
