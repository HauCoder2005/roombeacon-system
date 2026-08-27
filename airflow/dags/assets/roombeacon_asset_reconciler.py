"""Schedule fair reconciliation of Bronze image assets into MinIO.

The DAG defines task ordering and reporting only; download validation, retry
classification and storage behavior live in the asset application service.
"""

import logging
from datetime import datetime, timezone

from airflow.sdk import dag, task

logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_asset_reconciler"
DEFAULT_ARGS = {
    "owner": "roombeacon",
    "depends_on_past": False,
    "retries": 2,
}


@dag(
    dag_id=DAG_ID,
    description="Tự động đối soát, tải và nạp bù hình ảnh đa nguồn công bằng từ Bronze MySQL vào MinIO roombeacon-assets",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["roombeacon", "assets", "minio", "reconciliation", "images", "fair_scheduler"],
)
def roombeacon_asset_reconciler():
    """Build the asset reconciliation task graph."""

    @task
    def reconcile_asset_batch() -> dict:
        """1. Quét ứng viên hình ảnh đa nguồn và nạp một batch công bằng vào MinIO."""
        from roombeacon_crawler.application.orchestration.assets import sync_assets_minio

        logger.info("=" * 60)
        logger.info("STAGE 1: FAIR ASSET RECONCILER BATCH RUN")
        logger.info("=" * 60)

        return sync_assets_minio()

    @task
    def summarize_asset_run(batch_data: dict) -> None:
        """2. Báo cáo định lượng chi tiết chu kỳ đối soát và lưu trữ tài nguyên hình ảnh theo nguồn."""
        logger.info("=" * 60)
        logger.info("ROOMBEACON ASSET RECONCILER FAIR SUMMARY")
        logger.info("=" * 60)
        logger.info("Batch Budget          : %d", batch_data["batch_budget"])
        logger.info("Batch Used            : %d", batch_data["batch_used"])
        logger.info("Unused Capacity       : %d", batch_data["unused_capacity"])
        logger.info("MinIO Objects Before  : %d", batch_data["minio_objects_before"])
        logger.info("MinIO Objects After   : %d", batch_data["minio_objects_after"])
        logger.info("-" * 60)
        logger.info(
            "%-14s | %-8s | %-8s | %-8s | %-10s",
            "Source",
            "Selected",
            "Uploaded",
            "Stored",
            "Remaining",
        )
        logger.info("-" * 60)
        for s, m in batch_data.get("per_source", {}).items():
            logger.info(
                "%-14s | %-8d | %-8d | %-8d | %-10d",
                s,
                m.get("selected_this_run", 0),
                m.get("uploaded", 0),
                m.get("stored", 0),
                m.get("remaining_actionable", 0),
            )
        logger.info("=" * 60)

    # Workflow dependencies
    batch_res = reconcile_asset_batch()
    summarize_asset_run(batch_res)


dag_instance = roombeacon_asset_reconciler()
