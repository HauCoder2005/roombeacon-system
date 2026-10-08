"""Publish the bounded Bronze Parquet snapshot that feeds every downstream job.

This is the only DAG allowed to read MySQL Bronze. The read runs inside one
consistent read-only transaction, bounded by the Bronze version watermark,
with server-side statement and client socket timeouts. When the watermark is
unchanged the task skips, so no ``bronze_snapshot`` Asset event is emitted
and Silver is not rebuilt for an identical population.
"""

import logging
from datetime import datetime, timedelta, timezone

from airflow.sdk import Asset, dag, task


logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_bronze_snapshot"
BRONZE_SNAPSHOT_ASSET = Asset("bronze_snapshot")


@dag(
    dag_id=DAG_ID,
    description="Bounded MySQL Bronze -> Parquet snapshot (watermark, read-only)",
    schedule="30 1 * * *",
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    # Queue time counts: PARALLELISM=2 slots can be held by crawler tasks
    # (up to 180 min), so budget one crawler task plus every attempt.
    dagrun_timeout=timedelta(hours=6),
    tags=["roombeacon", "analytics", "bronze", "snapshot", "asset"],
)
def roombeacon_bronze_snapshot():
    @task(
        outlets=[BRONZE_SNAPSHOT_ASSET],
        pool="duckdb_analytics_pool",
        priority_weight=100,
        weight_rule="absolute",
        execution_timeout=timedelta(minutes=45),
        retries=2,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def extract_bronze_snapshot() -> dict:
        from airflow.sdk.exceptions import AirflowSkipException

        from analytics.bronze.snapshot import build_bronze_snapshot
        from analytics.duckdb.connection import resolve_runtime_path

        metadata = build_bronze_snapshot(
            snapshot_dir=resolve_runtime_path("/data/bronze/snapshot"),
        )
        watermark = metadata.get("watermark", {})
        if metadata["status"] == "UNCHANGED":
            raise AirflowSkipException(
                f"Bronze watermark unchanged at max_version_id={watermark.get('max_version_id')}"
            )
        logger.info(
            "Published Bronze snapshot_id=%s latest_rows=%d observations=%d max_version_id=%s",
            metadata["snapshot_id"],
            metadata["latest_row_count"],
            metadata["observation_row_count"],
            watermark.get("max_version_id"),
        )
        return {
            "snapshot_id": metadata["snapshot_id"],
            "latest_row_count": metadata["latest_row_count"],
            "observation_row_count": metadata["observation_row_count"],
            "watermark": watermark,
            "refresh_runtime_seconds": metadata.get("refresh_runtime_seconds"),
        }

    extract_bronze_snapshot()


dag_instance = roombeacon_bronze_snapshot()
