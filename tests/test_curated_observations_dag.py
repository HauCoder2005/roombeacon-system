"""Static contract for the Historical Curated Observations DAG."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAG = ROOT / "airflow/dags/analytics/roombeacon_curated_observations.py"


def test_curated_dag_is_driven_by_silver_and_emits_curated_asset():
    source = DAG.read_text(encoding="utf-8")

    assert 'DAG_ID = "roombeacon_curated_observations"' in source
    assert 'Asset("silver_rental_listings")' in source
    assert "schedule=[SILVER_RENTAL_LISTINGS_ASSET]" in source
    assert 'Asset("curated_listing_observations")' in source
    assert "outlets=[CURATED_OBSERVATIONS_ASSET]" in source
    assert "build_curated_observations(" in source


def test_curated_dag_reads_parquet_only_and_is_bounded():
    source = DAG.read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_modules = {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}

    for required in (
        "catchup=False", "max_active_runs=1", "dagrun_timeout=", "execution_timeout=",
        'pool="duckdb_analytics_pool"', "retry_exponential_backoff=True",
        'resolve_runtime_path("/data/curated_observations")',
    ):
        assert required in source
    for forbidden in ("pymysql", "create_analytics_connection", "ATTACH", "notebooks.utils", "parents[3]"):
        assert forbidden not in source
    assert "roombeacon_processing.curated" not in top_modules
