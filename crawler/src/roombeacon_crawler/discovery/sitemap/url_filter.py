import logging
from urllib.parse import urlparse, urlunparse

from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter
from roombeacon_crawler.discovery.models import DiscoveredUrl, DiscoveryType

logger = logging.getLogger(__name__)


class DiscoveryUrlFilter:
    """Bộ trợ giúp chuẩn hóa URL và lọc trùng lặp chung cho Sitemap Discovery.

    Cung cấp các hàm tiện ích kỹ thuật:
    - Chuẩn hóa URL (loại bỏ fragment, khoảng trắng thừa, chuẩn hóa scheme/netloc).
    - Khử trùng lặp trên tập URL ứng viên trong phiên chạy.
    - Áp dụng bộ lọc ngữ nghĩa do DiscoveryAdapter sở hữu (`adapter.filter_candidate_url`).
    """

    @staticmethod
    def normalize_url(raw_url: str) -> str:
        """Chuẩn hóa URL: chuẩn hóa scheme, netloc và loại bỏ fragment (#...)."""
        if not raw_url:
            return ""
        try:
            parsed = urlparse(raw_url.strip())
            return urlunparse((
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                parsed.params,
                parsed.query,
                "",  # Strip fragment
            ))
        except Exception:
            return raw_url.strip()

    @classmethod
    def filter_and_deduplicate(
        cls,
        entries: list[tuple[str, str | None]],
        adapter: SourceDiscoveryAdapter,
        discovered_from: str,
        discovery_type: DiscoveryType = DiscoveryType.SITEMAP_URLSET,
        seen_urls: set[str] | None = None,
    ) -> list[DiscoveredUrl]:
        """Chuẩn hóa, khử trùng lặp và ủy quyền lọc URL nghiệp vụ cho DiscoveryAdapter."""
        if seen_urls is None:
            seen_urls = set()

        results: list[DiscoveredUrl] = []

        for raw_url, lastmod in entries:
            url = cls.normalize_url(raw_url)
            if not url or url in seen_urls:
                continue

            # Ủy quyền kiểm tra phạm vi nội dung cho DiscoveryAdapter cụ thể
            if not adapter.filter_candidate_url(url):
                continue

            seen_urls.add(url)
            hint = adapter.classify_candidate_hint(url)

            results.append(
                DiscoveredUrl(
                    source=adapter.SOURCE_NAME,
                    url=url,
                    discovered_from=discovered_from,
                    discovery_type=discovery_type,
                    lastmod=lastmod,
                    target_hint=hint,
                )
            )

        return results
