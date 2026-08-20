import unittest

from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter
from roombeacon_crawler.sources.nhatrovn.adapter import NhatroVNSourceAdapter
from roombeacon_crawler.sources.phongtro123.adapter import Phongtro123SourceAdapter
from roombeacon_crawler.sources.resolver import SourceResolver


class TestSourceResolver(unittest.TestCase):
    def test_resolve_nhatot(self) -> None:
        url = "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"
        source_name = SourceResolver.resolve_source_name(url)
        self.assertEqual(source_name, "nhatot")

        adapter = SourceResolver.resolve_adapter(url)
        self.assertIsInstance(adapter, NhatotSourceAdapter)
        self.assertEqual(adapter.base_url, url)

    def test_resolve_nhatrovn(self) -> None:
        url = "https://nhatrovn.vn/cho-thue-phong-tro/ha-noi/"
        source_name = SourceResolver.resolve_source_name(url)
        self.assertEqual(source_name, "nhatrovn")

        adapter = SourceResolver.resolve_adapter(url)
        self.assertIsInstance(adapter, NhatroVNSourceAdapter)
        self.assertEqual(adapter.base_url, url)

    def test_resolve_phongtro123(self) -> None:
        url = "https://phongtro123.com/tinh-thanh/ho-chi-minh"
        source_name = SourceResolver.resolve_source_name(url)
        self.assertEqual(source_name, "phongtro123")

        adapter = SourceResolver.resolve_adapter(url)
        self.assertIsInstance(adapter, Phongtro123SourceAdapter)
        self.assertEqual(adapter.base_url, url)

    def test_unsupported_domain_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            SourceResolver.resolve_adapter("https://unknown-domain.com/listing")


if __name__ == "__main__":
    unittest.main()
