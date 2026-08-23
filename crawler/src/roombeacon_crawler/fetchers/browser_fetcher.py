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
        viewport: dict | None = None,
    ) -> None:
        self.timeout = timeout
        self.headless = headless
        self.user_agent = user_agent
        self.viewport = viewport or {"width": 1280, "height": 800}

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
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    user_agent=self.user_agent,
                    viewport=self.viewport,
                )
                page = await context.new_page()

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

                await browser.close()
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

        except PlaywrightTimeoutError as exc:
            elapsed = time.perf_counter() - start_time
            logger.error("Timeout khi render URL bằng Browser: %s", exc)
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
            logger.error("Lỗi ngoại lệ khi fetch qua Browser: %s", exc)
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
