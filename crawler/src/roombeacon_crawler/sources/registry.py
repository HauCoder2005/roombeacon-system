import logging
from typing import Type
from urllib.parse import urlparse

from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.discovery import (
    DuplicateDomainError,
    InvalidAdapterError,
    SourceDiscovery,
)

logger = logging.getLogger(__name__)


class UnsupportedSourceError(ValueError):
    """Ngoại lệ xảy ra khi URL an toàn nhưng chưa có Source Adapter nào trong hệ thống hỗ trợ."""

    pass


class SourceRegistry:
    """Central Registry quản lý đăng ký và phân giải Source Adapters thông qua cơ chế Auto-Discovery."""

    def __init__(self, auto_discover: bool = True, package_name: str = "roombeacon_crawler.sources") -> None:
        self._adapters: list[Type[BaseSourceAdapter]] = []
        self._domain_index: dict[str, Type[BaseSourceAdapter]] = {}

        if auto_discover:
            self.discover(package_name=package_name)

    def discover(self, package_name: str = "roombeacon_crawler.sources") -> int:
        """Quét và tự động đăng ký tất cả các Source Adapters tìm thấy trong package."""
        discovered = SourceDiscovery.discover_adapters(package_name=package_name)
        count = 0
        for adapter_cls in discovered:
            self.register(adapter_cls)
            count += 1
        return count

    def register(self, adapter_cls: Type[BaseSourceAdapter]) -> None:
        """Đăng ký một Source Adapter mới vào Registry và cập nhật Domain Index."""
        SourceDiscovery.validate_adapter_contract(adapter_cls)

        # Kiểm tra trùng lặp domain với các adapter đã đăng ký trước đó
        for domain in adapter_cls.DOMAINS:
            norm_domain = domain.strip().lower()
            if norm_domain in self._domain_index and self._domain_index[norm_domain] is not adapter_cls:
                existing_cls = self._domain_index[norm_domain]
                raise DuplicateDomainError(
                    f"Trùng lặp cấu hình domain '{norm_domain}'. "
                    f"Domain này đã được đăng ký bởi '{existing_cls.__name__}' và xung đột với '{adapter_cls.__name__}'."
                )

        # Cập nhật Domain Index
        for domain in adapter_cls.DOMAINS:
            norm_domain = domain.strip().lower()
            self._domain_index[norm_domain] = adapter_cls

        if adapter_cls not in self._adapters:
            self._adapters.append(adapter_cls)

    def unregister(self, adapter_or_name: str | Type[BaseSourceAdapter]) -> None:
        """Hủy đăng ký một Source Adapter khỏi Registry (phục vụ testing hoặc dynamic unload)."""
        if isinstance(adapter_or_name, str):
            target_classes = [
                cls for cls in self._adapters if getattr(cls, "SOURCE_NAME", None) == adapter_or_name
            ]
        else:
            target_classes = [cls for cls in self._adapters if cls == adapter_or_name]

        for cls in target_classes:
            if cls in self._adapters:
                self._adapters.remove(cls)
            # Xóa các domain trỏ tới class này
            domains_to_remove = [
                dom for dom, registered_cls in self._domain_index.items() if registered_cls == cls
            ]
            for dom in domains_to_remove:
                self._domain_index.pop(dom, None)

    def get_registered_adapters(self) -> list[Type[BaseSourceAdapter]]:
        """Trả về danh sách các lớp Adapter đã đăng ký."""
        return list(self._adapters)

    def list_sources(self) -> list[str]:
        """Trả về danh sách tên định danh đã sắp xếp của tất cả các nguồn đang hỗ trợ."""
        sources = [
            cls.SOURCE_NAME
            for cls in self._adapters
            if getattr(cls, "SOURCE_NAME", None)
        ]
        return sorted(list(set(sources)))

    def get_supported_sources(self) -> list[str]:
        """Trả về danh sách tên định danh của các nguồn đã đăng ký."""
        return self.list_sources()

    def get(self, source_name: str) -> Type[BaseSourceAdapter] | None:
        """Lấy lớp Adapter theo tên định danh source_name."""
        if not source_name:
            return None
        norm_name = source_name.strip().lower()
        for cls in self._adapters:
            if getattr(cls, "SOURCE_NAME", "").lower() == norm_name:
                return cls
        return None

    def get_adapter_by_name(self, source_name: str) -> Type[BaseSourceAdapter] | None:
        """Alias tương thích cho get()."""
        return self.get(source_name)

    def resolve_adapter_class_for_url(self, url: str) -> Type[BaseSourceAdapter] | None:
        """Phân giải lớp Adapter tương ứng cho URL dựa trên Domain Index và supports method."""
        if not url:
            return None

        try:
            parsed = urlparse(url.strip())
            hostname = (parsed.hostname or "").lower()
            if hostname in self._domain_index:
                return self._domain_index[hostname]

            # Kiểm tra fallback qua supports method của từng adapter
            for adapter_cls in self._adapters:
                if adapter_cls.supports(url):
                    return adapter_cls
        except Exception:
            return None

        return None

    def is_supported(self, url: str) -> bool:
        """Kiểm tra xem URL đầu vào có khớp với bất kỳ Source Adapter nào đã đăng ký không."""
        return self.resolve_adapter_class_for_url(url) is not None

    def resolve_source_name(self, url: str) -> str | None:
        """Phân giải tên định danh nguồn (source_name) từ URL."""
        adapter_cls = self.resolve_adapter_class_for_url(url)
        return adapter_cls.SOURCE_NAME if adapter_cls else None

    def resolve(
        self,
        url: str,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> BaseSourceAdapter:
        """Phân giải và khởi tạo đối tượng Source Adapter cho URL đầu vào.

        Raises:
            UnsupportedSourceError: Nếu không có Adapter nào hỗ trợ URL này.
        """
        adapter_cls = self.resolve_adapter_class_for_url(url)
        if adapter_cls:
            return adapter_cls(
                base_url=url,
                request_delay_seconds=request_delay_seconds,
                max_concurrency=max_concurrency,
            )

        parsed = urlparse(url)
        hostname = (parsed.hostname or url).lower()
        supported = ", ".join(self.list_sources())
        raise UnsupportedSourceError(
            f"Domain '{hostname}' hiện chưa được hỗ trợ bởi bất kỳ Source Adapter nào. Đang hỗ trợ: {supported}"
        )


# Khởi tạo singleton Source Registry với cơ chế Auto-Discovery hoàn toàn động
source_registry = SourceRegistry(auto_discover=True)
