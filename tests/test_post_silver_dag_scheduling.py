"""Post-Silver DAGs must survive waiting for a LocalExecutor slot.

A crawler task (execution_timeout 180 min) can hold the shared
duckdb_analytics_pool slot or executor slots. Queue time counts
toward dagrun_timeout, so each post-Silver DAG must (a) jump the queue when a
slot frees and (b) budget for one full crawler task before its own attempts.
"""

import ast
from datetime import timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DAGS = ROOT / "airflow/dags/analytics"
POST_SILVER_DAGS = (
    "roombeacon_bronze_snapshot.py",
    "roombeacon_silver_build.py",
    "roombeacon_curated_observations.py",
    "roombeacon_warehouse_load.py",
)
CRAWLER_TASK_TIMEOUT = timedelta(minutes=180)
MIN_PRIORITY = 100


def _decorator_kwargs(path: Path, name: str) -> dict[str, ast.expr]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and getattr(deco.func, "id", None) == name:
                    return {kw.arg: kw.value for kw in deco.keywords}
    raise AssertionError(f"no @{name}(...) in {path.name}")


def _timedelta(node: ast.expr) -> timedelta:
    assert isinstance(node, ast.Call) and getattr(node.func, "id", None) == "timedelta"
    return timedelta(**{kw.arg: ast.literal_eval(kw.value) for kw in node.keywords})


@pytest.mark.parametrize("filename", POST_SILVER_DAGS)
def test_post_silver_task_takes_priority_over_crawler_tasks(filename):
    task = _decorator_kwargs(DAGS / filename, "task")

    assert ast.literal_eval(task["priority_weight"]) >= MIN_PRIORITY
    assert ast.literal_eval(task["weight_rule"]) == "absolute"


@pytest.mark.parametrize("filename", POST_SILVER_DAGS)
def test_dagrun_timeout_covers_queue_wait_and_every_attempt(filename):
    dag = _decorator_kwargs(DAGS / filename, "dag")
    task = _decorator_kwargs(DAGS / filename, "task")

    retries = ast.literal_eval(task["retries"])
    attempts = _timedelta(task["execution_timeout"]) * (retries + 1)
    retry_waits = _timedelta(task["max_retry_delay"]) * retries
    required = CRAWLER_TASK_TIMEOUT + attempts + retry_waits

    assert _timedelta(dag["dagrun_timeout"]) >= required
