"""Exercise the DAG reporting boundary without importing Airflow on the host."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("count", [1, 2])
def test_mapped_reporting_outputs_remain_lists(count):
    path = Path(__file__).resolve().parents[1] / "airflow/dags/crawler/roombeacon_crawler.py"
    tree = ast.parse(path.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "summarize_run")
    function.decorator_list = []
    captured = Mock(return_value={})
    namespace = {
        "workflow": SimpleNamespace(summarize_run=captured),
        "_translate_failure": lambda operation, callback, *args, **kwargs: callback(*args, **kwargs),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)

    def pull(task_ids):
        task_id = task_ids if isinstance(task_ids, str) else task_ids[0]
        if task_id == "02_config_plan_crawls":
            return [{"mode": "FORCE_FULL"}] * count
        if task_id == "07_analytics_refresh_duckdb":
            return {"status": "SUCCESS"}
        values = [{"source": "chothuenha", "status": "SUCCESS"}] * count
        # Installed Airflow 3.3.1 collapses one value only for a string task ID.
        return values[0] if isinstance(task_ids, str) and count == 1 else values

    namespace["summarize_run"](ti=SimpleNamespace(xcom_pull=pull))
    for value in captured.call_args.args[1:5]:
        assert isinstance(value, list)
        assert len(value) == count
