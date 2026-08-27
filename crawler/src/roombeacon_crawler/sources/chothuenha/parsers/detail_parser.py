"""Extract semantic detail values from ChoThueNha listing pages."""

import re

from roombeacon_crawler.sources.common_html import HtmlNode, SourceDetailParser


class ChothuenhaDetailParser(SourceDetailParser):
    """Apply this source's detail-page HTML contract without downstream cleaning."""
    PRICE_CLASSES = ("price", "product-price")
    AREA_CLASSES = ("area", "dientich")
    DESCRIPTION_CLASSES = ("showText", "content-detail", "description")
    ADDRESS_CLASSES = ("pd-map", "p-map", "dv-bds-bd")
    SELLER_CLASSES = ("user-name", "author-name")
    ID_PATTERN = re.compile(r"-(\d+)(?:$|[/?#])")

    def _extract_address(self, root: HtmlNode) -> str | None:
        scoped_address = self._extract_scoped_address(root)
        if scoped_address:
            return scoped_address

        return self._extract_structured_address(root)
