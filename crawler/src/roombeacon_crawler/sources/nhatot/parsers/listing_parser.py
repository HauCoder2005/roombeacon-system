from html.parser import HTMLParser
import logging
import re
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.sources.nhatot.selectors.listing_selectors import (
    AREA_CLASSES,
    CARD_CONTAINER_CLASSES,
    CARD_CONTAINER_TESTIDS,
    LOCATION_CLASSES,
    MAIN_CONTAINER_CLASSES,
    MAIN_CONTAINER_TESTIDS,
    POSTED_AT_CLASSES,
    PRICE_CLASSES,
    SELLER_CLASSES,
    TITLE_CLASSES,
)

logger = logging.getLogger(__name__)

PRICE_REGEX = re.compile(
    r"\b(\d+(?:[.,]\d+)?\s*(?:triệu|tr|nghìn|tỷ|đ|vnđ)(?:\s*/\s*(?:tháng|m[²2]))?|\d{1,3}(?:\.\d{3})+\s*(?:đ|vnđ|đồng)(?:\s*/\s*tháng)?|thỏa\s+thuận|giá\s+thỏa\s+thuận)\b",
    re.IGNORECASE,
)

AREA_REGEX = re.compile(
    r"\b(\d+(?:[.,]\d+)?\s*m(?:²|2))\b",
    re.IGNORECASE,
)

LOCATION_PREFIX_REGEX = re.compile(
    r"((?:Quận|Huyện|Thị\s+xã|TP\.|TP\s+|Thành\s+phố|Phường|Đường|Xã)\s+[^,·\n\r|]{2,40}(?:,\s*(?:TP\.?\s*Hồ\s*Chí\s*Minh|TP\.?\s*HCM|Hà\s*Nội|Đà\s*Nẵng|Bình\s*Dương|Đồng\s*Nai|Cần\s*Thơ|[^,·\n\r|]{2,30}))*)",
    re.IGNORECASE,
)

ID_FROM_URL_REGEX = re.compile(r"/(\d+)\.htm", re.IGNORECASE)


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


class NhatotListingParser:
    """Parser chuyên trách bóc tách dữ liệu danh sách tin đăng từ HTML trang listing của Nhà Tốt."""

    def __init__(self, source_name: str = "nhatot") -> None:
        self.source_name = source_name

    def parse(
        self,
        html: str,
        source_url: str,
        page_number: int = 1,
        limit: int = 50,
    ) -> list[ListingCardRaw]:
        """Trích xuất danh sách các ListingCardRaw từ nội dung HTML của trang listing."""
        if not html:
            return []

        try:
            builder = DOMTreeBuilder()
            builder.feed(html)
        except Exception as exc:
            logger.error("Lỗi khi parse DOM tree listing Nhà Tốt: %s", exc)
            return []

        search_root = self._locate_main_container(builder.root)
        card_nodes = self._locate_card_nodes(search_root)

        records: list[ListingCardRaw] = []
        seen_urls: set[str] = set()

        for position, card_node in enumerate(card_nodes, 1):
            if len(records) >= limit:
                break

            record = self._extract_card(
                card_node=card_node,
                source_url=source_url,
                position=position,
                page_number=page_number,
            )
            if record and record.detail_url and record.detail_url not in seen_urls:
                seen_urls.add(record.detail_url)
                records.append(record)

        return records

    def _locate_main_container(self, root: DOMNode) -> DOMNode:
        """Xác định vùng danh sách tin chính để tránh nhặt nhầm sidebar/quảng cáo ngoài."""
        for testid in MAIN_CONTAINER_TESTIDS:
            found = root.find(data_testid=testid)
            if found:
                return found

        for cls in MAIN_CONTAINER_CLASSES:
            found = root.find(class_contains=cls)
            if found:
                return found

        main_tag = root.find(tag="main")
        if main_tag:
            return main_tag

        return root

    def _locate_card_nodes(self, search_root: DOMNode) -> list[DOMNode]:
        """Tìm các node listing card riêng biệt bên trong vùng danh sách chính."""
        cards: list[DOMNode] = []

        for cls in CARD_CONTAINER_CLASSES:
            for item in search_root.find_all(class_contains=cls):
                if item not in cards and not self._is_descendant(item, cards):
                    cards.append(item)

        if not cards:
            for testid in CARD_CONTAINER_TESTIDS:
                for item in search_root.find_all(data_testid=testid):
                    if item not in cards and not self._is_descendant(item, cards):
                        cards.append(item)

        if not cards:
            for a_tag in search_root.find_all(tag="a"):
                href = a_tag.attrs.get("href", "")
                if ".htm" in href and ("thue-phong-tro" in href or "thue" in href):
                    parent = (
                        a_tag.parent
                        if a_tag.parent and a_tag.parent.tag in ("li", "div", "article")
                        else a_tag
                    )
                    if parent not in cards and not self._is_descendant(parent, cards):
                        cards.append(parent)

        return cards

    def _is_descendant(self, node: DOMNode, ancestors: list[DOMNode]) -> bool:
        curr = node.parent
        while curr is not None:
            if curr in ancestors:
                return True
            curr = curr.parent
        return False

    def _extract_card(
        self,
        card_node: DOMNode,
        source_url: str,
        position: int,
        page_number: int,
    ) -> ListingCardRaw | None:
        """Trích xuất từng trường dữ liệu thô từ một node card đơn lẻ."""
        # 1. Detail URL
        href: str | None = None
        if card_node.tag == "a" and "href" in card_node.attrs:
            href = card_node.attrs["href"]
        else:
            for a in card_node.find_all(tag="a"):
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

        # 2. Listing ID
        listing_id_match = ID_FROM_URL_REGEX.search(abs_url)
        listing_id = listing_id_match.group(1) if listing_id_match else None

        card_text = card_node.get_text()

        # 3. Title Raw
        title_raw: str | None = None
        for cls in TITLE_CLASSES:
            node = card_node.find(class_contains=cls)
            if node:
                t = self._clean_title(node.get_text())
                if t:
                    title_raw = t
                    break

        if not title_raw:
            for tag_name in ("h3", "h2", "h4"):
                node = card_node.find(tag=tag_name)
                if node:
                    t = self._clean_title(node.get_text())
                    if t:
                        title_raw = t
                        break

        # 4. Price Raw
        price_raw: str | None = None
        for cls in PRICE_CLASSES:
            node = card_node.find(class_contains=cls)
            if node:
                p = self._extract_price(node.get_text())
                if p:
                    price_raw = p
                    break

        if not price_raw:
            price_raw = self._extract_price(card_text)

        # 5. Area Raw
        area_raw: str | None = None
        for cls in AREA_CLASSES:
            node = card_node.find(class_contains=cls)
            if node:
                a = self._extract_area(node.get_text())
                if a:
                    area_raw = a
                    break

        if not area_raw:
            area_raw = self._extract_area(card_text)

        # 6. Location Raw
        location_raw: str | None = None
        for cls in LOCATION_CLASSES:
            node = card_node.find(class_contains=cls)
            if node:
                loc = self._clean_location(node.get_text())
                if loc:
                    location_raw = loc
                    break

        if not location_raw:
            m = LOCATION_PREFIX_REGEX.search(card_text)
            if m:
                location_raw = self._clean_location(m.group(1))

        # 7. Posted At Raw
        posted_at_raw: str | None = None
        for cls in POSTED_AT_CLASSES:
            node = card_node.find(class_contains=cls)
            if node:
                posted_at_raw = node.get_text().strip() or None
                break

        # 8. Seller Raw
        seller_name_raw: str | None = None
        for cls in SELLER_CLASSES:
            node = card_node.find(class_contains=cls)
            if node:
                seller_name_raw = node.get_text().strip() or None
                break

        # 9. Thumbnail Image
        thumbnail_url_raw: str | None = None
        img_node = card_node.find(tag="img")
        if img_node:
            img_src = img_node.attrs.get("src") or img_node.attrs.get("data-src")
            if img_src:
                thumbnail_url_raw = urljoin(source_url, img_src)

        if not title_raw and not price_raw:
            return None

        return ListingCardRaw(
            source=self.source_name,
            listing_id=listing_id,
            detail_url=abs_url,
            title_raw=title_raw,
            price_raw=price_raw,
            area_raw=area_raw,
            location_raw=location_raw,
            posted_at_raw=posted_at_raw,
            seller_name_raw=seller_name_raw,
            seller_type_raw=None,
            thumbnail_url_raw=thumbnail_url_raw,
            card_position=position,
            page_number=page_number,
        )

    def _clean_title(self, raw: str) -> str | None:
        text = raw.strip()
        text = re.sub(
            r"^(?:tin\s+ưu\s+tiên\s*\d*|đã\s+xác\s+thực|môi\s+giới|chính\s+chủ|hot|mới)\s*[:·•|-]?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = " ".join(text.split())
        return text if len(text) >= 3 else None

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

    def _clean_location(self, raw: str) -> str | None:
        text = raw.strip()
        text = re.sub(
            r"^(?:tin\s+ưu\s+tiên\s*\d*|đã\s+xác\s+thực|môi\s+giới|chính\s+chủ|hot|mới)\s*[:·•|-]?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
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
        text = re.sub(
            r"\s*[·•|-]?\s*\d+(?:[.,]\d+)?\s*m(?:²|2).*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*[·•|-]?\s*\d+(?:[.,]\d+)?\s*(?:triệu|tr|nghìn|đ|vnđ).*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*[·•|-]?\s*(?:nội\s+thất\s+đầy\s+đủ|tin\s+ưu\s+tiên\s*\d*|đã\s+xác\s+thực|môi\s+giới|chính\s+chủ).*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = text.strip(" ·•|-,/")
        return text if len(text) >= 2 else None
