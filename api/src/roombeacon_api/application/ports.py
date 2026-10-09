"""Ports: what the use cases need from the outside world."""

from __future__ import annotations

from typing import Protocol

from ..domain.models import DataSnapshot, DistrictCard, WardCard
from .pagination import Page, PageRequest
from .sorting import SortSpec


class LocationRepository(Protocol):
    """Read-only access to location cards. Raises DependencyUnavailableError on outages."""

    def ping(self) -> None: ...

    def latest_snapshot(self) -> DataSnapshot | None: ...

    def list_districts(self, query: str, sort: SortSpec, page: PageRequest) -> Page[DistrictCard]: ...

    def get_district(self, district_id: str) -> DistrictCard | None: ...

    def list_wards(self, district_id: str, query: str, sort: SortSpec, page: PageRequest) -> Page[WardCard]: ...

    def find_wards(self, ward_name: str, district_id: str, limit: int) -> list[WardCard]: ...
