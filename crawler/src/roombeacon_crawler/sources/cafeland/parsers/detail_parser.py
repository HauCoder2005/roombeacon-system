"""Extract structured and semantic detail fields from CafeLand."""

import re

from roombeacon_crawler.sources.common_html import HtmlNode, SourceDetailParser


class CafelandDetailParser(SourceDetailParser):
    """Apply this source's detail-page HTML contract without downstream cleaning."""
    PRICE_CLASSES = ("price", "reals-price", "infor-data")
    AREA_CLASSES = ("reals-area", "acreage")
    DESCRIPTION_CLASSES = ("reals-description", "detail-content")
    ADDRESS_CLASSES = ("reales-location", "reals-location", "infor")
    SELLER_CLASSES = ("broker-name", "author-name")
    ID_PATTERN = re.compile(r"-(\d+)\.html", re.I)
    SCOPED_LOCATION_PATTERN = re.compile(
        r"Vị trí:\s*(.*?)(?:Lưu tin|\d{5,}|\bMã tài sản|\bNgày đăng|$)",
        re.IGNORECASE,
    )
    LOCATION_LABEL_PATTERN = re.compile(r"Vị trí:\s*", re.IGNORECASE)
    SAVE_LABEL_PATTERN = re.compile(r"Lưu tin", re.IGNORECASE)
    STRUCTURED_OFFICE_PREFIXES = ("Số 55/4 Tân Chánh Hiệp",)

    def parse(self, html: str, detail_url: str = "", **kwargs):
        """Parse a rental detail while refusing broker-profile locations."""
        detail = super().parse(html, detail_url=detail_url, **kwargs)
        if detail is not None and "/moi-gioi/" in detail_url.casefold():
            detail.address_raw = None
            detail.location_raw = None
        return detail

    def _valid_address(self, raw_address: str) -> str | None:
        address_candidate = raw_address.strip().strip(",").strip()
        if len(address_candidate) <= 2 or self._is_garbage_address(address_candidate):
            return None
        return address_candidate

    def _extract_scoped_location(self, root: HtmlNode) -> str | None:
        for location_node in root.find_all(class_token="reales-location"):
            match = self.SCOPED_LOCATION_PATTERN.search(location_node.text())
            if match:
                address_candidate = self._valid_address(match.group(1))
                if address_candidate:
                    return address_candidate
        return None

    def _extract_semantic_location(self, root: HtmlNode) -> str | None:
        for info_node in root.find_all(class_token="infor"):
            info_text = info_node.text()
            if "vị trí:" not in info_text.casefold():
                continue
            before_label, after_label = self.LOCATION_LABEL_PATTERN.split(
                info_text,
                maxsplit=1,
            )
            # HtmlNode places direct text before nested label text.
            for labeled_value in (after_label, before_label):
                raw_address = self.SAVE_LABEL_PATTERN.split(
                    labeled_value,
                    maxsplit=1,
                )[0]
                address_candidate = self._valid_address(raw_address)
                if address_candidate:
                    return address_candidate
        return None

    def _extract_address(self, root: HtmlNode) -> str | None:
        scoped_address = self._extract_scoped_location(root)
        if scoped_address:
            return scoped_address

        semantic_address = self._extract_semantic_location(root)
        if semantic_address:
            return semantic_address

        structured_address = self._extract_structured_address(root)
        if structured_address and not structured_address.startswith(
            self.STRUCTURED_OFFICE_PREFIXES
        ):
            return structured_address
        return None
