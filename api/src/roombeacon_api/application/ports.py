"""Ports: what the use cases need from the outside world.

Adapters raise DependencyUnavailableError on outages; use cases never see driver errors.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

from ..domain.models import (
    DataSnapshot,
    DistrictCard,
    ImageObject,
    ImageRef,
    ListingCard,
    MarketDay,
    MarketSummary,
    ModelInfo,
    ModelInput,
    PricePoint,
    PricePrediction,
    WardCard,
)
from .pagination import Page, PageRequest
from .sorting import SortSpec

if TYPE_CHECKING:
    from .listing_service import ListingFilters


class LocationRepository(Protocol):
    """Read-only access to location cards (ClickHouse warehouse)."""

    def ping(self) -> None: ...

    def latest_snapshot(self) -> DataSnapshot | None: ...

    def list_districts(self, query: str, sort: SortSpec, page: PageRequest) -> Page[DistrictCard]: ...

    def get_district(self, district_id: str) -> DistrictCard | None: ...

    def get_ward(self, ward_id: str) -> WardCard | None: ...

    def list_wards(self, district_id: str, query: str, sort: SortSpec, page: PageRequest) -> Page[WardCard]: ...

    def find_wards(self, ward_name: str, district_id: str, limit: int) -> list[WardCard]: ...


class ListingRepository(Protocol):
    """Listing search over published Silver Parquet."""

    def search(self, filters: "ListingFilters", sort: SortSpec, page: PageRequest) -> Page[ListingCard]: ...

    def get(self, listing_id: str) -> ListingCard | None: ...


class HistoryRepository(Protocol):
    def price_history(self, listing_id: str, page: PageRequest) -> Page[PricePoint]: ...


class MarketRepository(Protocol):
    def summary(self, district_id: str | None) -> MarketSummary: ...

    def daily(self, district_id: str | None, date_from: date | None, date_to: date | None) -> list[MarketDay]: ...


class PriceModel(Protocol):
    """The locked champion. Never retrained or reselected here."""

    def info(self) -> ModelInfo: ...

    def predict(self, inputs: list[ModelInput]) -> list[PricePrediction]: ...


class ImageStore(Protocol):
    """Listing images in object storage (read-only)."""

    def list_images(self, source: str, source_listing_id: str) -> list[ImageRef]: ...

    def get_image(self, key: str) -> ImageObject | None: ...
