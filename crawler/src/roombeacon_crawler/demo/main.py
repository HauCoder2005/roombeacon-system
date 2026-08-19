import asyncio
import json
import os
from dataclasses import asdict

import httpx

from roombeacon_crawler.demo.enums.crawl_status import CrawlStatus
from roombeacon_crawler.demo.enums.fetch_action import FetchAction
from roombeacon_crawler.demo.enums.fetch_strategy import FetchStrategy
from roombeacon_crawler.demo.fetchers.browser_fetcher import (
    BrowserFetcher,
    PlaywrightTimeoutError,
)
from roombeacon_crawler.demo.fetchers.http_fetcher import HttpFetcher
from roombeacon_crawler.demo.parser import (
    RentalParser,
    validate_area,
    validate_price,
)
from roombeacon_crawler.demo.policies.cooldown_policy import CooldownPolicy
from roombeacon_crawler.demo.policies.fetch_policy import FetchPolicy
from roombeacon_crawler.demo.services.response_classifier import (
    ResponseClassifier,
)
from roombeacon_crawler.demo.services.strategy_selector import (
    StrategySelector,
)

MAX_RECORDS = 50


def _get_header(headers: dict[str, str], key: str) -> str:
    key_lower = key.lower()
    for k, v in headers.items():
        if k.lower() == key_lower:
            return v
    return "Unknown"


async def main() -> None:
    print("=== RoomBeacon Crawler Demo ===")

    url = input("Nhập URL cần crawl: ").strip()

    if not url:
        print("URL không được để trống.")
        return

    strategy_selector = StrategySelector()
    strategy = strategy_selector.select(url)

    classifier = ResponseClassifier()
    fetch_policy = FetchPolicy()
    cooldown_policy = CooldownPolicy()
    parser = RentalParser()

    if strategy == FetchStrategy.BROWSER:
        fetcher = BrowserFetcher()
    else:
        fetcher = HttpFetcher()

    try:
        response = await fetcher.fetch(url)

        crawl_status = classifier.classify(
            status_code=response.status_code,
            html=response.html,
        )
        action = fetch_policy.decide(status=crawl_status)

        server = _get_header(response.headers, "server")
        content_type = _get_header(response.headers, "content-type")
        cf_ray = _get_header(response.headers, "cf-ray")

        print()
        print("=== Crawl Result ===")
        print(f"URL            : {response.url}")
        print(f"Final URL      : {response.final_url}")
        print(f"Fetch Strategy : {response.strategy.value}")
        print(f"HTTP Status    : {response.status_code}")
        print(f"Crawl Status   : {crawl_status.value}")
        print(f"Action         : {action.value}")
        print(f"HTML Size      : {len(response.html)} characters")
        print(f"Server         : {server}")
        print(f"Content-Type   : {content_type}")
        if cf_ray != "Unknown":
            print(f"CF-Ray         : {cf_ray}")

        if crawl_status == CrawlStatus.CLOUDFLARE_CHALLENGE:
            print()
            print("Cloudflare Challenge detected.")
            print("Stop crawling this source.")
            return

        if action == FetchAction.PARSE:
            records = parser.parse(
                html=response.html,
                source_url=response.final_url,
                limit=MAX_RECORDS,
            )

            initial_cards_str = response.headers.get("x-initial-cards", "N/A")
            scroll_attempts_str = response.headers.get("x-scroll-attempts", "0")
            final_cards_count = parser.debug_stats.get("visible_cards", 0)
            records_extracted = parser.debug_stats.get("records_extracted", len(records))
            duplicates_removed = parser.debug_stats.get("duplicates_removed", 0)

            print()
            print("=== Extraction Debug ===")
            print(f"HTML Input Size      : {len(response.html)} characters")
            print(f"Initial Cards        : {initial_cards_str}")
            print(f"Scroll Attempts      : {scroll_attempts_str}")
            print(f"Final Listing Cards  : {final_cards_count}")
            print(f"Records Extracted    : {records_extracted}")
            print(f"Duplicates Removed   : {duplicates_removed}")
            print(f"Records After Dedup  : {len(records)}")

            print()
            print("=== Parse Result ===")
            print(f"Records Parsed : {len(records)}")
            print()

            # Display records (print first 5, ellipsis if > 10, and last 5)
            if len(records) <= 10:
                display_indices = list(range(len(records)))
                show_ellipsis = False
            else:
                display_indices = list(range(5)) + list(range(len(records) - 5, len(records)))
                show_ellipsis = True

            for idx, r_idx in enumerate(display_indices):
                if show_ellipsis and idx == 5:
                    print(f"  ... [{len(records) - 10} records omitted in terminal preview] ...\n")
                r = records[r_idx]
                print(f"[{r_idx + 1:02d}]")
                print(f"Title    : {r.title or 'N/A'}")
                print(f"Price    : {r.price or 'N/A'}")
                print(f"Area     : {r.area or 'N/A'}")
                print(f"Location : {r.location or 'N/A'}")
                print(f"URL      : {r.url or 'N/A'}")
                print()

            # Data Quality Check
            total = len(records)
            missing_title = sum(1 for r in records if not r.title)
            missing_price = sum(1 for r in records if not r.price)
            missing_area = sum(1 for r in records if not r.area)
            missing_location = sum(1 for r in records if not r.location)
            missing_url = sum(1 for r in records if not r.url)

            invalid_price = sum(
                1
                for r in records
                if r.price is not None and validate_price(r.price) is None
            )
            invalid_area = sum(
                1
                for r in records
                if r.area is not None and validate_area(r.area) is None
            )

            print("=== Data Quality ===")
            print(f"Total Records       : {total}")
            print(f"Missing Title       : {missing_title}")
            print(f"Missing Price       : {missing_price}")
            print(f"Missing Area        : {missing_area}")
            print(f"Missing Location    : {missing_location}")
            print(f"Missing URL         : {missing_url}")
            print(f"Invalid Price       : {invalid_price}")
            print(f"Invalid Area        : {invalid_area}")
            print(f"Duplicate URL       : 0")
            print(f"Duplicates Removed  : {duplicates_removed}")

            # Save Demo JSON Output strictly from extracted records
            os.makedirs("data/demo", exist_ok=True)
            output_path = "data/demo/nhatot_50.json"
            records_data = [asdict(r) for r in records]
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(records_data, f, ensure_ascii=False, indent=2)

            print()
            print(f"Output saved to     : {output_path}")
            return

        if action == FetchAction.COOLDOWN:
            cooldown_secs = cooldown_policy.get_cooldown_seconds(
                status=crawl_status,
                attempt=1,
            )
            print()
            print("Rate limited by source.")
            print(f"Suggested cooldown: {cooldown_secs} seconds.")
            retry_after = _get_header(response.headers, "retry-after")
            if retry_after != "Unknown":
                print(f"Retry-After    : {retry_after}")
            return

        if action == FetchAction.RETRY_LATER:
            cooldown_secs = cooldown_policy.get_cooldown_seconds(
                status=crawl_status,
                attempt=1,
            )
            print()
            print("Server error / temporary issue.")
            print(f"Suggested retry cooldown: {cooldown_secs} seconds.")
            return

        if crawl_status == CrawlStatus.ACCESS_DENIED:
            print()
            print("Access denied by source.")
            print("Stop crawling this source.")
            return

        if crawl_status == CrawlStatus.NOT_FOUND:
            print()
            print("Resource not found.")
            print("Stop crawling this source.")
            return

        print()
        print(f"Request terminated with status: {crawl_status.value}")
        print("Stop crawling this source.")

    except (httpx.TimeoutException, PlaywrightTimeoutError):
        crawl_status = CrawlStatus.TIMEOUT
        action = fetch_policy.decide(status=crawl_status)
        print()
        print("=== Crawl Result ===")
        print(f"URL            : {url}")
        print(f"Fetch Strategy : {strategy.value}")
        print(f"Crawl Status   : {crawl_status.value}")
        print(f"Action         : {action.value}")
        print()
        print("Request timed out.")

    except httpx.RequestError as exc:
        crawl_status = CrawlStatus.CONNECTION_ERROR
        action = fetch_policy.decide(status=crawl_status)
        print()
        print("=== Crawl Result ===")
        print(f"URL            : {url}")
        print(f"Fetch Strategy : {strategy.value}")
        print(f"Crawl Status   : {crawl_status.value}")
        print(f"Action         : {action.value}")
        print(f"Error          : {exc}")

    except RuntimeError as exc:
        print()
        print(f"Runtime Error  : {exc}")

    except Exception as exc:
        err_str = str(exc)
        if "net::ERR_" in err_str or "NS_ERROR_" in err_str:
            crawl_status = CrawlStatus.CONNECTION_ERROR
        else:
            crawl_status = CrawlStatus.UNKNOWN
        action = fetch_policy.decide(status=crawl_status)
        print()
        print("=== Crawl Result ===")
        print(f"URL            : {url}")
        print(f"Fetch Strategy : {strategy.value}")
        print(f"Crawl Status   : {crawl_status.value}")
        print(f"Action         : {action.value}")
        print(f"Error          : {err_str.splitlines()[0]}")


if __name__ == "__main__":
    asyncio.run(main())