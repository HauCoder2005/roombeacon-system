"""Pydantic models documenting the envelope and cards in OpenAPI (/docs)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class PriceOut(BaseModel):
    currency: str = "VND"
    median: int | None
    p25: int | None
    p75: int | None
    median_per_m2: int | None
    median_area_m2: float | None


class DistrictStatsOut(BaseModel):
    listing_count: int
    priced_listing_count: int
    ward_count: int


class DistrictCardOut(BaseModel):
    id: str
    type: str = "district"
    name: str
    stats: DistrictStatsOut
    price: PriceOut
    links: dict[str, str]


class DistrictRefOut(BaseModel):
    id: str
    name: str


class WardStatsOut(BaseModel):
    listing_count: int
    priced_listing_count: int


class WardCardOut(BaseModel):
    id: str
    type: str = "ward"
    name: str
    district: DistrictRefOut
    stats: WardStatsOut
    price: PriceOut
    links: dict[str, str]


class PaginationOut(BaseModel):
    page: int
    per_page: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class SnapshotOut(BaseModel):
    snapshot_id: str
    loaded_at: str


class CacheOut(BaseModel):
    etag: str
    expires_at: str


class MetaOut(BaseModel):
    request_id: str
    timestamp: str
    api_version: str
    method: str
    path: str
    duration_ms: int
    resource: str | None
    data_snapshot: SnapshotOut | None
    cache: CacheOut | None
    pagination: PaginationOut | None
    sort: list[str] | None
    filters: dict[str, Any] | None


class ErrorItemOut(BaseModel):
    field: str | None
    code: str
    message: str


class Envelope(BaseModel, Generic[T]):
    success: bool
    code: int
    status: str
    message: str
    data: T | None
    errors: list[ErrorItemOut] | None
    meta: MetaOut
    links: dict[str, str | None] | None


class ChoicesOut(BaseModel):
    choices: list[WardCardOut]


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": Envelope[None], "description": description}
    for status, description in {
        401: "Missing or invalid API key",
        404: "Not found",
        422: "Invalid parameters",
        429: "Rate limited (see Retry-After)",
        500: "Internal error (quote meta.request_id)",
        503: "Warehouse unavailable (see Retry-After)",
    }.items()
}
