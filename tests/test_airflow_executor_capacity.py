"""The LocalExecutor must keep slots free for the post-Silver chain.

The crawler's mapped tasks run up to 180 min each. With PARALLELISM equal to
MAX_ACTIVE_TASKS_PER_DAG the crawler alone could hold every executor slot, so
build_curated / load_clickhouse sat queued until dagrun_timeout and ClickHouse
was never loaded automatically (observed 2026-10-07..09).
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
# bronze_snapshot -> silver_build -> curated -> warehouse share one DuckDB pool slot,
# plus one slot for the other short analytics/enrichment tasks.
POST_SILVER_RESERVED_SLOTS = 2


def _setting(name: str) -> str:
    match = re.search(rf'^\s+{name}: "([^"]+)"$', COMPOSE.read_text(encoding="utf-8"), re.M)
    assert match, name
    return match.group(1)


def _service_block(name: str) -> str:
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|^[a-z]|\Z)", text, re.S | re.M)
    assert match, name
    return match.group(1)


def _mebibytes(value: str) -> int:
    number, unit = re.fullmatch(r"(\d+)([mg])", value).groups()
    return int(number) * (1024 if unit == "g" else 1)


def test_one_dag_cannot_hold_every_executor_slot():
    parallelism = int(_setting("AIRFLOW__CORE__PARALLELISM"))
    per_dag = int(_setting("AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG"))

    assert parallelism - per_dag >= POST_SILVER_RESERVED_SLOTS


def test_lost_queued_tasks_are_retried_quickly():
    timeout = int(_setting("AIRFLOW__SCHEDULER__TASK_QUEUED_TIMEOUT"))

    assert 60 <= timeout <= 600


def test_scheduler_resources_cover_crawler_plus_one_duckdb_job():
    block = _service_block("airflow-scheduler")
    mem_limit = _mebibytes(re.search(r'mem_limit: "(\w+)"', block).group(1))
    memswap = _mebibytes(re.search(r'memswap_limit: "(\w+)"', block).group(1))
    cpus = float(re.search(r"cpus: ([\d.]+)", block).group(1))

    # Silver build peaks ~856MB next to two crawler tasks and the scheduler itself.
    assert mem_limit >= 2560
    assert memswap > mem_limit
    assert cpus >= 2.0
