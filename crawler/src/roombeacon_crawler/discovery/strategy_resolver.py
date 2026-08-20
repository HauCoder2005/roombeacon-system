from enum import Enum
import logging

from roombeacon_crawler.discovery.registry import DiscoveryRegistry, discovery_registry

logger = logging.getLogger(__name__)


class DiscoveryStrategy(str, Enum):
    """Chiến lược khám phá URL cho nguồn."""

    STANDARD = "standard"
    ENHANCED_DISCOVERY = "enhanced_discovery"


class DiscoveryStrategyResolver:
    """Bộ phân giải chiến lược khám phá URL cho từng target / website nguồn.

    Chỉ kiểm tra khả năng hỗ trợ từ DiscoveryRegistry. Tuyệt đối không chứa logic source-specific hardcoded.
    """

    def __init__(self, registry: DiscoveryRegistry | None = None) -> None:
        self.registry = registry or discovery_registry

    def resolve(self, source: str) -> DiscoveryStrategy:
        """Quyết định nguồn sử dụng chiến lược STANDARD (Pagination) hay ENHANCED_DISCOVERY (Sitemap)."""
        if not source:
            return DiscoveryStrategy.STANDARD

        if self.registry.has(source):
            return DiscoveryStrategy.ENHANCED_DISCOVERY

        return DiscoveryStrategy.STANDARD
