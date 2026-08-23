import re
from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.muaban.discovery.date_interpreter import (
    MuabanDateInterpreter,
)
from roombeacon_crawler.sources.muaban.discovery.pagination import (
    MuabanPagination,
)
from roombeacon_crawler.sources.muaban.parsers.detail_parser import (
    MuabanDetailParser,
)
from roombeacon_crawler.sources.muaban.parsers.listing_parser import (
    MuabanListingParser,
)
from roombeacon_crawler.sources.muaban.parsers.metadata_parser import (
    MuabanMetadataParser,
)


class MuabanSourceAdapter(BaseSourceAdapter):
    """Source Adapter cho website Mua Bán (muaban.net)."""

    SOURCE_NAME = "muaban"
    DOMAINS = ("muaban.net", "www.muaban.net")
    DEFAULT_BASE_URL = "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro"
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.ACCESS_CHALLENGED,
        supports_pagination=False,
        supports_sitemap_discovery=True,
        preferred_fetch_strategy=FetchStrategy.HTTP,
        robots_required=True,
        detail_fetch_supported=False,
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
            domain="muaban.net",
            base_url=self.base_url,
            default_strategy=FetchStrategy.HTTP,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )

        self.listing_parser = MuabanListingParser(source_name=self.SOURCE_NAME)
        self.detail_parser = MuabanDetailParser(source_name=self.SOURCE_NAME)
        self.metadata_parser = MuabanMetadataParser()
        self.pagination = MuabanPagination()
        self.date_interpreter = MuabanDateInterpreter()

    def classify_url(self, url: str) -> CrawlTargetType:
        """Phân loại URL mục tiêu của Muaban."""
        if not url:
            return CrawlTargetType.UNSUPPORTED
        try:
            parsed = urlparse(url.strip())
            path = parsed.path.lower().rstrip("/")

            # Detail URL dạng ...-id12345678 hoặc /id12345678
            if re.search(r"-id\d+", path) or re.search(r"/id\d+", path):
                return CrawlTargetType.DETAIL_PAGE

            # Listing categories
            if (
                path.startswith("/bat-dong-san")
                or path.startswith("/cho-thue")
                or path.startswith("/mua-ban-nha-dat")
                or path == ""
            ):
                return CrawlTargetType.LISTING_PAGE

            return CrawlTargetType.UNSUPPORTED
        except Exception:
            return CrawlTargetType.UNSUPPORTED

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        """Cấu hình các target định kỳ mặc định cho Muaban."""
        return (
            CrawlSeed(
                source=self.SOURCE_NAME,
                target_id="hcm_phongtro",
                url="https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro-tp-hcm",
                enabled=True,
                interval_minutes=60,
                target_type_hint=CrawlTargetType.LISTING_PAGE,
                label="muaban_hcm_phongtro",
            ),
        )
