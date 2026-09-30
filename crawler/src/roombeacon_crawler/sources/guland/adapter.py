"""Declare Guland capabilities; pagination remains disabled until its JS cursor is modeled."""

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import QueryPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter

from .parsers.detail_parser import GulandDetailParser
from .parsers.listing_parser import GulandListingParser


class GulandSourceAdapter(ScheduledHtmlSourceAdapter):
    INTERVAL_MINUTES = 10
    SOURCE_NAME = "guland"
    DOMAINS = ("guland.vn", "www.guland.vn")
    DEFAULT_BASE_URL = "https://guland.vn/cho-thue-phong-tro-tp-ho-chi-minh"
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.DISCOVERY_RESTRICTED,
        supports_pagination=False,
        historical_backfill_supported=False,
        preferred_fetch_strategy=FetchStrategy.HTTP,
        detail_fetch_supported=True,
    )
    LISTING_PREFIXES = ("/cho-thue-",)
    DETAIL_MARKERS = ("/post/",)
    LISTING_PARSER = GulandListingParser
    DETAIL_PARSER = GulandDetailParser
    PAGINATION = QueryPagination
