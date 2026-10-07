"""Static contracts for the warehouse DAG, Compose profile and image."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAG = ROOT / "airflow/dags/analytics/roombeacon_warehouse_load.py"
COMPOSE = ROOT / "docker-compose.yml"


def _service_block(name: str) -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|^[a-z]|\Z)", text, re.S | re.M)
    assert match, name
    return match.group(1)


def test_warehouse_dag_runs_after_curated_and_skips_when_disabled():
    source = DAG.read_text(encoding="utf-8")
    top = {n.module for n in ast.parse(source).body if isinstance(n, ast.ImportFrom)}

    assert 'DAG_ID = "roombeacon_warehouse_load"' in source
    assert 'Asset("curated_listing_observations")' in source
    assert "schedule=[CURATED_OBSERVATIONS_ASSET]" in source
    assert 'Asset("clickhouse_gold_marts")' in source
    assert "outlets=[CLICKHOUSE_GOLD_ASSET]" in source
    assert "AirflowSkipException" in source and "settings.enabled" in source
    for required in ("catchup=False", "max_active_runs=1", "execution_timeout=", "retry_exponential_backoff=True"):
        assert required in source
    for forbidden in ("pymysql", "ATTACH", "parents[3]", "password"):
        assert forbidden not in source
    assert not {"roombeacon_warehouse.loader", "roombeacon_warehouse.config"} & top


def test_clickhouse_is_profiled_pinned_local_only_and_non_root():
    block = _service_block("clickhouse")

    assert 'image: "clickhouse/clickhouse-server:25.8.33.6"' in block
    assert re.search(r"profiles:\n\s+- warehouse\n", block)
    assert '"127.0.0.1:8123:8123"' in block
    assert "9000" not in block
    assert 'user: "101:101"' in block
    assert 'path: ".env.local"' in block
    assert "no-new-privileges:true" in block
    assert "${" not in block.replace("$${", "")  # no interpolation from the shared .env
    assert "CLICKHOUSE_PASSWORD" in block  # fail-fast guard when the secret is unset


def test_scheduler_receives_env_local_and_warehouse_sources():
    block = _service_block("airflow-scheduler")
    text = COMPOSE.read_text(encoding="utf-8")

    assert 'path: ".env.local"' in block
    assert "required: false" in block
    assert '"./warehouse/src:/opt/roombeacon/warehouse/src:ro"' in text
    assert '"./processing/src:/opt/roombeacon/processing/src:ro"' in text


def test_airflow_image_installs_the_pinned_warehouse_package():
    dockerfile = (ROOT / "airflow/Dockerfile").read_text(encoding="utf-8")
    pyproject = (ROOT / "warehouse/pyproject.toml").read_text(encoding="utf-8")

    assert "-e /opt/roombeacon/warehouse" in dockerfile
    assert '"clickhouse-connect==0.8.18"' in pyproject


def test_env_local_template_is_tracked_without_secrets():
    template = (ROOT / ".env.local.example").read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1) for line in template.splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert values["WAREHOUSE_ENABLED"] == "false"
    for key, value in values.items():
        if "PASSWORD" in key:
            assert value == "", key
    for key in ("CLICKHOUSE_USER", "CLICKHOUSE_DB", "WAREHOUSE_CLICKHOUSE_USER", "WAREHOUSE_CLICKHOUSE_DATABASE"):
        assert key in values
    assert values["CLICKHOUSE_DB"] == values["WAREHOUSE_CLICKHOUSE_DATABASE"]


def test_clickhouse_init_grants_loader_only_its_database():
    script = (ROOT / "infrastructure/clickhouse/initdb/10-roombeacon-users.sh").read_text(encoding="utf-8")

    assert "GRANT SELECT, INSERT, CREATE TABLE, DROP TABLE, TRUNCATE ON" in script
    assert "ON *.*" not in script
    assert "set -euo pipefail" in script
