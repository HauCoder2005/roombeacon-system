import importlib
import inspect
import logging
import pkgutil
from typing import ClassVar

from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter

logger = logging.getLogger(__name__)


class DiscoveryRegistry:
    """Danh bạ đăng ký và tự động khám phá các DiscoveryAdapter cho nguồn lớn.

    Hoạt động hoàn toàn độc lập với SourceRegistry (HTML Source Adapters).
    """

    ADAPTERS_PACKAGE: ClassVar[str] = "roombeacon_crawler.discovery.adapters"

    def __init__(self, auto_discover: bool = True) -> None:
        self._adapters: dict[str, SourceDiscoveryAdapter] = {}
        if auto_discover:
            self.discover()

    def register(self, adapter: SourceDiscoveryAdapter) -> None:
        """Đăng ký một DiscoveryAdapter vào registry."""
        if not isinstance(adapter, SourceDiscoveryAdapter):
            raise TypeError(f"Adapter phải kế thừa từ SourceDiscoveryAdapter, nhận được: {type(adapter)}")

        name = adapter.SOURCE_NAME.lower().strip()
        if not name:
            raise ValueError(f"SOURCE_NAME của DiscoveryAdapter không được rỗng ({type(adapter).__name__})")

        self._adapters[name] = adapter
        logger.debug("Đã đăng ký DiscoveryAdapter: %s (%s)", name, type(adapter).__name__)

    def get(self, source_name: str) -> SourceDiscoveryAdapter | None:
        """Lấy DiscoveryAdapter tương ứng cho nguồn (trả về None nếu là Standard-only source)."""
        if not source_name:
            return None
        return self._adapters.get(source_name.lower().strip())

    def has(self, source_name: str) -> bool:
        """Kiểm tra nguồn có hỗ trợ DiscoveryAdapter nâng cao hay không."""
        if not source_name:
            return False
        return source_name.lower().strip() in self._adapters

    def list_sources(self) -> list[str]:
        """Danh sách tên các nguồn có DiscoveryAdapter."""
        return sorted(self._adapters.keys())

    def discover(self) -> None:
        """Tự động quét và nạp toàn bộ DiscoveryAdapter trong package roombeacon_crawler.discovery.adapters."""
        try:
            package = importlib.import_module(self.ADAPTERS_PACKAGE)
        except ImportError as exc:
            logger.warning("Không thể import package discovery adapters '%s': %s", self.ADAPTERS_PACKAGE, exc)
            return

        if not hasattr(package, "__path__"):
            return

        discovered_count = 0
        for _, module_name, _ in pkgutil.iter_modules(package.__path__):
            full_module_name = f"{self.ADAPTERS_PACKAGE}.{module_name}"
            try:
                mod = importlib.import_module(full_module_name)
                for attr_name in dir(mod):
                    obj = getattr(mod, attr_name)
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, SourceDiscoveryAdapter)
                        and obj is not SourceDiscoveryAdapter
                        and not inspect.isabstract(obj)
                        and getattr(obj, "SOURCE_NAME", "")
                    ):
                        adapter_inst = obj()
                        self.register(adapter_inst)
                        discovered_count += 1
            except Exception as exc:
                logger.warning("Lỗi khi load discovery adapter module '%s': %s", full_module_name, exc)

        logger.info("DiscoveryRegistry: Đã tự động khám phá %d discovery adapters: %s", discovered_count, self.list_sources())


# Singleton instance toàn cục
discovery_registry = DiscoveryRegistry(auto_discover=True)
