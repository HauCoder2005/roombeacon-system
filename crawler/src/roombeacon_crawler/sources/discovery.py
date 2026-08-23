import importlib
import inspect
import logging
import pkgutil
from typing import Type

from roombeacon_crawler.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class DuplicateDomainError(ValueError):
    """Ngoại lệ xảy ra khi hai Source Adapter khác nhau cùng đăng ký trùng một domain."""

    pass


class InvalidAdapterError(TypeError):
    """Ngoại lệ xảy ra khi một Source Adapter không đáp ứng đầy đủ contract nghiệp vụ tối thiểu."""

    pass


class SourceDiscovery:
    """Cơ chế tự động phát hiện và thu thập các Source Adapter (Plugin Discovery) trong hệ thống."""

    @staticmethod
    def validate_adapter_contract(adapter_cls: Type[BaseSourceAdapter]) -> None:
        """Xác thực tính hợp lệ của lớp Source Adapter theo contract BaseSourceAdapter."""
        if not inspect.isclass(adapter_cls) or not issubclass(adapter_cls, BaseSourceAdapter):
            raise InvalidAdapterError(
                f"Lớp {adapter_cls} phải kế thừa từ BaseSourceAdapter."
            )

        source_name = getattr(adapter_cls, "SOURCE_NAME", None)
        if not source_name or not isinstance(source_name, str) or not source_name.strip():
            raise InvalidAdapterError(
                f"Adapter '{adapter_cls.__name__}' trong module '{adapter_cls.__module__}' "
                f"phải định nghĩa thuộc tính SOURCE_NAME là chuỗi phi rỗng."
            )

        domains = getattr(adapter_cls, "DOMAINS", None)
        if not domains or not isinstance(domains, (tuple, list, set)) or len(domains) == 0:
            raise InvalidAdapterError(
                f"Adapter '{adapter_cls.__name__}' ({source_name}) "
                f"phải định nghĩa thuộc tính DOMAINS chứa ít nhất một tên miền hợp lệ."
            )

    @classmethod
    def discover_adapters(
        cls, package_name: str = "roombeacon_crawler.sources"
    ) -> list[Type[BaseSourceAdapter]]:
        """Quét và tự động nạp tất cả các lớp kế thừa từ BaseSourceAdapter trong package được chỉ định.

        Quy trình:
        1. Tìm các package con dưới `package_name`.
        2. Tải các module (đặc biệt là adapter.py hoặc module chứa BaseSourceAdapter).
        3. Thu thập các lớp concrete subclass của BaseSourceAdapter.
        4. Kiểm tra hợp đồng metadata.
        """
        try:
            package = importlib.import_module(package_name)
        except ImportError as exc:
            logger.error("Không thể import package nguồn '%s': %s", package_name, exc)
            raise ImportError(f"Không tìm thấy package nguồn: {package_name}") from exc

        package_path = getattr(package, "__path__", None)
        if not package_path:
            return []

        discovered: list[Type[BaseSourceAdapter]] = []
        seen_classes: set[Type[BaseSourceAdapter]] = set()

        for module_info in pkgutil.iter_modules(package_path):
            if module_info.ispkg:
                subpkg_name = f"{package_name}.{module_info.name}"
                try:
                    subpkg = importlib.import_module(subpkg_name)
                except Exception as exc:
                    logger.error("Lỗi khi tải subpackage nguồn '%s': %s", subpkg_name, exc)
                    raise ImportError(f"Lỗi tải subpackage '{subpkg_name}': {exc}") from exc

                # Thử tìm module adapter.py cụ thể trước, hoặc duyệt tất cả module trong subpackage
                modules_to_inspect = []
                try:
                    adapter_module = importlib.import_module(f"{subpkg_name}.adapter")
                    modules_to_inspect.append(adapter_module)
                except ImportError:
                    # Nếu không có module adapter.py riêng, quét toàn bộ module trong subpkg
                    subpkg_path = getattr(subpkg, "__path__", None)
                    if subpkg_path:
                        for sub_mod_info in pkgutil.iter_modules(subpkg_path):
                            try:
                                mod = importlib.import_module(f"{subpkg_name}.{sub_mod_info.name}")
                                modules_to_inspect.append(mod)
                            except Exception as sub_exc:
                                logger.error(
                                    "Lỗi khi tải module '%s.%s': %s",
                                    subpkg_name,
                                    sub_mod_info.name,
                                    sub_exc,
                                )
                                raise ImportError(
                                    f"Lỗi tải module '{subpkg_name}.{sub_mod_info.name}': {sub_exc}"
                                ) from sub_exc

                for mod in modules_to_inspect:
                    for _, obj in inspect.getmembers(mod, inspect.isclass):
                        if (
                            issubclass(obj, BaseSourceAdapter)
                            and obj is not BaseSourceAdapter
                            and not inspect.isabstract(obj)
                            and obj.__module__.startswith(package_name)
                        ):
                            if obj not in seen_classes:
                                cls.validate_adapter_contract(obj)
                                seen_classes.add(obj)
                                discovered.append(obj)
                                logger.debug(
                                    "Đã phát hiện Source Adapter: %s (%s)",
                                    obj.__name__,
                                    getattr(obj, "SOURCE_NAME", "N/A"),
                                )

        return discovered
