"""Declare Mogi HTTP source policy and cp pagination."""
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import QueryPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter
from .parsers.listing_parser import MogiListingParser
from .parsers.detail_parser import MogiDetailParser

class MogiPagination(QueryPagination): PARAMETER="cp"
class MogiSourceAdapter(ScheduledHtmlSourceAdapter):
    ENABLED=True
    INTERVAL_MINUTES=5
    SOURCE_NAME="mogi"; DOMAINS=("mogi.vn", "www.mogi.vn")
    DEFAULT_BASE_URL="https://mogi.vn/ho-chi-minh/thue-phong-tro-nha-tro"
    CAPABILITIES=SourceCapabilities(access_profile=SourceAccessProfile.STANDARD_PAGINATION, supports_pagination=True, preferred_fetch_strategy=FetchStrategy.BROWSER, detail_fetch_supported=True)
    LISTING_PREFIXES=("/ho-chi-minh/thue-phong-tro",); DETAIL_MARKERS=("-id",)
    LISTING_PARSER=MogiListingParser; DETAIL_PARSER=MogiDetailParser; PAGINATION=MogiPagination
