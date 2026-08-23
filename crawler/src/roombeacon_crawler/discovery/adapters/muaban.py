import re
from urllib.parse import urlparse
from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter


class MuabanDiscoveryAdapter(SourceDiscoveryAdapter):
    """Discovery Adapter chuyên trách khám phá URL từ Sitemap cho Muaban (muaban.net)."""

    SOURCE_NAME = "muaban"
    supports_lastmod = True

    DEFAULT_ENTRYPOINTS = (
        "https://muaban.net/sitemap.xml",
        "https://muaban.net/sitemap-bat-dong-san.xml",
    )

    RENT_PATTERNS = (
        "/bat-dong-san/cho-thue-phong-tro-nha-tro",
        "/bat-dong-san/cho-thue-can-ho-chung-cu",
        "/bat-dong-san/cho-thue-nha-dat",
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
            if "muaban.net" not in netloc:
                return False

            path = parsed.path.lower()
            if any(path.startswith(p) for p in self.RENT_PATTERNS):
                return True
            if "-id" in path or re.search(r"/id\d+", path):
                return True
            return False
        except Exception:
            return False

    def classify_candidate_hint(self, url: str) -> str | None:
        if not url:
            return None
        path = urlparse(url).path.lower()
        if "-id" in path or re.search(r"/id\d+", path):
            return "DETAIL_PAGE"
        if any(path.startswith(p) for p in self.RENT_PATTERNS):
            return "LISTING_PAGE"
        return None
