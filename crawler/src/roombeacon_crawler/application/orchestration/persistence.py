"""Persist successful local Bronze artifacts into observation history.

This module is Airflow-free and composes runtime adapters at the use-case boundary.
"""

import logging
import time
from roombeacon_crawler.enums.crawl_status import CrawlStatus

logger = logging.getLogger(__name__)


from roombeacon_crawler.application.orchestration.errors import CrawlerWorkflowError


def persist_bronze_mysql(result_payload: dict, **context) -> dict:
    """Đọc Bronze Artifacts (listings.json, details.json) và persist vào MySQL Database qua Use Case."""
    source = result_payload.get("source", "unknown")
    target_id = result_payload.get("target_id", "default")
    run_id = result_payload.get("run_id") or result_payload.get("crawl_run_id")
    bronze_path = result_payload.get("bronze_path")
    action = result_payload.get("action", "UNKNOWN")
    crawl_status = result_payload.get("crawl_status", "unknown")

    logger.info("=" * 60)
    logger.info("STAGE 5: PERSIST BRONZE TO MYSQL")
    logger.info("Source: %s | Target ID: %s | Run ID: %s | Bronze Path: %s", source, target_id, run_id, bronze_path)
    logger.info("=" * 60)

    if action in {"SKIPPED", "DEFERRED"} or crawl_status != CrawlStatus.SUCCESS.value:
        logger.info("Bỏ qua persist MySQL cho %s/%s (action=%s, status=%s, bronze_path=%s)", source, target_id, action, crawl_status, bronze_path)
        return {
            "source": source,
            "target_id": target_id,
            "run_id": run_id,
            "status": "SKIPPED_NO_DATA",
            "posts_created": 0,
            "posts_existing": 0,
            "observations_inserted": 0,
            "technical_duplicates": 0,
            "crawl_result": result_payload,
        }

    confirmed_empty = (
        result_payload.get("source_end_confirmed") is True
        and result_payload.get("stop_reason") == "SOURCE_END"
        and result_payload.get("observations_written") == 0
    )
    if not bronze_path:
        if confirmed_empty:
            return {
                "source": source, "target_id": target_id, "run_id": run_id,
                "status": "SUCCESS", "posts_created": 0, "posts_existing": 0,
                "observations_inserted": 0, "technical_duplicates": 0,
                "raw_objects_mirrored": 0, "crawl_result": result_payload,
            }
        raise CrawlerWorkflowError(
            f"Successful crawl missing Bronze artifacts for {source}/{target_id}"
        )

    from roombeacon_crawler.application.persistence.persist_observations import PersistBronzeObservationsUseCase
    from roombeacon_crawler.models.persistence_context import PersistenceContext
    from roombeacon_crawler.enums.ingestion_origin import IngestionOrigin
    from roombeacon_crawler.infrastructure.mysql.repositories.observation_repository import MySQLObservationRepository
    from roombeacon_crawler.infrastructure.mysql.repositories.platform_repository import MySQLPlatformRepository
    from roombeacon_crawler.infrastructure.mysql.repositories.post_children_repository import MySQLPostChildrenRepository
    from roombeacon_crawler.infrastructure.mysql.repositories.rental_post_repository import MySQLRentalPostRepository
    from roombeacon_crawler.infrastructure.mysql.schema import ensure_mysql_schema
    from roombeacon_crawler.infrastructure.mysql.transaction import MySQLTransactionManager
    from roombeacon_crawler.mappers.bronze_observation_loader import BronzeObservationLoader
    from roombeacon_crawler.infrastructure.storage.minio.raw_artifact_mirror import (
        MinIORawArtifactMirror,
    )

    try:
        ensure_mysql_schema()
    except Exception as exc:
        raise CrawlerWorkflowError("MySQL schema verification failed") from exc

    mapper_started = time.perf_counter()
    observations = BronzeObservationLoader.load_from_bronze_dir(bronze_path, run_id=run_id)
    mapper_seconds = time.perf_counter() - mapper_started
    if not observations:
        if not confirmed_empty:
            raise CrawlerWorkflowError(
                f"Bronze artifacts contain no observations for {source}/{target_id}"
            )
        return {
            "source": source, "target_id": target_id, "run_id": run_id,
            "status": "SUCCESS", "posts_created": 0, "posts_existing": 0,
            "observations_inserted": 0, "technical_duplicates": 0,
            "raw_objects_mirrored": 0, "crawl_result": result_payload,
        }

    # Verify the durable raw copy before allowing a checkpoint to advance.
    try:
        mirrored_keys = MinIORawArtifactMirror().mirror_directory(
            bronze_path, source=source, run_id=run_id,
        )
    except Exception as exc:
        raise CrawlerWorkflowError(
            f"Raw artifact mirror failed for {source}/{target_id}"
        ) from exc

    tx_mgr = MySQLTransactionManager()
    use_case = PersistBronzeObservationsUseCase(
        platform_repo=MySQLPlatformRepository(connection=None),
        rental_post_repo=MySQLRentalPostRepository(connection=None),
        observation_repo=MySQLObservationRepository(connection=None),
        children_repo=MySQLPostChildrenRepository(connection=None),
        transaction_mgr=tx_mgr,
    )

    try:
        from roombeacon_crawler.infrastructure.mysql.query_profiler import MySQLQueryProfiler

        persistence_started = time.perf_counter()
        query_profiler = MySQLQueryProfiler(tx_mgr.connection)
        with query_profiler:
            import_res = use_case.execute(observations, context=PersistenceContext(ingestion_origin=IngestionOrigin.LIVE_CRAWLER))
        total_persistence_seconds = time.perf_counter() - persistence_started
        table_profile = query_profiler.as_dict()
        logger.info("=" * 60)
        logger.info("MYSQL BRONZE PERSISTENCE")
        logger.info("=" * 60)
        logger.info("Source                 : %s", source)
        logger.info("Target                 : %s", target_id)
        logger.info("Run ID                 : %s", run_id)
        logger.info("Bronze Path            : %s", bronze_path)
        logger.info("Observations Read      : %d", len(observations))
        logger.info("Posts Created          : %d", import_res.posts_created)
        logger.info("Posts Existing         : %d", import_res.posts_existing)
        logger.info("Observations Inserted  : %d", import_res.observations_inserted)
        logger.info("Technical Duplicates   : %d", import_res.technical_duplicates)
        logger.info("Status                 : SUCCESS")
        logger.info(
            "Persistence timing seconds: mapper=%.3f begin=%.3f platform=%.3f posts=%.3f versions=%.3f children=%.3f commit=%.3f total=%.3f",
            mapper_seconds,
            import_res.transaction_begin_seconds,
            import_res.platform_seconds,
            import_res.rental_posts_seconds,
            import_res.rental_post_versions_seconds,
            import_res.children_seconds,
            import_res.commit_seconds,
            total_persistence_seconds,
        )
        for table, stats in table_profile.items():
            logger.info(
                "SQL profile table=%s rows=%d executions=%d total_seconds=%.6f avg_seconds=%.6f",
                table,
                stats["rows"],
                stats["executions"],
                stats["total_seconds"],
                stats["avg_seconds"],
            )
        logger.info("=" * 60)
        return {
            "source": source,
            "target_id": target_id,
            "run_id": run_id,
            "status": "SUCCESS",
            "posts_created": import_res.posts_created,
            "posts_existing": import_res.posts_existing,
            "observations_inserted": import_res.observations_inserted,
            "technical_duplicates": import_res.technical_duplicates,
            "raw_objects_mirrored": len(mirrored_keys),
            "mapper_seconds": mapper_seconds,
            "transaction_begin_seconds": import_res.transaction_begin_seconds,
            "platform_seconds": import_res.platform_seconds,
            "rental_posts_seconds": import_res.rental_posts_seconds,
            "rental_post_versions_seconds": import_res.rental_post_versions_seconds,
            "children_seconds": import_res.children_seconds,
            "commit_seconds": import_res.commit_seconds,
            "total_persistence_seconds": total_persistence_seconds,
            "table_profile": table_profile,
            "crawl_result": result_payload,
        }
    except Exception as exc:
        logger.error(
            "MySQL Bronze persistence failed (source=%s, target=%s, run_id=%s, error_class=%s)",
            source,
            target_id,
            run_id,
            type(exc).__name__,
        )
        raise CrawlerWorkflowError(
            f"MySQL persistence failed for {source}/{target_id} (run_id={run_id})"
        ) from exc
