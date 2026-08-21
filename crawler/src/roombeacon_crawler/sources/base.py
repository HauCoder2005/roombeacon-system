from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from roombeacon_crawler.config.source_settings import SourceSettings
from roombeacon_crawler.enums.crawl_target_type import CrawlTargetType
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.crawl_seed import CrawlSeed


@runtime_checkable
class SourcePagination(Protocol):
    """Protocol chuẩn hóa cho tất cả các triển khai phân trang của các Source Adapter."""

    def build_page_url(
        self,
        base_url: str = "",
        page_number: int = 1,
        *args,
        **kwargs,
    ) -> str:
        """Tạo URL cho trang thứ page_number dựa trên URL danh mục gốc."""
        ...

    def has_next_page(
        self,
        current_page: int,
        max_pages: int,
        current_items_count: int,
        html: str | None = None,
        **kwargs,
    ) -> bool:
        """Kiểm tra xem trang hiện tại có trang kế tiếp hay không."""
        ...


@dataclass(frozen=True)
class SourceMetadata:
    """Metadata cấu hình bất biến của một Source Adapter."""

    source_name: str
    display_name: str
    domains: tuple[str, ...]
    default_strategy: FetchStrategy = FetchStrategy.HTTP
    default_base_url: str = ""
    capabilities: dict[str, bool] = field(default_factory=dict)


from roombeacon_crawler.models.source_capabilities import SourceCapabilities


class BaseSourceAdapter(ABC):
    """Lớp cơ sở trừu tượng (Base Contract) cho tất cả Source Adapters trong RoomBeacon.

    Mỗi adapter đại diện cho một website nguồn độc lập (ví dụ: NhaTot, NhatroVN, Phongtro123, BatDongSan, Muaban).
    """

    SOURCE_NAME: str = ""
    DOMAINS: tuple[str, ...] = ()
    DEFAULT_BASE_URL: str = ""
    CAPABILITIES: SourceCapabilities = SourceCapabilities()

    def __init__(
        self,
        base_url: str | None = None,
        request_delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> None:
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.request_delay_seconds = request_delay_seconds
        self.max_concurrency = max_concurrency

        # Các thuộc tính nghiệp vụ bắt buộc phải được khởi tạo trong lớp con
        self.settings: SourceSettings
        self.listing_parser: Any
        self.detail_parser: Any
        self.metadata_parser: Any
        self.pagination: SourcePagination
        self.date_interpreter: Any

    @classmethod
    def supports(cls, url: str) -> bool:
        """Kiểm tra xem URL có thuộc danh sách domains do Adapter này xử lý hay không."""
        if not url:
            return False
        try:
            parsed = urlparse(url.strip())
            hostname = (parsed.hostname or "").lower()
            for domain in cls.DOMAINS:
                d = domain.lower()
                if hostname == d or hostname.endswith("." + d):
                    return True
        except Exception:
            return False
        return False

    def classify_url(self, url: str) -> CrawlTargetType:
        """Phân loại loại hình URL mục tiêu (LISTING_PAGE, DETAIL_PAGE, hoặc UNSUPPORTED).

        Mặc định trả về LISTING_PAGE nếu thuộc domain hỗ trợ. Lớp con có thể ghi đè.
        """
        if not url:
            return CrawlTargetType.UNSUPPORTED
        return CrawlTargetType.LISTING_PAGE

    def scheduled_targets(self) -> tuple[CrawlSeed, ...]:
        """Trả về danh sách các điểm vào (crawl seeds) định kỳ mặc định của nguồn này.

        Lớp con có thể ghi đè để cấu hình các URL danh mục mặc định cho lịch chạy tự động.
        """
        if self.DEFAULT_BASE_URL:
            return (
                CrawlSeed(
                    source=self.SOURCE_NAME,
                    url=self.DEFAULT_BASE_URL,
                    enabled=True,
                    target_type_hint=CrawlTargetType.LISTING_PAGE,
                    label=f"{self.SOURCE_NAME}_default",
                ),
            )
        return ()
