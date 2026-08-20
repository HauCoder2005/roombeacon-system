from typing import Any
from urllib.parse import urlparse

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy


class StrategySelector:
    """Lựa chọn chiến lược fetch (HTTP vs BROWSER) dựa trên adapter hint, domain mapping hoặc override."""

    DEFAULT_SOURCE_STRATEGIES: dict[str, FetchStrategy] = {
        "nhatot.com": FetchStrategy.BROWSER,
        "www.nhatot.com": FetchStrategy.BROWSER,
        "chotot.com": FetchStrategy.BROWSER,
        "www.chotot.com": FetchStrategy.BROWSER,
    }

    def __init__(
        self,
        custom_strategies: dict[str, FetchStrategy] | None = None,
    ) -> None:
        self.strategies = dict(self.DEFAULT_SOURCE_STRATEGIES)
        if custom_strategies:
            self.strategies.update(custom_strategies)

    def select(
        self,
        url: str,
        adapter: Any = None,
        override_strategy: FetchStrategy | None = None,
    ) -> FetchStrategy:
        """Xác định FetchStrategy cho một URL."""
        if override_strategy is not None:
            return override_strategy

        if adapter is not None and hasattr(adapter, "settings"):
            default_strat = getattr(adapter.settings, "default_strategy", None)
            if default_strat is not None:
                return default_strat

        try:
            parsed = urlparse(url)
            hostname = (parsed.netloc or "").lower().split(":")[0]
        except Exception:
            return FetchStrategy.HTTP

        for domain, strategy in self.strategies.items():
            if hostname == domain or hostname.endswith("." + domain):
                return strategy

        return FetchStrategy.HTTP
