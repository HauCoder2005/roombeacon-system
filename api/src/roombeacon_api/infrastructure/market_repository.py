"""ClickHouse adapters: per-listing price history and market summary / daily series.

District filters use the same name-hash ids as the location cards; every user
value is a server-side bound parameter.
"""

from __future__ import annotations

from datetime import date, timezone
import logging
import re
from typing import Any, Mapping

from ..application.pagination import Page, PageRequest
from ..domain.models import MarketDay, MarketSummary, PricePoint
from .clickhouse import query_rows
from .location_repository import PRICED


logger = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
DISTRICT_ID = "lower(hex(substring(SHA256(concat('DISTRICT', '|', assumeNotNull(d.district))), 1, 8)))"
DISTRICT_FILTER = f"(empty({{district_id:String}}) OR (d.location_level = 'DISTRICT' AND {DISTRICT_ID} = {{district_id:String}}))"


def _db(database: str) -> str:
    if not IDENTIFIER.fullmatch(database):
        raise ValueError("database must be a plain identifier")
    return f"`{database}`"


def _utc(value: Any) -> Any:
    return value.replace(tzinfo=timezone.utc) if value is not None and getattr(value, "tzinfo", 1) is None else value


def _number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if number != number else number


class ClickHouseHistoryRepository:
    def __init__(self, client: Any, database: str) -> None:
        self._client = client
        self._db = _db(database)

    def price_history(self, listing_id: str, page: PageRequest) -> Page[PricePoint]:
        key = {"listing_id": int(listing_id)}
        table = f"{self._db}.fact_listing_observation"
        total = query_rows(
            self._client, f"SELECT count() FROM {table} WHERE rental_post_id = {{listing_id:Int64}}", key, logger
        )[0][0]
        rows = query_rows(
            self._client,
            f"SELECT observed_at, price_amount, area_value, is_price_change, is_content_change FROM {table} "
            "WHERE rental_post_id = {listing_id:Int64} ORDER BY observed_at ASC, observation_id ASC "
            "LIMIT {limit:UInt32} OFFSET {offset:UInt32}",
            {**key, "limit": page.per_page, "offset": page.offset},
            logger,
        )
        points = [PricePoint(_utc(r[0]), _number(r[1]), _number(r[2]), bool(r[3]), bool(r[4])) for r in rows]
        return Page(points, int(total), page)


class ClickHouseMarketRepository:
    def __init__(self, client: Any, database: str) -> None:
        self._client = client
        self._db = _db(database)

    def summary(self, district_id: str | None) -> MarketSummary:
        rows = query_rows(
            self._client,
            f"""
SELECT
    count(),
    countIf({PRICED}),
    uniqExactIf(d.district, d.location_level = 'DISTRICT'),
    quantileExactIf(0.5)(f.price_amount_clean, {PRICED}),
    quantileExactIf(0.25)(f.price_amount_clean, {PRICED}),
    quantileExactIf(0.75)(f.price_amount_clean, {PRICED}),
    min(f.first_observed_at),
    max(f.last_observed_at)
FROM {self._db}.fact_listing_snapshot AS f
INNER JOIN {self._db}.dim_location AS d ON d.location_key = f.district_location_key
WHERE {DISTRICT_FILTER}""",
            {"district_id": district_id or ""},
            logger,
        )
        r = rows[0]
        return MarketSummary(int(r[0]), int(r[1]), int(r[2]), _number(r[3]), _number(r[4]), _number(r[5]), _utc(r[6]), _utc(r[7]))

    def daily(self, district_id: str | None, date_from: date | None, date_to: date | None) -> list[MarketDay]:
        parameters: Mapping[str, Any] = {
            "district_id": district_id or "",
            "date_from": (date_from or date(1970, 1, 1)).isoformat(),
            "date_to": (date_to or date(2999, 12, 31)).isoformat(),
        }
        rows = query_rows(
            self._client,
            f"""
SELECT
    o.observed_date,
    uniqExact(o.rental_post_id),
    countIf(o.version_seq = 1),
    countIf(o.is_price_change),
    quantileExactIf(0.5)(o.price_amount, o.is_market_eligible AND o.price_status = 'ACCEPTED_CLEAN')
FROM {self._db}.fact_listing_observation AS o
INNER JOIN {self._db}.dim_location AS d ON d.location_key = o.district_location_key
WHERE {DISTRICT_FILTER}
  AND o.observed_date BETWEEN toDate({{date_from:String}}) AND toDate({{date_to:String}})
GROUP BY o.observed_date
ORDER BY o.observed_date""",
            parameters,
            logger,
        )
        return [MarketDay(r[0], int(r[1]), int(r[2]), int(r[3]), _number(r[4])) for r in rows]
