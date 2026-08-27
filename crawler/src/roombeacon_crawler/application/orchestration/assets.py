"""Run bounded image reconciliation after analytics persistence.

This application boundary serializes the existing asset reconciler result for
orchestrators. It does not discover images from HTML or depend on Airflow.
"""

from dataclasses import asdict

from roombeacon_crawler.application.assets.asset_reconciler import (
    DEFAULT_ASSET_BATCH_SIZE,
    AssetReconcilerService,
)
from roombeacon_crawler.application.orchestration.errors import CrawlerWorkflowError


def sync_assets_minio(batch_size: int = DEFAULT_ASSET_BATCH_SIZE) -> dict:
    """Reconcile one fair, bounded batch and return scheduler-safe metrics."""
    try:
        result = AssetReconcilerService().reconcile_batch(batch_size=batch_size)
    except Exception as exc:
        raise CrawlerWorkflowError(
            f"Asset sync failed (error_class={type(exc).__name__})"
        ) from None

    return {
        "batch_budget": result.batch_budget,
        "batch_used": result.batch_used,
        "unused_capacity": result.unused_capacity,
        "candidates_found": result.candidates_found,
        "already_stored": result.already_stored,
        "attempted": result.attempted,
        "downloaded": result.downloaded,
        "uploaded": result.uploaded,
        "post_upload_verified": result.post_upload_verified,
        "skipped": result.skipped,
        "retryable_failed": result.retryable_failed,
        "terminal_failed": result.terminal_failed,
        "invalid_magic": result.invalid_magic,
        "pending_before": result.pending_before,
        "remaining_pending": result.remaining_pending,
        "duration_seconds": result.duration_seconds,
        "minio_objects_before": result.minio_objects_before,
        "minio_objects_after": result.minio_objects_after,
        "per_source": {source: asdict(metrics) for source, metrics in result.per_source.items()},
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }
