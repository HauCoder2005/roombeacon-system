"""ClickHouse adapter for LocationRepository over the roombeacon_dw star schema.

Every user value is a server-side bound parameter ({name:Type}); only the
validated database identifier and whitelisted ORDER BY columns are formatted
into SQL. Price statistics use exact quantiles over RENT listings whose price
is SUPPORTED, so cards are deterministic for a given warehouse load.
"""

from __future__ import annotations

from datetime import timezone
import logging
import math
import re
from typing import Any, Mapping, Sequence

from ..application.pagination import Page, PageRequest
from ..application.sorting import SortSpec
from ..domain.errors import DependencyUnavailableError
from ..domain.models import DataSnapshot, DistrictCard, PriceStats, WardCard


logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
SORT_COLUMNS = {"name": "name", "listing_count": "listing_count", "median_price": "median_price"}

PRICED = (
    "f.listing_intent = 'RENT' AND f.price_model_suitability = 'SUPPORTED' "
    "AND f.price_amount_clean IS NOT NULL"
)
STATS = f"""
    quantileExactIf(0.5)(f.price_amount_clean, {PRICED}) AS median_price,
    quantileExactIf(0.25)(f.price_amount_clean, {PRICED}) AS p25_price,
    quantileExactIf(0.75)(f.price_amount_clean, {PRICED}) AS p75_price,
    quantileExactIf(0.5)(f.price_amount_clean / f.area_value_clean, {PRICED} AND f.area_value_clean > 0)
        AS median_price_per_m2,
    quantileExactIf(0.5)(f.area_value_clean, {PRICED} AND f.area_value_clean > 0) AS median_area"""
NAME_FILTER = "(empty({q:String}) OR positionCaseInsensitiveUTF8(name, {q:String}) > 0)"


def _hash_id(*parts: str) -> str:
    """16-hex id from names: 'DISTRICT|<district>' or 'WARD|<district>|<ward>'."""
    joined = ", '|', ".join(parts)
    return f"lower(hex(substring(SHA256(concat({joined})), 1, 8)))"


DISTRICT_ID = _hash_id("'DISTRICT'", "assumeNotNull(d.district)")
WARD_ID = _hash_id("'WARD'", "assumeNotNull(w.district)", "assumeNotNull(w.ward)")
WARD_DISTRICT_ID = _hash_id("'DISTRICT'", "assumeNotNull(w.district)")


class ClickHouseLocationRepository:
    def __init__(self, client: Any, database: str) -> None:
        if not IDENTIFIER.fullmatch(database):
            raise ValueError("database must be a plain identifier")
        self._client = client
        db = f"`{database}`"
        self._db = db
        self._districts = f"""
SELECT
    {DISTRICT_ID} AS id,
    assumeNotNull(d.district) AS name,
    count() AS listing_count,
    countIf({PRICED}) AS priced_listing_count,
    uniqExactIf(w.ward, w.location_level = 'WARD') AS ward_count,{STATS}
FROM {db}.fact_listing_snapshot AS f
INNER JOIN {db}.dim_location AS d ON d.location_key = f.district_location_key
INNER JOIN {db}.dim_location AS w ON w.location_key = f.location_key
WHERE d.location_level = 'DISTRICT' AND d.district IS NOT NULL
GROUP BY d.district"""
        self._wards = f"""
SELECT
    {WARD_ID} AS id,
    assumeNotNull(w.ward) AS name,
    {WARD_DISTRICT_ID} AS district_id,
    assumeNotNull(w.district) AS district_name,
    count() AS listing_count,
    countIf({PRICED}) AS priced_listing_count,{STATS}
FROM {db}.fact_listing_snapshot AS f
INNER JOIN {db}.dim_location AS w ON w.location_key = f.location_key
WHERE w.location_level = 'WARD' AND w.district IS NOT NULL AND w.ward IS NOT NULL
GROUP BY w.district, w.ward"""

    # -- port implementation -------------------------------------------------

    def ping(self) -> None:
        self._rows("SELECT 1", {})

    def latest_snapshot(self) -> DataSnapshot | None:
        rows = self._rows(
            f"SELECT snapshot_id, loaded_at FROM {self._db}.etl_load_log ORDER BY loaded_at DESC LIMIT 1", {}
        )
        if not rows:
            return None
        snapshot_id, loaded_at = rows[0]
        if loaded_at.tzinfo is None:
            loaded_at = loaded_at.replace(tzinfo=timezone.utc)
        return DataSnapshot(str(snapshot_id), loaded_at)

    def list_districts(self, query: str, sort: SortSpec, page: PageRequest) -> Page[DistrictCard]:
        order = _order_by(sort)
        total = self._rows(f"SELECT count() FROM ({self._districts}) WHERE {NAME_FILTER}", {"q": query})[0][0]
        rows = self._rows(
            f"SELECT * FROM ({self._districts}) WHERE {NAME_FILTER} ORDER BY {order} "
            "LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
            {"q": query, "limit": page.per_page, "offset": page.offset},
        )
        return Page([_district(r) for r in rows], int(total), page)

    def get_district(self, district_id: str) -> DistrictCard | None:
        rows = self._rows(
            f"SELECT * FROM ({self._districts}) WHERE id = {{district_id:String}}", {"district_id": district_id}
        )
        return _district(rows[0]) if rows else None

    def get_ward(self, ward_id: str) -> WardCard | None:
        rows = self._rows(f"SELECT * FROM ({self._wards}) WHERE id = {{ward_id:String}}", {"ward_id": ward_id})
        return _ward(rows[0]) if rows else None

    def list_wards(self, district_id: str, query: str, sort: SortSpec, page: PageRequest) -> Page[WardCard]:
        order = _order_by(sort)
        where = f"district_id = {{district_id:String}} AND {NAME_FILTER}"
        total = self._rows(
            f"SELECT count() FROM ({self._wards}) WHERE {where}", {"district_id": district_id, "q": query}
        )[0][0]
        rows = self._rows(
            f"SELECT * FROM ({self._wards}) WHERE {where} ORDER BY {order} "
            "LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
            {"district_id": district_id, "q": query, "limit": page.per_page, "offset": page.offset},
        )
        return Page([_ward(r) for r in rows], int(total), page)

    def find_wards(self, ward_name: str, district_id: str, limit: int) -> list[WardCard]:
        rows = self._rows(
            f"SELECT * FROM ({self._wards}) "
            "WHERE lowerUTF8(name) = lowerUTF8({ward:String}) "
            "AND (empty({district_id:String}) OR district_id = {district_id:String}) "
            "ORDER BY listing_count DESC, id ASC LIMIT {limit:UInt32}",
            {"ward": ward_name, "district_id": district_id, "limit": limit},
        )
        return [_ward(r) for r in rows]

    # -- helpers -------------------------------------------------------------

    def _rows(self, sql: str, parameters: Mapping[str, Any]) -> Sequence[Sequence[Any]]:
        try:
            return self._client.query(sql, parameters=parameters).result_rows
        except Exception as exc:  # driver, network and server errors alike
            logger.warning("warehouse query failed: %s", type(exc).__name__)
            raise DependencyUnavailableError("warehouse") from exc


def _order_by(sort: SortSpec) -> str:
    column = SORT_COLUMNS.get(sort.field)
    if column is None:
        raise ValueError(f"unsupported sort field: {sort.field!r}")
    return f"{column} {'DESC' if sort.descending else 'ASC'}, id ASC"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) or math.isinf(number) else number


def _price(values: Sequence[Any]) -> PriceStats:
    return PriceStats(*(_number(v) for v in values))


def _district(row: Sequence[Any]) -> DistrictCard:
    return DistrictCard(str(row[0]), str(row[1]), int(row[2]), int(row[3]), int(row[4]), _price(row[5:10]))


def _ward(row: Sequence[Any]) -> WardCard:
    return WardCard(str(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]), int(row[5]), _price(row[6:11]))
