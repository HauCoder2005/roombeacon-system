import unittest

from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.discovery import (
    DuplicateDomainError,
    InvalidAdapterError,
    SourceDiscovery,
)
from roombeacon_crawler.sources.registry import (
    SourceRegistry,
    UnsupportedSourceError,
    source_registry,
)
from roombeacon_crawler.sources.resolver import SourceResolver


class FakeTestAdapter(BaseSourceAdapter):
    """Test-only adapter để chứng minh cơ chế mở rộng nguồn mới mà không cần sửa core code."""

    SOURCE_NAME = "faketest"
    DOMAINS = ("faketest.vn", "www.faketest.vn")
    DEFAULT_BASE_URL = "https://faketest.vn/phong-tro"


class TestSourceRegistryAndAutoDiscovery(unittest.TestCase):
    def test_global_registry_auto_discovers_all_five_default_sources(self) -> None:
        """Kiểm tra SourceRegistry tự động phát hiện đầy đủ 5 nguồn thông qua auto-discovery."""
        supported = source_registry.get_supported_sources()
        self.assertEqual(
            supported,
            ["batdongsan", "muaban", "nhatot", "nhatrovn", "phongtro123"],
        )
        self.assertEqual(
            source_registry.list_sources(),
            ["batdongsan", "muaban", "nhatot", "nhatrovn", "phongtro123"],
        )

    def test_source_discovery_utility(self) -> None:
        """Kiểm tra SourceDiscovery.discover_adapters phát hiện đúng các lớp adapter."""
        adapters = SourceDiscovery.discover_adapters("roombeacon_crawler.sources")
        discovered_names = sorted([cls.SOURCE_NAME for cls in adapters])
        self.assertEqual(
            discovered_names,
            ["batdongsan", "muaban", "nhatot", "nhatrovn", "phongtro123"],
        )

    def test_resolve_batdongsan(self) -> None:
        url = "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm"
        source_name = source_registry.resolve_source_name(url)
        self.assertEqual(source_name, "batdongsan")

        adapter = source_registry.resolve(url)
        self.assertEqual(adapter.SOURCE_NAME, "batdongsan")
        self.assertEqual(adapter.base_url, url)

    def test_resolve_muaban(self) -> None:
        url = "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm"
        source_name = source_registry.resolve_source_name(url)
        self.assertEqual(source_name, "muaban")

        adapter = source_registry.resolve(url)
        self.assertEqual(adapter.SOURCE_NAME, "muaban")
        self.assertEqual(adapter.base_url, url)

    def test_resolve_nhatot(self) -> None:
        url = "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"
        source_name = source_registry.resolve_source_name(url)
        self.assertEqual(source_name, "nhatot")

        adapter = source_registry.resolve(url)
        self.assertEqual(adapter.SOURCE_NAME, "nhatot")
        self.assertEqual(adapter.base_url, url)

    def test_resolve_nhatrovn(self) -> None:
        url = "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/"
        source_name = source_registry.resolve_source_name(url)
        self.assertEqual(source_name, "nhatrovn")

        adapter = source_registry.resolve(url)
        self.assertEqual(adapter.SOURCE_NAME, "nhatrovn")
        self.assertEqual(adapter.base_url, url)

    def test_resolve_phongtro123(self) -> None:
        url = "https://phongtro123.com/tinh-thanh/ho-chi-minh"
        source_name = source_registry.resolve_source_name(url)
        self.assertEqual(source_name, "phongtro123")

        adapter = source_registry.resolve(url)
        self.assertEqual(adapter.SOURCE_NAME, "phongtro123")
        self.assertEqual(adapter.base_url, url)

    def test_unsupported_domain_raises_unsupported_source_error(self) -> None:
        url = "https://arbitrary-safe-domain.com/rentals"
        self.assertFalse(source_registry.is_supported(url))
        self.assertIsNone(source_registry.resolve_source_name(url))

        with self.assertRaises(UnsupportedSourceError) as ctx:
            source_registry.resolve(url)

        self.assertIn("arbitrary-safe-domain.com", str(ctx.exception))
        self.assertIn("batdongsan, muaban, nhatot, nhatrovn, phongtro123", str(ctx.exception))

    def test_duplicate_domain_detection_raises_error(self) -> None:
        """Kiểm tra phát hiện và ngăn chặn trùng lặp domain giữa các adapter."""
        local_registry = SourceRegistry(auto_discover=False)
        local_registry.register(FakeTestAdapter)

        class ConflictingAdapter(BaseSourceAdapter):
            SOURCE_NAME = "conflicting"
            DOMAINS = ("faketest.vn",)

        with self.assertRaises(DuplicateDomainError) as ctx:
            local_registry.register(ConflictingAdapter)

        self.assertIn("faketest.vn", str(ctx.exception))
        self.assertIn("FakeTestAdapter", str(ctx.exception))
        self.assertIn("ConflictingAdapter", str(ctx.exception))

    def test_invalid_adapter_validation(self) -> None:
        """Kiểm tra xác thực adapter không hợp lệ (thiếu SOURCE_NAME hoặc DOMAINS)."""
        local_registry = SourceRegistry(auto_discover=False)

        class MissingNameAdapter(BaseSourceAdapter):
            SOURCE_NAME = ""
            DOMAINS = ("valid.com",)

        with self.assertRaises(InvalidAdapterError):
            local_registry.register(MissingNameAdapter)

        class EmptyDomainsAdapter(BaseSourceAdapter):
            SOURCE_NAME = "valid_name"
            DOMAINS = ()

        with self.assertRaises(InvalidAdapterError):
            local_registry.register(EmptyDomainsAdapter)

    def test_extensibility_with_custom_test_adapter(self) -> None:
        """Regression test: Thêm nguồn mới hoạt động ngay mà không cần sửa code registry.py hay resolver.py."""
        local_registry = SourceRegistry(auto_discover=False)
        self.assertEqual(len(local_registry.list_sources()), 0)

        local_registry.register(FakeTestAdapter)

        test_url = "https://faketest.vn/phong-tro?district=1"
        self.assertTrue(local_registry.is_supported(test_url))
        self.assertEqual(local_registry.resolve_source_name(test_url), "faketest")

        adapter = local_registry.resolve(test_url)
        self.assertIsInstance(adapter, FakeTestAdapter)
        self.assertEqual(adapter.base_url, test_url)

    def test_source_resolver_facade(self) -> None:
        self.assertTrue(SourceResolver.is_supported("https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro"))
        self.assertTrue(SourceResolver.is_supported("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro"))
        self.assertTrue(SourceResolver.is_supported("https://www.nhatot.com/thue-phong-tro"))
        self.assertTrue(SourceResolver.is_supported("https://nhatrovn.vn/cho-thue-phong-tro/"))
        self.assertEqual(
            SourceResolver.resolve_source_name("https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm"),
            "batdongsan",
        )
        self.assertEqual(
            SourceResolver.resolve_source_name("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro"),
            "muaban",
        )
        self.assertEqual(
            SourceResolver.get_supported_sources(),
            ["batdongsan", "muaban", "nhatot", "nhatrovn", "phongtro123"],
        )


if __name__ == "__main__":
    unittest.main()
