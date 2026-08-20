import re
from urllib.parse import urlparse
from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter


class NhaTotDiscoveryAdapter(SourceDiscoveryAdapter):
    """Discovery Adapter chuyên trách khám phá URL từ Sitemap cho website Nhà Tốt (nhatot.com).

    Chỉ đảm nhiệm khám phá danh sách URL ứng viên cho thuê phòng trọ / căn hộ / nhà ở.
    Tuyệt đối không bóc tách dữ liệu bài đăng hay thay thế NhatotSourceAdapter.
    """

    SOURCE_NAME = "nhatot"
    supports_lastmod = True

    DEFAULT_ENTRYPOINTS = (
        "https://www.nhatot.com/sitemaps.xml",
        "https://www.nhatot.com/sitemap_rent.xml",
    )

    RENT_PATTERNS = (
        "/thue-phong-tro",
        "/thue-nha-o",
        "/thue-can-ho",
        "/thue-mat-bang",
        "/thue-",
        "/phong-tro",
        "/nha-tro",
    )

    NON_RENT_EXCLUDES = (
        "/mua-ban-",
        "/viec-lam",
        "/xe-",
        "/do-dien-tu",
        "/dich-vu",
        "/thu-cung",
        "/me-va-be",
        "/thoi-trang",
    )

    def discover_entrypoints(self) -> list[str]:
        return list(self.DEFAULT_ENTRYPOINTS)

    def filter_candidate_url(self, url: str) -> bool:
        if not url:
            return False
        try:
            parsed = urlparse(url.strip())
            netloc = parsed.netloc.lower()
            if "nhatot.com" not in netloc and "chotot.com" not in netloc:
                return False

            path = parsed.path.lower()

            # 1. Loại bỏ các danh mục không liên quan
            if any(path.startswith(exc) or exc in path for exc in self.NON_RENT_EXCLUDES):
                return False

            # 2. Khớp các URL danh mục / listing cho thuê
            if any(path.startswith(p) or p in path for p in self.RENT_PATTERNS):
                return True

            # 3. Khớp các URL chi tiết tin đăng cho thuê
            if ("-pr" in path or re.search(r"/\d+\.htm", path)) and not any(exc in path for exc in self.NON_RENT_EXCLUDES):
                # Nếu có từ khóa thuê hoặc nằm trong domain nhatot chuyên biệt
                if "nhatot.com" in netloc or any(p in path for p in self.RENT_PATTERNS):
                    return True

            return False
        except Exception:
            return False

    def classify_candidate_hint(self, url: str) -> str | None:
        if not url:
            return None
        path = urlparse(url).path.lower()
        if "-pr" in path or re.search(r"/\d+\.htm", path):
            return "DETAIL_PAGE"
        if any(p in path for p in self.RENT_PATTERNS):
            return "LISTING_PAGE"
        return None
