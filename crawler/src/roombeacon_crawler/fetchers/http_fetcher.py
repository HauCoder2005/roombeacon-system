import logging
import time
from datetime import datetime, timezone

import httpx

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.captured_response import CapturedResponse

logger = logging.getLogger(__name__)


class HttpFetcher:
    """Fetcher bất đồng bộ sử dụng HTTPX để thu thập response từ các nguồn HTTP tiêu chuẩn."""

    def __init__(
        self,
        timeout: float = 30.0,
        timeout_seconds: float | None = None,
        user_agent: str = "RoomBeaconCrawler/0.1",
        follow_redirects: bool = True,
    ) -> None:
        self.timeout = timeout_seconds if timeout_seconds is not None else timeout
        self.user_agent = user_agent
        self.follow_redirects = follow_redirects

    async def fetch(self, url: str) -> CapturedResponse:
        """Gửi HTTP GET request và capture response thành đối tượng CapturedResponse."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        start_time = time.perf_counter()
        request_time = datetime.now(timezone.utc)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
            verify=True,
        ) as client:
            response = await client.get(url, headers=headers)
            elapsed = time.perf_counter() - start_time

            return CapturedResponse(
                request_url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                html=response.text,
                headers=dict(response.headers),
                fetch_strategy=FetchStrategy.HTTP,
                fetched_at=request_time.isoformat(),
                elapsed_ms=elapsed * 1000.0,
            )
