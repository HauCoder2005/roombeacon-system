import unittest
from unittest.mock import patch, MagicMock

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.discovery.strategy_resolver import (
    DiscoveryStrategy,
    DiscoveryStrategyResolver,
)
from roombeacon_crawler.discovery.registry import discovery_registry
from roombeacon_crawler.services.source_qualifier import SourceQualifier
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.registry import source_registry
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter
from roombeacon_crawler.sources.phongtro123.adapter import Phongtro123SourceAdapter
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.sources.muaban.adapter import MuabanSourceAdapter
from roombeacon_crawler.sources.batdongsan.adapter import BatDongSanSourceAdapter


class TestSourceAccessProfilesAndCapabilities(unittest.TestCase):
    """Kiểm thử hệ thống Source Access Profiles và Source Capabilities."""

    def test_source_access_profile_enum_values(self) -> None:
        self.assertEqual(SourceAccessProfile.STANDARD_PAGINATION.value, "STANDARD_PAGINATION")
        self.assertEqual(SourceAccessProfile.DISCOVERY_RESTRICTED.value, "DISCOVERY_RESTRICTED")
        self.assertEqual(SourceAccessProfile.ACCESS_CHALLENGED.value, "ACCESS_CHALLENGED")

    def test_all_registered_adapters_have_capabilities(self) -> None:
        adapters = [
            NhatroVNSourceAdapter,
            Phongtro123SourceAdapter,
            NhatotSourceAdapter,
            MuabanSourceAdapter,
            BatDongSanSourceAdapter,
        ]
        for adapter_cls in adapters:
            self.assertTrue(hasattr(adapter_cls, "CAPABILITIES"))
            caps = adapter_cls.CAPABILITIES
            self.assertIsInstance(caps, SourceCapabilities)
            self.assertIsInstance(caps.access_profile, SourceAccessProfile)
            self.assertIsInstance(caps.supports_pagination, bool)
            self.assertIsInstance(caps.supports_sitemap_discovery, bool)
            self.assertIsInstance(caps.preferred_fetch_strategy, FetchStrategy)

    def test_nhatrovn_and_phongtro123_capabilities(self) -> None:
        for adapter_cls in (NhatroVNSourceAdapter, Phongtro123SourceAdapter):
            caps = adapter_cls.CAPABILITIES
            self.assertEqual(caps.access_profile, SourceAccessProfile.STANDARD_PAGINATION)
            self.assertTrue(caps.supports_pagination)
            self.assertFalse(caps.supports_sitemap_discovery)
            self.assertEqual(caps.preferred_fetch_strategy, FetchStrategy.HTTP)

    def test_nhatot_capabilities(self) -> None:
        caps = NhatotSourceAdapter.CAPABILITIES
        self.assertEqual(caps.access_profile, SourceAccessProfile.DISCOVERY_RESTRICTED)
        self.assertFalse(caps.supports_pagination)
        self.assertTrue(caps.supports_sitemap_discovery)
        self.assertEqual(caps.preferred_fetch_strategy, FetchStrategy.BROWSER)

    def test_muaban_and_batdongsan_capabilities(self) -> None:
        for adapter_cls in (MuabanSourceAdapter, BatDongSanSourceAdapter):
            caps = adapter_cls.CAPABILITIES
            self.assertEqual(caps.access_profile, SourceAccessProfile.ACCESS_CHALLENGED)
            self.assertFalse(caps.supports_pagination)
            self.assertTrue(caps.supports_sitemap_discovery)

    def test_discovery_strategy_resolver_by_capabilities(self) -> None:
        resolver = DiscoveryStrategyResolver()
        self.assertEqual(resolver.resolve("nhatrovn"), DiscoveryStrategy.STANDARD)
        self.assertEqual(resolver.resolve("phongtro123"), DiscoveryStrategy.STANDARD)
        self.assertEqual(resolver.resolve("nhatot"), DiscoveryStrategy.ENHANCED_DISCOVERY)
        self.assertEqual(resolver.resolve("muaban"), DiscoveryStrategy.ENHANCED_DISCOVERY)
        self.assertEqual(resolver.resolve("batdongsan"), DiscoveryStrategy.ENHANCED_DISCOVERY)
        self.assertEqual(resolver.resolve("unknown_source"), DiscoveryStrategy.STANDARD)

    @patch("roombeacon_crawler.policies.robots_policy.RobotsPolicy.evaluate")
    def test_source_qualifier_returns_access_profile(self, mock_robots_eval: MagicMock) -> None:
        mock_robots_eval.return_value = ("ALLOWED", "https://phongtro123.com/robots.txt")
        qualifier = SourceQualifier()
        res = qualifier.qualify("https://phongtro123.com/cho-thue-phong-tro")
        self.assertEqual(res.access_profile, "STANDARD_PAGINATION")
        self.assertIsNotNone(res.capabilities)
        self.assertEqual(res.capabilities["access_profile"], "STANDARD_PAGINATION")
        self.assertTrue(res.capabilities["supports_pagination"])

    def test_nhatot_detail_url_classification_and_isolation(self) -> None:
        """Kiểm thử URL detail của NhaTot được phân loại chính xác thành DETAIL_PAGE."""
        adapter = NhatotSourceAdapter()
        detail_url = "https://www.nhatot.com/thue-phong-tro-thanh-pho-thu-duc-tp-ho-chi-minh/134263371.htm"
        category_url = "https://www.nhatot.com/thue-phong-tro"
        
        from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
        self.assertEqual(adapter.classify_url(detail_url), CrawlTargetType.DETAIL_PAGE)
        self.assertEqual(adapter.classify_url(category_url), CrawlTargetType.LISTING_PAGE)

    def test_operation_specific_transports_modeled(self) -> None:
        """Kiểm thử tách biệt giữa Discovery Transport và Content Transport."""
        caps = SourceCapabilities(
            access_profile=SourceAccessProfile.DISCOVERY_RESTRICTED,
            preferred_discovery_transport=FetchStrategy.HTTP,
            preferred_fetch_strategy=FetchStrategy.BROWSER,
        )
        self.assertEqual(caps.preferred_discovery_transport, FetchStrategy.HTTP)
        self.assertEqual(caps.preferred_content_transport, FetchStrategy.BROWSER)
        self.assertNotEqual(caps.preferred_discovery_transport, caps.preferred_content_transport)


if __name__ == "__main__":
    unittest.main()
