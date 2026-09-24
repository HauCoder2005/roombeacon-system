import asyncio
import sys
import logging
import os

from roombeacon_crawler.config.get_env import bootstrap_runtime_environment, env
from roombeacon_crawler.application.crawl.deferred_details import DeferredDetailProcessor
from roombeacon_crawler.repositories.local_deferred_detail_repository import LocalDeferredDetailRepository
from roombeacon_crawler.sources.resolver import SourceResolver
from roombeacon_crawler.infrastructure.storage.local.local_storage_writer import LocalStorageWriter
from roombeacon_crawler.services.fetch_coordinator import FetchCoordinator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

async def main():
    bootstrap_runtime_environment(load_dotenv_file=True)
    source_name = "phongtro123"
    target_id = "hcm_phongtro"
    adapter = SourceResolver.resolve("https://phongtro123.com/tinh-thanh/ho-chi-minh")
    if not adapter:
        return
        
    writer = LocalStorageWriter()
    deferred_repo = LocalDeferredDetailRepository()
    
    coordinator = FetchCoordinator()
    
    processor = DeferredDetailProcessor(
        source_name=source_name,
        target_id=target_id,
        adapter=adapter,
        coordinator=coordinator,
        deferred_repository=deferred_repo
    )
    
    logger.info("Starting drain of deferred queue...")
    processed_count = 0
    try:
        while True:
            logger.info("Fetching next batch...")
            details = await processor.process_pending_details(
                crawl_details=True,
                max_details_per_run=100
            )
            if not details:
                logger.info("No more details to process.")
                break
            
            writer.save_bronze_dataset(
                run_id="manual_drain_" + str(processed_count),
                source=source_name,
                records=[],
                metadata=[],
                details=details
            )
            
            deferred_repo.flush()
            processed_count += len(details)
            logger.info(f"Processed {processed_count} details so far.")
            if processed_count >= 100:
                break
    finally:
        pass
        
if __name__ == "__main__":
    asyncio.run(main())
