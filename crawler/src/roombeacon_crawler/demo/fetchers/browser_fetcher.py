import os

from roombeacon_crawler.demo.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.demo.models.captured_response import CapturedResponse

try:
    from playwright.async_api import (
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
except ImportError:
    async_playwright = None
    PlaywrightTimeoutError = TimeoutError

MAIN_CONTAINER_SELECTOR = (
    "div[class*='ListAds_ListAds'], div[class*='ListAds_wrapper'], "
    "div[class*='ListAds'], div[class*='list-view'], div[data-testid='list-ads']"
)

LISTING_CARD_SELECTOR = (
    "div[class*='AdItem_adItemWrapper'], li[class*='AdItem_adItemWrapper'], "
    "div[class*='AdItem_wrapper'], div[data-testid='ad-item']"
)


class BrowserFetcher:
    def __init__(
        self,
        timeout: float = 30.0,
        headless: bool = False,
        max_scroll_attempts: int = 10,
    ) -> None:
        self.timeout = timeout
        self.headless = headless
        self.max_scroll_attempts = max_scroll_attempts

    async def fetch(self, url: str) -> CapturedResponse:
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Please run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        timeout_ms = int(self.timeout * 1000)
        initial_cards = 0
        scroll_attempts_done = 0
        final_cards = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            try:
                page = await browser.new_page()
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )

                # Wait 3 seconds for initial JavaScript to settle
                await page.wait_for_timeout(3000)

                # Locate main listing container and card locator
                container = page.locator(MAIN_CONTAINER_SELECTOR).first
                if await container.count() > 0:
                    cards_locator = container.locator(LISTING_CARD_SELECTOR)
                else:
                    cards_locator = page.locator(LISTING_CARD_SELECTOR)

                initial_cards = await cards_locator.count()
                current_count = initial_cards

                # Controlled scroll to reach up to 50 listing cards
                no_growth_streak = 0
                for _ in range(self.max_scroll_attempts):
                    if current_count >= 50:
                        break

                    try:
                        if current_count > 0:
                            last_card = cards_locator.nth(current_count - 1)
                            await last_card.scroll_into_view_if_needed()
                        await page.evaluate(
                            "window.scrollBy(0, window.innerHeight * 1.5)"
                        )
                    except Exception:
                        await page.evaluate(
                            "window.scrollBy(0, window.innerHeight * 1.5)"
                        )

                    scroll_attempts_done += 1
                    await page.wait_for_timeout(1200)

                    new_count = await cards_locator.count()
                    if new_count > current_count:
                        no_growth_streak = 0
                        current_count = new_count
                    else:
                        no_growth_streak += 1
                        if no_growth_streak >= 2:
                            break

                final_cards = current_count

                # Capture full screenshot after loading completes
                os.makedirs("data/demo", exist_ok=True)
                try:
                    await page.screenshot(
                        path="data/demo/debug_listing_page.png",
                        full_page=True,
                    )
                except Exception:
                    pass

                html = await page.content()
                final_url = page.url
                status_code = response.status if response else 200
                headers = await response.all_headers() if response else {}

                # Save raw captured HTML for debugging
                try:
                    with open("data/demo/debug_nhatot.html", "w", encoding="utf-8") as f:
                        f.write(html)
                except Exception:
                    pass

            finally:
                await browser.close()

        # Attach scroll metadata to headers
        headers["x-initial-cards"] = str(initial_cards)
        headers["x-scroll-attempts"] = str(scroll_attempts_done)
        headers["x-final-cards"] = str(final_cards)

        return CapturedResponse(
            url=url,
            final_url=final_url,
            status_code=status_code,
            html=html,
            headers=headers,
            strategy=FetchStrategy.BROWSER,
        )
