import unittest

from roombeacon_crawler.discovery.adapters.batdongsan import BatDongSanDiscoveryAdapter
from roombeacon_crawler.discovery.adapters.muaban import MuabanDiscoveryAdapter
from roombeacon_crawler.discovery.adapters.nhatot import NhaTotDiscoveryAdapter
from roombeacon_crawler.discovery.base import SourceDiscoveryAdapter
from roombeacon_crawler.discovery.models import DiscoveryType
from roombeacon_crawler.discovery.sitemap.url_filter import DiscoveryUrlFilter


class TestDiscoveryAdapters(unittest.TestCase):
    """Kiểm thử tính đúng đắn của các DiscoveryAdapter nguồn lớn (NhaTot, BatDongSan, Muaban)."""

    def test_adapter_contract_purity(self) -> None:
        """Đảm bảo DiscoveryAdapter không chứa hàm parse HTML nghiệp vụ."""
        for adapter in (NhaTotDiscoveryAdapter(), BatDongSanDiscoveryAdapter(), MuabanDiscoveryAdapter()):
            self.assertIsInstance(adapter, SourceDiscoveryAdapter)
            self.assertFalse(hasattr(adapter, "parse_listing"))
            self.assertFalse(hasattr(adapter, "parse_detail"))
            self.assertFalse(hasattr(adapter, "listing_parser"))
            self.assertFalse(hasattr(adapter, "detail_parser"))
            self.assertTrue(len(adapter.discover_entrypoints()) > 0)

    def test_nhatot_candidate_filtering_and_deduplication(self) -> None:
        adapter = NhaTotDiscoveryAdapter()
        raw_entries = [
            ("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh/101.htm", "2026-08-20T08:00:00Z"),
            ("https://www.nhatot.com/thue-can-ho-chung-cu-tp-ho-chi-minh/102.htm", "2026-08-20T08:30:00Z"),
            ("https://www.nhatot.com/mua-ban-xe-may/201.htm", "2026-08-20T09:00:00Z"),  # Non-rental -> Loại
            ("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh/101.htm#fragment", "2026-08-20T08:00:00Z"),  # Duplicate -> Khử
        ]

        discovered = DiscoveryUrlFilter.filter_and_deduplicate(
            entries=raw_entries,
            adapter=adapter,
            discovered_from="https://www.nhatot.com/sitemap.xml",
            discovery_type=DiscoveryType.SITEMAP_URLSET,
        )

        self.assertEqual(len(discovered), 2)
        urls = [d.url for d in discovered]
        self.assertIn("https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh/101.htm", urls)
        self.assertIn("https://www.nhatot.com/thue-can-ho-chung-cu-tp-ho-chi-minh/102.htm", urls)
        self.assertNotIn("https://www.nhatot.com/mua-ban-xe-may/201.htm", urls)

    def test_batdongsan_candidate_filtering(self) -> None:
        bds = BatDongSanDiscoveryAdapter()
        self.assertTrue(bds.filter_candidate_url("https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm"))
        self.assertTrue(bds.filter_candidate_url("https://batdongsan.com.vn/cho-thue-nha-rieng-pr12345"))
        self.assertFalse(bds.filter_candidate_url("https://batdongsan.com.vn/tin-tuc/thi-truong-bds"))

    def test_muaban_candidate_filtering(self) -> None:
        muaban = MuabanDiscoveryAdapter()
        self.assertTrue(muaban.filter_candidate_url("https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm"))
        self.assertTrue(muaban.filter_candidate_url("https://muaban.net/cho-thue-phong-tro-id67890"))
        self.assertFalse(muaban.filter_candidate_url("https://muaban.net/viec-lam/tuyen-dung-tp-hcm"))


if __name__ == "__main__":
    unittest.main()
