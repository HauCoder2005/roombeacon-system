import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from roombeacon_crawler.discovery.adapters.nhatot import NhaTotDiscoveryAdapter
from roombeacon_crawler.discovery.engine import SitemapDiscoveryEngine
from roombeacon_crawler.discovery.models import (
    DiscoveryStatus,
)
from roombeacon_crawler.discovery.sitemap.fetcher import (
    SitemapFetchResponse,
    SitemapFetcher,
)
from roombeacon_crawler.discovery.storage import DiscoveryStorage

SAMPLE_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
   <sitemap>
      <loc>https://example.com/sitemaps/sitemap-rent-1.xml</loc>
   </sitemap>
</sitemapindex>
"""

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


class TestSitemapDiscoveryEngine(unittest.IsolatedAsyncioTestCase):
    """Kiểm thử SitemapDiscoveryEngine điều phối toàn diện quy trình khám phá và lưu trữ Artifact."""

    async def test_engine_discovery_traversal_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            mock_fetcher = MagicMock(spec=SitemapFetcher)

            async def mock_fetch(url: str) -> SitemapFetchResponse:
                if "sitemap_main.xml" in url:
                    return SitemapFetchResponse(url=url, status_code=200, content=SAMPLE_INDEX_XML, is_success=True)
                elif "sitemap-rent-1.xml" in url:
                    return SitemapFetchResponse(url=url, status_code=200, content=SAMPLE_URLSET_XML, is_success=True)
                return SitemapFetchResponse(url=url, status_code=404, content=None, is_success=False)

            mock_fetcher.fetch = AsyncMock(side_effect=mock_fetch)

            adapter = NhaTotDiscoveryAdapter()
            adapter.DEFAULT_ENTRYPOINTS = ("https://example.com/sitemap_main.xml",)

            storage = DiscoveryStorage(base_dir=tmp_dir)
            engine = SitemapDiscoveryEngine(
                fetcher=mock_fetcher,
                storage=storage,
            )

            discovered, result, artifact = await engine.discover(
                adapter=adapter,
                run_id="run_disc_modular_test",
                max_depth=3,
            )

            self.assertEqual(len(discovered), 2)
            self.assertEqual(result.status, DiscoveryStatus.SUCCESS)
            self.assertEqual(result.count, 2)
            self.assertTrue(os.path.exists(result.artifact_path))

            # Đọc lại artifact qua DiscoveryStorage
            loaded_artifact = storage.load_artifact(result.artifact_path)
            self.assertIsNotNone(loaded_artifact)
            self.assertEqual(loaded_artifact.source, "nhatot")
            self.assertEqual(loaded_artifact.count, 2)


if __name__ == "__main__":
    unittest.main()
