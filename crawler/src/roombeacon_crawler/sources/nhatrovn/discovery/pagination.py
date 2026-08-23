import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from roombeacon_crawler.sources.nhatrovn.dom import DOMTreeBuilder

logger = logging.getLogger(__name__)


class NhatroVNPagination:
    """Cơ chế phân trang động cho website NhatroVN, bảo toàn nguyên vẹn URL và bộ lọc của người dùng."""

    def build_page_url(
        self,
        base_url: str = "",
        page_number: int = 1,
        *args,
        **kwargs,
    ) -> str:
        """Tạo URL cho trang thứ page_number dựa trên URL hiện tại và bảo toàn query params.

        Hỗ trợ gọi theo cả hai dạng:
        - build_page_url(base_url, page_number)
        - build_page_url(page_number, base_url)
        - build_page_url(base_url=..., page_number=...)
        """
        if isinstance(base_url, int):
            actual_page = base_url
            actual_url = str(page_number) if isinstance(page_number, str) else kwargs.get("base_url", "")
            base_url = actual_url
            page_number = actual_page

        if not base_url:
            base_url = "https://nhatrovn.vn/cho-thue-phong-tro/"

        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        if page_number > 1:
            query_params["page"] = [str(page_number)]
        else:
            query_params.pop("page", None)

        encoded_query = urlencode(query_params, doseq=True)
        return urlunparse((
            parsed.scheme or "https",
            parsed.netloc or "nhatrovn.vn",
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
        raw_html: str | None = None,
        **kwargs,
    ) -> bool:
        """Xác định xem trang hiện tại có trang tiếp theo không."""
        # 1. Giới hạn nghiệp vụ cấu hình
        if current_page >= max_pages:
            return False

        # 2. Trang hiện tại rỗng (0 items) -> Không còn trang tiếp
        if current_items_count == 0:
            return False

        # 3. Không có HTML -> mặc định tiếp tục nếu chưa đạt max_pages
        effective_html = html if html is not None else (raw_html or kwargs.get("raw_html"))
        if not effective_html:
            return current_page < max_pages

        try:
            root = DOMTreeBuilder.parse(effective_html)

            # 4. Trích xuất thông tin Trang X / Y từ text: e.g. "(Trang 1 / 42)" hoặc "Trang 5/42"
            text_nodes = root.find_all(
                predicate=lambda n: "Trang" in n.get_text() and "/" in n.get_text()
            )
            for elem in text_nodes:
                text = elem.get_text()
                match = re.search(r"Trang\s*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE)
                if match:
                    total_pages = int(match.group(2))
                    logger.debug("Phát hiện tổng số trang của nguồn: %d (Trang hiện tại: %d)", total_pages, current_page)
                    return current_page < total_pages

            # 5. Kiểm tra sự tồn tại của nút Next Arrow không có class disabled
            next_arrows = root.find_all(
                tag="a",
                class_contains="pagination-arrow",
                predicate=lambda n: "disabled" not in n.get("class"),
            )
            for arrow in next_arrows:
                text = arrow.get_text()
                if ">" in text or "gt;" in text or "next" in text.lower() or "chevron_right" in text:
                    return True

            # 6. Kiểm tra số trang lớn nhất tìm thấy trong các pagination buttons
            page_buttons = root.find_all(class_contains="pagination-btn")
            max_seen_page = current_page
            for btn in page_buttons:
                text = btn.get_text().strip()
                if text.isdigit():
                    max_seen_page = max(max_seen_page, int(text))

            if max_seen_page > current_page:
                return True
        except Exception as exc:
            logger.warning("Lỗi phân tích pagination HTML trên trang %d: %s. Cho phép tiếp tục nếu chưa đạt max_pages.", current_page, exc)

        # 7. Nếu có items và không có chỉ dấu hết trang -> cho phép tiếp tục
        return current_page < max_pages
