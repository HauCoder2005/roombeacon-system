"""Declare ChoThueNha policy and compose its source-specific parsers."""

import re
from urllib.parse import urlparse

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import QueryPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter

from .parsers.detail_parser import ChothuenhaDetailParser
from .parsers.listing_parser import ChothuenhaListingParser


class ChothuenhaSourceAdapter(ScheduledHtmlSourceAdapter):
    """Configure this source's domains, selectors, pagination, and crawl capabilities."""
    INTERVAL_MINUTES = 5
    SOURCE_NAME = "chothuenha"
    DOMAINS = ("chothuenha.com.vn", "www.chothuenha.com.vn")
    DEFAULT_BASE_URL = (
        "https://chothuenha.com.vn/cho-thue-phong-tro-nha-tro-ho-chi-minh"
    )
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.STANDARD_PAGINATION,
        supports_pagination=True,
        preferred_fetch_strategy=FetchStrategy.HTTP,
        detail_fetch_supported=True,
    )
    LISTING_PREFIXES = ("/cho-thue-phong-tro",)
    DETAIL_MARKERS = ()
    LISTING_PARSER = ChothuenhaListingParser
    DETAIL_PARSER = ChothuenhaDetailParser
    PAGINATION = QueryPagination
    DETAIL_PATH_PATTERN = re.compile(
        r"^/(?:phong-tro|nha-tro)-[^/]+-\d+$",
        re.IGNORECASE,
    )

    def classify_url(self, url: str) -> CrawlTargetType:
        """Classify a supported URL as a listing, detail, or unsupported target."""
        if not self.supports(url):
            return CrawlTargetType.UNSUPPORTED
        path = urlparse(url).path.rstrip("/")
        if path.startswith("/cho-thue-phong-tro"):
            return CrawlTargetType.LISTING_PAGE
        if self.DETAIL_PATH_PATTERN.fullmatch(path):
            return CrawlTargetType.DETAIL_PAGE
        return CrawlTargetType.UNSUPPORTED
