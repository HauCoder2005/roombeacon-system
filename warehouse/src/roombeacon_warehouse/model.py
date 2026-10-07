"""Analytical / dimensional modeling from curated observations and Silver.

Runs entirely offline on Parquet with DuckDB; nothing here talks to MySQL or
ClickHouse. Every table is written to a staging Parquet file so the loader can
stream it in bounded batches: memory does not grow with observation history.
Surrogate keys are deterministic hashes of natural keys (stable across loads).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pandas as pd

from .schema import LOAD_ORDER, TABLES


CURATED_METADATA = "_metadata.json"
SILVER_FILENAME = "rental_listings.parquet"
SILVER_METADATA = "rental_listings.metadata.json"
DUCKDB_MEMORY_LIMIT = "256MB"
DUCKDB_THREADS = 1
STREAM_VECTORS = 25  # 25 x 2048 rows per streamed batch

CURATED_COLUMNS = (
    "observation_id", "rental_post_id", "source_code", "crawl_run_id", "observed_at",
    "observed_date", "version_seq", "content_hash", "is_content_change", "is_price_change",
    "price_amount", "price_status", "area_value", "area_status", "price_per_m2",
    "province", "district", "ward", "listing_intent", "rental_scope",
    "is_market_eligible", "has_trusted_coordinate",
)
SILVER_COLUMNS = (
    "rental_post_id", "source_code", "first_observed_at", "last_observed_at", "active_days",
    "province_text_extracted", "district_text_extracted", "ward_current",
    "price_amount_clean", "area_value_clean", "listing_intent", "rental_scope",
    "price_model_suitability", "row_quality_status", "has_trusted_coordinate",
    "duplicate_candidate_status",
)


class WarehouseModelError(RuntimeError):
    """Raised when warehouse inputs are missing, stale or tampered with."""


@dataclass(frozen=True)
class WarehouseModel:
    snapshot_id: str
    curated_metadata_sha256: str
    silver_output_sha256: str
    files: dict[str, Path]
    counts: dict[str, int] = field(default_factory=dict)

    def row_counts(self) -> dict[str, int]:
        return dict(self.counts)

    def iter_batches(self, name: str, vectors: int = STREAM_VECTORS) -> Iterator[pd.DataFrame]:
        """Yield the staged table in bounded pandas batches, in declared column order."""
        columns = ", ".join(f'"{c}"' for c in TABLES[name].column_names)
        connection = _connect()
        try:
            result = connection.execute(
                f"SELECT {columns} FROM read_parquet({_literal(self.files[name])})"
            )
            while True:
                batch = result.fetch_df_chunk(vectors)
                if batch.empty:
                    break
                yield batch
        finally:
            connection.close()

    def frame(self, name: str) -> pd.DataFrame:
        """Whole staged table (tests and small dimensions only)."""
        batches = list(self.iter_batches(name))
        if not batches:
            return pd.DataFrame(columns=TABLES[name].column_names)
        return pd.concat(batches, ignore_index=True)


def stable_key(*parts: Any) -> int:
    """Deterministic positive Int64 surrogate key for a natural key."""
    text = "\x1f".join("\x00" if part is None or part is pd.NA else str(part) for part in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big") & (2**63 - 1) or 1


def _literal(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _connect(temp_directory: Path | None = None) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    connection.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    connection.execute(f"SET threads = {int(DUCKDB_THREADS)}")
    connection.execute("SET preserve_insertion_order = false")
    if temp_directory is not None:
        connection.execute(f"SET temp_directory = {_literal(temp_directory)}")
    return connection


def verify_curated(curated_dir: Path) -> tuple[list[Path], dict[str, Any], str]:
    curated_dir = Path(curated_dir)
    metadata_path = curated_dir / CURATED_METADATA
    if not metadata_path.is_file():
        raise WarehouseModelError(f"Curated observations are not published in {curated_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    files = metadata.get("files") or {}
    if not files:
        raise WarehouseModelError("Curated metadata lists no files")
    paths = []
    for relative, entry in sorted(files.items()):
        path = curated_dir / relative
        if not path.is_file() or _sha256(path) != entry.get("sha256"):
            raise WarehouseModelError(f"Curated file does not match metadata sha256: {relative}")
        paths.append(path)
    return paths, metadata, _sha256(metadata_path)


def verify_silver(silver_dir: Path, snapshot_id: str) -> tuple[Path, dict[str, Any]]:
    silver_path = Path(silver_dir) / SILVER_FILENAME
    metadata_path = Path(silver_dir) / SILVER_METADATA
    if not silver_path.is_file() or not metadata_path.is_file():
        raise WarehouseModelError(f"Canonical Silver is not published in {silver_dir}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not metadata.get("output_sha256") or _sha256(silver_path) != metadata["output_sha256"]:
        raise WarehouseModelError("Canonical Silver does not match its metadata output_sha256")
    silver_snapshot = (metadata.get("source_snapshot") or {}).get("snapshot_id")
    if silver_snapshot != snapshot_id:
        raise WarehouseModelError(
            f"Silver snapshot {silver_snapshot} differs from curated snapshot {snapshot_id}"
        )
    return silver_path, metadata


def _none(value: Any) -> Any:
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return None
    return value


def _location_keys(province: Any, district: Any, ward: Any) -> tuple[int, int]:
    province, district, ward = _none(province), _none(district), _none(ward)
    unknown = stable_key("UNKNOWN", None, None, None)
    district_key = stable_key("DISTRICT", province, district, None) if district is not None else unknown
    if ward is not None:
        return stable_key("WARD", province, district, ward), district_key
    return district_key, district_key


def build_location_tables(triples: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (dim_location, triple -> key map) for distinct admin triples."""
    rows: dict[int, dict[str, Any]] = {
        stable_key("UNKNOWN", None, None, None): {
            "location_level": "UNKNOWN", "province": None, "district": None, "ward": None,
            "parent_location_key": None,
        }
    }
    mapping = []
    for province, district, ward in triples.drop_duplicates().itertuples(index=False, name=None):
        province, district, ward = _none(province), _none(district), _none(ward)
        district_key = None
        if district is not None:
            district_key = stable_key("DISTRICT", province, district, None)
            rows.setdefault(district_key, {
                "location_level": "DISTRICT", "province": province, "district": district,
                "ward": None, "parent_location_key": None,
            })
        if ward is not None:
            rows.setdefault(stable_key("WARD", province, district, ward), {
                "location_level": "WARD", "province": province, "district": district,
                "ward": ward, "parent_location_key": district_key,
            })
        location_key, district_location_key = _location_keys(province, district, ward)
        mapping.append((province, district, ward, location_key, district_location_key))
    dim = pd.DataFrame([{"location_key": key, **value} for key, value in rows.items()])
    dim["parent_location_key"] = dim["parent_location_key"].astype("Int64")
    dim = dim.sort_values("location_key", kind="stable").reset_index(drop=True)
    key_map = pd.DataFrame(
        mapping,
        columns=["province", "district", "ward", "location_key", "district_location_key"],
    ).astype({"province": "object", "district": "object", "ward": "object"})
    return dim[TABLES["dim_location"].column_names], key_map


def build_dim_date(first: date, last: date) -> pd.DataFrame:
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    stamps = pd.to_datetime(pd.Series(days))
    iso = stamps.dt.isocalendar()
    frame = pd.DataFrame(
        {
            "date_key": (stamps.dt.year * 10000 + stamps.dt.month * 100 + stamps.dt.day).astype("int64"),
            "calendar_date": days,
            "year": stamps.dt.year.astype("int64"),
            "quarter": stamps.dt.quarter.astype("int64"),
            "month": stamps.dt.month.astype("int64"),
            "day": stamps.dt.day.astype("int64"),
            "iso_week": iso.week.astype("int64").to_numpy(),
            "day_of_week": iso.day.astype("int64").to_numpy(),
        }
    )
    frame["is_weekend"] = frame["day_of_week"].ge(6)
    return frame[TABLES["dim_date"].column_names]


DATE_KEY = "CAST(year({0}) * 10000 + month({0}) * 100 + day({0}) AS BIGINT)"

FACT_OBSERVATION_SQL = f"""
SELECT c.observation_id, c.rental_post_id, {DATE_KEY.format('c.observed_date')} AS date_key,
       c.observed_date, c.observed_at, src.source_key, loc.location_key, loc.district_location_key,
       c.crawl_run_id, c.version_seq, c.is_content_change, c.is_price_change,
       c.price_amount, c.price_status, c.area_value, c.area_status, c.price_per_m2,
       c.listing_intent, c.rental_scope, c.is_market_eligible, c.has_trusted_coordinate,
       $snapshot_id AS snapshot_id
FROM curated c
JOIN source_map src ON src.source_code = c.source_code
JOIN location_map loc
  ON loc.province IS NOT DISTINCT FROM c.province
 AND loc.district IS NOT DISTINCT FROM c.district
 AND loc.ward IS NOT DISTINCT FROM c.ward
"""

FACT_SNAPSHOT_SQL = """
WITH history AS (
    SELECT rental_post_id, COUNT(*) AS observation_count,
           COUNT(*) FILTER (WHERE is_content_change) AS content_version_count
    FROM curated GROUP BY rental_post_id
)
SELECT $snapshot_id AS snapshot_id, CAST($as_of_date_key AS BIGINT) AS as_of_date_key,
       s.rental_post_id, src.source_key, loc.location_key, loc.district_location_key,
       s.first_observed_at, s.last_observed_at, CAST(s.active_days AS BIGINT) AS active_days,
       COALESCE(h.observation_count, 0) AS observation_count,
       COALESCE(h.content_version_count, 0) AS content_version_count,
       s.price_amount_clean, s.area_value_clean, s.listing_intent, s.rental_scope,
       s.price_model_suitability, s.row_quality_status,
       COALESCE(s.has_trusted_coordinate, FALSE) AS has_trusted_coordinate,
       s.duplicate_candidate_status
FROM silver s
JOIN source_map src ON src.source_code = s.source_code
JOIN location_map loc
  ON loc.province IS NOT DISTINCT FROM s.province_text_extracted
 AND loc.district IS NOT DISTINCT FROM s.district_text_extracted
 AND loc.ward IS NOT DISTINCT FROM s.ward_current
LEFT JOIN history h ON h.rental_post_id = s.rental_post_id
"""

MARKET_DAILY_SQL = """
WITH daily_state AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY rental_post_id, date_key ORDER BY observed_at DESC, observation_id DESC
    ) AS state_rank
    FROM fact
), first_seen AS (
    SELECT rental_post_id, MIN(date_key) AS first_date_key FROM fact GROUP BY rental_post_id
), activity AS (
    SELECT date_key, district_location_key, source_key,
           COUNT(*) AS observations,
           COUNT(*) FILTER (WHERE is_content_change) AS content_changes,
           COUNT(*) FILTER (WHERE is_price_change) AS price_changes
    FROM fact
    GROUP BY ALL
), state AS (
    SELECT s.date_key, s.district_location_key, s.source_key,
           ANY_VALUE(s.observed_date) AS market_date,
           COUNT(*) AS listings_observed,
           COUNT(*) FILTER (WHERE f.first_date_key = s.date_key) AS new_listings,
           COUNT(*) FILTER (WHERE s.is_market_eligible) AS market_eligible_listings,
           quantile_cont(s.price_amount, 0.5) FILTER (WHERE s.is_market_eligible) AS median_price,
           quantile_cont(s.price_amount, 0.25) FILTER (WHERE s.is_market_eligible) AS p25_price,
           quantile_cont(s.price_amount, 0.75) FILTER (WHERE s.is_market_eligible) AS p75_price,
           quantile_cont(s.price_per_m2, 0.5) FILTER (WHERE s.is_market_eligible) AS median_price_per_m2,
           quantile_cont(s.area_value, 0.5)
               FILTER (WHERE s.is_market_eligible AND s.area_status = 'ACCEPTED_CLEAN') AS median_area
    FROM daily_state s
    JOIN first_seen f USING (rental_post_id)
    WHERE s.state_rank = 1
    GROUP BY s.date_key, s.district_location_key, s.source_key
)
SELECT state.date_key, state.market_date, state.district_location_key, state.source_key,
       state.listings_observed, state.new_listings, activity.observations,
       activity.content_changes, activity.price_changes, state.market_eligible_listings,
       state.median_price, state.p25_price, state.p75_price, state.median_price_per_m2,
       state.median_area, $snapshot_id AS snapshot_id
FROM state
JOIN activity USING (date_key, district_location_key, source_key)
"""

ORDER_BY = {
    "fact_listing_observation": "observation_id",
    "fact_listing_snapshot": "rental_post_id",
    "agg_market_daily": "date_key, district_location_key, source_key",
}


def build_warehouse_model(curated_dir: Path, silver_dir: Path, staging_dir: Path) -> WarehouseModel:
    """Verify inputs and write every warehouse table to ``staging_dir``."""
    curated_files, curated_metadata, curated_metadata_sha = verify_curated(Path(curated_dir))
    snapshot_id = curated_metadata["source_snapshot_id"]
    silver_path, silver_metadata = verify_silver(Path(silver_dir), snapshot_id)
    if curated_metadata.get("silver_output_sha256") != silver_metadata["output_sha256"]:
        raise WarehouseModelError("Curated observations were built from a different Silver file")

    staging_dir = Path(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    files = {name: staging_dir / f"{name}.parquet" for name in LOAD_ORDER}
    curated_list = "[" + ", ".join(_literal(p) for p in curated_files) + "]"
    connection = _connect(staging_dir / ".spill")
    try:
        connection.execute(
            "CREATE VIEW curated AS SELECT "
            + ", ".join(f'"{c}"' for c in CURATED_COLUMNS)
            + f" FROM read_parquet({curated_list}, hive_partitioning = false)"
        )
        connection.execute(
            "CREATE VIEW silver AS SELECT "
            + ", ".join(f'"{c}"' for c in SILVER_COLUMNS)
            + f" FROM read_parquet({_literal(silver_path)})"
        )
        (curated_rows,) = connection.execute("SELECT COUNT(*) FROM curated").fetchone()
        if curated_rows != curated_metadata.get("row_count"):
            raise WarehouseModelError("Curated row count differs from metadata")

        sources = sorted(
            row[0] for row in connection.execute(
                "SELECT source_code FROM curated UNION SELECT source_code FROM silver"
            ).fetchall()
        )
        dim_source = pd.DataFrame(
            {"source_key": [stable_key("SOURCE", s) for s in sources], "source_code": sources}
        )
        triples = connection.execute(
            "SELECT province, district, ward FROM curated UNION "
            "SELECT province_text_extracted, district_text_extracted, ward_current FROM silver"
        ).df()
        dim_location, location_map = build_location_tables(triples)
        first_day, as_of = connection.execute(
            "SELECT MIN(observed_date), MAX(CAST(observed_at AS DATE)) FROM curated"
        ).fetchone()
        dim_date = build_dim_date(first_day, as_of)

        connection.register("source_map", dim_source)
        connection.register("location_map", location_map)
        params = {"snapshot_id": snapshot_id}
        for name, frame in (("dim_date", dim_date), ("dim_source", dim_source), ("dim_location", dim_location)):
            connection.register(f"_{name}", frame)
            connection.execute(
                f"COPY (SELECT * FROM _{name}) TO {_literal(files[name])} (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        queries = {
            "fact_listing_observation": (FACT_OBSERVATION_SQL, params),
            "fact_listing_snapshot": (
                FACT_SNAPSHOT_SQL,
                {**params, "as_of_date_key": int(as_of.strftime("%Y%m%d"))},
            ),
        }
        for name, (sql, bind) in queries.items():
            connection.execute(
                f"COPY ({sql} ORDER BY {ORDER_BY[name]}) TO {_literal(files[name])} "
                "(FORMAT PARQUET, COMPRESSION ZSTD)",
                bind,
            )
        connection.execute(
            f"CREATE VIEW fact AS SELECT * FROM read_parquet({_literal(files['fact_listing_observation'])})"
        )
        connection.execute(
            f"COPY ({MARKET_DAILY_SQL} ORDER BY {ORDER_BY['agg_market_daily']}) "
            f"TO {_literal(files['agg_market_daily'])} (FORMAT PARQUET, COMPRESSION ZSTD)",
            params,
        )
        counts = {
            name: connection.execute(
                f"SELECT COUNT(*) FROM read_parquet({_literal(path)})"
            ).fetchone()[0]
            for name, path in files.items()
        }
    finally:
        connection.close()

    if counts["fact_listing_observation"] != curated_rows:
        raise WarehouseModelError("Observation fact lost rows while joining dimensions")
    (silver_rows,) = duckdb.execute(f"SELECT COUNT(*) FROM read_parquet({_literal(silver_path)})").fetchone()
    if counts["fact_listing_snapshot"] != silver_rows:
        raise WarehouseModelError("Snapshot fact lost rows while joining dimensions")
    return WarehouseModel(
        snapshot_id=snapshot_id,
        curated_metadata_sha256=curated_metadata_sha,
        silver_output_sha256=silver_metadata["output_sha256"],
        files=files,
        counts=counts,
    )
