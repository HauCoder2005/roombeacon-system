from abc import ABC, abstractmethod
from typing import ClassVar


class SourceDiscoveryAdapter(ABC):
    """Hợp đồng trừu tượng (Interface) cho bộ khám phá URL nguồn lớn (Discovery Adapter).

    Trách nhiệm:
    - Cung cấp danh sách sitemap entrypoints hoặc URL feeds của nguồn.
    - Lọc URL ứng viên (Candidate URL filtering) theo phạm vi cho thuê phòng trọ / nhà trọ.
    - Gợi ý phân loại sơ bộ (Target hint) nếu nhận diện được qua URL pattern.
    - TUYỆT ĐỐI KHÔNG: parse nội dung HTML, trích xuất field tin đăng, sinh ListingCardRaw, hay ghi Bronze dataset.
    """

    SOURCE_NAME: ClassVar[str] = ""
    supports_lastmod: bool = True

    def supports_source(self, source_name: str) -> bool:
        """Kiểm tra adapter có hỗ trợ nguồn tương ứng hay không."""
        return source_name.lower().strip() == self.SOURCE_NAME.lower().strip()

    @abstractmethod
    def discover_entrypoints(self) -> list[str]:
        """Trả về danh sách URL Sitemap hoặc Sitemap Index khởi tạo của nguồn."""
        raise NotImplementedError

    @abstractmethod
    def filter_candidate_url(self, url: str) -> bool:
        """Kiểm tra xem URL ứng viên có thuộc phạm vi dữ liệu cho thuê phòng/nhà trọ cần thu thập hay không.

        Quyết định cuối cùng về việc parse/hợp lệ vẫn thuộc về SourceAdapter.classify_url().
        """
        raise NotImplementedError

    def classify_candidate_hint(self, url: str) -> str | None:
        """Gợi ý phân loại sơ bộ dạng trang (LISTING_PAGE, DETAIL_PAGE) từ URL pattern nếu có."""
        return None


# Alias tương thích kiến trúc
BaseDiscoveryAdapter = SourceDiscoveryAdapter
LargeSourceDiscoveryAdapter = SourceDiscoveryAdapter
