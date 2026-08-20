from dataclasses import dataclass
from enum import Enum
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class SitemapDocumentType(str, Enum):
    INDEX = "sitemapindex"
    URLSET = "urlset"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    """Mục sitemap chuẩn hóa chứa URL và mốc thời gian cập nhật tùy chọn."""

    loc: str
    lastmod: str | None = None


class SitemapUrlsetParser:
    """Parser chuyên biệt phân tích tài liệu Sitemap <urlset> XML chuẩn.

    Trách nhiệm duy nhất: Bóc tách danh sách <url><loc> và <lastmod> từ XML urlset.
    Không chứa logic lọc nghiệp vụ nguồn hay định danh website cụ thể.
    """

    @staticmethod
    def _strip_tag(tag: str) -> str:
        """Loại bỏ XML namespace: '{http://...}loc' -> 'loc'."""
        if "}" in tag:
            return tag.split("}", 1)[1].lower()
        return tag.lower()

    @classmethod
    def detect_type(cls, root_tag: str) -> SitemapDocumentType:
        """Nhận diện loại tài liệu sitemap từ thẻ gốc XML."""
        tag = cls._strip_tag(root_tag)
        if tag == "sitemapindex":
            return SitemapDocumentType.INDEX
        elif tag == "urlset":
            return SitemapDocumentType.URLSET
        return SitemapDocumentType.UNKNOWN

    @classmethod
    def parse_urlset(cls, content: str | bytes) -> list[SitemapEntry]:
        """Bóc tách các mục URL từ nội dung XML <urlset>."""
        if not content:
            return []

        try:
            content_bytes = content.strip().encode("utf-8") if isinstance(content, str) else content.strip()
            root = ET.fromstring(content_bytes)

            root_tag = cls._strip_tag(root.tag)
            if root_tag != "urlset":
                logger.debug("Tài liệu không phải urlset (thẻ gốc: %s)", root.tag)
                return []

            entries: list[SitemapEntry] = []
            for child in root:
                if cls._strip_tag(child.tag) == "url":
                    loc_val: str | None = None
                    lastmod_val: str | None = None
                    for elem in child:
                        elem_tag = cls._strip_tag(elem.tag)
                        if elem_tag == "loc" and elem.text:
                            loc_val = elem.text.strip()
                        elif elem_tag == "lastmod" and elem.text:
                            lastmod_val = elem.text.strip()
                    if loc_val:
                        entries.append(SitemapEntry(loc=loc_val, lastmod=lastmod_val))

            return entries

        except ET.ParseError as err:
            logger.warning("Lỗi cú pháp XML khi parse urlset: %s", err)
            return []
        except Exception as exc:
            logger.exception("Ngoại lệ khi parse urlset: %s", exc)
            return []


# Alias tương thích
SitemapParser = SitemapUrlsetParser
