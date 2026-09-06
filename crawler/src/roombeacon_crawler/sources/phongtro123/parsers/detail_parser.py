"""Extract PhongTro123 detail fields into the raw detail model."""

from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import logging
import re
from urllib.parse import urljoin

from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw

logger = logging.getLogger(__name__)


class DOMNode:
    def __init__(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        parent: "DOMNode | None" = None,
    ) -> None:
        self.tag = tag.lower()
        self.attrs: dict[str, str] = {k.lower(): (v or "") for k, v in attrs}
        self.parent = parent
        self.children: list[DOMNode] = []
        self.text_parts: list[str] = []

    def get_text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.get_text())
        return " ".join(" ".join(parts).split())

    def find_all(
        self,
        tag: str | None = None,
        class_contains: str | None = None,
        attr_has: tuple[str, str] | None = None,
    ) -> list["DOMNode"]:
        results: list[DOMNode] = []
        match = True

        if tag and self.tag != tag.lower():
            match = False

        if class_contains:
            cls = self.attrs.get("class", "")
            if class_contains.lower() not in cls.lower():
                match = False

        if attr_has:
            k, v = attr_has
            if k.lower() not in self.attrs or v.lower() not in self.attrs[k.lower()].lower():
                match = False

        if match and (tag or class_contains or attr_has):
            results.append(self)

        for child in self.children:
            results.extend(child.find_all(tag, class_contains, attr_has))

        return results

    def find(
        self,
        tag: str | None = None,
        class_contains: str | None = None,
        attr_has: tuple[str, str] | None = None,
    ) -> "DOMNode | None":
        res = self.find_all(tag=tag, class_contains=class_contains, attr_has=attr_has)
        return res[0] if res else None


class DOMTreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = DOMNode("root", [])
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = DOMNode(tag, attrs, parent=self.current)
        self.current.children.append(node)
        if tag.lower() not in ("br", "img", "input", "hr", "meta", "link"):
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        if self.current.parent and self.current.tag == tag.lower():
            self.current = self.current.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.text_parts.append(data.strip())


class Phongtro123DetailParser:
    """Parser bóc tách thông tin chi tiết bài đăng phòng trọ từ Phongtro123."""

    def __init__(self, source_name: str = "phongtro123") -> None:
        self.source_name = source_name

    @staticmethod
    def _extract_full_address(root: DOMNode) -> str | None:
        """Extract the main listing address from semantic, source-scoped data."""
        # The production detail table pairs a stable Vietnamese label with its
        # adjacent value cell; row position and generated CSS are irrelevant.
        for row in root.find_all(tag="tr"):
            cells = [child for child in row.children if child.tag in {"td", "th"}]
            if len(cells) < 2:
                continue
            label = cells[0].get_text().strip().rstrip(":").casefold()
            if label == "địa chỉ":
                value = cells[1].get_text().strip()
                return value or None

        # Structured PostalAddress is the controlled fallback for layouts that
        # omit the visible table while preserving the listing schema payload.
        for script in root.find_all(tag="script", attr_has=("type", "ld+json")):
            raw = script.get_text().strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            nodes = payload if isinstance(payload, list) else [payload]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                address = node.get("address")
                if isinstance(address, dict):
                    value = address.get("streetAddress")
                    if isinstance(value, str) and value.strip():
                        return value.strip()

        address_node = root.find(class_contains="post-address") or root.find(
            class_contains="item-address"
        )
        value = address_node.get_text().strip() if address_node else ""
        return value or None

    def parse(
        self,
        html: str,
        detail_url: str = "",
        source_url: str = "",
        listing_id: str | None = None,
        **kwargs,
    ) -> ListingDetailRaw | None:
        if not html or not html.strip():
            return None

        effective_url = detail_url or source_url
        try:
            builder = DOMTreeBuilder()
            builder.feed(html)
            root = builder.root

            if not listing_id and effective_url:
                match = re.search(r"-pr(\d+)", effective_url)
                if match:
                    listing_id = match.group(1)

            title_node = root.find(tag="h1")
            title_raw = title_node.get_text() if title_node else None

            price_node = root.find(class_contains="item-price") or root.find(class_contains="post-price") or root.find(class_contains="price")
            price_raw = price_node.get_text() if price_node else None

            area_node = root.find(class_contains="item-acreage") or root.find(class_contains="post-acreage") or root.find(class_contains="acreage")
            area_raw = area_node.get_text() if area_node else None

            address_raw = self._extract_full_address(root)

            # Try finding the "Thông tin mô tả" heading, then getting its parent or next siblings
            description_raw = None
            desc_node = root.find(class_contains="section-post-summary") or root.find(class_contains="post-main-content") or root.find(class_contains="post-description")
            if desc_node:
                description_raw = desc_node.get_text()
            else:
                for heading in root.find_all(tag="h2") + root.find_all(tag="h3"):
                    if "mô tả" in heading.get_text().lower():
                        if heading.parent:
                            description_raw = heading.parent.get_text()
                            break

            author_node = root.find(class_contains="author-name") or root.find(class_contains="user-name") or root.find(class_contains="post-author")
            seller_name_raw = author_node.get_text() if author_node else None

            # Extract phone number from <a> tags with tel: or zalo.me
            seller_phone_raw = None
            for a_node in root.find_all(tag="a"):
                href = a_node.attrs.get("href", "")
                if href.startswith("tel:"):
                    phone = href[4:].strip().replace(" ", "")
                    # Ignore general hotlines
                    if not phone.startswith("1900") and not phone.startswith("1800") and not phone.startswith("0909316890"):
                        seller_phone_raw = phone
                        break
                elif "zalo.me/" in href:
                    zalo_id = href.split("zalo.me/")[-1].strip()
                    if zalo_id.startswith("0") and len(zalo_id) >= 10 and not zalo_id.startswith("0909316890"):
                        seller_phone_raw = zalo_id
                        break

            from roombeacon_crawler.sources.common_html import extract_scoped_images
            from roombeacon_crawler.sources.common_html_location import extract_google_maps_info
            
            gallery = root.find(class_contains="post-images") or root.find(class_contains="image-gallery") or root.find(class_contains="post-slider")
            image_urls = extract_scoped_images(gallery, effective_url)

            # Map Extraction
            # We need to pass the raw BeautifulSoup parsing into extract_google_maps_info if we want full map support
            # For simplicity, let's extract the iframe directly from the HTML text
            latitude = None
            longitude = None
            import re
            map_match = re.search(r'q=(-?\d+\.\d+)%2C(-?\d+\.\d+)', html)
            if not map_match:
                map_match = re.search(r'q=(-?\d+\.\d+),(-?\d+\.\d+)', html)
            if map_match:
                latitude = float(map_match.group(1))
                longitude = float(map_match.group(2))
            
            # Pack coordinates into location_raw as JSON
            import json
            location_raw = address_raw
            if latitude and longitude:
                location_raw = json.dumps({"address": address_raw, "latitude": latitude, "longitude": longitude})

            return ListingDetailRaw(
                source=self.source_name,
                listing_id=listing_id,
                detail_url=effective_url,
                title_raw=title_raw,
                price_raw=price_raw,
                area_raw=area_raw,
                address_raw=address_raw,
                location_raw=location_raw,
                description_raw=description_raw,
                seller_name_raw=seller_name_raw,
                seller_phone_raw=seller_phone_raw,
                image_urls_raw=image_urls,
                crawled_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.warning("PhongTro123 detail parse failed (error_class=%s)", type(exc).__name__)
            return None
