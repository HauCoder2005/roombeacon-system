from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.nhatot.discovery.date_interpreter import (
    NhatotDateInterpreter,
)
from roombeacon_crawler.sources.nhatot.discovery.pagination import NhatotPagination
from roombeacon_crawler.sources.nhatot.parsers.detail_parser import NhatotDetailParser
from roombeacon_crawler.sources.nhatot.parsers.listing_parser import NhatotListingParser
from roombeacon_crawler.sources.nhatot.parsers.metadata_parser import NhatotMetadataParser


class NhatotSourceAdapter(BaseSourceAdapter):
    """Source Adapter cho website Nhà Tốt (nhatot.com), tích hợp các parsers và discovery mechanisms."""

    SOURCE_NAME = "nhatot"
    DOMAINS = ("nhatot.com", "www.nhatot.com")
    DEFAULT_BASE_URL = "https://www.nhatot.com/thue-phong-tro"

    def __init__(
        self,
        base_url: str | None = None,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> None:
        super().__init__(
            base_url=base_url or self.DEFAULT_BASE_URL,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )
        self.settings = SourceSettings(
            source_name=self.SOURCE_NAME,
            domain="nhatot.com",
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

    def classify_url(self, url: str) -> CrawlTargetType:
        """Phân loại URL mục tiêu cho website Nhà Tốt."""
        if not url:
            return CrawlTargetType.UNSUPPORTED
        try:
            parsed = urlparse(url.strip())
            path = parsed.path.lower().rstrip("/")
            if path.endswith(".htm") and not path.startswith("/thue-phong-tro"):
                return CrawlTargetType.DETAIL_PAGE
            if path.startswith("/thue-phong-tro") or path == "":
                return CrawlTargetType.LISTING_PAGE
            return CrawlTargetType.UNSUPPORTED
        except Exception:
            return CrawlTargetType.UNSUPPORTED

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        """Cấu hình các target định kỳ mặc định cho NhaTot."""
        return (
            CrawlSeed(
                source=self.SOURCE_NAME,
                url="https://www.nhatot.com/thue-phong-tro-tp-ho-chi-minh",
                enabled=True,
                target_type_hint=CrawlTargetType.LISTING_PAGE,
                label="nhatot_hcm_phongtro",
            ),
        )
