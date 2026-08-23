import re
from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.models.source_capabilities import SourceCapabilities
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.batdongsan.discovery.date_interpreter import (
    BatDongSanDateInterpreter,
)
from roombeacon_crawler.sources.batdongsan.discovery.pagination import (
    BatDongSanPagination,
)
from roombeacon_crawler.sources.batdongsan.parsers.detail_parser import (
    BatDongSanDetailParser,
)
from roombeacon_crawler.sources.batdongsan.parsers.listing_parser import (
    BatDongSanListingParser,
)
from roombeacon_crawler.sources.batdongsan.parsers.metadata_parser import (
    BatDongSanMetadataParser,
)


class BatDongSanSourceAdapter(BaseSourceAdapter):
    """Source Adapter cho website Bất Động Sản (batdongsan.com.vn)."""

    SOURCE_NAME = "batdongsan"
    DOMAINS = ("batdongsan.com.vn", "www.batdongsan.com.vn")
    DEFAULT_BASE_URL = "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro"
    CAPABILITIES = SourceCapabilities(
        access_profile=SourceAccessProfile.ACCESS_CHALLENGED,
        supports_pagination=False,
        supports_sitemap_discovery=True,
        preferred_discovery_transport=FetchStrategy.HTTP,
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
            domain="batdongsan.com.vn",
            base_url=self.base_url,
            default_strategy=FetchStrategy.HTTP,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )

        self.listing_parser = BatDongSanListingParser(source_name=self.SOURCE_NAME)
        self.detail_parser = BatDongSanDetailParser(source_name=self.SOURCE_NAME)
        self.metadata_parser = BatDongSanMetadataParser()
        self.pagination = BatDongSanPagination()
        self.date_interpreter = BatDongSanDateInterpreter()

    def classify_url(self, url: str) -> CrawlTargetType:
        """Phân loại URL mục tiêu của BatDongSan."""
        if not url:
            return CrawlTargetType.UNSUPPORTED
        try:
            parsed = urlparse(url.strip())
            path = parsed.path.lower().rstrip("/")

            # Detail URL dạng ...-pr12345678 hoặc /pr12345678
            if re.search(r"-pr\d+", path) or re.search(r"/pr\d+", path):
                return CrawlTargetType.DETAIL_PAGE

            # Listing categories
            if (
                path.startswith("/cho-thue-")
                or path.startswith("/nha-dat-cho-thue")
                or path.startswith("/ban-")
                or path.startswith("/nha-dat-ban")
                or path == ""
            ):
                return CrawlTargetType.LISTING_PAGE

            return CrawlTargetType.UNSUPPORTED
        except Exception:
            return CrawlTargetType.UNSUPPORTED

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        """Cấu hình các target định kỳ mặc định cho BatDongSan."""
        return (
            CrawlSeed(
                source=self.SOURCE_NAME,
                target_id="hcm_phongtro",
                url="https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro-tp-hcm",
                enabled=True,
                interval_minutes=120,
                target_type_hint=CrawlTargetType.LISTING_PAGE,
                label="batdongsan_hcm_phongtro",
            ),
        )
