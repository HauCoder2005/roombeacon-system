"""/api/v1/listings: search, detail (market comparison + model valuation), price history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from ...application.listing_service import LISTING_SORT_FIELDS, ListingFilters, ListingService
from ...application.pagination import PageRequest
from ...application.sorting import SortSpec
from ..cards import listing_detail_out, listing_out, price_point_out
from ..envelope import ok_response
from ..params import LISTING_ID, LOCATION_ID, filters_of, normalize_text
from ..schemas import ERROR_RESPONSES, Envelope
from ..security import require_api_key


router = APIRouter(prefix="/api/v1/listings", tags=["listings"], dependencies=[Depends(require_api_key)])


def get_service(request: Request) -> ListingService:
    return request.app.state.listing_service


def _snapshot(request: Request):
    return request.app.state.location_service.snapshot()


@router.get("", summary="Search listings (TP.HCM, priced, deduplicated)", response_model=Envelope[list[dict[str, Any]]], responses=ERROR_RESPONSES)
def search_listings(
    request: Request,
    service: ListingService = Depends(get_service),
    district_id: str | None = Query(None, pattern=LOCATION_ID),
    ward_id: str | None = Query(None, pattern=LOCATION_ID),
    q: str = Query("", max_length=100, description="Case-insensitive text in the title"),
    price_min: int | None = Query(None, ge=0, le=1_000_000_000, description="VND per month"),
    price_max: int | None = Query(None, ge=0, le=1_000_000_000),
    area_min: float | None = Query(None, ge=0, le=10_000, description="m²"),
    area_max: float | None = Query(None, ge=0, le=10_000),
    intent: str = Query("RENT", max_length=16, description="RENT | TRANSFER | SALE | UNKNOWN | ANY"),
    include_duplicates: bool = Query(False),
    sort: str = Query("-last_observed_at", max_length=32, description="last_observed_at | price | area; prefix - for descending"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> Response:
    spec = SortSpec.parse(sort, LISTING_SORT_FIELDS)
    text = normalize_text(q)
    filters = ListingFilters(
        district_id=district_id, ward_id=ward_id, q=text, price_min=price_min, price_max=price_max,
        area_min=area_min, area_max=area_max, intent=intent.strip().upper(), exclude_duplicates=not include_duplicates,
    )
    result, valuations = service.search(filters, spec, PageRequest(page, per_page))
    return ok_response(
        request,
        message="Listings retrieved",
        data=[listing_out(card, valuations.get(card.id)) for card in result.items],
        resource="listing",
        snapshot=_snapshot(request),
        page=result,
        sort=spec,
        filters=filters_of(
            district_id=district_id, ward_id=ward_id, q=text, price_min=price_min, price_max=price_max,
            area_min=area_min, area_max=area_max,
            intent=None if filters.intent == "RENT" else filters.intent, include_duplicates=include_duplicates,
        ),
    )


@router.get("/{listing_id}", summary="Listing detail with market comparison and model valuation", response_model=Envelope[dict[str, Any]], responses=ERROR_RESPONSES)
def get_listing(
    request: Request,
    listing_id: str = Path(pattern=LISTING_ID),
    service: ListingService = Depends(get_service),
) -> Response:
    detail = service.get(listing_id)
    return ok_response(
        request,
        message="Listing retrieved",
        data=listing_detail_out(detail),
        resource="listing",
        snapshot=_snapshot(request),
        links={"self": request.url.path, "price_history": f"{request.url.path}/price-history"},
    )


@router.get("/{listing_id}/price-history", summary="Observed price history of one listing", response_model=Envelope[list[dict[str, Any]]], responses=ERROR_RESPONSES)
def get_price_history(
    request: Request,
    listing_id: str = Path(pattern=LISTING_ID),
    service: ListingService = Depends(get_service),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> Response:
    result = service.price_history(listing_id, PageRequest(page, per_page))
    return ok_response(
        request,
        message="Price history retrieved",
        data=[price_point_out(point) for point in result.items],
        resource="price_point",
        snapshot=_snapshot(request),
        page=result,
    )
