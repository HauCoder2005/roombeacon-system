from abc import ABC, abstractmethod
from typing import Any
from roombeacon_crawler.models.captured_response import CapturedResponse
from roombeacon_crawler.models.crawl_target import CrawlTarget


class FetchPort(ABC):
    """Port giao tiếp trừu tượng cho các bộ thu thập HTTP qua mạng."""

    @abstractmethod
    async def fetch(
        self,
        target: CrawlTarget,
        run_id: str,
        max_retries: int = 2,
    ) -> CapturedResponse:
        """Thực hiện yêu cầu HTTP và trả về CapturedResponse."""
        pass


class BrowserFetchPort(ABC):
    """Port giao tiếp trừu tượng cho các bộ thu thập render trình duyệt (Headless Browser)."""

    @abstractmethod
    async def fetch(
        self,
        target: CrawlTarget,
        run_id: str,
        max_retries: int = 2,
    ) -> CapturedResponse:
        """Thực hiện điều hướng trình duyệt và trả về CapturedResponse."""
        pass
