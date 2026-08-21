from dataclasses import dataclass
import gzip
import logging
from typing import ClassVar

import httpx

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.policies.robots_policy import RobotsPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SitemapFetchResponse:
    """Kết quả phản hồi kỹ thuật khi tải tài liệu Sitemap."""

    url: str
    status_code: int
    content: str | None
    is_success: bool
    error: str | None = None


class SitemapFetcher:
    """HTTP/Browser Client chuyên trách tải nội dung tài liệu Sitemap XML/Gzip qua mạng."""

    DEFAULT_USER_AGENT: ClassVar[str] = "RoomBeaconCrawler/0.1"
    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 20.0

    def __init__(
        self,
        user_agent: str | None = None,
        timeout_seconds: float | None = None,
        robots_policy: RobotsPolicy | None = None,
    ) -> None:
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS
        self.robots_policy = robots_policy or RobotsPolicy()

    async def fetch(
        self,
        url: str,
        transport: FetchStrategy = FetchStrategy.HTTP,
    ) -> SitemapFetchResponse:
        """Tải tài liệu Sitemap từ URL sử dụng chiến lược transport được chỉ định."""
        if not url:
            return SitemapFetchResponse(
                url="",
                status_code=400,
                content=None,
                is_success=False,
                error="URL rỗng",
            )

        # Kiểm tra Robots Policy
        decision, robots_url = self.robots_policy.evaluate(url)
        if decision == "DENIED":
            logger.warning("SitemapFetcher: URL bị từ chối bởi robots.txt: %s", url)
            return SitemapFetchResponse(
                url=url,
                status_code=403,
                content=None,
                is_success=False,
                error=f"Robots policy denied ({robots_url})",
            )

        if transport == FetchStrategy.BROWSER:
            try:
                from roombeacon_crawler.fetchers.browser_fetcher import BrowserFetcher
                bf = BrowserFetcher(user_agent=self.user_agent, timeout=self.timeout)
                res = await bf.fetch(url)
                return SitemapFetchResponse(
                    url=url,
                    status_code=res.status_code,
                    content=res.html,
                    is_success=(res.status_code == 200 and bool(res.html)),
                    error=res.error,
                )
            except Exception as exc:
                logger.warning("SitemapFetcher: Lỗi tải sitemap qua Browser %s: %s", url, exc)
                return SitemapFetchResponse(
                    url=url,
                    status_code=500,
                    content=None,
                    is_success=False,
                    error=str(exc),
                )

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/xml, text/xml, application/x-gzip, */*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.warning("SitemapFetcher: Lỗi HTTP %d từ %s", response.status_code, url)
                    return SitemapFetchResponse(
                        url=url,
                        status_code=response.status_code,
                        content=None,
                        is_success=False,
                        error=f"HTTP {response.status_code}",
                    )

                content_bytes = response.content
                if url.endswith(".gz") or content_bytes[:2] == b"\x1f\x8b":
                    try:
                        content_bytes = gzip.decompress(content_bytes)
                    except Exception as gz_err:
                        logger.warning("SitemapFetcher: Lỗi giải nén gzip từ %s: %s", url, gz_err)

                content_str = content_bytes.decode("utf-8", errors="replace")
                return SitemapFetchResponse(
                    url=url,
                    status_code=200,
                    content=content_str,
                    is_success=True,
                )

        except httpx.RequestError as exc:
            logger.warning("SitemapFetcher: Lỗi kết nối khi tải %s: %s", url, exc)
            return SitemapFetchResponse(
                url=url,
                status_code=0,
                content=None,
                is_success=False,
                error=str(exc),
            )
        except Exception as exc:
            logger.exception("SitemapFetcher: Ngoại lệ bất ngờ khi tải %s: %s", url, exc)
            return SitemapFetchResponse(
                url=url,
                status_code=500,
                content=None,
                is_success=False,
                error=str(exc),
            )

    async def fetch_sitemap_content(self, url: str) -> str | None:
        """Hàm trợ giúp tương thích trả về chuỗi nội dung XML trực tiếp."""
        resp = await self.fetch(url)
        return resp.content if resp.is_success else None
