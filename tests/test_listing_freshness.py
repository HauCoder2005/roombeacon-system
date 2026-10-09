"""Listing freshness: posted dates interpreted at observation time, never guessed."""

from datetime import datetime
import json

import duckdb
import pandas as pd
import pytest

from roombeacon_processing.freshness import (
    FreshnessError,
    build_listing_freshness,
    interpret_posted_at,
    publish_listing_freshness,
)


SEEN = datetime(2026, 9, 21, 10, 0)


@pytest.mark.parametrize(
    "raw, expected, status",
    [
        ("Vừa xong", datetime(2026, 9, 21, 10, 0), "RELATIVE"),
        ("Hôm nay", datetime(2026, 9, 21, 10, 0), "RELATIVE"),
        ("hôm qua", datetime(2026, 9, 20, 10, 0), "RELATIVE"),
        ("Cập nhật: 3 ngày trước", datetime(2026, 9, 18, 10, 0), "RELATIVE"),
        ("2 tuần trước", datetime(2026, 9, 7, 10, 0), "RELATIVE"),
        ("5 tháng trước", datetime(2026, 4, 24, 10, 0), "RELATIVE"),
        ("6 năm trước", datetime(2020, 9, 22, 10, 0), "RELATIVE"),
        ("45 phút trước", datetime(2026, 9, 21, 9, 15), "RELATIVE"),
        ("15/03/2019", datetime(2019, 3, 15), "ABSOLUTE"),
        ("Ngày đăng: 01-09-2026", datetime(2026, 9, 1), "ABSOLUTE"),
        ("2026-08-20", datetime(2026, 8, 20), "ABSOLUTE"),
        ("31/02/2026", None, "UNPARSED"),
        ("Tin VIP", None, "UNPARSED"),
        ("", None, "MISSING"),
        (None, None, "MISSING"),
        ("25/12/2026", None, "IMPLAUSIBLE"),
        ("01/01/1999", None, "IMPLAUSIBLE"),
    ],
)
def test_interpret_posted_at(raw, expected, status):
    assert interpret_posted_at(raw, SEEN) == (expected, status)


def _observations():
    return pd.DataFrame(
        {
            "rental_post_id": [1, 1, 2, 3, 4],
            "observation_id": [10, 11, 20, 30, 40],
            "observed_at": pd.to_datetime(["2026-09-21 10:00", "2026-10-01 10:00", "2026-09-25 08:00", "2026-09-22 00:00", "2026-09-23 00:00"]),
            "posted_at_raw": ["2 ngày trước", "Hôm nay", "15/03/2019", None, "Tin VIP"],
            "property_type_raw": ["Phòng trọ", None, "Căn hộ", None, None],
        }
    )


def test_freshness_uses_the_earliest_evidence_and_the_threshold():
    fresh = build_listing_freshness(_observations(), stale_after_days=90).set_index("rental_post_id")

    # Post 1: "2 days ago" on 09-21 beats the later "today" bump on 10-01.
    assert fresh.loc[1, "posted_at"] == pd.Timestamp("2026-09-19 10:00")
    assert fresh.loc[1, "listing_age_days"] == 12
    assert fresh.loc[1, "freshness_status"] == "FRESH"
    assert fresh.loc[1, "property_type_raw"] == "Phòng trọ"
    assert fresh.loc[2, "freshness_status"] == "STALE"
    assert fresh.loc[2, "posted_at_status"] == "ABSOLUTE"
    assert fresh.loc[3, "freshness_status"] == "UNKNOWN" and fresh.loc[3, "posted_at_status"] == "MISSING"
    assert fresh.loc[4, "freshness_status"] == "UNKNOWN" and fresh.loc[4, "posted_at_status"] == "UNPARSED"
    assert pd.isna(fresh.loc[4, "posted_at"])
    assert (fresh["stale_after_days"] == 90).all()


def _write_snapshot(directory, observations, with_posted=True):
    directory.mkdir()
    frame = observations if with_posted else observations.drop(columns=["posted_at_raw", "property_type_raw"])
    connection = duckdb.connect()
    connection.register("o", frame)
    connection.execute(f"COPY o TO '{directory / 'observations.parquet'}' (FORMAT PARQUET)")
    connection.close()


def test_publish_writes_parquet_and_metadata_atomically(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot"
    _write_snapshot(snapshot, _observations())
    monkeypatch.setattr(
        "roombeacon_processing.freshness.verify_bronze_observations",
        lambda path: (path / "observations.parquet", {"snapshot_id": "snap-1"}),
    )

    result = publish_listing_freshness(snapshot, tmp_path / "freshness", stale_after_days=90)

    assert result.row_count == 4 and result.snapshot_id == "snap-1"
    metadata = json.loads((tmp_path / "freshness" / "listing_freshness.metadata.json").read_text())
    assert metadata["stale_after_days"] == 90
    assert metadata["freshness_counts"] == {"FRESH": 1, "STALE": 1, "UNKNOWN": 2}
    stored = duckdb.sql(f"SELECT count(*) FROM read_parquet('{tmp_path / 'freshness' / 'listing_freshness.parquet'}')").fetchone()[0]
    assert stored == 4
    assert not list((tmp_path / "freshness").glob(".tmp*"))


def test_publish_refuses_snapshots_without_posted_dates(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot"
    _write_snapshot(snapshot, _observations(), with_posted=False)
    monkeypatch.setattr(
        "roombeacon_processing.freshness.verify_bronze_observations",
        lambda path: (path / "observations.parquet", {"snapshot_id": "old"}),
    )

    with pytest.raises(FreshnessError, match="refresh the Bronze snapshot"):
        publish_listing_freshness(snapshot, tmp_path / "freshness")
