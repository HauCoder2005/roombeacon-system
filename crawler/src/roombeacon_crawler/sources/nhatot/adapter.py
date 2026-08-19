from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.sources.nhatot.discovery.date_interpreter import NhatotDateInterpreter
from roombeacon_crawler.sources.nhatot.discovery.pagination import NhatotPagination
from roombeacon_crawler.sources.nhatot.parsers.detail_parser import NhatotDetailParser
from roombeacon_crawler.sources.nhatot.parsers.listing_parser import NhatotListingParser
from roombeacon_crawler.sources.nhatot.parsers.metadata_parser import NhatotMetadataParser


class NhatotSourceAdapter:
    """Source Adapter cho website Nhà Tốt (nhatot.com), tích hợp các parsers và discovery mechanisms."""

    SOURCE_NAME = "nhatot"
    DOMAIN = "nhatot.com"
    DEFAULT_BASE_URL = "https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> None:
        self.base_url = base_url
        self.settings = SourceSettings(
            source_name=self.SOURCE_NAME,
            domain=self.DOMAIN,
            base_url=self.base_url,
            default_strategy=FetchStrategy.BROWSER,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )

        self.listing_parser = NhatotListingParser(source_name=self.SOURCE_NAME)
        self.detail_parser = NhatotDetailParser(source_name=self.SOURCE_NAME)
        self.metadata_parser = NhatotMetadataParser()
        self.pagination = NhatotPagination()
        self.date_interpreter = NhatotDateInterpreter()
