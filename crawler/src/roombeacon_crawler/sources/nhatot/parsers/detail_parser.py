"""Extract the primary NhaTot detail, including its scoped full address."""

import json
import logging
import re
from urllib.parse import urljoin

from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.sources.nhatot.parsers.listing_parser import (
    DOMTreeBuilder,
    ID_FROM_URL_REGEX,
    PRICE_REGEX,
    AREA_REGEX,
)
from roombeacon_crawler.sources.nhatot.selectors.detail_selectors import (
    AMENITY_CLASSES,
    AREA_CLASSES,
    DEPOSIT_CLASSES,
    DESCRIPTION_CLASSES,
    FURNISHING_CLASSES,
    IMAGE_CLASSES,
    POSTED_AT_CLASSES,
    PRICE_CLASSES,
    PROPERTY_TYPE_CLASSES,
    SELLER_NAME_CLASSES,
    SELLER_TYPE_CLASSES,
    TITLE_CLASSES,
)

logger = logging.getLogger(__name__)


class NhatotDetailParser:
    """Parser chuyên trách bóc tách thông tin chi tiết đầy đủ từ HTML trang tin đăng của Nhà Tốt."""

    def __init__(self, source_name: str = "nhatot") -> None:
        self.source_name = source_name

    @staticmethod
    def _structured_address(root) -> str | None:
        """Read the Product offer's PostalAddress, excluding breadcrumb JSON-LD."""
        for script in root.find_all(tag="script"):
            if script.attrs.get("type", "").casefold() != "application/ld+json":
                continue
            try:
                payload = json.loads(script.get_text())
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if not isinstance(item, dict) or item.get("@type") != "Product":
                    continue
                offers = item.get("offers")
                place = offers.get("availableAtOrFrom") if isinstance(offers, dict) else None
                address = place.get("address") if isinstance(place, dict) else None
                value = address.get("streetAddress") if isinstance(address, dict) else None
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _semantic_address(root) -> str | None:
        """Read the value inside the exact primary 'Địa chỉ bất động sản' section."""
        for label in root.find_all(tag="p"):
            if label.get_text().strip().casefold() != "địa chỉ bất động sản":
                continue
            section = label.parent
            if section is None:
                return None
            for child in section.children:
                if child is label:
                    continue
                for span in child.find_all(tag="span"):
                    value = span.get_text().strip()
                    normalized = value.casefold()
                    if value and any(token in normalized for token in ("đường", "hẻm", "phường", "xã")):
                        return value
            return None
        return None

    @classmethod
    def _extract_full_address(cls, root) -> str | None:
        """Apply deterministic structured, semantic, then stable-class strategies."""
        value = cls._structured_address(root) or cls._semantic_address(root)
        if value:
            return value
        for stable_class in ("AdDecription_address", "full-address"):
            node = root.find(class_contains=stable_class)
            if node and node.get_text().strip():
                return node.get_text().strip()
        return None

    def parse(
        self,
        html: str,
        detail_url: str,
        listing_id: str | None = None,
    ) -> ListingDetailRaw:
        """Trích xuất đối tượng ListingDetailRaw từ trang chi tiết tin đăng."""
        if listing_id is None:
            match = ID_FROM_URL_REGEX.search(detail_url)
            listing_id = match.group(1) if match else None

        if not html:
            return ListingDetailRaw(
                source=self.source_name,
                listing_id=listing_id,
                detail_url=detail_url,
                title_raw=None,
                price_raw=None,
                area_raw=None,
                address_raw=None,
                location_raw=None,
                description_raw=None,
                posted_at_raw=None,
            )

        try:
            builder = DOMTreeBuilder()
            builder.feed(html)
            root = builder.root
        except Exception as exc:
            logger.error("NhaTot detail DOM parse failed (error_class=%s)", type(exc).__name__)
            return ListingDetailRaw(
                source=self.source_name,
                listing_id=listing_id,
                detail_url=detail_url,
                title_raw=None,
                price_raw=None,
                area_raw=None,
                address_raw=None,
                location_raw=None,
                description_raw=None,
                posted_at_raw=None,
            )

        # 1. Title
        title_raw: str | None = None
        for cls in TITLE_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                t = node.get_text().strip()
                if t:
                    title_raw = t
                    break
        if not title_raw:
            h1 = root.find(tag="h1")
            if h1:
                title_raw = h1.get_text().strip() or None

        # 2. Price
        price_raw: str | None = None
        for cls in PRICE_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                p = self._extract_price(node.get_text())
                if p:
                    price_raw = p
                    break
        if not price_raw:
            price_raw = self._extract_price(root.get_text())

        # 3. Area
        area_raw: str | None = None
        for cls in AREA_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                a = self._extract_area(node.get_text())
                if a:
                    area_raw = a
                    break
        if not area_raw:
            area_raw = self._extract_area(root.get_text())

        # 4. Address & Location
        address_raw = self._extract_full_address(root)

        location_raw: str | None = address_raw

        # 5. Description
        description_raw: str | None = None
        for cls in DESCRIPTION_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                desc = node.get_text().strip()
                if desc:
                    description_raw = desc
                    break

        # 6. Posted At & Updated At
        posted_at_raw: str | None = None
        for cls in POSTED_AT_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                posted_at_raw = node.get_text().strip() or None
                break

        # 7. Property Type, Furnishing, Deposit
        property_type_raw: str | None = None
        for cls in PROPERTY_TYPE_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                property_type_raw = node.get_text().strip() or None
                break

        furnishing_raw: str | None = None
        for cls in FURNISHING_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                furnishing_raw = node.get_text().strip() or None
                break

        deposit_raw: str | None = None
        for cls in DEPOSIT_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                deposit_raw = node.get_text().strip() or None
                break

        # 8. Seller Information
        seller_name_raw: str | None = None
        for cls in SELLER_NAME_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                seller_name_raw = node.get_text().strip() or None
                break

        seller_type_raw: str | None = None
        for cls in SELLER_TYPE_CLASSES:
            node = root.find(class_contains=cls)
            if node:
                seller_type_raw = node.get_text().strip() or None
                break

        # 9. Image URLs
        image_urls_raw: list[str] = []
        for img in root.find_all(tag="img"):
            src = img.attrs.get("src") or img.attrs.get("data-src")
            if src and not src.startswith("data:"):
                abs_img = urljoin(detail_url, src)
                if abs_img not in image_urls_raw and ("chotot" in abs_img or "nhatot" in abs_img or "cdn" in abs_img):
                    image_urls_raw.append(abs_img)

        # 10. Amenities
        amenities_raw: list[str] = []
        for cls in AMENITY_CLASSES:
            for item in root.find_all(class_contains=cls):
                amenity_text = item.get_text().strip()
                if amenity_text and amenity_text not in amenities_raw:
                    amenities_raw.append(amenity_text)

        return ListingDetailRaw(
            source=self.source_name,
            listing_id=listing_id,
            detail_url=detail_url,
            title_raw=title_raw,
            price_raw=price_raw,
            area_raw=area_raw,
            address_raw=address_raw,
            location_raw=location_raw,
            description_raw=description_raw,
            posted_at_raw=posted_at_raw,
            updated_at_raw=None,
            property_type_raw=property_type_raw,
            furnishing_raw=furnishing_raw,
            deposit_raw=deposit_raw,
            seller_name_raw=seller_name_raw,
            seller_type_raw=seller_type_raw,
            image_urls_raw=image_urls_raw,
            amenities_raw=amenities_raw,
        )

    def _extract_price(self, raw: str) -> str | None:
        m = PRICE_REGEX.search(raw)
        if m:
            val = m.group(1).strip()
            if re.match(r"^\d+\s*k$", val, re.IGNORECASE):
                return None
            return val
        return None

    def _extract_area(self, raw: str) -> str | None:
        m = AREA_REGEX.search(raw)
        return m.group(1).strip() if m else None
