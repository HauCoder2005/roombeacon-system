"""Local Parquet fixtures: snapshot -> Silver subset -> curated observations."""

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from analytics.bronze.snapshot import write_bronze_snapshot
from roombeacon_processing.curated import build_curated_observations


def observations_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observation_id": [101, 102, 103, 104, 105],
            "rental_post_id": [11, 11, 11, 12, 13],
            "source_code": ["phongtro123", "phongtro123", "phongtro123", "mogi", "phongtro123"],
            "source_listing_id": ["a", "a", "a", "b", "c"],
            "crawl_run_id": ["r1", "r2", "r3", "r2", "r3"],
            "observed_at": pd.to_datetime(
                [
                    "2026-09-20 08:00", "2026-09-21 08:00", "2026-09-21 20:00",
                    "2026-09-21 09:00", "2026-09-21 10:00",
                ]
            ),
            "content_hash": ["h1", "h1", "h2", "h9", "h7"],
            "ingestion_origin": ["LIVE_CRAWLER"] * 5,
            "price_raw": ["3 triệu", "3 triệu", "3,5 triệu", "5 tỷ", "4 triệu"],
            "price_amount": [3_000_000.0, 3_000_000.0, 3_500_000.0, 5e9, 4_000_000.0],
            "currency": ["VND"] * 5,
            "period": ["MONTH"] * 5,
            "area_raw": ["20 m2", "20 m2", "20 m2", None, "25 m2"],
            "area_value": [20.0, 20.0, 20.0, None, 25.0],
        }
    )


def silver_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rental_post_id": [11, 12, 13],
            "source_code": ["phongtro123", "mogi", "phongtro123"],
            "title_raw": ["Phòng đẹp LH 0909123456", "Bán nhà", "Phòng"],
            "url": ["https://x/a", "https://x/b", "https://x/c"],
            "first_observed_at": pd.to_datetime(["2026-09-20 08:00", "2026-09-21 09:00", "2026-09-21 10:00"]),
            "last_observed_at": pd.to_datetime(["2026-09-21 20:00", "2026-09-21 09:00", "2026-09-21 10:00"]),
            "active_days": [1, 0, 0],
            "province_text_extracted": ["Hồ Chí Minh"] * 3,
            "district_text_extracted": ["Quận 1", "Quận 7", "Quận 1"],
            "ward_current": ["Phường Bến Nghé", None, "Phường Đa Kao"],
            "ward_mapping_status": ["MAPPED", "MISSING", "MAPPED"],
            "admin_consistency_status": ["CONSISTENT", "MISSING_EVIDENCE", "CONSISTENT"],
            "listing_intent": ["RENT", "SALE", "UNKNOWN"],
            "rental_scope": ["SINGLE_OR_ORDINARY_UNIT", "UNKNOWN", "SINGLE_OR_ORDINARY_UNIT"],
            "price_model_suitability": ["SUPPORTED", "EXCLUDED", "SUPPORTED"],
            "row_quality_status": ["READY", "REQUIRES_REVIEW", "READY_WITH_FLAGS"],
            "has_trusted_coordinate": [True, False, False],
            "duplicate_candidate_group": ["g1", None, None],
            "duplicate_candidate_status": ["UNIQUE_FINGERPRINT", "INSUFFICIENT_DATA", "POSSIBLE_DUPLICATE"],
            "price_amount_clean": [3_500_000.0, None, 4_000_000.0],
            "area_value_clean": [20.0, None, 25.0],
        }
    )


def _latest_and_evidence(observations: pd.DataFrame):
    last = observations.sort_values("observed_at").groupby("rental_post_id").tail(1).sort_values("rental_post_id")
    latest = pd.DataFrame(
        {
            "rental_post_id": last.rental_post_id.values,
            "source_code": last.source_code.values,
            "source_listing_id": last.source_listing_id.values,
            "title_raw": ["t"] * len(last),
            "price_amount": last.price_amount.values,
            "area_value": last.area_value.values,
            "full_address_text": [None] * len(last),
            "location_raw": ["loc"] * len(last),
            "best_address_text": ["loc"] * len(last),
            "latest_observed_at": last.observed_at.values,
        }
    )
    evidence = pd.DataFrame(
        {
            "rental_post_id": last.rental_post_id.values,
            "evidence_observation_id": last.observation_id.values,
            "evidence_version_time_matches": [1] * len(last),
            "evidence_price_id": [1] * len(last),
            "price_raw": last.price_raw.values,
            "currency": ["VND"] * len(last),
            "period": ["MONTH"] * len(last),
            "evidence_area_id": [1] * len(last),
            "area_raw": last.area_raw.values,
            "price_lineage_aligned": [True] * len(last),
            "area_lineage_aligned": [True] * len(last),
        }
    )
    return latest, evidence


def write_pipeline_inputs(root: Path, *, snapshot_id: str = "snap-wh") -> dict[str, Path]:
    snapshot_dir, silver_dir, curated_dir = root / "snapshot", root / "silver", root / "curated"
    observations = observations_frame()
    latest, evidence = _latest_and_evidence(observations)
    write_bronze_snapshot(
        latest, evidence, snapshot_dir, source_database="fixture",
        snapshot_id=snapshot_id, observations=observations,
    )
    silver_dir.mkdir(parents=True)
    silver_path = silver_dir / "rental_listings.parquet"
    connection = duckdb.connect()
    connection.register("s", silver_frame())
    connection.execute("COPY s TO ? (FORMAT PARQUET)", [str(silver_path)])
    connection.close()
    (silver_dir / "rental_listings.metadata.json").write_text(
        json.dumps(
            {
                "output_sha256": hashlib.sha256(silver_path.read_bytes()).hexdigest(),
                "source_snapshot": {"snapshot_id": snapshot_id},
            }
        )
    )
    build_curated_observations(snapshot_dir, silver_dir, curated_dir)
    return {"snapshot": snapshot_dir, "silver": silver_dir, "curated": curated_dir}


@pytest.fixture
def pipeline_inputs(tmp_path) -> dict[str, Path]:
    return write_pipeline_inputs(tmp_path)
