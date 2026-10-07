"""Publish Historical Curated Observations after each Silver publication.

Inputs are Parquet only: the validated Bronze snapshot (observations.parquet)
and the canonical Silver built from that same snapshot. The output is a
date-partitioned Parquet dataset that feeds the ClickHouse warehouse load.
"""

import logging
from datetime import datetime, timedelta, timezone

from airflow.sdk import Asset, dag, task


logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_curated_observations"
SILVER_RENTAL_LISTINGS_ASSET = Asset("silver_rental_listings")
CURATED_OBSERVATIONS_ASSET = Asset("curated_listing_observations")


@dag(
    dag_id=DAG_ID,
    description="Silver + Bronze snapshot history -> curated observation Parquet",
    schedule=[SILVER_RENTAL_LISTINGS_ASSET],
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=60),
    tags=["roombeacon", "analytics", "curated", "parquet", "asset"],
)
def roombeacon_curated_observations():
    @task(
        outlets=[CURATED_OBSERVATIONS_ASSET],
        pool="duckdb_analytics_pool",
        execution_timeout=timedelta(minutes=45),
        retries=2,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def build_curated() -> dict:
        from analytics.duckdb.connection import resolve_runtime_path
        from roombeacon_processing.curated import build_curated_observations

        result = build_curated_observations(
            resolve_runtime_path("/data/bronze/snapshot"),
            resolve_runtime_path("/data/silver"),
            resolve_runtime_path("/data/curated_observations"),
        )
        logger.info(
            "Published curated observations snapshot_id=%s rows=%d posts=%d partitions=%d",
            result.snapshot_id,
            result.row_count,
            result.post_count,
            result.partition_count,
        )
        return result.to_dict()

    build_curated()


dag_instance = roombeacon_curated_observations()
