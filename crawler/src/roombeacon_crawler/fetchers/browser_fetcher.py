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
        user_agent: str = "RoomBeaconCrawler/0.1",
    ) -> None:
        self.timeout = timeout
        self.headless = headless
        self.user_agent = user_agent

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

        timeout_ms = int(self.timeout * 1000)
        start_time = time.monotonic()
        fetched_at = datetime.now(timezone.utc).isoformat()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                page = await browser.new_page(user_agent=self.user_agent)
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )

                if wait_selector:
                    try:
                        await page.wait_for_selector(
                            wait_selector,
                            timeout=wait_timeout_ms,
                        )
                    except Exception as exc:
                        logger.debug(
                            "Hết thời gian chờ selector %s trên %s: %s",
                            wait_selector,
                            url,
                            exc,
                        )

                html = await page.content()
                final_url = page.url
                status_code = response.status if response else 200
                headers = await response.all_headers() if response else {}
                elapsed_ms = (time.monotonic() - start_time) * 1000.0
            finally:
                await browser.close()

        return CapturedResponse(
            request_url=url,
            final_url=final_url,
            status_code=status_code,
            html=html,
            headers=headers,
            fetch_strategy=FetchStrategy.BROWSER,
            fetched_at=fetched_at,
            elapsed_ms=elapsed_ms,
        )
