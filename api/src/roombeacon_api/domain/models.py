"""Location cards: the read models the API serves.

Districts and wards are grouped by their normalized names, not by province,
because province spellings in Silver are not yet normalized ("TPHCM",
"TP.HCM", ...). Identifiers are 16-hex hashes of those names, stable across loads.
No coordinates are derived here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


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


@dataclass(frozen=True)
class ListingCard:
    """One Silver listing. Text fields may still contain contact numbers: mask on output."""

    id: str
    title: str
    source: str
    source_listing_id: str | None
    source_url: str | None
    price_vnd: float | None
    area_m2: float | None
    district_id: str | None
    district: str | None
    ward_id: str | None
    ward: str | None
    intent: str | None
    scope: str | None
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    active_days: int | None
    duplicate_status: str | None
    price_suitability: str | None


@dataclass(frozen=True)
class PricePoint:
    observed_at: datetime
    price: float | None
    area_m2: float | None
    is_price_change: bool
    is_content_change: bool


@dataclass(frozen=True)
class MarketSummary:
    listing_count: int
    priced_listing_count: int
    district_count: int
    median: float | None
    p25: float | None
    p75: float | None
    data_from: datetime | None
    data_until: datetime | None


@dataclass(frozen=True)
class MarketDay:
    day: date
    listings_observed: int
    new_listings: int
    price_changes: int
    median_price: float | None


@dataclass(frozen=True)
class ModelInput:
    """F4 inputs. source_code None means "not a listing": the model's reference source is used."""

    area_m2: float
    district: str | None
    ward: str | None
    source_code: str | None


@dataclass(frozen=True)
class PricePrediction:
    value: float
    low: float
    high: float
    unknown_features: tuple[str, ...]


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    family: str
    feature_set: str
    target_transform: str
    trained_until: datetime | None
    test_mae: float | None
    test_median_ae: float | None
    test_r2: float | None
    readiness: str
    reference_source: str
    interval_coverage: float
    typical_area_range: tuple[float, float]
    reliable_price_range: tuple[float, float]


@dataclass(frozen=True)
class ImageRef:
    """One stored listing image; position is the source gallery order (public id)."""

    position: int
    key: str


IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


@dataclass(frozen=True)
class ImageObject:
    content: bytes
    content_type: str
    etag: str | None
    size: int
