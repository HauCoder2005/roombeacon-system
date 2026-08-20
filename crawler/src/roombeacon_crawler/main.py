import argparse
import asyncio
import logging
import sys

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.sources.resolver import SourceResolver
from roombeacon_crawler.validators.url_validator import URLValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("roombeacon_crawler")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="roombeacon-crawler",
        description="RoomBeacon Local Diagnostics & Debug CLI.\n"
                    "LƯU Ý: Airflow UI là entry point chính để trigger production crawl runs.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Đường dẫn URL mục tiêu cần crawl",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Số trang listing tối đa cần duyệt",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Số lượng record tối đa cần thu thập",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Chỉ trích xuất listing cards, không crawl detail pages",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Kiểm tra cấu hình môi trường và tính khả dụng của crawler dependencies",
    )
    return parser.parse_args()


def run_diagnostics() -> None:
    """Kiểm tra và in thông tin chẩn đoán hệ thống."""
    supported = ", ".join(SourceResolver.get_supported_sources())
    print("=" * 60)
    print("ROOMBEACON CRAWLER DIAGNOSTICS")
    print("=" * 60)
    print(f"Environment:          {env.project.environment}")
    print(f"User Agent:           {env.crawler.user_agent}")
    print(f"Playwright Headless:  {env.crawler.playwright_headless}")
    print(f"Request Timeout:      {env.crawler.request_timeout_seconds}s")
    print(f"Request Delay:        {env.crawler.request_delay_seconds}s")
    print(f"Max Concurrency:      {env.crawler.max_concurrency}")
    print(f"Max Retries:          {env.crawler.max_retries}")
    print(f"Supported Sources:    {supported}")
    print(f"Primary Entry Point:  Airflow UI (DAG: roombeacon_crawler)")
    print("=" * 60)


async def main_async(args: argparse.Namespace) -> None:
    if args.diagnostics:
        run_diagnostics()
        return

    logger.info("=== Khởi chạy RoomBeacon Crawler CLI (Local / Debug Mode) ===")
    logger.info("Lưu ý: Để trigger production crawl, vui lòng sử dụng Airflow UI.")

    settings = CrawlerSettings()

    target_url = args.url
    if target_url:
        is_valid, err = URLValidator.validate(target_url)
        if not is_valid:
            logger.error("URL đầu vào không an toàn hoặc không hợp lệ: %s", err)
            sys.exit(1)

        runner = CrawlRunner(
            target_url=target_url,
            settings=settings,
        )
    else:
        runner = CrawlRunner(
            settings=settings,
        )

    records, result = await runner.run(
        max_pages=args.max_pages,
        max_records=args.max_records,
        crawl_details=not args.no_details,
    )

    logger.info(
        "=== Hoàn thành phiên crawl %s: %d records, %d trang thành công, %d trang lỗi ===",
        result.run_id,
        result.records_created,
        result.pages_success,
        result.pages_failed,
    )


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
