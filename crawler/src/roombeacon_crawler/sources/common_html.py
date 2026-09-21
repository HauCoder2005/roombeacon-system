"""Provide small HTML primitives reused by source-specific rental parsers.

The module handles DOM traversal and safe raw-value extraction only. Selector
choices, URL identity rules and source capabilities remain in each source.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.sources.map_extractor import MapLocationExtractor
from roombeacon_crawler.sources.address_quality import most_specific_address
import re


class HtmlNode:
    """Minimal DOM node used without adding a third-party parser dependency."""

    def __init__(self, tag: str, attrs=(), parent: "HtmlNode | None" = None):
        self.tag = tag.lower()
        self.attrs = {key.lower(): (value or "") for key, value in attrs}
        self.parent = parent
        self.children: list[HtmlNode] = []
        self.text_parts: list[str] = []

    def text(self) -> str:
        """Return normalized text from this node and all descendants."""
        return " ".join(" ".join(self.text_parts + [c.text() for c in self.children]).split())

    def find_all(self, *, tag: str | None = None, class_token: str | None = None):
        """Depth-first search for nodes matching an optional tag and class."""
        result = []
        classes = self.attrs.get("class", "").split()
        if (tag is None or self.tag == tag) and (class_token is None or class_token in classes):
            result.append(self)
        for child in self.children:
            result.extend(child.find_all(tag=tag, class_token=class_token))
        return result

    def first(self, *, tag: str | None = None, class_token: str | None = None):
        """Return the first matching descendant or ``None``."""
        values = self.find_all(tag=tag, class_token=class_token)
        return values[0] if values else None


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = HtmlNode("root")
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = HtmlNode(tag, attrs, self.current)
        self.current.children.append(node)
        if tag.lower() not in {"area", "base", "br", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node.parent and node.tag != tag.lower():
            node = node.parent
        if node.parent:
            self.current = node.parent

    def handle_data(self, data):
        if data.strip():
            self.current.text_parts.append(data.strip())


def parse_html(html: str) -> HtmlNode:
    """Parse HTML into the dependency-free ``HtmlNode`` tree."""
    builder = _TreeBuilder()
    builder.feed(html)
    return builder.root


def first_text(node: HtmlNode, classes: tuple[str, ...]) -> str | None:
    """Return the first non-empty text for a source-prioritized class list."""
    for class_name in classes:
        found = node.first(class_token=class_name)
        if found and found.text():
            return found.text()
    return None


class SourceListingParser:
    """Extract cards using one source's explicitly supplied DOM contract."""

    CARD_CLASSES: tuple[str, ...] = ()
    LINK_CLASSES: tuple[str, ...] = ()
    PRICE_CLASSES: tuple[str, ...] = ()
    AREA_CLASSES: tuple[str, ...] = ()
    LOCATION_CLASSES: tuple[str, ...] = ()
    DATE_CLASSES: tuple[str, ...] = ()
    IMAGE_CLASSES: tuple[str, ...] = ()
    DETAIL_PATH_PREFIXES: tuple[str, ...] = ()
    ID_PATTERN = re.compile(r"(?:-id|-pr|-)(\d{4,})(?:\.html)?(?:$|[/?#])", re.I)

    def __init__(self, source_name: str):
        self.source_name = source_name

    def _detail_link(self, card: HtmlNode, source_url: str) -> tuple[HtmlNode, str] | None:
        candidates = []
        for class_name in self.LINK_CLASSES:
            candidates.extend(card.find_all(tag="a", class_token=class_name))
        candidates.extend(card.find_all(tag="a"))
        for node in candidates:
            href = node.attrs.get("href", "").strip()
            title = node.attrs.get("title", "").strip() or node.text()
            path = urlparse(urljoin(source_url, href)).path
            if self.DETAIL_PATH_PREFIXES and not any(path.startswith(prefix) for prefix in self.DETAIL_PATH_PREFIXES):
                continue
            if href and title and not href.startswith(("#", "javascript:", "tel:", "mailto:")):
                return node, urljoin(source_url, href)
        return None

    def _identity(self, detail_url: str) -> str:
        match = self.ID_PATTERN.search(detail_url)
        if match:
            return match.group(1)
        return urlparse(detail_url).path.strip("/").removesuffix(".html")

    def parse(self, html: str, source_url: str, page_number: int = 1, limit: int = 50):
        """Extract deduplicated source-near cards up to the requested limit."""
        if not html or not html.strip():
            return []
        root = parse_html(html)
        cards = []
        for class_name in self.CARD_CLASSES:
            cards = root.find_all(class_token=class_name)
            if cards:
                break
        result: list[ListingCardRaw] = []
        seen: set[str] = set()
        for card in cards:
            linked = self._detail_link(card, source_url)
            if not linked:
                continue
            link, detail_url = linked
            if detail_url in seen:
                continue
            title = link.attrs.get("title", "").strip() or link.text()
            if not title:
                continue
            image = None
            image_nodes = []
            for class_name in self.IMAGE_CLASSES:
                image_nodes.extend(card.find_all(class_token=class_name))
            image_nodes.extend(card.find_all(tag="img"))
            for node in image_nodes:
                candidate = node.attrs.get("data-src") or node.attrs.get("src")
                if candidate and not candidate.startswith("data:"):
                    image = urljoin(source_url, candidate)
                    break
            result.append(ListingCardRaw(
                source=self.source_name,
                listing_id=self._identity(detail_url),
                detail_url=detail_url,
                title_raw=title,
                price_raw=first_text(card, self.PRICE_CLASSES),
                area_raw=first_text(card, self.AREA_CLASSES),
                location_raw=first_text(card, self.LOCATION_CLASSES),
                posted_at_raw=first_text(card, self.DATE_CLASSES),
                thumbnail_url_raw=image,
                card_position=len(result) + 1,
                page_number=page_number,
            ))
            seen.add(detail_url)
            if len(result) >= limit:
                break
        return result


class SourceDetailParser:
    """Extract detail values using source-scoped classes and semantic labels."""

    TITLE_CLASSES: tuple[str, ...] = ()
    PRICE_CLASSES: tuple[str, ...] = ()
    AREA_CLASSES: tuple[str, ...] = ()
    DESCRIPTION_CLASSES: tuple[str, ...] = ()
    ADDRESS_CLASSES: tuple[str, ...] = ()
    SELLER_CLASSES: tuple[str, ...] = ()
    ADDRESS_LABELS = {"địa chỉ", "địa điểm", "vị trí"}
    GARBAGE_ADDRESS_MARKERS = (
        "lọc theo khu vực",
        "toàn quốc tp.",
        "địa chỉ vpđd:",
        "địa chỉ trụ sở",
    )
    PROVINCE_MARKERS = (
        "hà nội",
        "hồ chí minh",
        "đà nẵng",
        "cần thơ",
        "hải phòng",
        "an giang",
        "bắc ninh",
        "bình dương",
    )
    ADDRESS_JSONLD_TYPES = {
        "accommodation",
        "apartment",
        "house",
        "hostel",
        "offer",
        "product",
        "realestatelisting",
        "residence",
        "room",
        "singlefamilyresidence",
    }
    ID_PATTERN = SourceListingParser.ID_PATTERN

    def __init__(self, source_name: str):
        self.source_name = source_name

    def _is_garbage_address(self, address_candidate: str | None) -> bool:
        """Reject navigation menus, breadcrumbs, filter sidebars, or corporate offices."""
        if not address_candidate or len(address_candidate.strip()) < 3:
            return True
        normalized_address = address_candidate.strip().casefold()
        if any(
            marker in normalized_address for marker in self.GARBAGE_ADDRESS_MARKERS
        ):
            return True
        province_count = sum(
            marker in normalized_address for marker in self.PROVINCE_MARKERS
        )
        return province_count >= 4

    def _extract_structured_address(self, root: HtmlNode) -> str | None:
        """Return a PostalAddress owned by a real-estate JSON-LD entity."""
        for script in root.find_all(tag="script"):
            if "ld+json" not in script.attrs.get("type", ""):
                continue
            try:
                payload = json.loads("".join(script.text_parts).strip())
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            pending_entities = payload if isinstance(payload, list) else [payload]
            while pending_entities:
                entity = pending_entities.pop(0)
                if isinstance(entity, list):
                    pending_entities.extend(entity)
                elif isinstance(entity, dict):
                    raw_types = entity.get("@type", "")
                    item_types = raw_types if isinstance(raw_types, list) else [raw_types]
                    normalized_types = {
                        str(entity_type).rsplit("/", 1)[-1].casefold().strip()
                        for entity_type in item_types
                    }
                    if normalized_types & self.ADDRESS_JSONLD_TYPES:
                        structured_address = entity.get("address")
                        if isinstance(structured_address, str):
                            address_candidate = structured_address.strip()
                            if not self._is_garbage_address(address_candidate):
                                return address_candidate
                        if isinstance(structured_address, dict):
                            address_parts = [
                                structured_address.get(field)
                                for field in (
                                    "streetAddress",
                                    "addressLocality",
                                    "addressRegion",
                                )
                            ]
                            address_candidate = ", ".join(
                                str(part).strip()
                                for part in address_parts
                                if part and str(part).strip()
                            )
                            if not self._is_garbage_address(address_candidate):
                                return address_candidate
                    for child_key in ("@graph", "itemListElement", "mainEntity", "itemOffered"):
                        nested_entity = entity.get(child_key)
                        if isinstance(nested_entity, (list, dict)):
                            pending_entities.append(nested_entity)
        return None

    def _semantic_address(self, root: HtmlNode) -> str | None:
        for tag in ("tr", "li", "div", "p"):
            for row in root.find_all(tag=tag):
                children = [c for c in row.children if c.text()]
                if len(children) >= 2:
                    label = children[0].text().strip().rstrip(":").casefold()
                    if label in self.ADDRESS_LABELS:
                        value = children[1].text().strip()
                        if value and not self._is_garbage_address(value):
                            return value
                txt = row.text().strip()
                if any(txt.casefold().startswith(l + ":") for l in self.ADDRESS_LABELS):
                    for l in self.ADDRESS_LABELS:
                        prefix = l + ":"
                        if txt.casefold().startswith(prefix):
                            candidate = txt[len(prefix):].strip(" ,-\u2022")
                            if candidate and not self._is_garbage_address(candidate):
                                return candidate
        return None

    def _extract_scoped_address(self, root: HtmlNode) -> str | None:
        for class_name in self.ADDRESS_CLASSES:
            address_node = root.first(class_token=class_name)
            if not address_node or not address_node.text():
                continue
            address_candidate = address_node.text().replace(
                "Xem trên bản đồ", ""
            ).strip()
            if not self._is_garbage_address(address_candidate):
                return address_candidate
        return None

    def _extract_address(self, root: HtmlNode) -> str | None:
        return most_specific_address(
            self._extract_structured_address(root),
            self._semantic_address(root),
            self._extract_scoped_address(root),
        )

    def parse(self, html: str, detail_url: str = "", source_url: str = "", listing_id: str | None = None, **kwargs):
        """Extract one source-near detail record without semantic cleaning."""
        if not html or not html.strip():
            return None
        root = parse_html(html)
        effective_url = detail_url or source_url
        if not listing_id:
            match = self.ID_PATTERN.search(effective_url)
            listing_id = match.group(1) if match else urlparse(effective_url).path.strip("/").removesuffix(".html")
        address = self._extract_address(root)
        images = []
        for image in root.find_all(tag="img"):
            src = image.attrs.get("data-src") or image.attrs.get("src")
            if src and not src.startswith("data:"):
                absolute = urljoin(effective_url, src)
                if absolute not in images:
                    images.append(absolute)
        title = first_text(root, self.TITLE_CLASSES)
        if not title:
            h1 = root.first(tag="h1")
            title = h1.text() if h1 else None

        map_location = MapLocationExtractor.extract_map_from_html(html)

        return ListingDetailRaw(
            map_location=map_location,
            source=self.source_name,
            listing_id=listing_id,
            detail_url=effective_url,
            title_raw=title,
            price_raw=first_text(root, self.PRICE_CLASSES),
            area_raw=first_text(root, self.AREA_CLASSES),
            address_raw=address or (map_location.query_raw if map_location else None),
            location_raw=address or (map_location.query_raw if map_location else None),
            description_raw=first_text(root, self.DESCRIPTION_CLASSES),
            seller_name_raw=first_text(root, self.SELLER_CLASSES),
            image_urls_raw=images,
        )


class QueryPagination:
    """Build page-number URLs using a source-declared query parameter."""

    PARAMETER = "page"

    def build_page_url(self, base_url: str = "", page_number: int = 1, *args, **kwargs):
        """Insert the configured page query parameter while preserving the URL."""
        if page_number <= 1:
            return base_url
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query[self.PARAMETER] = [str(page_number)]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def has_next_page(self, current_page: int, max_pages: int, current_items_count: int, **kwargs):
        """Continue only while limits remain and the current page produced items."""
        return current_page < max_pages and current_items_count > 0


class PathPagination(QueryPagination):
    """Build `/page/N` URLs for sources whose audited route uses that form."""

    def build_page_url(self, base_url: str = "", page_number: int = 1, *args, **kwargs):
        """Append the source's ``/page/N`` suffix for pages after the first."""
        if page_number <= 1:
            return base_url
        parsed = urlparse(base_url)
        path = re.sub(r"/page/\d+/?$", "", parsed.path.rstrip("/")) + f"/page/{page_number}"
        return urlunparse(parsed._replace(path=path))


class EmbeddedMetadataParser:
    """Read only embedded meta and JSON-LD records."""

    @staticmethod
    def parse_meta_tags(html: str):
        """Extract case-insensitive meta names and raw content values."""
        return {key.casefold(): value for key, value in re.findall(r'<meta[^>]+(?:name|property)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)', html or "", re.I)}

    @staticmethod
    def parse_json_ld(html: str):
        """Extract valid object/list JSON-LD payloads and ignore malformed blocks."""
        values = []
        for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html or "", re.I | re.S):
            try:
                value = json.loads(raw.strip())
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            values.extend(value if isinstance(value, list) else [value] if isinstance(value, dict) else [])
        return values


class VietnameseDateInterpreter:
    """Interpret common relative Vietnamese timestamps for frontier policies."""

    @staticmethod
    def interpret(posted_at_raw: str | None, reference_now: datetime | None = None):
        """Convert supported Vietnamese relative dates into UTC datetimes."""
        if not posted_at_raw:
            return None
        now = reference_now or datetime.now(timezone.utc)
        text = posted_at_raw.casefold()
        if "vừa" in text or "hôm nay" in text:
            return now
        if "hôm qua" in text:
            return now - timedelta(days=1)
        for unit, delta in (("phút", "minutes"), ("giờ", "hours"), ("ngày", "days")):
            match = re.search(rf"(\d+)\s*{unit}", text)
            if match:
                return now - timedelta(**{delta: int(match.group(1))})
        match = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
        if match:
            try:
                return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1)), tzinfo=timezone.utc)
            except ValueError:
                return None
        return None
