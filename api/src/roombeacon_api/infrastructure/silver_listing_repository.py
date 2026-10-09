"""Listing search over the published Silver Parquet, held in an in-process DuckDB table.

Silver is ~130k rows, so it is loaded once into memory and reloaded when the
file is republished (mtime/size change). District and ward ids are the same
name hashes the warehouse cards use: sha256('DISTRICT|<district>')[:16] and
sha256('WARD|<district>|<ward>')[:16].

Search scope: TP.HCM only (rows whose province text names another province are
excluded), SUPPORTED prices, one intent (RENT by default) and, by default, no
POSSIBLE_DUPLICATE rows. Detail lookups ignore those filters.
"""

from __future__ import annotations

from datetime import timezone
import os
from pathlib import Path
import threading
from typing import Any

import duckdb

from ..application.listing_service import ListingFilters
from ..application.pagination import Page, PageRequest
from ..application.sorting import SortSpec
from ..domain.errors import DependencyUnavailableError
from ..domain.models import ListingCard


SORT_COLUMNS = {"last_observed_at": "last_observed_at", "price": "price_vnd", "area": "area_m2"}
CARD_COLUMNS = (
    "id, title, source, source_listing_id, source_url, price_vnd, area_m2, district_id, district, ward_id, ward, intent, scope, "
    "first_observed_at, last_observed_at, active_days, duplicate_status, price_suitability"
)
HCM_PROVINCE = r"(ho chi minh|hcm|sai gon|saigon)"
LOAD_SQL = f"""
CREATE OR REPLACE TABLE listings AS
SELECT
    CAST(rental_post_id AS VARCHAR) AS id,
    coalesce(nullif(trim(title_clean), ''), nullif(trim(title_raw), ''), '') AS title,
    source_code AS source,
    CAST(source_listing_id AS VARCHAR) AS source_listing_id,
    url AS source_url,
    price_amount_clean AS price_vnd,
    area_value_clean AS area_m2,
    CASE WHEN district_text_extracted IS NULL THEN NULL
         ELSE left(sha256('DISTRICT|' || district_text_extracted), 16) END AS district_id,
    district_text_extracted AS district,
    CASE WHEN district_text_extracted IS NULL OR ward_current IS NULL THEN NULL
         ELSE left(sha256('WARD|' || district_text_extracted || '|' || ward_current), 16) END AS ward_id,
    ward_current AS ward,
    listing_intent AS intent,
    rental_scope AS scope,
    first_observed_at,
    last_observed_at,
    CAST(active_days AS BIGINT) AS active_days,
    duplicate_candidate_status AS duplicate_status,
    price_model_suitability AS price_suitability,
    (province_text_extracted IS NULL
     OR regexp_matches(lower(strip_accents(province_text_extracted)), '{HCM_PROVINCE}')) AS in_market,
    lower(coalesce(nullif(trim(title_clean), ''), nullif(trim(title_raw), ''), '')) AS title_search
FROM read_parquet($path)
"""


class SilverListingRepository:
    def __init__(self, silver_path: str | Path) -> None:
        self._path = Path(silver_path)
        self._lock = threading.Lock()
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._signature: tuple[int, int] | None = None

    # -- port implementation -------------------------------------------------

    def search(self, filters: ListingFilters, sort: SortSpec, page: PageRequest) -> Page[ListingCard]:
        column = SORT_COLUMNS.get(sort.field)
        if column is None:
            raise ValueError(f"unsupported sort field: {sort.field!r}")
        where = [
            "in_market",
            "price_suitability = 'SUPPORTED'",
            "price_vnd IS NOT NULL",
        ]
        params: dict[str, Any] = {}
        if filters.intent != "ANY":
            where.append("intent = $intent")
            params["intent"] = filters.intent
        if filters.exclude_duplicates:
            where.append("coalesce(duplicate_status, '') <> 'POSSIBLE_DUPLICATE'")
        for name, clause in (
            ("district_id", "district_id = $district_id"),
            ("ward_id", "ward_id = $ward_id"),
            ("price_min", "price_vnd >= $price_min"),
            ("price_max", "price_vnd <= $price_max"),
            ("area_min", "area_m2 >= $area_min"),
            ("area_max", "area_m2 <= $area_max"),
        ):
            value = getattr(filters, name)
            if value is not None:
                where.append(clause)
                params[name] = value
        if filters.q:
            where.append("contains(title_search, lower($q))")
            params["q"] = filters.q
        condition = " AND ".join(where)
        direction = "DESC" if sort.descending else "ASC"
        cursor = self._cursor()
        try:
            total = cursor.execute(f"SELECT count(*) FROM listings WHERE {condition}", params).fetchone()[0]
            rows = cursor.execute(
                f"SELECT {CARD_COLUMNS} FROM listings WHERE {condition} "
                f"ORDER BY {column} {direction} NULLS LAST, id ASC LIMIT $limit OFFSET $offset",
                {**params, "limit": page.per_page, "offset": page.offset},
            ).fetchall()
        finally:
            cursor.close()
        return Page([_card(r) for r in rows], int(total), page)

    def get(self, listing_id: str) -> ListingCard | None:
        cursor = self._cursor()
        try:
            row = cursor.execute(f"SELECT {CARD_COLUMNS} FROM listings WHERE id = $id", {"id": listing_id}).fetchone()
        finally:
            cursor.close()
        return _card(row) if row else None

    def latest_with_images(self, pairs: frozenset[tuple[str, str]], level: str, location_ids: list[str]) -> dict[str, str]:
        if level not in {"district", "ward"}:
            raise ValueError(f"unsupported level: {level!r}")
        if not pairs or not location_ids:
            return {}
        column = f"{level}_id"
        cursor = self._cursor()
        try:
            self._sync_image_pairs(cursor, pairs)
            rows = cursor.execute(
                f"""
                SELECT l.{column}, arg_max(l.id, (l.last_observed_at, l.id))
                FROM listings AS l
                INNER JOIN image_pairs AS p ON p.source = l.source AND p.sid = l.source_listing_id
                WHERE list_contains($ids, l.{column})
                  AND l.in_market AND l.price_suitability = 'SUPPORTED' AND l.price_vnd IS NOT NULL
                  AND coalesce(l.duplicate_status, '') <> 'POSSIBLE_DUPLICATE'
                GROUP BY l.{column}
                """,
                {"ids": list(location_ids)},
            ).fetchall()
        finally:
            cursor.close()
        return {location: listing for location, listing in rows}

    def _sync_image_pairs(self, cursor: duckdb.DuckDBPyConnection, pairs: frozenset[tuple[str, str]]) -> None:
        """Refresh the shared image_pairs table only when the index changed."""
        with self._lock:
            if getattr(self, "_pairs_signature", None) == (self._signature, hash(pairs)):
                return
            cursor.execute("CREATE OR REPLACE TABLE image_pairs (source VARCHAR, sid VARCHAR)")
            cursor.executemany("INSERT INTO image_pairs VALUES (?, ?)", sorted(pairs))
            self._pairs_signature = (self._signature, hash(pairs))

    # -- loading ---------------------------------------------------------------

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        try:
            stat = os.stat(self._path)
        except OSError as exc:
            raise DependencyUnavailableError("silver") from exc
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if self._connection is None or signature != self._signature:
                connection = duckdb.connect(":memory:", config={"threads": "2", "memory_limit": "256MB"})
                try:
                    connection.execute(LOAD_SQL, {"path": str(self._path)})
                except duckdb.Error as exc:
                    connection.close()
                    raise DependencyUnavailableError("silver") from exc
                if self._connection is not None:
                    self._connection.close()
                self._connection, self._signature = connection, signature
            return self._connection.cursor()


def _utc(value: Any) -> Any:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def _card(row: Any) -> ListingCard:
    return ListingCard(
        id=row[0], title=row[1], source=row[2], source_listing_id=row[3], source_url=row[4],
        price_vnd=row[5], area_m2=row[6], district_id=row[7], district=row[8], ward_id=row[9], ward=row[10],
        intent=row[11], scope=row[12], first_observed_at=_utc(row[13]), last_observed_at=_utc(row[14]),
        active_days=row[15], duplicate_status=row[16], price_suitability=row[17],
    )
