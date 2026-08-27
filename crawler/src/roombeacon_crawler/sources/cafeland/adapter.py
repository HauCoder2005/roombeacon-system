"""Declare CafeLand HTTP source policy and audited path pagination."""

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

    def classify_url(self, url: str) -> CrawlTargetType:
        """Reject broker profiles even when their route ends in ``.html``."""
        if "/moi-gioi/" in urlparse(url).path.casefold():
            return CrawlTargetType.UNSUPPORTED
        return super().classify_url(url)
