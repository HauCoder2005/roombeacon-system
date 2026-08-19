import asyncio
import logging
import sys

from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("roombeacon_crawler")


async def main() -> None:
    """Entry point chính thức của RoomBeacon Production Crawler."""
    logger.info("=== Khởi động RoomBeacon Production Crawler ===")

    settings = CrawlerSettings()
    adapter = NhatotSourceAdapter(
        request_delay_seconds=settings.request_delay_seconds,
        max_concurrency=settings.max_concurrency,
    )

    runner = CrawlRunner(
        adapter=adapter,
        settings=settings,
    )

    records, result = await runner.run()

    logger.info(
        "=== Hoàn thành phiên crawl %s: %d records, %d trang thành công, %d trang lỗi ===",
        result.run_id,
        result.records_created,
        result.pages_success,
        result.pages_failed,
    )


if __name__ == "__main__":
    asyncio.run(main())
