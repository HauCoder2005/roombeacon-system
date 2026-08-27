from urllib.parse import urlparse

from roombeacon_crawler.demo.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.demo.sources.source_policy import (
    DEFAULT_STRATEGY,
    SOURCE_STRATEGIES,
)


class StrategySelector:
    """Provide the demo-only StrategySelector contract used by the isolated example crawler."""
    def select(self, url: str) -> FetchStrategy:
        """Execute the demo-only select step without affecting production workflows."""
        try:
            parsed = urlparse(url)
            hostname = (parsed.hostname or parsed.netloc or "").lower()
        except Exception:
            return DEFAULT_STRATEGY

        for domain, strategy in SOURCE_STRATEGIES.items():
            if domain in hostname:
                return strategy

        return DEFAULT_STRATEGY
