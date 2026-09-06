"""Acquire JavaScript-rendered pages through a managed Playwright browser.

The fetcher owns browser lifecycle and response capture only; policy, retries and
source parsing remain outside this adapter.
"""

import logging
import time
from datetime import datetime, timezone

from roombeacon_crawler.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.models.captured_response import CapturedResponse

try:
    from playwright.async_api import (
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
except ImportError:
    async_playwright = None
    PlaywrightTimeoutError = TimeoutError

logger = logging.getLogger(__name__)


class BrowserFetcher:
    """Fetcher bất đồng bộ sử dụng Playwright Chromium để render JavaScript của các dynamic pages."""

    def __init__(
        self,
        timeout: float = 30.0,
        headless: bool = True,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport: dict | None = None,
    ) -> None:
        self.timeout = timeout
        self.headless = headless
        self.user_agent = user_agent
        self.viewport = viewport or {"width": 1280, "height": 800}
        self._playwright = None
        self._browser = None
        self._context = None
        self.launch_count = 0
        self.context_count = 0
        self.page_count = 0

    async def _get_context(self):
        """Create one browser/context lazily and reuse it for the crawl run."""
        if self._context is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            self.launch_count += 1
            self._context = await self._browser.new_context(
                user_agent=self.user_agent,
                viewport=self.viewport,
            )
            self.context_count += 1
        return self._context

    async def close(self) -> None:
        """Close the run-scoped Playwright resources without retaining state."""
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = self._browser = self._playwright = None

    async def fetch(
        self,
        url: str,
        wait_selector: str | None = None,
        wait_timeout_ms: int = 5000,
    ) -> CapturedResponse:
        """Mở browser, navigate tới URL, đợi render và trả về CapturedResponse."""
        if async_playwright is None:
            raise RuntimeError(
                "Playwright chưa được cài đặt. Vui lòng chạy:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        start_time = time.perf_counter()
        request_time = datetime.now(timezone.utc)

        try:
            context = await self._get_context()
            page = await context.new_page()
            self.page_count += 1
            try:

                response = await page.goto(
                    url,
                    timeout=int(self.timeout * 1000),
                    wait_until="domcontentloaded",
                )

                if wait_selector:
                    try:
                        await page.wait_for_selector(
                            wait_selector,
                            timeout=wait_timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        logger.warning(
                            "Hết thời gian đợi selector '%s' trên %s",
                            wait_selector,
                            url,
                        )

                html = await page.content()
                final_url = page.url
                status_code = response.status if response else 200
                headers = await response.all_headers() if response else {}

                elapsed = time.perf_counter() - start_time

                return CapturedResponse(
                    request_url=url,
                    final_url=final_url,
                    status_code=status_code,
                    html=html,
                    headers=headers,
                    fetch_strategy=FetchStrategy.BROWSER,
                    fetched_at=request_time.isoformat(),
                    elapsed_ms=elapsed * 1000.0,
                )
            finally:
                await page.close()

        except PlaywrightTimeoutError as exc:
            elapsed = time.perf_counter() - start_time
            logger.error("Browser render timed out (error_class=%s)", type(exc).__name__)
            return CapturedResponse(
                request_url=url,
                final_url=url,
                status_code=408,
                html="",
                headers={},
                fetch_strategy=FetchStrategy.BROWSER,
                fetched_at=request_time.isoformat(),
                elapsed_ms=elapsed * 1000.0,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            logger.error("Browser fetch failed (error_class=%s)", type(exc).__name__)
            return CapturedResponse(
                request_url=url,
                final_url=url,
                status_code=500,
                html="",
                headers={},
                fetch_strategy=FetchStrategy.BROWSER,
                fetched_at=request_time.isoformat(),
                elapsed_ms=elapsed * 1000.0,
            )
