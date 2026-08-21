from dataclasses import dataclass, field
from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.enums.source_access_profile import SourceAccessProfile


@dataclass(frozen=True, slots=True)
class SourceCapabilities:
    """Mô hình khai báo năng lực của nguồn dữ liệu (Source Capabilities).

    Cho phép hệ thống phân giải chiến lược xử lý theo năng lực (Capability-Driven Architecture)
    mà không cần bất kỳ câu lệnh hardcoded `if source == ...` nào trong Core Engine.
    """

    access_profile: SourceAccessProfile = SourceAccessProfile.STANDARD_PAGINATION
    supports_pagination: bool = True
    supports_sitemap_discovery: bool = False
    historical_backfill_supported: bool = True
    forward_incremental_supported: bool = True
    seed_page_discovery_supported: bool = True
    preferred_seed_transport: FetchStrategy = FetchStrategy.HTTP
    preferred_discovery_transport: FetchStrategy = FetchStrategy.HTTP
    preferred_fetch_strategy: FetchStrategy = FetchStrategy.HTTP
    robots_required: bool = True
    detail_fetch_supported: bool = True
    custom_flags: dict[str, bool] = field(default_factory=dict)

    @property
    def preferred_content_transport(self) -> FetchStrategy:
        """Alias biểu thị chiến lược vận chuyển nội dung (Content Transport)."""
        return self.preferred_fetch_strategy
