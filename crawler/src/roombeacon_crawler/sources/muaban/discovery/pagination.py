import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)


class MuabanPagination:
    """Cơ chế phân trang động cho Muaban (muaban.net)."""

    def build_page_url(
        self,
        base_url: str = "",
        page_number: int = 1,
        *args,
        **kwargs,
    ) -> str:
        """Tạo URL phân trang theo cấu trúc query param ?page={page_number}."""
        if isinstance(base_url, int):
            actual_page = base_url
            actual_url = str(page_number) if isinstance(page_number, str) else kwargs.get("base_url", "")
            base_url = actual_url
            page_number = actual_page

        if not base_url:
            base_url = "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro"

        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        if page_number > 1:
            query_params["page"] = [str(page_number)]
        else:
            query_params.pop("page", None)

        encoded_query = urlencode(query_params, doseq=True)
        return urlunparse((
            parsed.scheme or "https",
            parsed.netloc or "muaban.net",
            parsed.path,
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

        # Kiểm tra nếu HTML có pagination indicators
        return current_page < max_pages
