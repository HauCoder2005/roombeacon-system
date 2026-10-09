"""Static contract for the listing-freshness DAG (no Airflow import needed)."""

import ast
from pathlib import Path


DAG = Path(__file__).resolve().parents[1] / "airflow/dags/analytics/roombeacon_listing_freshness.py"


def test_freshness_dag_follows_silver_and_publishes_an_asset():
    source = DAG.read_text(encoding="utf-8")
    top_imports = {n.module for n in ast.parse(source).body if isinstance(n, ast.ImportFrom)}

    assert 'DAG_ID = "roombeacon_listing_freshness"' in source
    assert 'Asset("silver_rental_listings")' in source and "schedule=[SILVER_RENTAL_LISTINGS_ASSET]" in source
    assert 'Asset("listing_freshness")' in source and "outlets=[LISTING_FRESHNESS_ASSET]" in source
    assert 'pool="duckdb_analytics_pool"' in source
    assert 'os.getenv("LISTING_STALE_AFTER_DAYS", "90")' in source
    assert '"/data/bronze/snapshot"' in source and '"/data/freshness"' in source
    for required in ("catchup=False", "max_active_runs=1", "execution_timeout=", "retry_exponential_backoff=True"):
        assert required in source
    for forbidden in ("pymysql", "mysql", "password"):
        assert forbidden not in source.lower()
    assert "roombeacon_processing.freshness" not in top_imports
