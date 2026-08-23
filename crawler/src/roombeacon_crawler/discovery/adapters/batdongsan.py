import re
from urllib.parse import urlparse
from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter


class BatDongSanDiscoveryAdapter(SourceDiscoveryAdapter):
    """Discovery Adapter chuyên trách khám phá URL từ Sitemap cho BatDongSan (batdongsan.com.vn)."""

    SOURCE_NAME = "batdongsan"
    supports_lastmod = True

    DEFAULT_ENTRYPOINTS = (
        "https://batdongsan.com.vn/sitemap.xml",
        "https://batdongsan.com.vn/sitemaps/cho-thue-nha-tro-phong-tro.xml",
    )

    RENT_PATTERNS = (
        "/cho-thue-nha-tro-phong-tro",
        "/cho-thue-can-ho-chung-cu",
        "/cho-thue-nha-rieng",
        "/cho-thue-",
    )

    def discover_entrypoints(self) -> list[str]:
        return list(self.DEFAULT_ENTRYPOINTS)

    def filter_candidate_url(self, url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url.strip())
            netloc = parsed.netloc.lower()
            if "batdongsan.com.vn" not in netloc:
                return False

            path = parsed.path.lower()
            if any(path.startswith(p) for p in self.RENT_PATTERNS):
                return True
            if "-pr" in path or re.search(r"/pr\d+", path):
                return True
            return False
        except Exception:
            return False

    def classify_candidate_hint(self, url: str) -> str | None:
        if not url:
            return None
        path = urlparse(url).path.lower()
        if "-pr" in path or re.search(r"/pr\d+", path):
            return "DETAIL_PAGE"
        if any(path.startswith(p) for p in self.RENT_PATTERNS):
            return "LISTING_PAGE"
        return None
