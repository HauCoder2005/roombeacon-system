import unittest

from roombeacon_crawler.discovery.sitemap.index_parser import SitemapIndexParser

SAMPLE_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <sitemap>
      <loc>https://example.com/sitemaps/sitemap-rent-1.xml</loc>
      <lastmod>2026-08-19T10:00:00+07:00</lastmod>
   </sitemap>
   <sitemap>
      <loc>https://example.com/sitemaps/sitemap-rent-2.xml</loc>
      <lastmod>2026-08-19T11:00:00+07:00</lastmod>
   </sitemap>
</sitemapindex>
"""


class TestSitemapIndexParser(unittest.TestCase):
    """Kiểm thử SitemapIndexParser trích xuất danh sách child sitemaps."""

    def test_parse_index_extracts_child_sitemaps(self) -> None:
        entries = SitemapIndexParser.parse_index(SAMPLE_INDEX_XML)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].loc, "https://example.com/sitemaps/sitemap-rent-1.xml")
        self.assertEqual(entries[0].lastmod, "2026-08-19T10:00:00+07:00")
        self.assertEqual(entries[1].loc, "https://example.com/sitemaps/sitemap-rent-2.xml")
        self.assertEqual(entries[1].lastmod, "2026-08-19T11:00:00+07:00")

    def test_parse_index_on_urlset_returns_empty(self) -> None:
        urlset_xml = "<urlset><url><loc>https://example.com/1</loc></url></urlset>"
        entries = SitemapIndexParser.parse_index(urlset_xml)
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
