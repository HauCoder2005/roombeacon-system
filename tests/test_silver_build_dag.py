import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEW_DAG = ROOT / "airflow/dags/analytics/roombeacon_silver_build.py"
LEGACY_DAG = ROOT / "airflow/dags/analytics/roombeacon_silver_materializer.py"


def test_legacy_mysql_attach_materializer_dag_is_removed():
    # It ATTACHed MySQL through DuckDB (OOM path) and duplicated publication.
    assert not LEGACY_DAG.exists()
    for dag_file in (ROOT / "airflow/dags").rglob("*.py"):
        assert 'DAG_ID = "roombeacon_silver_materializer"' not in dag_file.read_text(encoding="utf-8")


def test_silver_paths_resolve_to_the_container_data_volume():
    source = NEW_DAG.read_text(encoding="utf-8")

    # parents[3] of /opt/airflow/dags/analytics/<dag>.py is /opt, not the data volume.
    assert "parents[3]" not in source
    assert 'resolve_runtime_path("/data/bronze/snapshot")' in source
    assert 'resolve_runtime_path("/data/silver")' in source


def test_snapshot_only_asset_dag_contract():
    source = NEW_DAG.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lowered = source.lower()

    assert tree is not None
    assert 'DAG_ID = "roombeacon_silver_build"' in source
    assert 'Asset("bronze_snapshot")' in source
    assert 'Asset("silver_rental_listings")' in source
    assert "schedule=[BRONZE_SNAPSHOT_ASSET]" in source
    assert "outlets=[SILVER_RENTAL_LISTINGS_ASSET]" in source
    assert "catchup=False" in source
    assert "max_active_runs=1" in source
    assert "dagrun_timeout=" in source
    assert "execution_timeout=" in source
    assert 'pool="duckdb_analytics_pool"' in source
    assert "retry_exponential_backoff=True" in source
    assert "build_silver(" in source
    assert "pymysql" not in lowered
    assert "create_analytics_connection" not in source
    assert "notebooks.utils" not in source


def test_new_dag_documents_the_replaced_oom_path():
    source = NEW_DAG.read_text(encoding="utf-8")

    assert "SIGKILL" in source
    assert "OOM" in source
    assert "ATTACH" in source
