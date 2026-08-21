from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.crawl_seed import CrawlSeed
from roombeacon_crawler.sources.base import BaseSourceAdapter
from roombeacon_crawler.sources.nhatrovn.discovery.date_interpreter import (
    NhatroVNDateInterpreter,
)
from roombeacon_crawler.sources.nhatrovn.discovery.pagination import (
    NhatroVNPagination,
)
from roombeacon_crawler.sources.nhatrovn.parsers.detail_parser import (
    NhatroVNDetailParser,
)
from roombeacon_crawler.sources.nhatrovn.parsers.listing_parser import (
    NhatroVNListingParser,
)


from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile
from roombeacon_crawler.models.source_capabilities import SourceCapabilities


class NhatroVNSourceAdapter(BaseSourceAdapter):
    """Source Adapter cho website Nhà Trọ Việt Nam (nhatrovn.vn)."""

    SOURCE_NAME = "nhatrovn"
    DOMAINS = ("nhatrovn.vn", "www.nhatrovn.vn")
    DEFAULT_BASE_URL = "https://nhatrovn.vn/cho-thue-phong-tro/"
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
            domain="nhatrovn.vn",
            base_url=self.base_url,
            default_strategy=FetchStrategy.HTTP,
            request_delay_seconds=request_delay_seconds,
            max_concurrency=max_concurrency,
        )

        self.listing_parser = NhatroVNListingParser(source_name=self.SOURCE_NAME)
        self.detail_parser = NhatroVNDetailParser(source_name=self.SOURCE_NAME)
        self.metadata_parser = None
        self.pagination = NhatroVNPagination()
        self.date_interpreter = NhatroVNDateInterpreter()

    def classify_url(self, url: str) -> CrawlTargetType:
        """Phân loại URL mục tiêu cho website NhatroVN:

        - DETAIL_PAGE: chứa '/chi-tiet/'
        - LISTING_PAGE: root danh mục '/cho-thue-phong-tro' hoặc các sub-paths theo tỉnh thành/quận huyện/bộ lọc
        - UNSUPPORTED: các đường dẫn khác không thuộc tin phòng trọ (tin tức, liên hệ, tài khoản, v.v.)
        """
        if not url:
            return CrawlTargetType.UNSUPPORTED
        try:
            parsed = urlparse(url.strip())
            path = parsed.path.lower().rstrip("/")

            if "/chi-tiet/" in path:
                return CrawlTargetType.DETAIL_PAGE

            if path.startswith("/cho-thue-phong-tro") or path == "" or "/tim-kiem" in path:
                return CrawlTargetType.LISTING_PAGE

            return CrawlTargetType.UNSUPPORTED
        except Exception:
            return CrawlTargetType.UNSUPPORTED

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        """Cấu hình các target định kỳ mặc định cho NhatroVN."""
        return (
            CrawlSeed(
                source=self.SOURCE_NAME,
                target_id="hcm_phongtro",
                url="https://nhatrovn.vn/cho-thue-phong-tro/ho-chi-minh/",
                enabled=True,
                interval_minutes=30,
                target_type_hint=CrawlTargetType.LISTING_PAGE,
                label="nhatrovn_hcm_phongtro",
            ),
        )
