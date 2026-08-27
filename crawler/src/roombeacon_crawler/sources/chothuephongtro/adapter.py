"""Declare ChoThuePhongTro HTTP pagination and detail capabilities."""
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import QueryPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter
from .parsers.listing_parser import ChothuephongtroListingParser
from .parsers.detail_parser import ChothuephongtroDetailParser

class ChothuephongtroSourceAdapter(ScheduledHtmlSourceAdapter):
    ENABLED=True
    INTERVAL_MINUTES=5
    SOURCE_NAME="chothuephongtro"; DOMAINS=("chothuephongtro.me", "www.chothuephongtro.me")
    DEFAULT_BASE_URL="https://chothuephongtro.me/ho-chi-minh.html"
    CAPABILITIES=SourceCapabilities(access_profile=SourceAccessProfile.STANDARD_PAGINATION, supports_pagination=True, preferred_fetch_strategy=FetchStrategy.HTTP, detail_fetch_supported=True)
    LISTING_PREFIXES=("/ho-chi-minh",); DETAIL_MARKERS=("-pr",)
    LISTING_PARSER=ChothuephongtroListingParser; DETAIL_PARSER=ChothuephongtroDetailParser; PAGINATION=QueryPagination
