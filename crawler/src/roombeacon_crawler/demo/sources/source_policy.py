from roombeacon_crawler.demo.enums.fetch_strategy import FetchStrategy

SOURCE_STRATEGIES: dict[str, FetchStrategy] = {
    "nhatot.com": FetchStrategy.BROWSER,
}

DEFAULT_STRATEGY: FetchStrategy = FetchStrategy.HTTP
