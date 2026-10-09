"""Domain cards -> JSON. Money is integer VND; unknown statistics are null, never 0."""

from __future__ import annotations

from typing import Any

from ..domain.models import DistrictCard, PriceStats, WardCard


DISTRICTS_PATH = "/api/v1/locations/districts"


def _money(value: float | None) -> int | None:
    return None if value is None else int(round(value))


def price_out(price: PriceStats) -> dict[str, Any]:
    return {
        "currency": "VND",
        "median": _money(price.median),
        "p25": _money(price.p25),
        "p75": _money(price.p75),
        "median_per_m2": _money(price.median_per_m2),
        "median_area_m2": None if price.median_area is None else round(price.median_area, 1),
    }


def district_out(card: DistrictCard) -> dict[str, Any]:
    return {
        "id": card.id,
        "type": "district",
        "name": card.name,
        "stats": {
            "listing_count": card.listing_count,
            "priced_listing_count": card.priced_listing_count,
            "ward_count": card.ward_count,
        },
        "price": price_out(card.price),
        "links": {"self": f"{DISTRICTS_PATH}/{card.id}", "wards": f"{DISTRICTS_PATH}/{card.id}/wards"},
    }


def ward_out(card: WardCard) -> dict[str, Any]:
    return {
        "id": card.id,
        "type": "ward",
        "name": card.name,
        "district": {"id": card.district_id, "name": card.district_name},
        "stats": {"listing_count": card.listing_count, "priced_listing_count": card.priced_listing_count},
        "price": price_out(card.price),
        "links": {
            "district": f"{DISTRICTS_PATH}/{card.district_id}",
            "district_wards": f"{DISTRICTS_PATH}/{card.district_id}/wards",
        },
    }
