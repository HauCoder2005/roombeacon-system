"""Historical Curated Observations: one cleaned row per Bronze observation."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from analytics.bronze.snapshot import write_bronze_snapshot
from roombeacon_processing import curated
from roombeacon_processing.curated import (
    CURATED_COLUMNS,
    CuratedBuildError,
    build_curated_observations,
    curate_observations,
)
from roombeacon_processing.price_area_validation import validate_area, validate_price


def _observations():
    return pd.DataFrame(
        {
            "observation_id": [101, 102, 103, 104],
            "rental_post_id": [11, 11, 11, 12],
            "source_code": ["phongtro123"] * 3 + ["mogi"],
            "source_listing_id": ["a", "a", "a", "b"],
            "crawl_run_id": ["r1", "r2", "r3", "r2"],
            "observed_at": pd.to_datetime(
                ["2026-09-20 08:00", "2026-09-21 08:00", "2026-09-22 08:00", "2026-09-21 09:00"]
            ),
            "content_hash": ["h1", "h1", "h2", "h9"],
            "ingestion_origin": ["LIVE_CRAWLER"] * 4,
            "price_raw": ["3 triệu", "3 triệu", "3,5 triệu", "5 đồng"],
            "price_amount": [3_000_000.0, 3_000_000.0, 3_500_000.0, 5.0],
            "currency": ["VND"] * 4,
            "period": ["MONTH"] * 4,
            "area_raw": ["20 m2", "20 m2", "20 m2", None],
            "area_value": [20.0, 20.0, 20.0, None],
        }
    )


def _silver():
    return pd.DataFrame(
        {
            "rental_post_id": [11, 12],
            "source_code": ["phongtro123", "mogi"],
            "province_text_extracted": ["Hồ Chí Minh", "Hồ Chí Minh"],
            "district_text_extracted": ["Quận 1", "Quận 7"],
            "ward_current": ["Phường Bến Nghé", None],
            "ward_mapping_status": ["MAPPED", "MISSING"],
            "admin_consistency_status": ["CONSISTENT", "MISSING_EVIDENCE"],
            "listing_intent": ["RENT", "SALE"],
            "rental_scope": ["SINGLE_OR_ORDINARY_UNIT", "UNKNOWN"],
            "price_model_suitability": ["SUPPORTED", "EXCLUDED"],
            "row_quality_status": ["READY", "REQUIRES_REVIEW"],
            "has_trusted_coordinate": [True, False],
            "duplicate_candidate_group": ["g1", None],
            # PII-adjacent / free-text columns must never reach curated output.
            "title_raw": ["Phòng đẹp, LH 0909", "Bán nhà"],
            "url": ["https://x/a", "https://x/b"],
        }
    )


def test_curated_rows_preserve_grain_and_order_versions_per_post():
    result = curate_observations(_observations(), _silver())

    assert list(result.columns) == list(CURATED_COLUMNS)
    assert result.observation_id.tolist() == [101, 102, 103, 104]
    assert result.version_seq.tolist() == [1, 2, 3, 1]
    assert result.observed_date.astype(str).tolist() == [
        "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-21"
    ]
    # The first sighting is a change; an identical content hash is a re-sighting.
    assert result.is_content_change.tolist() == [True, False, True, True]
    assert result.is_price_change.tolist() == [False, False, True, False]


def test_observation_validation_reuses_the_silver_domain_rules():
    result = curate_observations(_observations(), _silver()).set_index("observation_id")

    for oid, amount in [(101, 3_000_000), (104, 5)]:
        assert result.loc[oid, "price_status"] == validate_price(Decimal(str(amount)))
    assert result.loc[104, "area_status"] == validate_area(None)
    assert result.loc[101, "price_per_m2"] == pytest.approx(150_000.0)
    assert pd.isna(result.loc[104, "price_per_m2"])


def test_market_eligibility_requires_clean_price_and_supported_rent_post():
    result = curate_observations(_observations(), _silver()).set_index("observation_id")

    assert result.loc[[101, 102, 103], "is_market_eligible"].all()
    # SALE intent and a suspicious 5 VND price are both excluded.
    assert not result.loc[104, "is_market_eligible"]


def test_curated_output_excludes_free_text_and_contact_fields():
    result = curate_observations(_observations(), _silver())

    for column in ("title_raw", "url", "price_raw", "area_raw", "seller_phone", "seller_name"):
        assert column not in result.columns
    assert result.district.tolist() == ["Quận 1"] * 3 + ["Quận 7"]
    assert result.ward.tolist()[:3] == ["Phường Bến Nghé"] * 3


def test_observation_for_post_absent_from_silver_fails_closed():
    silver = _silver().iloc[:1]

    with pytest.raises(CuratedBuildError, match="absent from Silver"):
        curate_observations(_observations(), silver)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_inputs(tmp_path: Path, *, silver_snapshot_id: str | None = None):
    snapshot_dir, silver_dir = tmp_path / "snapshot", tmp_path / "silver"
    observations = _observations()
    latest = pd.DataFrame(
        {
            "rental_post_id": [11, 12], "source_code": ["phongtro123", "mogi"],
            "source_listing_id": ["a", "b"], "title_raw": ["t1", "t2"],
            "price_amount": [3_500_000.0, 5.0], "area_value": [20.0, None],
            "full_address_text": [None, None], "location_raw": ["Q1", "Q7"],
            "best_address_text": ["Q1", "Q7"],
            "latest_observed_at": pd.to_datetime(["2026-09-22 08:00", "2026-09-21 09:00"]),
        }
    )
    evidence = pd.DataFrame(
        {
            "rental_post_id": [11, 12], "evidence_observation_id": [103, 104],
            "evidence_version_time_matches": [1, 1], "evidence_price_id": [1, 2],
            "price_raw": ["3,5 triệu", "5 đồng"], "currency": ["VND", "VND"],
            "period": ["MONTH", "MONTH"], "evidence_area_id": [1, None],
            "area_raw": ["20 m2", None], "price_lineage_aligned": [True, True],
            "area_lineage_aligned": [True, True],
        }
    )
    metadata = write_bronze_snapshot(
        latest, evidence, snapshot_dir, source_database="fixture",
        snapshot_id="snap-1", observations=observations,
    )
    silver_dir.mkdir()
    silver_path = silver_dir / "rental_listings.parquet"
    connection = duckdb.connect()
    connection.register("s", _silver())
    connection.execute("COPY s TO ? (FORMAT PARQUET)", [str(silver_path)])
    connection.close()
    (silver_dir / "rental_listings.metadata.json").write_text(
        json.dumps(
            {
                "output_sha256": _sha(silver_path),
                "source_snapshot": {"snapshot_id": silver_snapshot_id or metadata["snapshot_id"]},
            }
        )
    )
    return snapshot_dir, silver_dir


def _read_curated(output_dir: Path) -> pd.DataFrame:
    connection = duckdb.connect()
    try:
        return connection.execute(
            "SELECT * FROM read_parquet(?, hive_partitioning = false) ORDER BY observation_id",
            [str(output_dir / "**" / "*.parquet")],
        ).df()
    finally:
        connection.close()


def test_build_publishes_date_partitions_with_verifiable_metadata(tmp_path):
    snapshot_dir, silver_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "curated_observations"

    result = build_curated_observations(snapshot_dir, silver_dir, output_dir)

    assert result.row_count == 4
    assert result.snapshot_id == "snap-1"
    partitions = sorted(p.name for p in output_dir.iterdir() if p.is_dir())
    assert partitions == [
        "observed_date=2026-09-20", "observed_date=2026-09-21", "observed_date=2026-09-22"
    ]
    metadata = json.loads((output_dir / "_metadata.json").read_text())
    assert metadata["row_count"] == 4
    assert metadata["source_snapshot_id"] == "snap-1"
    assert metadata["columns"] == list(CURATED_COLUMNS)
    for relative, entry in metadata["files"].items():
        assert _sha(output_dir / relative) == entry["sha256"]
    loaded = _read_curated(output_dir)
    assert loaded.observation_id.tolist() == [101, 102, 103, 104]
    assert not list(tmp_path.glob(".curated_observations.*"))


def test_silver_from_another_snapshot_is_rejected_and_previous_output_kept(tmp_path):
    snapshot_dir, silver_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "curated_observations"
    build_curated_observations(snapshot_dir, silver_dir, output_dir)
    before = (output_dir / "_metadata.json").read_bytes()
    stale_snapshot, stale_silver = _write_inputs(tmp_path / "stale", silver_snapshot_id="other")

    with pytest.raises(CuratedBuildError, match="snapshot"):
        build_curated_observations(stale_snapshot, stale_silver, output_dir)

    assert (output_dir / "_metadata.json").read_bytes() == before


def test_tampered_silver_is_rejected(tmp_path):
    snapshot_dir, silver_dir = _write_inputs(tmp_path)
    metadata_path = silver_dir / "rental_listings.metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["output_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(CuratedBuildError, match="sha256"):
        build_curated_observations(snapshot_dir, silver_dir, tmp_path / "out")


def test_failed_publication_restores_previous_output(tmp_path, monkeypatch):
    snapshot_dir, silver_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "curated_observations"
    build_curated_observations(snapshot_dir, silver_dir, output_dir)
    before = (output_dir / "_metadata.json").read_bytes()

    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(curated, "_verify_readback", explode)
    with pytest.raises(RuntimeError, match="disk full"):
        build_curated_observations(snapshot_dir, silver_dir, output_dir)

    assert (output_dir / "_metadata.json").read_bytes() == before
    assert not list(tmp_path.glob(".curated_observations.*"))
