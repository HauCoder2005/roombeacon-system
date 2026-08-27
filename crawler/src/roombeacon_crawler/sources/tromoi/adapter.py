"""Declare TroMoi's robots-restricted pagination capability."""
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import QueryPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter
from .parsers.listing_parser import TromoiListingParser
from .parsers.detail_parser import TromoiDetailParser

class TromoiSourceAdapter(ScheduledHtmlSourceAdapter):
    INTERVAL_MINUTES=5
    SOURCE_NAME="tromoi"; DOMAINS=("tromoi.com", "www.tromoi.com")
    DEFAULT_BASE_URL="https://tromoi.com/tim-tro-tai-ho-chi-minh"
    CAPABILITIES=SourceCapabilities(access_profile=SourceAccessProfile.STANDARD_PAGINATION, supports_pagination=True, supports_sitemap_discovery=True, preferred_fetch_strategy=FetchStrategy.HTTP, detail_fetch_supported=True)
    LISTING_PREFIXES=("/tim-tro-", "/phong-tro"); DETAIL_MARKERS=("/phong-tro/",)
    LISTING_PARSER=TromoiListingParser; DETAIL_PARSER=TromoiDetailParser; PAGINATION=QueryPagination
