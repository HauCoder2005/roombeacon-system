"""Provide small HTML primitives reused by source-specific rental parsers.

The module handles DOM traversal and safe raw-value extraction only. Selector
choices, URL identity rules and source capabilities remain in each source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw


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

@dataclass
class LocationCandidate:
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_url: str | None = None


def extract_google_maps_info(
    root: "HtmlNode | None", html: str | None = None
) -> LocationCandidate:
    """Extract a map address or coordinates from structured HTML attributes."""
    cand = LocationCandidate()
    if not root:
        return cand

    for iframe in root.find_all(tag="iframe"):
        src = (iframe.attrs.get("src") or iframe.attrs.get("data-src") or "").strip()
        if "google.com/maps" in src or "maps.google.com" in src:
            parsed = urlparse(src)
            qs = parse_qs(parsed.query)

            if "q" in qs:
                q_val = qs["q"][0]
                coords_match = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", q_val)
                if coords_match:
                    cand.latitude = float(coords_match.group(1))
                    cand.longitude = float(coords_match.group(2))
                else:
                    cand.address = q_val.replace("+", " ").strip()
            
            if cand.latitude is None and cand.longitude is None:
                for param in ("ll", "center", "sll"):
                    if param in qs:
                        coords_match = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", qs[param][0])
                        if coords_match:
                            cand.latitude = float(coords_match.group(1))
                            cand.longitude = float(coords_match.group(2))
                            break

            if cand.latitude is not None or cand.longitude is not None or cand.address:
                return cand

    for el in root.find_all():
        lat = el.attrs.get("data-lat") or el.attrs.get("data-latitude")
        lng = el.attrs.get("data-lng") or el.attrs.get("data-longitude")
        addr = el.attrs.get("data-address")
        if lat and lng:
            try:
                cand.latitude = float(lat)
                cand.longitude = float(lng)
            except ValueError:
                pass
        if addr:
            cand.address = addr
        if cand.latitude is not None or cand.longitude is not None or cand.address is not None:
            return cand

    for script in root.find_all(tag="script"):
        if script.attrs.get("type") == "application/ld+json":
            try:
                import json
                data = json.loads(script.text())
                if isinstance(data, dict):
                    geo = data.get("geo")
                    if isinstance(geo, dict):
                        lat = geo.get("latitude")
                        lng = geo.get("longitude")
                        if lat is not None and lng is not None:
                            cand.latitude = float(lat)
                            cand.longitude = float(lng)
                            return cand
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    return cand


def normalize_vietnamese_phone(phone: str | None) -> str | None:
    """Normalize Vietnamese phone to 09xxxxxxxx."""
    if not phone:
        return None
    cleaned = re.sub(r"[\s.\-()]", "", phone)
    if cleaned.startswith("+84"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("84"):
        cleaned = "0" + cleaned[2:]
    if len(cleaned) >= 9 and cleaned.startswith("0"):
        return cleaned
    return None


def extract_phone_from_text(text: str | None) -> str | None:
    """Extract raw phone string from text."""
    if not text:
        return None
    match = re.search(r"(?:\+?84|0)[\d\s.\-()]{7,15}", text)
    if match:
        candidate = match.group(0).strip(" .")
        if len(re.sub(r"[\s.\-()]", "", candidate)) >= 9:
            return candidate
    return None


def extract_scoped_phone(
    root: HtmlNode | None,
    fallback_text: str | None = None,
    **_kwargs,
) -> str | None:
    """Extract phone strictly within a specific container."""
    if not root:
        return extract_phone_from_text(fallback_text)

    for script in root.find_all(tag="script"):
        text = script.text()
        if text:
            match = re.search(
                r"(?:phone|mobile|hotline)[\"']?\s*[:=]\s*[\"']([0-9\s.+]+)[\"']",
                text,
                re.IGNORECASE,
            )
            if match:
                phone = match.group(1).strip()
                if len(re.sub(r"[\s.\-()]", "", phone)) >= 9:
                    return phone

    for a in root.find_all(tag="a"):
        href = a.attrs.get("href", "").strip()
        if href.startswith("tel:"):
            phone = href[4:].strip()
            if phone.startswith("1900") or phone.startswith("1800"):
                continue
            if phone and "*" not in phone:
                return phone

    for el in root.find_all():
        phone = el.attrs.get("data-phone") or el.attrs.get("data-mobile")
        if phone:
            phone_str = str(phone).strip()
            is_service_number = phone_str.startswith(("1800", "1900"))
            if "*" not in phone_str and not is_service_number:
                return phone_str

    text = root.text()
    found = extract_phone_from_text(text)
    if found and not found.startswith("1900") and not found.startswith("1800"):
        return found

    found = extract_phone_from_text(fallback_text)
    if found and not found.startswith("1900") and not found.startswith("1800"):
        return found
    return None


def extract_best_image_url(attrs: dict[str, str], base_url: str) -> str | None:
    """Extract best image URL respecting priority and srcset resolution."""
    for attr in ("data-original", "data-lazy-src", "data-src"):
        val = attrs.get(attr)
        if val and isinstance(val, str) and not val.startswith("data:"):
            return urljoin(base_url, val.strip())

    srcset = attrs.get("srcset")
    if srcset and isinstance(srcset, str):
        candidates = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            pieces = part.split()
            url = pieces[0]
            if url.startswith("data:"):
                continue
            size = 0
            if len(pieces) > 1:
                match = re.match(r"^(\d+)[wx]$", pieces[1])
                if match:
                    size = int(match.group(1))
            candidates.append((size, url))
        if candidates:
            candidates.sort(key=lambda candidate: candidate[0], reverse=True)
            return urljoin(base_url, candidates[0][1])

    src = attrs.get("src")
    if src and isinstance(src, str) and not src.startswith("data:"):
        return urljoin(base_url, src.strip())

    return None


def deduplicate_images(urls: list[str]) -> list[str]:
    """Keep image order while removing duplicate URLs."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def extract_json_ld_images(root: HtmlNode | None, base_url: str) -> list[str]:
    """Extract images from JSON-LD representing the listing."""
    if not root:
        return []
    images: list[str] = []
    for script in root.find_all(tag="script"):
        t = script.attrs.get("type")
        if t != "application/ld+json":
            continue
        text = script.text()
        if not text:
            continue
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    item_type = item_type[0]
                supported_types = {
                    "Product",
                    "RealEstateListing",
                    "Apartment",
                    "House",
                    "Accommodation",
                    "Room",
                    "Place",
                }
                if item_type in supported_types:
                    img = item.get("image")
                    if isinstance(img, str):
                        images.append(urljoin(base_url, img))
                    elif isinstance(img, list):
                        for i in img:
                            if isinstance(i, str):
                                images.append(urljoin(base_url, i))
                            elif isinstance(i, dict) and "url" in i:
                                images.append(urljoin(base_url, i["url"]))
                    elif isinstance(img, dict) and "url" in img:
                        images.append(urljoin(base_url, img["url"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return deduplicate_images(images)


def extract_scoped_images(
    container: HtmlNode | None,
    base_url: str,
) -> list[str]:
    """Extract deduplicated images strictly within a specific container."""
    if not container:
        return []
    images: list[str] = []
    for img in container.find_all(tag="img"):
        url = extract_best_image_url(img.attrs, base_url)
        if url:
            images.append(url)
    return deduplicate_images(images)

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

    MAP_CLASSES: tuple[str, ...] = ()

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

    MAP_CLASSES: tuple[str, ...] = ()

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
        structured_address = self._extract_structured_address(root)
        if structured_address:
            return structured_address

        semantic_address = self._semantic_address(root)
        if semantic_address:
            return semantic_address

        return self._extract_scoped_address(root)

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
        gallery_classes = getattr(self, "GALLERY_CLASSES", ()) or ()
        if gallery_classes:
            gallery_container = None
            for cls in gallery_classes:
                found = root.find_all(class_token=cls)
                if found:
                    gallery_container = found[0]
                    break
            images = extract_scoped_images(gallery_container, effective_url)
            
        if not images:
            images = extract_json_ld_images(root, effective_url)
            
        title = None
        h1 = root.first(tag="h1")
        if h1:
            title = h1.text() or None
            
        if not title:
            title = first_text(root, self.TITLE_CLASSES)

        lat = None
        lng = None
        if self.MAP_CLASSES:
            for cls in self.MAP_CLASSES:
                map_nodes = root.find_all(class_token=cls)
                if map_nodes:
                    cand = extract_google_maps_info(map_nodes[0], html)
                    if cand.latitude is not None and cand.longitude is not None:
                        from roombeacon_crawler.validators.location_validator import LocationValidator
                        v_lat, v_lng = LocationValidator.validate_coordinates(cand.latitude, cand.longitude, self.source_name)
                        lat, lng = v_lat, v_lng
                    if cand.address and not address:
                        address = cand.address
                    break

        # Phone Extraction Logic
        seller_phone = None
        seller_classes = getattr(self, "SELLER_CLASSES", ()) or ()
        contact_classes = getattr(self, "CONTACT_CLASSES", ()) or ()
        all_classes = tuple(seller_classes) + tuple(contact_classes)
        
        if all_classes:
            seller_container = None
            for cls in all_classes:
                found = root.find_all(class_token=cls)
                if found:
                    seller_container = found[0]
                    break
            seller_phone = extract_scoped_phone(seller_container, fallback_text=first_text(root, self.DESCRIPTION_CLASSES))
        else:
            seller_phone = extract_phone_from_text(first_text(root, self.DESCRIPTION_CLASSES))

        return ListingDetailRaw(
            source=self.source_name,
            listing_id=listing_id,
            detail_url=effective_url,
            title_raw=title,
            price_raw=first_text(root, self.PRICE_CLASSES),
            area_raw=first_text(root, self.AREA_CLASSES),
            address_raw=address,
            location_raw=address,
            latitude=lat,
            longitude=lng,
            description_raw=first_text(root, self.DESCRIPTION_CLASSES),
            seller_name_raw=first_text(root, self.SELLER_CLASSES),
            seller_phone_raw=seller_phone,
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
