from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


class Phongtro123Pagination:
    """Xử lý phân trang cho nguồn Phongtro123."""

    def build_page_url(
        self,
        base_url: str = "",
        page_number: int = 1,
        *args,
        **kwargs,
    ) -> str:
        """Tạo URL cho trang thứ N."""
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

        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        ))

    def has_next_page(
        self,
        current_page: int,
        max_pages: int,
        current_items_count: int,
        **kwargs,
    ) -> bool:
        """Xác định có nên tiếp tục sang trang tiếp theo hay không."""
        if current_page >= max_pages:
            return False
        if current_items_count == 0:
            return False
        return True
