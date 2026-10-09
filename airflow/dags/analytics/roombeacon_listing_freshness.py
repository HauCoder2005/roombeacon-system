"""Publish listing freshness (posted dates, age, FRESH/STALE/UNKNOWN) after each Silver publication.

Inputs are Parquet only: the validated Bronze snapshot observations, whose
posted_at_raw text is interpreted at each observation's time. The output sits
beside Silver (data/freshness) and leaves the Silver contract unchanged.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from airflow.sdk import Asset, dag, task


logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_listing_freshness"
SILVER_RENTAL_LISTINGS_ASSET = Asset("silver_rental_listings")
LISTING_FRESHNESS_ASSET = Asset("listing_freshness")


@dag(
    dag_id=DAG_ID,
    description="Bronze snapshot posted dates -> listing freshness Parquet",
    schedule=[SILVER_RENTAL_LISTINGS_ASSET],
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    # Queue time counts: the shared DuckDB pool slot can be held by a crawler task
    # (up to 180 min), so budget one crawler task plus every attempt.
    dagrun_timeout=timedelta(hours=6),
    tags=["roombeacon", "analytics", "freshness", "parquet", "asset"],
)
def roombeacon_listing_freshness():
    @task(
        outlets=[LISTING_FRESHNESS_ASSET],
        pool="duckdb_analytics_pool",
        priority_weight=100,
        weight_rule="absolute",
        execution_timeout=timedelta(minutes=30),
        retries=2,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def build_freshness() -> dict:
        from analytics.duckdb.connection import resolve_runtime_path
        from roombeacon_processing.freshness import publish_listing_freshness

        result = publish_listing_freshness(
            resolve_runtime_path("/data/bronze/snapshot"),
            resolve_runtime_path("/data/freshness"),
            stale_after_days=int(os.getenv("LISTING_STALE_AFTER_DAYS", "90")),
        )
        logger.info(
            "Published listing freshness snapshot_id=%s rows=%d counts=%s",
            result.snapshot_id,
            result.row_count,
            result.freshness_counts,
        )
        return result.to_dict()

    build_freshness()


dag_instance = roombeacon_listing_freshness()
