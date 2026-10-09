"""In-memory fixtures for the RoomBeacon API: no ClickHouse, Docker or network."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib

import pytest
from fastapi.testclient import TestClient

from roombeacon_api.application.listing_service import ListingFilters
from roombeacon_api.application.pagination import Page, PageRequest
from roombeacon_api.application.sorting import SortSpec
from roombeacon_api.config import ApiSettings, ClickHouseSettings, Secret
from roombeacon_api.domain.errors import DependencyUnavailableError
from roombeacon_api.domain.models import (
    DataSnapshot,
    DistrictCard,
    ListingCard,
    MarketDay,
    MarketSummary,
    ModelInfo,
    ImageObject,
    ImageRef,
    ModelInput,
    PricePoint,
    PricePrediction,
    PriceStats,
    WardCard,
)
from roombeacon_api.main import create_app


API_KEY = "test-key-0123456789abcdef"
BINH_THANH = "0a1b2c3d4e5f6071"
QUAN_3 = "1a1b2c3d4e5f6072"
GO_VAP = "2a1b2c3d4e5f6073"
WARD_25 = "aa00000000000001"


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
    WardCard(WARD_25, "Phường 25", BINH_THANH, "Quận Bình Thạnh", 900, 850, price(4_200_000)),
    WardCard("aa00000000000002", "Phường 1", BINH_THANH, "Quận Bình Thạnh", 300, 280, price(3_900_000)),
    WardCard("aa00000000000003", "Phường 1", QUAN_3, "Quận 3", 200, 190, price(6_000_000)),
    WardCard("aa00000000000004", "Phường 1", GO_VAP, "Quận Gò Vấp", 150, 140, price(3_400_000)),
    WardCard("aa00000000000005", "Phường Võ Thị Sáu", QUAN_3, "Quận 3", 400, 380, price(6_500_000)),
]
SNAPSHOT = DataSnapshot("db804eae-1774-4659-aa9a-255830997f5d", datetime(2026, 10, 9, 9, 52, 26, tzinfo=timezone.utc))
T0 = datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


def listing(
    listing_id: str,
    title: str,
    price_vnd: float | None,
    area: float | None,
    *,
    district=(BINH_THANH, "Quận Bình Thạnh"),
    ward=(WARD_25, "Phường 25"),
    source: str = "phongtro123",
    url: str | None = None,
    last_seen: datetime = T1,
) -> ListingCard:
    return ListingCard(
        id=listing_id, title=title, source=source, source_listing_id=f"pr{listing_id}",
        source_url=url or f"https://example.test/{listing_id}.html",
        price_vnd=price_vnd, area_m2=area,
        district_id=district[0] if district else None, district=district[1] if district else None,
        ward_id=ward[0] if ward else None, ward=ward[1] if ward else None,
        intent="RENT", scope="SINGLE_OR_ORDINARY_UNIT",
        first_observed_at=T0, last_observed_at=last_seen, active_days=11,
        duplicate_status="UNIQUE_FINGERPRINT", price_suitability="SUPPORTED",
    )


LISTINGS = [
    listing("101", "Phòng trọ 25m2 gần chợ Bà Chiểu, gọi 0912.345.678", 3_500_000, 25.0,
            url="https://example.test/lien-he-0912345678-pr101.html"),
    listing("102", "Căn hộ mini full nội thất", 5_200_000, 30.0),
    listing("103", "Phòng có gác Quận 3", 6_000_000, 22.0, district=(QUAN_3, "Quận 3"),
            ward=("aa00000000000005", "Phường Võ Thị Sáu"), source="mogi"),
    listing("104", "Phòng giá rẻ Gò Vấp", 2_200_000, 18.0, district=(GO_VAP, "Quận Gò Vấp"), ward=None),
    listing("105", "Tin chưa có diện tích", 4_000_000, None, ward=None),
]
HISTORY = {
    "101": [
        PricePoint(T0, 3_800_000, 25.0, False, True),
        PricePoint(datetime(2026, 9, 28, tzinfo=timezone.utc), 3_500_000, 25.0, True, True),
    ]
}


def _sort_value(card, field: str):
    return {"name": card.name, "listing_count": card.listing_count, "median_price": card.price.median}[field]


def _page(items: list, sort: SortSpec, page: PageRequest, value=_sort_value) -> Page:
    present = [c for c in items if value(c, sort.field) is not None]
    missing = [c for c in items if value(c, sort.field) is None]
    present.sort(key=lambda c: (value(c, sort.field), c.id), reverse=sort.descending)
    ordered = present + missing
    return Page(ordered[page.offset : page.offset + page.per_page], len(ordered), page)


class _Guarded:
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


class FakeLocationRepository(_Guarded):
    def ping(self) -> None:
        self._guard("ping")

    def latest_snapshot(self) -> DataSnapshot | None:
        self._guard("latest_snapshot")
        return SNAPSHOT

    def list_districts(self, query: str, sort: SortSpec, page: PageRequest) -> Page[DistrictCard]:
        self._guard("list_districts")
        return _page([d for d in DISTRICTS if query.casefold() in d.name.casefold()], sort, page)

    def get_district(self, district_id: str) -> DistrictCard | None:
        self._guard("get_district")
        return next((d for d in DISTRICTS if d.id == district_id), None)

    def get_ward(self, ward_id: str) -> WardCard | None:
        self._guard("get_ward")
        return next((w for w in WARDS if w.id == ward_id), None)

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


def _listing_value(card: ListingCard, field: str):
    return {"last_observed_at": card.last_observed_at, "price": card.price_vnd, "area": card.area_m2}[field]


class FakeListingRepository(_Guarded):
    def __init__(self) -> None:
        super().__init__()
        self.last_filters: ListingFilters | None = None

    def search(self, filters: ListingFilters, sort: SortSpec, page: PageRequest) -> Page[ListingCard]:
        self._guard("search")
        self.last_filters = filters
        rows = [
            c for c in LISTINGS
            if (not filters.district_id or c.district_id == filters.district_id)
            and (not filters.ward_id or c.ward_id == filters.ward_id)
            and (not filters.q or filters.q.casefold() in c.title.casefold())
            and (filters.price_min is None or (c.price_vnd or 0) >= filters.price_min)
            and (filters.price_max is None or (c.price_vnd or 0) <= filters.price_max)
            and (filters.area_min is None or (c.area_m2 or 0) >= filters.area_min)
            and (filters.area_max is None or (c.area_m2 or 0) <= filters.area_max)
        ]
        return _page(rows, sort, page, _listing_value)

    def get(self, listing_id: str) -> ListingCard | None:
        self._guard("get")
        return next((c for c in LISTINGS if c.id == listing_id), None)

    def latest_with_images(self, pairs, level: str, location_ids: list[str]) -> dict[str, str]:
        self._guard("latest_with_images")
        out = {}
        for card in sorted(LISTINGS, key=lambda c: (c.last_observed_at, c.id)):
            location = card.district_id if level == "district" else card.ward_id
            if location in location_ids and (card.source, card.source_listing_id) in pairs:
                out[location] = card.id
        return out


class FakeHistoryRepository(_Guarded):
    def price_history(self, listing_id: str, page: PageRequest) -> Page[PricePoint]:
        self._guard("price_history")
        points = HISTORY.get(listing_id, [])
        return Page(points[page.offset : page.offset + page.per_page], len(points), page)


class FakeMarketRepository(_Guarded):
    def summary(self, district_id: str | None) -> MarketSummary:
        self._guard("summary")
        return MarketSummary(132494, 110000, 55, 4_000_000, 3_000_000, 5_500_000, T0, T1)

    def daily(self, district_id: str | None, date_from: date | None, date_to: date | None) -> list[MarketDay]:
        self._guard("daily")
        days = [
            MarketDay(date(2026, 9, 23), 14967, 962, 2694, 3_900_000),
            MarketDay(date(2026, 9, 24), 12000, 800, 150, 4_000_000),
        ]
        return [d for d in days if (date_from is None or d.day >= date_from) and (date_to is None or d.day <= date_to)]


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


class FakeImageStore:
    """Two images for listing 101 (source phongtro123, source id pr101), one non-image object."""

    def __init__(self) -> None:
        self.unavailable = False
        self.objects = {
            "phongtro123/pr101/img_1_aaaaaaaa.jpg": ImageObject(JPEG, "image/jpeg", '"etag1"', len(JPEG)),
            "phongtro123/pr101/img_2_bbbbbbbb.jpg": ImageObject(JPEG, "image/jpeg", '"etag2"', len(JPEG)),
            "phongtro123/pr102/img_1_cccccccc.jpg": ImageObject(b"<html>", "text/html", '"etag3"', 6),
        }

    def list_images(self, source: str, source_listing_id: str) -> list[ImageRef]:
        if self.unavailable:
            raise DependencyUnavailableError("images")
        prefix = f"{source}/{source_listing_id}/"
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        return [ImageRef(int(k.split("img_")[1].split("_")[0]), k) for k in keys]

    def get_image(self, key: str) -> ImageObject | None:
        if self.unavailable:
            raise DependencyUnavailableError("images")
        return self.objects.get(key)

    def listings_with_images(self) -> frozenset[tuple[str, str]]:
        if self.unavailable:
            raise DependencyUnavailableError("images")
        return frozenset({("phongtro123", "pr101")})


class FakePriceModel:
    """Deterministic stand-in: 160k VND per m², +10% when the source is known."""

    KNOWN_WARDS = {"Phường 25", "Phường Võ Thị Sáu"}

    def __init__(self) -> None:
        self.unavailable = False
        self.inputs: list[ModelInput] = []

    def info(self) -> ModelInfo:
        if self.unavailable:
            raise DependencyUnavailableError("price_model")
        return ModelInfo(
            model_id="roombeacon-price-lgbm-f4-raw-test", family="LightGBM Regressor",
            feature_set="F4 — AREA + SOURCE + LOCATION", target_transform="RAW",
            trained_until=datetime(2026, 9, 29, 14, 31, 4, tzinfo=timezone.utc),
            test_mae=916127.0, test_median_ae=623718.0, test_r2=0.205, readiness="experimental",
            reference_source="phongtro123", interval_coverage=0.5,
            typical_area_range=(15.0, 50.0), reliable_price_range=(3_000_000.0, 5_500_000.0),
        )

    def predict(self, inputs: list[ModelInput]) -> list[PricePrediction]:
        if self.unavailable:
            raise DependencyUnavailableError("price_model")
        self.inputs.extend(inputs)
        out = []
        for item in inputs:
            value = item.area_m2 * 160_000 * (1.1 if item.source_code else 1.0)
            unknown = () if (item.ward is None or item.ward in self.KNOWN_WARDS) else ("ward",)
            out.append(PricePrediction(value, value * 0.8, value * 1.2, unknown))
        return out


def make_settings(**overrides) -> ApiSettings:
    base = ApiSettings(
        api_key_sha256=(hashlib.sha256(API_KEY.encode()).hexdigest(),),
        auth_enabled=True,
        rate_limit_per_minute=1000,
        cors_origins=(),
        allowed_hosts=("testserver",),
        docs_enabled=False,
        images_enabled=True,
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
def listings() -> FakeListingRepository:
    return FakeListingRepository()


@pytest.fixture
def history() -> FakeHistoryRepository:
    return FakeHistoryRepository()


@pytest.fixture
def market() -> FakeMarketRepository:
    return FakeMarketRepository()


@pytest.fixture
def price_model() -> FakePriceModel:
    return FakePriceModel()


@pytest.fixture
def settings() -> ApiSettings:
    return make_settings()


@pytest.fixture
def images() -> FakeImageStore:
    return FakeImageStore()


def build_app(settings, repository, listings=None, history=None, market=None, price_model=None, images=None):
    return create_app(
        settings,
        repository=repository,
        listing_repository=listings or FakeListingRepository(),
        history_repository=history or FakeHistoryRepository(),
        market_repository=market or FakeMarketRepository(),
        price_model=price_model or FakePriceModel(),
        image_store=images or FakeImageStore(),
    )


@pytest.fixture
def client(settings, repository, listings, history, market, price_model, images) -> TestClient:
    app = build_app(settings, repository, listings, history, market, price_model, images)
    with TestClient(app, headers={"X-API-Key": API_KEY}, raise_server_exceptions=False) as test_client:
        yield test_client
