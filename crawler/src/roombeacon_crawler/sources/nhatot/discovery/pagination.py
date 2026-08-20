from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


class NhatotPagination:
    """Xử lý cấu trúc phân trang thực tế của website Nhà Tốt (tham số ?page=N)."""

    @staticmethod
    def build_page_url(
        base_url: str = "",
        page_number: int = 1,
        *args,
        **kwargs,
    ) -> str:
        """Tạo URL hoàn chỉnh cho trang thứ N."""
        if isinstance(base_url, int):
            actual_page = base_url
            actual_url = str(page_number) if isinstance(page_number, str) else kwargs.get("base_url", "")
            base_url = actual_url
            page_number = actual_page

        if page_number <= 1:
            return base_url

        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params["page"] = [str(page_number)]
        new_query = urlencode(query_params, doseq=True)

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            )
        )

    @staticmethod
    def extract_page_number(url: str) -> int:
        """Trích xuất số trang hiện tại từ query params của URL."""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        pages = query_params.get("page")
        if pages and pages[0].isdigit():
            return int(pages[0])
        return 1

    @staticmethod
    def has_next_page(
        current_page: int,
        max_pages: int,
        current_items_count: int,
        min_items_threshold: int = 1,
        **kwargs,
    ) -> bool:
        """Xác định có nên tiếp tục chuyển sang trang kế tiếp hay không."""
        if current_page >= max_pages:
            return False
        if current_items_count < min_items_threshold:
            return False
        return True
