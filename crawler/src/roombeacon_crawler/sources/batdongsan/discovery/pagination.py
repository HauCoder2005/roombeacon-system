import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)


class BatDongSanPagination:
    """Cơ chế phân trang động cho BatDongSan (batdongsan.com.vn)."""

    def build_page_url(
        self,
        base_url: str = "",
        page_number: int = 1,
        *args,
        **kwargs,
    ) -> str:
        """Tạo URL phân trang theo cấu trúc /p{page_number} hoặc ?page={page_number}."""
        if isinstance(base_url, int):
            actual_page = base_url
            actual_url = str(page_number) if isinstance(page_number, str) else kwargs.get("base_url", "")
            base_url = actual_url
            page_number = actual_page

        if not base_url:
            base_url = "https://batdongsan.com.vn/cho-thue-nha-tro-phong-tro"

        parsed = urlparse(base_url)
        path = parsed.path.rstrip("/")

        # Xóa tiền tố trang cũ nếu đã có (ví dụ /p2 -> '')
        path = re.sub(r"/p\d+$", "", path)

        if page_number > 1:
            new_path = f"{path}/p{page_number}"
        else:
            new_path = path or "/"

        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params.pop("page", None)
        query_params.pop("p", None)
        encoded_query = urlencode(query_params, doseq=True)

        return urlunparse((
            parsed.scheme or "https",
            parsed.netloc or "batdongsan.com.vn",
            new_path,
            parsed.params,
            encoded_query,
            parsed.fragment,
        ))

    def has_next_page(
        self,
        current_page: int,
        max_pages: int,
        current_items_count: int,
        html: str | None = None,
        **kwargs,
    ) -> bool:
        """Kiểm tra điều kiện phân trang sang trang kế tiếp."""
        if current_page >= max_pages:
            return False

        if current_items_count == 0:
            return False

        if not html:
            return current_page < max_pages

        # Kiểm tra nút pagination nếu có HTML
        if 'class="re__pagination-icon"' in html or "re__pagination" in html:
            if "icon-chevron-right--disabled" in html or "disabled" in html and f"/p{current_page + 1}" not in html:
                return False
            return current_page < max_pages

        return current_page < max_pages
