"""Location cards: the read models the API serves.

Districts and wards are grouped by their normalized names, not by province,
because province spellings in Silver are not yet normalized ("TPHCM",
"TP.HCM", ...). Identifiers are 16-hex hashes of those names, stable across loads.
No coordinates are derived here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PriceStats:
    """Monthly rent statistics over RENT listings with SUPPORTED prices (VND)."""

    median: float | None
    p25: float | None
    p75: float | None
    median_per_m2: float | None
    median_area: float | None


@dataclass(frozen=True)
class DistrictCard:
    id: str
    name: str
    listing_count: int
    priced_listing_count: int
    ward_count: int
    price: PriceStats


@dataclass(frozen=True)
class WardCard:
    id: str
    name: str
    district_id: str
    district_name: str
    listing_count: int
    priced_listing_count: int
    price: PriceStats


@dataclass(frozen=True)
class DataSnapshot:
    snapshot_id: str
    loaded_at: datetime
