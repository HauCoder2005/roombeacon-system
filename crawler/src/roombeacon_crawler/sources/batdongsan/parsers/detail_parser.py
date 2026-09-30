from roombeacon_crawler.sources.map_extractor import MapLocationExtractor
"""Extract BatDongSan detail fields without persistence side effects."""

import logging
import re
from urllib.parse import urljoin

from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.sources.nhatrovn.dom import DOMTreeBuilder

logger = logging.getLogger(__name__)


class BatDongSanDetailParser:
    """Parser bóc tách toàn bộ thông tin chi tiết một phòng trọ từ HTML trang detail của BatDongSan."""

    def __init__(self, source_name: str = "batdongsan") -> None:
        self.source_name = source_name

    def parse(
        self,
        html: str,
        detail_url: str,
        listing_id: str | None = None,
    ) -> ListingDetailRaw:
        """Extract one source-near detail record from the supplied response."""
        if not html:
            return ListingDetailRaw(
            map_location=MapLocationExtractor.extract_map_from_html(html),
                source=self.source_name,
                listing_id=listing_id,
                detail_url=detail_url,
            )

        root = DOMTreeBuilder.parse(html)

        if not listing_id:
            match = re.search(r"-pr(\d+)", detail_url) or re.search(r"/pr(\d+)", detail_url)
            listing_id = match.group(1) if match else None

        title_elem = root.find(tag="h1", class_contains="js__pr-title") or root.find(tag="h1")
        title_raw = title_elem.get_text() if title_elem else None

        address_elem = root.find(class_contains="js__pr-address") or root.find(class_contains="re__pr-address")
        address_raw = address_elem.get_text() if address_elem else None

        price_elem = root.find(class_contains="js__pr-price") or root.find(class_contains="re__pr-config-value")
        price_raw = price_elem.get_text() if price_elem else None

        desc_elem = root.find(class_contains="js__pr-description") or root.find(class_contains="re__section-body")
        description_raw = desc_elem.get_text() if desc_elem else None

        from roombeacon_crawler.sources.common_html import extract_scoped_images, extract_json_ld_images
        image_urls_raw = []
        gallery = root.find(class_contains="js__pr-scrollbar") or root.find(class_contains="re__pr-media") or root.find(class_contains="slick-slider")
        if gallery:
            image_urls_raw = extract_scoped_images(gallery, detail_url)
        if not image_urls_raw:
            image_urls_raw = extract_json_ld_images(root, detail_url)

        return ListingDetailRaw(
            map_location=MapLocationExtractor.extract_map_from_html(html),
            source=self.source_name,
            listing_id=listing_id,
            detail_url=detail_url,
            title_raw=title_raw,
            price_raw=price_raw,
            address_raw=address_raw,
            location_raw=address_raw,
            description_raw=description_raw,
            image_urls_raw=image_urls_raw,
        )
