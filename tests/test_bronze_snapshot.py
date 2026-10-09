import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from analytics.bronze.snapshot import (
    BronzeSnapshotError,
    BronzeSnapshotNotFoundError,
    load_bronze_snapshot,
    write_bronze_snapshot,
)


def _frames():
    latest = pd.DataFrame(
        {
            "rental_post_id": [1, 2],
            "source_code": ["a", "b"],
            "source_listing_id": ["x", "y"],
            "title_raw": ["one", "two"],
            "price_amount": [1_000_000.0, 2_000_000.0],
            "area_value": [20.0, 30.0],
            "full_address_text": [None, "Ward 1"],
            "location_raw": ["District 1", "Ward 1"],
            "best_address_text": ["District 1", "Ward 1"],
            "latest_observed_at": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        }
    )
    evidence = pd.DataFrame(
        {
            "rental_post_id": [1, 2],
            "evidence_observation_id": [10, 20],
            "evidence_version_time_matches": [1, 1],
            "evidence_price_id": [101, 201],
            "price_raw": ["1 million", "2 million"],
            "currency": ["VND", "VND"],
            "period": ["MONTH", "MONTH"],
            "evidence_area_id": [102, 202],
            "area_raw": ["20 m2", "30 m2"],
            "price_lineage_aligned": [True, True],
            "area_lineage_aligned": [True, True],
        }
    )
    return latest, evidence


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_snapshot_write_read_roundtrip_and_safe_metadata(tmp_path, monkeypatch):
    latest, evidence = _frames()
    metadata = write_bronze_snapshot(
        latest,
        evidence,
        tmp_path,
        source_database="fixture_bronze",
        snapshot_id="fixture-snapshot",
        created_at="2026-01-03T00:00:00+00:00",
    )
    import pymysql

    monkeypatch.setattr(
        pymysql,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("local loader attempted MySQL access")
        ),
    )
    loaded_latest, loaded_evidence, context = load_bronze_snapshot(tmp_path)
    assert loaded_latest.rental_post_id.tolist() == [1, 2]
    assert loaded_evidence.evidence_observation_id.tolist() == [10, 20]
    assert loaded_evidence.price_lineage_aligned.all()
    assert loaded_evidence.area_lineage_aligned.all()
    assert context["snapshot_id"] == metadata["snapshot_id"] == "fixture-snapshot"
    assert context["latest_row_count"] == context["unique_rental_post_id_count"] == 2
    rendered = (tmp_path / "metadata.json").read_text()
    assert "password" not in rendered.lower()
    assert "fixture_bronze" in rendered


def test_invalid_refresh_preserves_previous_snapshot(tmp_path):
    latest, evidence = _frames()
    write_bronze_snapshot(latest, evidence, tmp_path, source_database="fixture")
    before = {name: _digest(tmp_path / name) for name in (
        "latest_posts.parquet", "raw_evidence.parquet", "metadata.json"
    )}
    invalid = latest.copy()
    invalid.loc[1, "rental_post_id"] = 1
    with pytest.raises(BronzeSnapshotError, match="grain violation"):
        write_bronze_snapshot(invalid, evidence, tmp_path, source_database="fixture")
    after = {name: _digest(tmp_path / name) for name in before}
    assert after == before


def test_missing_snapshot_has_actionable_refresh_command(tmp_path):
    with pytest.raises(BronzeSnapshotNotFoundError, match="python -m analytics.bronze.snapshot"):
        load_bronze_snapshot(tmp_path)


def test_loader_rejects_metadata_or_parquet_mismatch(tmp_path):
    latest, evidence = _frames()
    write_bronze_snapshot(latest, evidence, tmp_path, source_database="fixture")
    metadata_path = tmp_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["latest_row_count"] = 999
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(BronzeSnapshotError, match="metadata mismatch"):
        load_bronze_snapshot(tmp_path)


def test_official_notebooks_use_one_local_snapshot_contract_only():
    root = Path(__file__).resolve().parents[1]
    eda = (root / "notebooks/01_roombeacon_eda.ipynb").read_text()
    silver = (root / "notebooks/02_roombeacon_silver.ipynb").read_text()
    for notebook in (eda, silver):
        assert "load_bronze_snapshot" in notebook
        assert re.search(r"""data\\?['"]\s*/\s*\\?['"]bronze\\?['"]\s*/\s*\\?['"]snapshot""", notebook)
        assert "create_analytics_connection" not in notebook
        assert "load_snapshot(" not in notebook
