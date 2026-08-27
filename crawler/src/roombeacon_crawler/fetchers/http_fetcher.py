"""Perform asynchronous HTTP acquisition and return normalized responses.

Classification, retries, rate limiting and parser selection are coordinated by
higher-level services.
"""

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
        self._client: httpx.AsyncClient | None = None
        self.client_count = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the run-scoped keep-alive client, creating it lazily."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                verify=True,
            )
            self.client_count += 1
        return self._client

    async def close(self) -> None:
        """Close the reusable client at the crawl-run boundary."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def fetch(self, url: str) -> CapturedResponse:
        """Gửi HTTP GET request và capture response thành đối tượng CapturedResponse."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        start_time = time.perf_counter()
        request_time = datetime.now(timezone.utc)

        client = await self._get_client()
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
