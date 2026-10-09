"""Bounded, watermark-aware Bronze snapshot extraction.

The snapshot job is the only component allowed to read MySQL Bronze. These
tests use an in-memory fake DB-API connection; no database is contacted.
"""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from analytics.bronze import snapshot as snap


ROOT = Path(__file__).resolve().parents[1]


def _payload(location, lat=None, lon=None):
    return json.dumps(
        {
            "location_raw": location,
            "map_location": {
                "provider": "google" if lat is not None else None,
                "latitude": None if lat is None else str(lat),
                "longitude": None if lon is None else str(lon),
                "query_raw": None,
            },
        }
    )


def _tables():
    """Two posts; post 1 has two versions with an unchanged content hash."""
    return {
        "platforms": pd.DataFrame({"id": [1], "code": ["phongtro123"], "name": ["PT123"]}),
        "rental_posts": pd.DataFrame(
            {
                "id": [11, 12],
                "platform_id": [1, 1],
                "platform_post_id": ["a", "b"],
                "first_observed_at": pd.to_datetime(["2026-09-20 01:00", "2026-09-21 01:00"]),
                "last_observed_at": pd.to_datetime(["2026-09-22 01:00", "2026-09-21 01:00"]),
            }
        ),
        "rental_post_versions": pd.DataFrame(
            {
                "id": [101, 102, 103],
                "rental_post_id": [11, 11, 12],
                "crawl_run_id": ["run_1", "run_2", "run_2"],
                "observed_at": pd.to_datetime(
                    ["2026-09-20 01:00", "2026-09-22 01:00", "2026-09-21 01:00"]
                ),
                "url": ["u1", "u1", "u2"],
                "title_raw": ["Phòng 1", "Phòng 1", "Phòng 2"],
                "content_hash": ["h1", "h1", "h2"],
                "ingestion_origin": ["LIVE_CRAWLER"] * 3,
                "source_payload": [_payload("Q1"), _payload("Q1"), _payload("Q3")],
            }
        ),
        "post_prices": pd.DataFrame(
            {
                "id": [201, 202, 203, 204],
                "rental_post_id": [11, 11, 11, 12],
                "rental_post_version_id": [101, 102, 102, 103],
                "price_raw": ["3 triệu", "3,1 triệu", "3,2 triệu", "4 triệu"],
                "price_amount": [3_000_000, 3_100_000, 3_200_000, 4_000_000],
                "currency": ["VND"] * 4,
                "period": ["MONTH"] * 4,
            }
        ),
        "post_addresses": pd.DataFrame(
            {
                "id": [301],
                "rental_post_id": [11],
                "rental_post_version_id": [101],
                "full_address_text": ["1 Lê Lợi, Bến Nghé, Quận 1"],
                "created_at": pd.to_datetime(["2026-09-20 01:00"]),
            }
        ),
        "post_details": pd.DataFrame(
            {
                "id": [401, 402, 403],
                "rental_post_id": [11, 11, 12],
                "rental_post_version_id": [101, 102, 103],
                "area_raw": ["20 m2", "20 m2", "25 m2"],
                "area_value": [20.0, 20.0, 25.0],
                "posted_at_raw": ["2 ngày trước", "Hôm nay", "15/03/2019"],
                "property_type_raw": ["Phòng trọ", "Phòng trọ", None],
            }
        ),
    }


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((" ".join(sql.split()), params))
        normalized = " ".join(sql.split()).upper()
        self._rows, self.description = [], None
        if normalized.startswith("SELECT COUNT(*), MAX(ID), MAX(OBSERVED_AT) FROM RENTAL_POST_VERSIONS"):
            versions = self.conn.tables["rental_post_versions"]
            self._rows = [(len(versions), int(versions.id.max()), versions.observed_at.max().to_pydatetime())]
            self.description = [("count",), ("max_id",), ("max_observed_at",)]
            return
        for name in ("rental_post_versions", "post_prices", "post_addresses", "post_details", "rental_posts", "platforms"):
            if f"FROM {name.upper()}" in normalized:
                frame = self.conn.tables[name]
                params = params or {}
                if "max_version_id" in params:
                    key = "id" if name == "rental_post_versions" else "rental_post_version_id"
                    frame = frame[frame[key] <= params["max_version_id"]]
                if "after_id" in params:
                    frame = frame[frame["id"] > params["after_id"]].sort_values("id").head(params["page_rows"])
                self.description = [(column,) for column in frame.columns]
                self._rows = [tuple(row) for row in frame.itertuples(index=False)]
                return

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchmany(self, size):
        batch, self._rows = self._rows[:size], self._rows[size:]
        return batch

    def fetchall(self):
        batch, self._rows = self._rows, []
        return batch


class FakeConnection:
    def __init__(self, tables):
        self.tables = tables
        self.executed = []
        self.closed = False
        self.rolled_back = False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_env_local_is_loaded_and_dotenv_is_never_read(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("RB_SNAPSHOT_PROBE=from_dotenv\nRB_ONLY_DOTENV=1\n")
    (tmp_path / ".env.local").write_text("RB_SNAPSHOT_PROBE=from_env_local\n")
    monkeypatch.delenv("RB_SNAPSHOT_PROBE", raising=False)
    monkeypatch.delenv("RB_ONLY_DOTENV", raising=False)

    assert snap.load_env_local(tmp_path) is True

    assert os.environ["RB_SNAPSHOT_PROBE"] == "from_env_local"
    assert "RB_ONLY_DOTENV" not in os.environ


def test_missing_env_local_does_not_fall_back_to_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("RB_ONLY_DOTENV=1\n")
    monkeypatch.delenv("RB_ONLY_DOTENV", raising=False)

    assert snap.load_env_local(tmp_path) is False
    assert "RB_ONLY_DOTENV" not in os.environ


def test_snapshot_module_never_references_dotenv_file():
    source = (ROOT / "analytics/bronze/snapshot.py").read_text(encoding="utf-8")
    assert '".env"' not in source
    assert "'.env'" not in source


def test_extraction_is_bounded_by_watermark_inside_read_only_snapshot():
    connection = FakeConnection(_tables())

    frames, watermark = snap.extract_bronze_frames(connection)

    assert watermark.max_version_id == 103
    assert watermark.version_count == 3
    statements = [sql.upper() for sql, _ in connection.executed]
    assert any("MAX_EXECUTION_TIME" in sql for sql in statements)
    assert any("WITH CONSISTENT SNAPSHOT, READ ONLY" in sql for sql in statements)
    bounded = [
        (sql, params) for sql, params in connection.executed
        if any(f"FROM {name}" in sql for name in ("rental_post_versions", "post_prices", "post_addresses", "post_details"))
        and "MAX(id)" not in sql
    ]
    assert {sql.split(" FROM ")[1].split()[0] for sql, _ in bounded} == {
        "rental_post_versions", "post_prices", "post_addresses", "post_details"
    }
    for sql, params in bounded:
        assert "%(max_version_id)s" in sql
        assert params["max_version_id"] == 103
    assert connection.rolled_back is True
    assert set(frames) == {
        "platforms", "rental_posts", "rental_post_versions",
        "post_prices", "post_addresses", "post_details",
    }


def test_observation_history_keeps_one_row_per_version_with_latest_child_rows():
    frames = _tables()

    history = snap.build_observation_history(frames)

    assert history.observation_id.tolist() == [101, 102, 103]
    assert history.rental_post_id.tolist() == [11, 11, 12]
    assert history.source_code.unique().tolist() == ["phongtro123"]
    # Version 102 has two price rows; the highest child id wins, as in v_latest_posts.
    assert history.set_index("observation_id").loc[102, "price_amount"] == 3_200_000
    assert history.set_index("observation_id").loc[102, "price_raw"] == "3,2 triệu"
    assert set(snap.REQUIRED_OBSERVATION_COLUMNS) <= set(history.columns)
    assert not {"source_payload", "seller_phone", "seller_name"} & set(history.columns)


def test_build_snapshot_publishes_three_files_with_watermark(tmp_path):
    connection = FakeConnection(_tables())

    metadata = snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: connection,
        source_database="fixture",
    )

    assert metadata["status"] == "PUBLISHED"
    assert metadata["watermark"]["max_version_id"] == 103
    assert metadata["observation_row_count"] == 3
    for name in ("latest_posts.parquet", "raw_evidence.parquet", "observations.parquet", "metadata.json"):
        assert (tmp_path / name).is_file()
    latest, evidence, context = snap.load_bronze_snapshot(tmp_path)
    assert len(latest) == len(evidence) == 2
    observations, obs_context = snap.load_bronze_observations(tmp_path)
    assert observations.observation_id.tolist() == [101, 102, 103]
    assert obs_context["snapshot_id"] == context["snapshot_id"]
    assert connection.closed is True


def test_unchanged_watermark_skips_republication(tmp_path):
    first = snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: FakeConnection(_tables()),
        source_database="fixture",
    )
    before = (tmp_path / "metadata.json").read_bytes()

    connection = FakeConnection(_tables())
    second = snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: connection,
        source_database="fixture",
    )

    assert second["status"] == "UNCHANGED"
    # Only session setup plus the watermark probe ran; no table was scanned.
    assert not any("FROM rental_post_versions WHERE" in sql for sql, _ in connection.executed)
    assert not any("FROM post_prices" in sql for sql, _ in connection.executed)
    assert connection.closed is True
    assert second["snapshot_id"] == first["snapshot_id"]
    assert (tmp_path / "metadata.json").read_bytes() == before


def test_new_versions_advance_the_watermark(tmp_path):
    snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: FakeConnection(_tables()),
        source_database="fixture",
    )
    tables = _tables()
    tables["rental_post_versions"] = pd.concat(
        [
            tables["rental_post_versions"],
            pd.DataFrame(
                {
                    "id": [104], "rental_post_id": [12], "crawl_run_id": ["run_3"],
                    "observed_at": pd.to_datetime(["2026-09-23 01:00"]), "url": ["u2"],
                    "title_raw": ["Phòng 2"], "content_hash": ["h3"],
                    "ingestion_origin": ["LIVE_CRAWLER"], "source_payload": [_payload("Q3")],
                }
            ),
        ],
        ignore_index=True,
    )

    metadata = snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: FakeConnection(tables),
        source_database="fixture",
    )

    assert metadata["status"] == "PUBLISHED"
    assert metadata["watermark"]["max_version_id"] == 104
    assert metadata["observation_row_count"] == 4


def test_snapshot_without_observations_is_rejected_by_history_loader(tmp_path):
    from tests.test_bronze_snapshot import _frames

    latest, evidence = _frames()
    snap.write_bronze_snapshot(latest, evidence, tmp_path, source_database="fixture")

    with pytest.raises(snap.BronzeSnapshotNotFoundError, match="observations"):
        snap.load_bronze_observations(tmp_path)


def test_packaged_snapshot_sql_matches_notebook_copy():
    packaged = (ROOT / "analytics/bronze/sql/latest_evidence.sql").read_bytes()
    notebook = (ROOT / "notebooks/sql/eda_snapshot.sql").read_bytes()
    assert packaged == notebook


def test_extraction_streams_batches_into_duckdb_without_pandas_tables():
    import duckdb

    tables = _tables()
    connection = FakeConnection(tables)
    duck = duckdb.connect()
    fetch_sizes = []
    original = FakeCursor.fetchmany

    def recording_fetchmany(self, size):
        fetch_sizes.append(size)
        return original(self, size)

    FakeCursor.fetchmany = recording_fetchmany
    try:
        watermark, extracted = snap.extract_bronze_to_duckdb(connection, duck)
    finally:
        FakeCursor.fetchmany = original

    assert extracted and watermark.max_version_id == 103
    assert set(fetch_sizes) == {snap.FETCH_BATCH_ROWS}
    for name, frame in tables.items():
        assert duck.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == len(frame)
    # Declared staging types, independent of what the first batch looked like.
    types = dict(duck.execute("SELECT column_name, data_type FROM information_schema.columns "
                              "WHERE table_name = 'post_prices'").fetchall())
    assert types["price_amount"] == "DOUBLE"


def test_snapshot_job_cleans_up_its_staging_database(tmp_path):
    snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: FakeConnection(_tables()),
        source_database="fixture",
    )

    assert not list(tmp_path.glob(".staging.*"))
    assert not list(tmp_path.glob(".*.tmp"))


def test_dags_use_the_airflow_sdk_skip_exception():
    for dag in ("roombeacon_bronze_snapshot.py", "roombeacon_warehouse_load.py"):
        source = (ROOT / "airflow/dags/analytics" / dag).read_text(encoding="utf-8")
        assert "from airflow.sdk.exceptions import AirflowSkipException" in source
        assert "from airflow.exceptions import" not in source


def test_large_tables_are_read_in_bounded_key_range_pages(monkeypatch):
    monkeypatch.setattr(snap, "FETCH_BATCH_ROWS", 2)
    tables = _tables()
    connection = FakeConnection(tables)

    frames, _ = snap.extract_bronze_frames(connection)

    for name in ("rental_posts", "rental_post_versions", "post_prices", "post_addresses", "post_details"):
        pages = [
            (sql, p) for sql, p in connection.executed
            if f"FROM {name} " in sql + " " and "MAX(id)" not in sql
        ]
        assert pages, name
        for sql, params in pages:
            assert "id > %(after_id)s" in sql and "ORDER BY id LIMIT %(page_rows)s" in sql, sql
            assert params["page_rows"] == 2
        # Pages continue after the last id seen and stop on a short page.
        assert [p["after_id"] for _, p in pages][0] == 0
        assert len(frames[name]) == len(tables[name])
    versions = [
        p["after_id"] for sql, p in connection.executed
        if "FROM rental_post_versions " in sql + " " and "MAX(id)" not in sql
    ]
    assert versions == [0, 102]


def test_failed_rollback_does_not_mask_the_original_error():
    class Broken(FakeConnection):
        def rollback(self):
            raise RuntimeError("connection already lost")

    class Timeout(FakeCursor):
        def execute(self, sql, params=None):
            if "FROM post_prices" in sql:
                raise TimeoutError("timed out")
            return super().execute(sql, params)

    connection = Broken(_tables())
    connection.cursor = lambda: Timeout(connection)

    with pytest.raises(snap.BronzeSnapshotError, match="post_prices: TimeoutError"):
        snap.extract_bronze_frames(connection)
    assert connection.closed is True


def test_observation_history_carries_raw_posted_dates_and_property_type():
    connection = FakeConnection(_tables())
    frames, _ = snap.extract_bronze_frames(connection)

    history = snap.build_observation_history(frames).set_index("observation_id")

    assert history.loc[101, "posted_at_raw"] == "2 ngày trước"
    assert history.loc[103, "posted_at_raw"] == "15/03/2019"
    assert history.loc[101, "property_type_raw"] == "Phòng trọ"
    detail_sql = next(sql for sql, _ in connection.executed if "FROM post_details" in sql)
    assert "posted_at_raw" in detail_sql and "property_type_raw" in detail_sql


def test_snapshot_without_posted_date_columns_is_not_current(tmp_path):
    import json

    connection = FakeConnection(_tables())
    metadata = snap.build_bronze_snapshot(
        project_root=ROOT, snapshot_dir=tmp_path, connect=lambda: connection, source_database="fixture",
    )
    watermark = snap.BronzeWatermark(**metadata["watermark"])
    assert snap.is_snapshot_current(tmp_path, watermark)

    stored = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    stored["observation_columns"] = [c for c in stored["observation_columns"] if c not in {"posted_at_raw", "property_type_raw"}]
    (tmp_path / "metadata.json").write_text(json.dumps(stored), encoding="utf-8")

    assert not snap.is_snapshot_current(tmp_path, watermark)
