from enum import Enum
import logging

from roombeacon_crawler.discovery.registry import DiscoveryRegistry, discovery_registry
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile

logger = logging.getLogger(__name__)


class DiscoveryStrategy(str, Enum):
    """Chiến lược khám phá URL cho nguồn."""

    STANDARD = "standard"
    ENHANCED_DISCOVERY = "enhanced_discovery"


class DiscoveryStrategyResolver:
    """Bộ phân giải chiến lược khám phá URL cho từng target / website nguồn.

    Quyết định dựa trên SourceCapabilities và DiscoveryRegistry. Tuyệt đối không chứa logic source-specific hardcoded.
    """

    def __init__(self, registry: DiscoveryRegistry | None = None) -> None:
        self.registry = registry or discovery_registry

    def resolve(self, source: str) -> DiscoveryStrategy:
        """Quyết định nguồn sử dụng chiến lược STANDARD (Pagination) hay ENHANCED_DISCOVERY (Sitemap)."""
        if not source:
            return DiscoveryStrategy.STANDARD

        from roombeacon_crawler.sources.registry import source_registry

        # 1. Kiểm tra năng lực qua Source Adapter Capabilities
        for adapter_cls in source_registry.get_registered_adapters():
            if getattr(adapter_cls, "SOURCE_NAME", None) == source:
                caps = getattr(adapter_cls, "CAPABILITIES", None)
                if caps:
                    if caps.access_profile in (
                        SourceAccessProfile.DISCOVERY_RESTRICTED,
                        SourceAccessProfile.ACCESS_CHALLENGED,
                    ) and self.registry.has(source):
                        return DiscoveryStrategy.ENHANCED_DISCOVERY
                    if caps.supports_sitemap_discovery and self.registry.has(source):
                        return DiscoveryStrategy.ENHANCED_DISCOVERY

        # 2. Kiểm tra trực tiếp qua Discovery Registry
        if self.registry.has(source):
            return DiscoveryStrategy.ENHANCED_DISCOVERY

        return DiscoveryStrategy.STANDARD
