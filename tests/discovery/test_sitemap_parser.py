import unittest

from roombeacon_crawler.discovery.sitemap.parser import (
    SitemapDocumentType,
    SitemapEntry,
    SitemapUrlsetParser,
)

SAMPLE_URLSET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <url>
      <loc>https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh/101.htm</loc>
      <lastmod>2026-08-20T08:00:00Z</lastmod>
   </url>
   <url>
      <loc>https://www.nhatot.com/thue-can-ho-chung-cu-tp-ho-chi-minh/102.htm</loc>
      <lastmod>2026-08-20T08:30:00Z</lastmod>
   </url>
</urlset>
"""


class TestSitemapUrlsetParser(unittest.TestCase):
    """Kiểm thử SitemapUrlsetParser trích xuất URL và lastmod từ XML urlset."""

    def test_parse_urlset_extracts_all_entries(self) -> None:
        entries = SitemapUrlsetParser.parse_urlset(SAMPLE_URLSET_XML)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].loc, "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh/101.htm")
        self.assertEqual(entries[0].lastmod, "2026-08-20T08:00:00Z")
        self.assertEqual(entries[1].loc, "https://www.nhatot.com/thue-can-ho-chung-cu-tp-ho-chi-minh/102.htm")
        self.assertEqual(entries[1].lastmod, "2026-08-20T08:30:00Z")

    def test_parse_urlset_empty_or_invalid_returns_empty_list(self) -> None:
        self.assertEqual(SitemapUrlsetParser.parse_urlset(""), [])
        self.assertEqual(SitemapUrlsetParser.parse_urlset("<invalid>xml"), [])


if __name__ == "__main__":
    unittest.main()
