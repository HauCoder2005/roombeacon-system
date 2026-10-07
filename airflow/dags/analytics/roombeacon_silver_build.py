"""Build canonical Silver from the validated local Bronze snapshot Asset.

This replaces the legacy path that repeatedly ended in SIGKILL/OOM after it
used DuckDB ATTACH and materialized database-backed Bronze relations. The task
below has no database access: it consumes only bounded snapshot Parquet files.
"""

import logging
from datetime import datetime, timedelta, timezone

from airflow.sdk import Asset, dag, task


logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_silver_build"
BRONZE_SNAPSHOT_ASSET = Asset("bronze_snapshot")
SILVER_RENTAL_LISTINGS_ASSET = Asset("silver_rental_listings")


@dag(
    dag_id=DAG_ID,
    description="Build canonical Silver from the validated Bronze Parquet snapshot",
    schedule=[BRONZE_SNAPSHOT_ASSET],
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=90),
    tags=["roombeacon", "analytics", "silver", "asset", "snapshot"],
)
def roombeacon_silver_build():
    @task(
        outlets=[SILVER_RENTAL_LISTINGS_ASSET],
        pool="duckdb_analytics_pool",
        execution_timeout=timedelta(minutes=75),
        retries=2,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def build_snapshot_silver() -> dict:
        from analytics.duckdb.connection import resolve_runtime_path
        from roombeacon_processing.build import build_silver

        # /data is the shared data volume in Docker; on the host it maps to
        # <project>/data. Never derive it from this file's location.
        result = build_silver(
            resolve_runtime_path("/data/bronze/snapshot"),
            resolve_runtime_path("/data/silver"),
        )
        logger.info(
            "Published Silver snapshot_id=%s rows=%d columns=%d runtime_seconds=%.2f",
            result.snapshot_id,
            result.row_count,
            result.column_count,
            result.runtime_seconds,
        )
        return result.to_dict()

    build_snapshot_silver()


dag_instance = roombeacon_silver_build()
