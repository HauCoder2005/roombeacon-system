from abc import ABC, abstractmethod
import logging
from urllib.parse import urlparse, urlunparse

from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.sources.registry import SourceRegistry, source_registry

logger = logging.getLogger(__name__)


def normalize_target_url(url: str) -> str:
    """Chuẩn hóa canonical URL phục vụ deduplication an toàn trước khi crawl."""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    path = parsed.path.rstrip("/")
    if not path:
        path = "/"
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


class ScheduledTargetProvider(ABC):
    """Interface trừu tượng cung cấp danh sách target định kỳ cho scheduled orchestration."""

    @abstractmethod
    def get_scheduled_targets(self) -> list[CrawlSeed]:
        """Thu thập danh sách các điểm vào (CrawlSeed) định kỳ."""
        ...


class AdapterScheduledTargetProvider(ScheduledTargetProvider):
    """Provider thu thập targets từ metadata `scheduled_targets()` của các Source Adapter đã auto-discovered."""

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self.registry = registry or source_registry

    def get_scheduled_targets(self) -> list[CrawlSeed]:
        """Duyệt qua tất cả các adapter đã được phát hiện, trích xuất và deduplicate các targets hợp lệ."""
        adapters = self.registry.get_registered_adapters()
        collected: list[CrawlSeed] = []
        seen_canonical_urls: set[str] = set()

        for adapter_cls in adapters:
            try:
                instance = adapter_cls()
                seeds = instance.scheduled_targets()
                for seed in seeds:
                    if not seed.enabled or not seed.url:
                        continue
                    canonical_url = normalize_target_url(seed.url)
                    if canonical_url in seen_canonical_urls:
                        logger.warning(
                            "Phát hiện URL định kỳ trùng lặp, bỏ qua duplicate: %s (Source: %s)",
                            seed.url,
                            seed.source,
                        )
                        continue
                    seen_canonical_urls.add(canonical_url)
                    collected.append(seed)
            except Exception as exc:
                logger.error(
                    "Lỗi khi đọc scheduled_targets từ adapter %s: %s",
                    adapter_cls.__name__,
                    exc,
                )

        logger.info(
            "DISCOVERED SCHEDULED TARGETS: %d targets từ %d adapters",
            len(collected),
            len(adapters),
        )
        return collected
