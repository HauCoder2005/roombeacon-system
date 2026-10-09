"""Static contract for the only DAG allowed to read MySQL Bronze."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAG = ROOT / "airflow/dags/analytics/roombeacon_bronze_snapshot.py"


def _source() -> str:
    return DAG.read_text(encoding="utf-8")


def test_snapshot_dag_produces_the_bronze_snapshot_asset():
    source = _source()

    assert 'DAG_ID = "roombeacon_bronze_snapshot"' in source
    assert 'Asset("bronze_snapshot")' in source
    assert "outlets=[BRONZE_SNAPSHOT_ASSET]" in source
    assert "build_bronze_snapshot(" in source


def test_snapshot_dag_is_bounded_and_single_flight():
    source = _source()

    for required in (
        "catchup=False",
        "max_active_runs=1",
        "dagrun_timeout=",
        "execution_timeout=",
        'pool="duckdb_analytics_pool"',
        "retry_exponential_backoff=True",
    ):
        assert required in source


def test_unchanged_watermark_skips_without_emitting_an_asset_event():
    source = _source()

    assert "AirflowSkipException" in source
    assert '"UNCHANGED"' in source


def test_dag_module_does_no_runtime_work_at_import():
    tree = ast.parse(_source())
    top_level_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    top_level_modules = {
        node.module for node in tree.body if isinstance(node, ast.ImportFrom)
    }

    assert "analytics.bronze.snapshot" not in top_level_modules
    assert "pymysql" not in top_level_imports
    assert ".env" not in _source().replace(".env.local", "")


def test_container_paths_use_the_shared_data_volume_resolver():
    source = _source()

    assert "resolve_runtime_path(" in source
    assert "parents[3]" not in source
