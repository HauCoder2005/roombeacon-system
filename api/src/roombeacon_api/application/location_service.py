"""Location use cases: list/get district cards, list ward cards, resolve a ward name."""

from __future__ import annotations

import threading
import time
from typing import Callable

from ..domain.errors import AmbiguousLocationError, NotFoundError
from ..domain.models import DataSnapshot, DistrictCard, WardCard
from .pagination import Page, PageRequest
from .ports import LocationRepository
from .sorting import SortSpec


MAX_RESOLVE_CHOICES = 20
SORT_FIELDS = frozenset({"name", "listing_count", "median_price"})


class LocationService:
    def __init__(
        self,
        repository: LocationRepository,
        snapshot_ttl_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repository = repository
        self._snapshot_ttl = snapshot_ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshot: tuple[float, DataSnapshot | None] | None = None

    def ready(self) -> None:
        self._repository.ping()

    def snapshot(self) -> DataSnapshot | None:
        """Latest warehouse load, cached briefly: it changes at most once a day."""
        with self._lock:
            cached = self._snapshot
        if cached is not None and self._clock() - cached[0] < self._snapshot_ttl:
            return cached[1]
        snapshot = self._repository.latest_snapshot()
        with self._lock:
            self._snapshot = (self._clock(), snapshot)
        return snapshot

    def list_districts(self, query: str, sort: SortSpec, page: PageRequest) -> Page[DistrictCard]:
        return self._repository.list_districts(query, sort, page)

    def get_district(self, district_id: str) -> DistrictCard:
        card = self._repository.get_district(district_id)
        if card is None:
            raise NotFoundError("district", district_id)
        return card

    def list_wards(self, district_id: str, query: str, sort: SortSpec, page: PageRequest) -> Page[WardCard]:
        self.get_district(district_id)
        return self._repository.list_wards(district_id, query, sort, page)

    def resolve_ward(self, ward_name: str, district_id: str | None) -> WardCard:
        matches = self._repository.find_wards(ward_name, district_id or "", MAX_RESOLVE_CHOICES + 1)
        if not matches:
            raise NotFoundError("ward", ward_name)
        if len(matches) > 1:
            raise AmbiguousLocationError(matches[:MAX_RESOLVE_CHOICES])
        return matches[0]
