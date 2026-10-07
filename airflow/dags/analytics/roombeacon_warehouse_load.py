"""Load the ClickHouse warehouse (facts, dimensions, Gold marts).

Runs after each curated observations publication. Inputs are Parquet only.
Connection settings come from .env.local (injected into the scheduler by
Compose ``env_file``). When WAREHOUSE_ENABLED is not true the task skips, so
the warehouse stays opt-in behind the ``warehouse`` Compose profile.
"""

import logging
from datetime import datetime, timedelta, timezone

from airflow.sdk import Asset, dag, task


logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_warehouse_load"
CURATED_OBSERVATIONS_ASSET = Asset("curated_listing_observations")
CLICKHOUSE_GOLD_ASSET = Asset("clickhouse_gold_marts")


@dag(
    dag_id=DAG_ID,
    description="Curated observations + Silver -> ClickHouse star schema and Gold marts",
    schedule=[CURATED_OBSERVATIONS_ASSET],
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=60),
    tags=["roombeacon", "warehouse", "clickhouse", "gold", "asset"],
)
def roombeacon_warehouse_load():
    @task(
        outlets=[CLICKHOUSE_GOLD_ASSET],
        pool="duckdb_analytics_pool",
        execution_timeout=timedelta(minutes=45),
        retries=2,
        retry_delay=timedelta(minutes=5),
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=20),
    )
    def load_clickhouse() -> dict:
        from airflow.exceptions import AirflowSkipException

        from analytics.duckdb.connection import resolve_runtime_path
        from roombeacon_warehouse.config import load_warehouse_settings
        from roombeacon_warehouse.loader import run_warehouse_load

        settings = load_warehouse_settings()
        if not settings.enabled:
            raise AirflowSkipException(
                "Warehouse disabled: set WAREHOUSE_ENABLED=true in .env.local "
                "and start the 'warehouse' Compose profile"
            )
        summary = run_warehouse_load(
            resolve_runtime_path("/data/curated_observations"),
            resolve_runtime_path("/data/silver"),
            settings=settings,
        )
        logger.info(
            "Loaded ClickHouse load_id=%s snapshot_id=%s rows=%s target=%s",
            summary["load_id"],
            summary["snapshot_id"],
            summary["row_counts"],
            summary["settings"],
        )
        return summary

    load_clickhouse()


dag_instance = roombeacon_warehouse_load()
