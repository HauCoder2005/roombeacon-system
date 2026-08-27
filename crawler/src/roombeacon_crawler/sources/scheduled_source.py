"""Compose audited source components into conservative scheduled adapters."""

from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.common_html import EmbeddedMetadataParser, VietnameseDateInterpreter


class ScheduledHtmlSourceAdapter(BaseSourceAdapter):
    """Shared composition only; each concrete source owns policy and selectors."""

    TARGET_ID = "hcm_phongtro"
    INTERVAL_MINUTES = 30
    BOOTSTRAP_SAFETY_MAX_PAGES = 10
    ENABLED = True
    LISTING_PREFIXES: tuple[str, ...] = ()
    DETAIL_MARKERS: tuple[str, ...] = ()
    LISTING_PARSER = None
    DETAIL_PARSER = None
    PAGINATION = None

    def __init__(self, base_url=None, request_delay_seconds=1.5, max_concurrency=1):
        super().__init__(base_url or self.DEFAULT_BASE_URL, request_delay_seconds, max_concurrency)
        strategy = self.CAPABILITIES.preferred_fetch_strategy
        self.settings = SourceSettings(
            source_name=self.SOURCE_NAME,
            domain=self.DOMAINS[0],
            base_url=self.base_url,
            default_strategy=strategy,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )
        self.listing_parser = self.LISTING_PARSER(self.SOURCE_NAME)
        self.detail_parser = self.DETAIL_PARSER(self.SOURCE_NAME)
        self.metadata_parser = EmbeddedMetadataParser()
        self.pagination = self.PAGINATION()
        self.date_interpreter = VietnameseDateInterpreter()

    def classify_url(self, url: str) -> CrawlTargetType:
        """Classify supported listing/detail paths without performing I/O."""
        if not self.supports(url):
            return CrawlTargetType.UNSUPPORTED
        path = urlparse(url).path.casefold()
        if any(marker in path for marker in self.DETAIL_MARKERS):
            return CrawlTargetType.DETAIL_PAGE
        if not self.LISTING_PREFIXES or any(path.startswith(prefix) for prefix in self.LISTING_PREFIXES):
            return CrawlTargetType.LISTING_PAGE
        return CrawlTargetType.UNSUPPORTED

    def scheduled_targets(self):
        """Expose the adapter's conservative default target to orchestration."""
        return (CrawlSeed(
            source=self.SOURCE_NAME,
            target_id=self.TARGET_ID,
            url=self.DEFAULT_BASE_URL,
            enabled=self.ENABLED,
            interval_minutes=self.INTERVAL_MINUTES,
            bootstrap_safety_max_pages=self.BOOTSTRAP_SAFETY_MAX_PAGES,
            crawl_details=self.CAPABILITIES.detail_fetch_supported,
            max_details_per_run=20,
            target_type_hint=CrawlTargetType.LISTING_PAGE,
            label=f"{self.SOURCE_NAME}_hcm_phongtro",
        ),)
