"""Parse sitemap-index XML and return child sitemap locations."""

import logging
import xml.etree.ElementTree as ET

from roombeacon_crawler.discovery.sitemap.parser import (
    SitemapEntry,
    SitemapUrlsetParser,
)

logger = logging.getLogger(__name__)


class SitemapIndexParser:
    """Parser chuyên biệt phân tích tài liệu <sitemapindex> XML.

    Trách nhiệm duy nhất: Bóc tách danh sách URL sitemap con (<sitemap><loc>) và lastmod.
    Tuyệt đối không fetch hay lọc URL ứng viên nghiệp vụ tại đây.
    """

    @classmethod
    def parse_index(cls, content: str | bytes) -> list[SitemapEntry]:
        """Trích xuất danh sách sitemap con từ nội dung XML <sitemapindex>."""
        if not content:
            return []

        try:
            content_bytes = content.strip().encode("utf-8") if isinstance(content, str) else content.strip()
            root = ET.fromstring(content_bytes)

            root_tag = SitemapUrlsetParser._strip_tag(root.tag)
            if root_tag != "sitemapindex":
                logger.debug("Tài liệu không phải sitemapindex (thẻ gốc: %s)", root.tag)
                return []

            entries: list[SitemapEntry] = []
            for child in root:
                if SitemapUrlsetParser._strip_tag(child.tag) == "sitemap":
                    loc_val: str | None = None
                    lastmod_val: str | None = None
                    for elem in child:
                        elem_tag = SitemapUrlsetParser._strip_tag(elem.tag)
                        if elem_tag == "loc" and elem.text:
                            loc_val = elem.text.strip()
                        elif elem_tag == "lastmod" and elem.text:
                            lastmod_val = elem.text.strip()
                    if loc_val:
                        entries.append(SitemapEntry(loc=loc_val, lastmod=lastmod_val))

            return entries

        except ET.ParseError:
            logger.warning("Sitemap index XML is malformed (error_class=ParseError)")
            return []
        except Exception as exc:
            logger.error("Sitemap index parse failed (error_class=%s)", type(exc).__name__)
            return []

    @classmethod
    def extract_child_sitemaps(cls, content: str | bytes) -> list[SitemapEntry]:
        """Hàm trợ giúp tương thích trích xuất child sitemaps."""
        return cls.parse_index(content)
