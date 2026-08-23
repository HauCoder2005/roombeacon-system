import tempfile
import unittest

from roombeacon_crawler.discovery.strategy_resolver import (
    DiscoveryStrategy,
    DiscoveryStrategyResolver,
)
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.services.crawl_planner import CrawlPlanner


class TestStrategyResolver(unittest.TestCase):
    """Kiểm thử DiscoveryStrategyResolver phân định STANDARD vs ENHANCED_DISCOVERY."""

    def test_resolver_decides_based_on_registry_presence(self) -> None:
        resolver = DiscoveryStrategyResolver()
        self.assertEqual(resolver.resolve("nhatot"), DiscoveryStrategy.ENHANCED_DISCOVERY)
        self.assertEqual(resolver.resolve("batdongsan"), DiscoveryStrategy.ENHANCED_DISCOVERY)
        self.assertEqual(resolver.resolve("muaban"), DiscoveryStrategy.ENHANCED_DISCOVERY)
        self.assertEqual(resolver.resolve("nhatrovn"), DiscoveryStrategy.STANDARD)
        self.assertEqual(resolver.resolve("phongtro123"), DiscoveryStrategy.STANDARD)
        self.assertEqual(resolver.resolve(""), DiscoveryStrategy.STANDARD)

    def test_crawl_planner_integrates_strategy_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = LocalCrawlStateRepository(base_data_dir=tmp_dir)
            planner = CrawlPlanner(state_repository=repo)

            seeds = [
                CrawlSeed(
                    source="nhatrovn",
                    target_id="hcm_phongtro",
                    url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                ),
                CrawlSeed(
                    source="phongtro123",
                    target_id="hcm_phongtro",
                    url="https://phongtro123.com/tinh-thanh/ho-chi-minh",
                ),
                CrawlSeed(
                    source="nhatot",
                    target_id="hcm_phongtro",
                    url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
                ),
            ]

            plans = planner.plan_all(seeds)
            self.assertEqual(len(plans), 3)

            plan_dict = {p.source: p for p in plans}
            self.assertEqual(plan_dict["nhatrovn"].discovery_strategy, DiscoveryStrategy.STANDARD)
            self.assertEqual(plan_dict["phongtro123"].discovery_strategy, DiscoveryStrategy.STANDARD)
            self.assertEqual(plan_dict["nhatot"].discovery_strategy, DiscoveryStrategy.ENHANCED_DISCOVERY)


if __name__ == "__main__":
    unittest.main()
