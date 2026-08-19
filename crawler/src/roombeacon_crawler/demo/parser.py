import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.demo.models.crawl_record import CrawlRecord
from roombeacon_crawler.demo.sources.nhatot.selectors import (
    AREA_CLASSES,
    CARD_CONTAINER_CLASSES,
    CARD_CONTAINER_TESTIDS,
    LOCATION_CLASSES,
    MAIN_CONTAINER_CLASSES,
    MAIN_CONTAINER_TESTIDS,
    PRICE_CLASSES,
    TITLE_CLASSES,
)

# Strict price pattern with word boundary and valid currency units
PRICE_REGEX = re.compile(
    r"\b(\d+(?:[.,]\d+)?\s*(?:triệu|tr|nghìn|tỷ|đ|vnđ)(?:\s*/\s*(?:tháng|m[²2]))?|\d{1,3}(?:\.\d{3})+\s*(?:đ|vnđ|đồng)(?:\s*/\s*tháng)?|thỏa\s+thuận|giá\s+thỏa\s+thuận)\b",
    re.IGNORECASE,
)

# Strict area pattern for square meters only
AREA_REGEX = re.compile(
    r"\b(\d+(?:[.,]\d+)?\s*m(?:²|2))\b",
    re.IGNORECASE,
)

# Vietnamese geographic prefixes for location identification
LOCATION_PREFIX_REGEX = re.compile(
    r"((?:Quận|Huyện|Thị\s+xã|TP\.|TP\s+|Thành\s+phố|Phường|Đường|Xã)\s+[^,·\n\r|]{2,40}(?:,\s*(?:TP\.?\s*Hồ\s*Chí\s*Minh|TP\.?\s*HCM|Hà\s*Nội|Đà\s*Nẵng|Bình\s*Dương|Đồng\s*Nai|Cần\s*Thơ|[^,·\n\r|]{2,30}))*)",
    re.IGNORECASE,
)


def validate_price(price_raw: str | None) -> str | None:
    if not price_raw:
        return None
    m = PRICE_REGEX.search(price_raw)
    if m:
        val = m.group(1).strip()
        # Reject false positives like "6 K", "10 K"
        if re.match(r"^\d+\s*k$", val, re.IGNORECASE):
            return None
        return val
    return None


def validate_area(area_raw: str | None) -> str | None:
    if not area_raw:
        return None
    m = AREA_REGEX.search(area_raw)
    if m:
        return m.group(1).strip()
    return None


def clean_title(title_raw: str | None) -> str | None:
    if not title_raw:
        return None
    text = title_raw.strip()
    # Strip prefix badges like "Tin ưu tiên 6", "Tin ưu tiên 10", "Môi giới", "Đã xác thực"
    text = re.sub(
        r"^(?:tin\s+ưu\s+tiên\s*\d*|đã\s+xác\s+thực|môi\s+giới|chính\s+chủ|hot|mới)\s*[:·•|-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = " ".join(text.split())
    return text if len(text) >= 3 else None


def clean_location(loc_raw: str | None) -> str | None:
    if not loc_raw:
        return None
    text = loc_raw.strip()
    # Strip prefix badges
    text = re.sub(
        r"^(?:tin\s+ưu\s+tiên\s*\d*|đã\s+xác\s+thực|môi\s+giới|chính\s+chủ|hot|mới)\s*[:·•|-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Strip time markers (e.g. 3 giờ trước, 1 ngày trước)
    text = re.sub(
        r"\s*[·•|-]?\s*\d+\s*(?:giờ|ngày|phút|tháng|năm)\s*trước.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*[·•|-]?\s*(?:hôm\s+nay|vừa\s+xong|hôm\s+qua).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Strip area markers (e.g. 35m2, 30 m2, 35 m²)
    text = re.sub(
        r"\s*[·•|-]?\s*\d+(?:[.,]\d+)?\s*m(?:²|2).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Strip price markers (e.g. 2 triệu/tháng, 3.5 tr/tháng)
    text = re.sub(
        r"\s*[·•|-]?\s*\d+(?:[.,]\d+)?\s*(?:triệu|tr|nghìn|đ|vnđ).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Strip interior / status fluff
    text = re.sub(
        r"\s*[·•|-]?\s*(?:nội\s+thất\s+đầy\s+đủ|tin\s+ưu\s+tiên\s*\d*|đã\s+xác\s+thực|môi\s+giới|chính\s+chủ).*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.strip(" ·•|-,/")
    return text if len(text) >= 2 else None


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
        data_testid: str | None = None,
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

        if data_testid:
            dt = self.attrs.get("data-testid", "")
            if data_testid.lower() not in dt.lower():
                match = False

        if attr_has:
            k, v = attr_has
            if k.lower() not in self.attrs or v.lower() not in self.attrs[k.lower()].lower():
                match = False

        if match and (tag or class_contains or data_testid or attr_has):
            results.append(self)

        for child in self.children:
            results.extend(child.find_all(tag, class_contains, data_testid, attr_has))

        return results

    def find(
        self,
        tag: str | None = None,
        class_contains: str | None = None,
        data_testid: str | None = None,
        attr_has: tuple[str, str] | None = None,
    ) -> "DOMNode | None":
        res = self.find_all(tag, class_contains, data_testid, attr_has)
        return res[0] if res else None


class DOMTreeBuilder(HTMLParser):
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr",
        "img", "input", "link", "meta", "param",
        "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.root = DOMNode("root", [])
        self.current = self.root

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = DOMNode(tag, attrs, parent=self.current)
        self.current.children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.VOID_TAGS:
            return
        curr = self.current
        while curr.parent is not None:
            if curr.tag == tag.lower():
                self.current = curr.parent
                break
            curr = curr.parent

    def handle_data(self, data: str) -> None:
        cleaned = data.strip()
        if cleaned:
            self.current.text_parts.append(cleaned)


class RentalParser:
    def __init__(self) -> None:
        self.debug_stats: dict[str, object] = {
            "html_input_size": 0,
            "main_container_found": False,
            "visible_cards": 0,
            "records_extracted": 0,
            "duplicates_removed": 0,
            "records_after_dedup": 0,
            "card_previews": [],
        }

    def parse(
        self,
        html: str,
        source_url: str,
        limit: int = 50,
    ) -> list[CrawlRecord]:
        self.debug_stats = {
            "html_input_size": len(html) if html else 0,
            "main_container_found": False,
            "visible_cards": 0,
            "records_extracted": 0,
            "duplicates_removed": 0,
            "records_after_dedup": 0,
            "card_previews": [],
        }

        if not html:
            return []

        try:
            builder = DOMTreeBuilder()
            builder.feed(html)
        except Exception:
            return []

        # Step 1: Locate Main Listing Container
        main_container = self._find_main_container(builder.root)
        if main_container is not None:
            self.debug_stats["main_container_found"] = True
            search_root = main_container
        else:
            self.debug_stats["main_container_found"] = False
            search_root = builder.root

        # Step 2: Locate Listing Cards inside Main Container
        cards = self._find_listing_cards(search_root)
        self.debug_stats["visible_cards"] = len(cards)

        records: list[CrawlRecord] = []
        seen_urls: set[str] = set()
        previews: list[str] = []
        duplicates_removed = 0
        total_extracted = 0

        for card in cards:
            record = self._parse_single_card(card, source_url)
            if record and record.url:
                total_extracted += 1
                preview = " ".join(card.get_text().split())[:100]

                if record.url in seen_urls:
                    duplicates_removed += 1
                else:
                    seen_urls.add(record.url)
                    records.append(record)
                    previews.append(preview)
                    if len(records) >= limit:
                        break

        self.debug_stats["records_extracted"] = total_extracted
        self.debug_stats["duplicates_removed"] = duplicates_removed
        self.debug_stats["records_after_dedup"] = len(records)
        self.debug_stats["card_previews"] = previews

        return records[:limit]

    def _find_main_container(self, root: DOMNode) -> DOMNode | None:
        # Check testids first
        for testid in MAIN_CONTAINER_TESTIDS:
            found = root.find(data_testid=testid)
            if found:
                return found

        # Check classes
        for cls in MAIN_CONTAINER_CLASSES:
            found = root.find(class_contains=cls)
            if found:
                return found

        # Check semantic main tag
        main_tag = root.find(tag="main")
        if main_tag:
            return main_tag

        return None

    def _find_listing_cards(self, search_root: DOMNode) -> list[DOMNode]:
        cards: list[DOMNode] = []

        # Primary: card wrapper classes
        for cls in ("AdItem_adItemWrapper", "AdItem_wrapper"):
            for item in search_root.find_all(class_contains=cls):
                if item not in cards and not self._is_descendant_of_any(item, cards):
                    cards.append(item)

        # Secondary: card testids
        for testid in CARD_CONTAINER_TESTIDS:
            for item in search_root.find_all(data_testid=testid):
                if item not in cards and not self._is_descendant_of_any(item, cards):
                    cards.append(item)

        # Tertiary: direct adItem class if wrapper wasn't present
        if not cards:
            for item in search_root.find_all(class_contains="AdItem_adItem"):
                if item not in cards and not self._is_descendant_of_any(item, cards):
                    cards.append(item)

        # Fallback: listing links
        if not cards:
            for a_tag in search_root.find_all(tag="a"):
                href = a_tag.attrs.get("href", "")
                if ".htm" in href and ("thue-phong-tro" in href or "thue" in href):
                    parent = (
                        a_tag.parent
                        if a_tag.parent and a_tag.parent.tag in ("li", "div", "article")
                        else a_tag
                    )
                    if parent not in cards and not self._is_descendant_of_any(parent, cards):
                        cards.append(parent)

        return cards

    def _is_descendant_of_any(self, node: DOMNode, ancestors: list[DOMNode]) -> bool:
        curr = node.parent
        while curr is not None:
            if curr in ancestors:
                return True
            curr = curr.parent
        return False

    def _parse_single_card(
        self,
        card: DOMNode,
        source_url: str,
    ) -> CrawlRecord | None:
        # Extract URL strictly from inside card
        href: str | None = None
        if card.tag == "a" and "href" in card.attrs:
            href = card.attrs["href"]
        else:
            a_tags = card.find_all(tag="a")
            for a in a_tags:
                h = a.attrs.get("href", "")
                if h and not h.startswith("#") and not h.startswith("javascript:"):
                    if ".htm" in h or "thue" in h or "/" in h:
                        href = h
                        break

        if not href:
            return None

        abs_url = urljoin(source_url, href).split("#")[0]
        parsed_url = urlparse(abs_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return None

        if parsed_url.path in ("", "/", "/chuyen-muc", "/dashboard", "/login", "/tro-giup"):
            return None

        card_text = card.get_text()

        # 1. Extract Title strictly inside card
        title: str | None = None
        for cls in TITLE_CLASSES:
            node = card.find(class_contains=cls)
            if node:
                t = clean_title(node.get_text())
                if t:
                    title = t
                    break

        if not title:
            for tag_name in ("h3", "h2", "h4"):
                node = card.find(tag=tag_name)
                if node:
                    t = clean_title(node.get_text())
                    if t:
                        title = t
                        break

        if not title:
            title_node = card.find(attr_has=("itemprop", "name"))
            if title_node:
                title = clean_title(title_node.get_text())

        # 2. Extract Price strictly inside card
        price: str | None = None
        for cls in PRICE_CLASSES:
            node = card.find(class_contains=cls)
            if node:
                p = validate_price(node.get_text())
                if p:
                    price = p
                    break

        if not price:
            price_node = card.find(attr_has=("itemprop", "price"))
            if price_node:
                price = validate_price(price_node.get_text())

        if not price:
            price = validate_price(card_text)

        # 3. Extract Area strictly inside card
        area: str | None = None
        for cls in AREA_CLASSES:
            node = card.find(class_contains=cls)
            if node:
                a = validate_area(node.get_text())
                if a:
                    area = a
                    break

        if not area:
            area = validate_area(card_text)

        # 4. Extract Location strictly inside card
        location: str | None = None
        for cls in LOCATION_CLASSES:
            node = card.find(class_contains=cls)
            if node:
                loc = clean_location(node.get_text())
                if loc:
                    location = loc
                    break

        if not location:
            loc_node = card.find(attr_has=("itemprop", "address"))
            if loc_node:
                location = clean_location(loc_node.get_text())

        if not location:
            m = LOCATION_PREFIX_REGEX.search(card_text)
            if m:
                location = clean_location(m.group(1))

        if not title and not price:
            return None

        return CrawlRecord(
            title=title,
            price=price,
            area=area,
            location=location,
            url=abs_url,
        )
