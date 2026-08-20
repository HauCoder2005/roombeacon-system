from html.parser import HTMLParser
import logging
import re
from urllib.parse import urljoin, urlparse

from roombeacon_crawler.models.listing_card_raw import ListingCardRaw

logger = logging.getLogger(__name__)

ID_REGEX = re.compile(r"(?:-pr(\d+)|-(\d+)\.html|/(\d+)\.htm)", re.IGNORECASE)
PRICE_REGEX = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:triệu|tr|nghìn|k|tỷ|đ|đồng|vnđ)(?:\s*/\s*(?:tháng|m[²2]))?|\d{1,3}(?:\.\d{3})+\s*(?:đ|vnđ|đồng)(?:\s*/\s*tháng)?|thỏa\s+thuận)",
    re.IGNORECASE,
)
AREA_REGEX = re.compile(r"(\d+(?:[.,]\d+)?\s*m(?:²|2))", re.IGNORECASE)


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


class Phongtro123ListingParser:
    """Parser bóc tách danh sách phòng trọ từ HTML trang listing của Phongtro123."""

    def __init__(self, source_name: str = "phongtro123") -> None:
        self.source_name = source_name

    def parse(
        self,
        html: str,
        source_url: str,
        page_number: int = 1,
        limit: int = 50,
    ) -> list[ListingCardRaw]:
        if not html or not html.strip():
            return []

        cards: list[ListingCardRaw] = []
        seen_urls: set[str] = set()

        try:
            builder = DOMTreeBuilder()
            builder.feed(html)

            # Tìm các card items
            post_items = builder.root.find_all(class_contains="post-item")
            if not post_items:
                post_items = builder.root.find_all(class_contains="item-post")

            position = 0
            for item in post_items:
                if len(cards) >= limit:
                    break

                # Detail link
                title_node = item.find(class_contains="post-title") or item.find(tag="h3")
                link_node = title_node.find(tag="a") if title_node else item.find(tag="a")
                if not link_node:
                    continue

                raw_href = link_node.attrs.get("href", "").strip()
                if not raw_href:
                    continue

                detail_url = urljoin(source_url, raw_href)
                if detail_url in seen_urls:
                    continue

                title_raw = title_node.get_text() if title_node else link_node.get_text()
                if not title_raw:
                    continue

                # ID extraction
                id_match = ID_REGEX.search(detail_url)
                listing_id = ""
                if id_match:
                    listing_id = next(g for g in id_match.groups() if g is not None)
                if not listing_id:
                    listing_id = urlparse(detail_url).path.strip("/").replace(".html", "")

                # Price
                price_node = item.find(class_contains="post-price") or item.find(class_contains="item-price") or item.find(class_contains="price")
                price_raw = price_node.get_text() if price_node else None
                if not price_raw:
                    match = PRICE_REGEX.search(item.get_text())
                    price_raw = match.group(1) if match else None

                # Area
                area_node = item.find(class_contains="post-acreage") or item.find(class_contains="item-acreage") or item.find(class_contains="acreage")
                area_raw = area_node.get_text() if area_node else None
                if not area_raw:
                    match = AREA_REGEX.search(item.get_text())
                    area_raw = match.group(1) if match else None

                # Location
                loc_node = item.find(class_contains="post-location") or item.find(class_contains="location") or item.find(class_contains="post-address")
                location_raw = loc_node.get_text() if loc_node else None

                # Time
                time_node = item.find(class_contains="post-time") or item.find(class_contains="time") or item.find(tag="time")
                posted_at_raw = time_node.get_text() if time_node else None

                # Author
                author_node = item.find(class_contains="post-author") or item.find(class_contains="author") or item.find(class_contains="user-name")
                seller_name_raw = author_node.get_text() if author_node else None

                # Thumbnail image
                img_node = item.find(tag="img")
                thumbnail_url_raw = None
                if img_node:
                    src = img_node.attrs.get("data-src") or img_node.attrs.get("src")
                    if src and not src.startswith("data:"):
                        thumbnail_url_raw = urljoin(source_url, src)

                position += 1
                seen_urls.add(detail_url)
                cards.append(
                    ListingCardRaw(
                        source=self.source_name,
                        listing_id=listing_id,
                        detail_url=detail_url,
                        title_raw=title_raw,
                        price_raw=price_raw,
                        area_raw=area_raw,
                        location_raw=location_raw,
                        posted_at_raw=posted_at_raw,
                        seller_name_raw=seller_name_raw,
                        thumbnail_url_raw=thumbnail_url_raw,
                        card_position=position,
                        page_number=page_number,
                    )
                )
        except Exception as exc:
            logger.warning("Lỗi parse listing HTML phongtro123: %s", exc)

        return cards
