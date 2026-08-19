import httpx

from roombeacon_crawler.demo.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.demo.models.captured_response import CapturedResponse


class HttpFetcher:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def fetch(self, url: str) -> CapturedResponse:
        headers = {
            "User-Agent": "RoomBeaconCrawler/0.1",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)

        return CapturedResponse(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            html=response.text,
            headers=dict(response.headers),
            strategy=FetchStrategy.HTTP,
        )
