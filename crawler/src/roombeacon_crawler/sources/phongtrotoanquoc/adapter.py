"""Register PhongTroToanQuoc as controlled-disabled pending a valid robots policy."""

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.common_html import QueryPagination
from roombeacon_crawler.sources.scheduled_source import ScheduledHtmlSourceAdapter

from .parsers.detail_parser import PhongtrotoanquocDetailParser
from .parsers.listing_parser import PhongtrotoanquocListingParser


class PhongtrotoanquocSourceAdapter(ScheduledHtmlSourceAdapter):
    SOURCE_NAME = "phongtrotoanquoc"
    DOMAINS = ("phongtrotoanquoc.com", "www.phongtrotoanquoc.com")
    DEFAULT_BASE_URL = (
        "https://phongtrotoanquoc.com/phong-tro/thanh-pho-ho-chi-minh"
    )
    ENABLED = False
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.ACCESS_CHALLENGED,
        supports_pagination=False,
        historical_backfill_supported=False,
        preferred_fetch_strategy=FetchStrategy.BROWSER,
        robots_required=True,
        detail_fetch_supported=False,
    )
    LISTING_PREFIXES = ("/phong-tro/",)
    DETAIL_MARKERS = ("/tin/", "/post/")
    LISTING_PARSER = PhongtrotoanquocListingParser
    DETAIL_PARSER = PhongtrotoanquocDetailParser
    PAGINATION = QueryPagination
