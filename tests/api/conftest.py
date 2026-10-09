"""In-memory fixtures for the RoomBeacon API: no ClickHouse, Docker or network."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib

import pytest
from fastapi.testclient import TestClient

from roombeacon_api.application.pagination import Page, PageRequest
from roombeacon_api.application.sorting import SortSpec
from roombeacon_api.config import ApiSettings, ClickHouseSettings, Secret
from roombeacon_api.domain.errors import DependencyUnavailableError
from roombeacon_api.domain.models import DataSnapshot, DistrictCard, PriceStats, WardCard
from roombeacon_api.main import create_app


API_KEY = "test-key-0123456789abcdef"
BINH_THANH = "0a1b2c3d4e5f6071"
QUAN_3 = "1a1b2c3d4e5f6072"
GO_VAP = "2a1b2c3d4e5f6073"


def price(median: float | None) -> PriceStats:
    if median is None:
        return PriceStats(None, None, None, None, None)
    return PriceStats(median, median * 0.8, median * 1.2, median / 25, 25.0)


DISTRICTS = [
    DistrictCard(BINH_THANH, "Quận Bình Thạnh", 6120, 5800, 20, price(4_000_000)),
    DistrictCard(QUAN_3, "Quận 3", 4100, 3900, 12, price(5_500_000)),
    DistrictCard(GO_VAP, "Quận Gò Vấp", 7300, 7000, 16, price(3_500_000)),
    DistrictCard("3a1b2c3d4e5f6074", "Huyện Cần Giờ", 12, 3, 2, price(None)),
]
WARDS = [
    WardCard("aa00000000000001", "Phường 25", BINH_THANH, "Quận Bình Thạnh", 900, 850, price(4_200_000)),
    WardCard("aa00000000000002", "Phường 1", BINH_THANH, "Quận Bình Thạnh", 300, 280, price(3_900_000)),
    WardCard("aa00000000000003", "Phường 1", QUAN_3, "Quận 3", 200, 190, price(6_000_000)),
    WardCard("aa00000000000004", "Phường 1", GO_VAP, "Quận Gò Vấp", 150, 140, price(3_400_000)),
    WardCard("aa00000000000005", "Phường Võ Thị Sáu", QUAN_3, "Quận 3", 400, 380, price(6_500_000)),
]
SNAPSHOT = DataSnapshot("db804eae-1774-4659-aa9a-255830997f5d", datetime(2026, 10, 9, 9, 52, 26, tzinfo=timezone.utc))


def _sort_value(card, field: str):
    return {"name": card.name, "listing_count": card.listing_count, "median_price": card.price.median}[field]


def _page(items: list, sort: SortSpec, page: PageRequest) -> Page:
    present = [c for c in items if _sort_value(c, sort.field) is not None]
    missing = [c for c in items if _sort_value(c, sort.field) is None]
    present.sort(key=lambda c: (_sort_value(c, sort.field), c.id), reverse=sort.descending)
    ordered = present + missing
    return Page(ordered[page.offset : page.offset + page.per_page], len(ordered), page)


class FakeLocationRepository:
    def __init__(self) -> None:
        self.unavailable = False
        self.explode: Exception | None = None
        self.calls: list[str] = []

    def _guard(self, name: str) -> None:
        self.calls.append(name)
        if self.explode is not None:
            raise self.explode
        if self.unavailable:
            raise DependencyUnavailableError("warehouse")

    def ping(self) -> None:
        self._guard("ping")

    def latest_snapshot(self) -> DataSnapshot | None:
        self._guard("latest_snapshot")
        return SNAPSHOT

    def list_districts(self, query: str, sort: SortSpec, page: PageRequest) -> Page[DistrictCard]:
        self._guard("list_districts")
        items = [d for d in DISTRICTS if query.casefold() in d.name.casefold()]
        return _page(items, sort, page)

    def get_district(self, district_id: str) -> DistrictCard | None:
        self._guard("get_district")
        return next((d for d in DISTRICTS if d.id == district_id), None)

    def list_wards(self, district_id: str, query: str, sort: SortSpec, page: PageRequest) -> Page[WardCard]:
        self._guard("list_wards")
        items = [w for w in WARDS if w.district_id == district_id and query.casefold() in w.name.casefold()]
        return _page(items, sort, page)

    def find_wards(self, ward_name: str, district_id: str, limit: int) -> list[WardCard]:
        self._guard("find_wards")
        found = [
            w for w in WARDS
            if w.name.casefold() == ward_name.casefold() and (not district_id or w.district_id == district_id)
        ]
        return sorted(found, key=lambda w: (-w.listing_count, w.id))[:limit]


def make_settings(**overrides) -> ApiSettings:
    base = ApiSettings(
        api_key_sha256=(hashlib.sha256(API_KEY.encode()).hexdigest(),),
        auth_enabled=True,
        rate_limit_per_minute=1000,
        cors_origins=(),
        allowed_hosts=("testserver",),
        docs_enabled=False,
        clickhouse=ClickHouseSettings(
            host="127.0.0.1", port=8123, database="roombeacon_dw", user="reader",
            password=Secret("unused"), secure=False, connect_timeout_seconds=5, query_timeout_seconds=10,
        ),
    )
    return replace(base, **overrides)


@pytest.fixture
def repository() -> FakeLocationRepository:
    return FakeLocationRepository()


@pytest.fixture
def settings() -> ApiSettings:
    return make_settings()


@pytest.fixture
def client(settings, repository) -> TestClient:
    app = create_app(settings, repository=repository)
    with TestClient(app, headers={"X-API-Key": API_KEY}, raise_server_exceptions=False) as test_client:
        yield test_client
