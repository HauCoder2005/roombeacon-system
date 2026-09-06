"""Declare CafeLand HTTP source policy and audited path pagination."""

import re
from urllib.parse import urlparse

from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import PathPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter

from .parsers.detail_parser import CafelandDetailParser
from .parsers.listing_parser import CafelandListingParser


class CafelandPagination(PathPagination):
    """Build CafeLand's audited ``/page-N/`` listing route."""

    def build_page_url(
        self, base_url: str = "", page_number: int = 1, *args, **kwargs
    ) -> str:
        """Build this source's URL for the requested listing page."""
        if page_number <= 1:
            return base_url
        return f"{base_url.rstrip('/')}/page-{page_number}/"


class CafelandSourceAdapter(ScheduledHtmlSourceAdapter):
    """Configure this source's domains, selectors, pagination, and crawl capabilities."""
    ENABLED = True
    INTERVAL_MINUTES = 5
    SOURCE_NAME = "cafeland"
    DOMAINS = ("nhadat.cafeland.vn",)
    DEFAULT_BASE_URL = (
        "https://nhadat.cafeland.vn/cho-thue/phong-tro-tai-tp-ho-chi-minh/"
    )
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.STANDARD_PAGINATION,
        supports_pagination=True,
        preferred_fetch_strategy=FetchStrategy.HTTP,
        detail_fetch_supported=True,
    )
    LISTING_PREFIXES = ("/cho-thue/phong-tro",)
    DETAIL_MARKERS = (".html",)
    LISTING_PARSER = CafelandListingParser
    DETAIL_PARSER = CafelandDetailParser
    PAGINATION = CafelandPagination
    DETAIL_PATH_PATTERN = re.compile(
        r"^/cho-thue-phong-tro-[^/]+-\d+\.html$",
        re.IGNORECASE,
    )

    def classify_url(self, url: str) -> CrawlTargetType:
        """Accept only the audited room-listing category and detail routes."""
        if not self.supports(url):
            return CrawlTargetType.UNSUPPORTED
        path = urlparse(url).path.casefold()
        if path.startswith(self.LISTING_PREFIXES):
            return CrawlTargetType.LISTING_PAGE
        if self.DETAIL_PATH_PATTERN.fullmatch(path):
            return CrawlTargetType.DETAIL_PAGE
        return CrawlTargetType.UNSUPPORTED
