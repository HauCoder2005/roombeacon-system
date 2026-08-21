from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.phongtro123.discovery.date_interpreter import (
    Phongtro123DateInterpreter,
)
from roombeacon_crawler.sources.phongtro123.discovery.pagination import (
    Phongtro123Pagination,
)
from roombeacon_crawler.sources.phongtro123.parsers.detail_parser import (
    Phongtro123DetailParser,
)
from roombeacon_crawler.sources.phongtro123.parsers.listing_parser import (
    Phongtro123ListingParser,
)
from roombeacon_crawler.sources.phongtro123.parsers.metadata_parser import (
    Phongtro123MetadataParser,
)


from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities


class Phongtro123SourceAdapter(BaseSourceAdapter):
    """Source Adapter cho website Phongtro123 (phongtro123.com)."""

    SOURCE_NAME = "phongtro123"
    DOMAINS = ("phongtro123.com", "www.phongtro123.com")
    DEFAULT_BASE_URL = "https://phongtro123.com/cho-thue-phong-tro"
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.STANDARD_PAGINATION,
        supports_pagination=True,
        supports_sitemap_discovery=False,
        preferred_fetch_strategy=FetchStrategy.HTTP,
        robots_required=True,
        detail_fetch_supported=True,
    )

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
            domain="phongtro123.com",
            base_url=self.base_url,
            default_strategy=FetchStrategy.HTTP,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )

        self.listing_parser = Phongtro123ListingParser(source_name=self.SOURCE_NAME)
        self.detail_parser = Phongtro123DetailParser(source_name=self.SOURCE_NAME)
        self.metadata_parser = Phongtro123MetadataParser()
        self.pagination = Phongtro123Pagination()
        self.date_interpreter = Phongtro123DateInterpreter()

    def classify_url(self, url: str) -> CrawlTargetType:
        """Phân loại URL mục tiêu cho website Phongtro123."""
        if not url:
            return CrawlTargetType.UNSUPPORTED
        try:
            parsed = urlparse(url.strip())
            path = parsed.path.lower().rstrip("/")
            if "-pr" in path or "/chi-tiet/" in path:
                return CrawlTargetType.DETAIL_PAGE
            if (
                path.startswith("/cho-thue-phong-tro")
                or path.startswith("/tinh-thanh")
                or path == ""
            ):
                return CrawlTargetType.LISTING_PAGE
            return CrawlTargetType.UNSUPPORTED
        except Exception:
            return CrawlTargetType.UNSUPPORTED

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        """Cấu hình các target định kỳ mặc định cho Phongtro123."""
        return (
            CrawlSeed(
                source=self.SOURCE_NAME,
                target_id="hcm_phongtro",
                url="https://phongtro123.com/tinh-thanh/ho-chi-minh",
                enabled=True,
                interval_minutes=45,
                target_type_hint=CrawlTargetType.LISTING_PAGE,
                label="phongtro123_hcm_phongtro",
            ),
        )
