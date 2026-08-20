import unittest

from roombeacon_crawler.discovery.adapters.batdongsan import BatDongSanDiscoveryAdapter
from roombeacon_crawler.discovery.adapters.muaban import MuabanDiscoveryAdapter
from roombeacon_crawler.discovery.adapters.nhatot import NhaTotDiscoveryAdapter
from roombeacon_crawler.discovery.registry import (
    DiscoveryRegistry,
    discovery_registry,
)


class TestDiscoveryRegistry(unittest.TestCase):
    """Kiểm thử DiscoveryRegistry và khả năng tự động khám phá DiscoveryAdapters."""

    def test_auto_discovery_registers_large_sources(self) -> None:
        reg = DiscoveryRegistry(auto_discover=True)
        # Nguồn lớn có Discovery Adapter
        self.assertTrue(reg.has("nhatot"))
        self.assertTrue(reg.has("batdongsan"))
        self.assertTrue(reg.has("muaban"))

        self.assertIsInstance(reg.get("nhatot"), NhaTotDiscoveryAdapter)
        self.assertIsInstance(reg.get("batdongsan"), BatDongSanDiscoveryAdapter)
        self.assertIsInstance(reg.get("muaban"), MuabanDiscoveryAdapter)

    def test_standard_sources_have_no_discovery_adapter(self) -> None:
        reg = DiscoveryRegistry(auto_discover=True)
        # Nguồn chuẩn (Standard) không dùng Sitemap Discovery
        self.assertFalse(reg.has("nhatrovn"))
        self.assertFalse(reg.has("phongtro123"))
        self.assertIsNone(reg.get("nhatrovn"))
        self.assertIsNone(reg.get("phongtro123"))

    def test_list_sources_returns_sorted_names(self) -> None:
        sources = discovery_registry.list_sources()
        self.assertIn("batdongsan", sources)
        self.assertIn("muaban", sources)
        self.assertIn("nhatot", sources)
        self.assertNotIn("nhatrovn", sources)


if __name__ == "__main__":
    unittest.main()
