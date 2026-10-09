import inspect
from pathlib import Path

import pandas as pd
import pytest

import roombeacon_processing.build as build_module


def test_build_module_has_no_mysql_access_path():
    source = inspect.getsource(build_module).lower()

    assert "attach" not in source
    assert "pymysql" not in source
    assert "mysqlclient" not in source
    assert "create_analytics_connection" not in source


def test_build_requires_snapshot_validation_and_quality_gate(monkeypatch, tmp_path: Path):
    bronze = pd.DataFrame({"rental_post_id": [1]})
    evidence = pd.DataFrame({"rental_post_id": [1]})
    context = {
        "snapshot_id": "snapshot-1",
        "files": {
            "latest_posts.parquet": {"sha256": "a" * 64},
            "raw_evidence.parquet": {"sha256": "b" * 64},
        },
    }
    silver = pd.DataFrame({"rental_post_id": [1]})
    calls = []

    monkeypatch.setattr(
        build_module,
        "load_bronze_snapshot",
        lambda path: (calls.append(("load", path)) or (bronze, evidence, context)),
    )
    monkeypatch.setattr(
        build_module,
        "build_silver_dataset",
        lambda actual_bronze, actual_evidence: (
            calls.append(("transform", actual_bronze, actual_evidence)) or silver
        ),
    )
    monkeypatch.setattr(
        build_module,
        "evaluate_pre_silver_quality_gate",
        lambda actual_bronze, actual_silver: (
            calls.append(("gate", actual_bronze, actual_silver))
            or type("Gate", (), {"passed": False})()
        ),
    )

    with pytest.raises(build_module.SilverBuildError, match="quality gate"):
        build_module.build_silver(tmp_path / "snapshot", tmp_path / "silver")

    assert [call[0] for call in calls] == ["load", "transform", "gate"]


def test_build_propagates_snapshot_hash_failure(monkeypatch, tmp_path: Path):
    error = RuntimeError("snapshot file does not match metadata")
    monkeypatch.setattr(
        build_module, "load_bronze_snapshot", lambda path: (_ for _ in ()).throw(error)
    )

    with pytest.raises(RuntimeError, match="does not match metadata"):
        build_module.build_silver(tmp_path / "snapshot", tmp_path / "silver")
