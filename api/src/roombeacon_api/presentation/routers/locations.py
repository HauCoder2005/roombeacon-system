"""/api/v1/locations: district and ward cards for UI card grids and pickers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse, Response

from ...application.location_service import SORT_FIELDS, LocationService
from ...application.pagination import PageRequest
from ...application.sorting import SortSpec
from ...domain.errors import AmbiguousLocationError
from ..cards import district_out, ward_out
from ..envelope import envelope, ok_response
from ..schemas import ERROR_RESPONSES, ChoicesOut, DistrictCardOut, Envelope, WardCardOut
from ..params import LOCATION_ID, filters_of as _filters, normalize_text as _text
from ..security import require_api_key


router = APIRouter(prefix="/api/v1/locations", tags=["locations"], dependencies=[Depends(require_api_key)])


def get_service(request: Request) -> LocationService:
    return request.app.state.location_service


def _covers(request: Request, level: str, ids: list[str]) -> dict:
    service = request.app.state.cover_service
    return service.covers(level, ids) if service is not None else {}


@router.get(
    "/districts",
    summary="List district cards",
    response_model=Envelope[list[DistrictCardOut]],
    responses=ERROR_RESPONSES,
)
def list_districts(
    request: Request,
    service: LocationService = Depends(get_service),
    q: str = Query("", max_length=100, description="Case-insensitive name search"),
    sort: str = Query("-listing_count", max_length=32, description="name | listing_count | median_price; prefix - for descending"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> Response:
    spec = SortSpec.parse(sort, SORT_FIELDS)
    result = service.list_districts(_text(q), spec, PageRequest(page, per_page))
    covers = _covers(request, "district", [card.id for card in result.items])
    return ok_response(
        request,
        message="District cards retrieved",
        data=[district_out(card, covers.get(card.id)) for card in result.items],
        resource="district",
        snapshot=service.snapshot(),
        page=result,
        sort=spec,
        filters=_filters(q=_text(q)),
    )


@router.get(
    "/districts/{district_id}",
    summary="Get one district card",
    response_model=Envelope[DistrictCardOut],
    responses=ERROR_RESPONSES,
)
def get_district(
    request: Request,
    district_id: str = Path(pattern=LOCATION_ID),
    service: LocationService = Depends(get_service),
) -> Response:
    card = service.get_district(district_id)
    return ok_response(
        request,
        message="District card retrieved",
        data=district_out(card, _covers(request, "district", [card.id]).get(card.id)),
        resource="district",
        snapshot=service.snapshot(),
        links={"self": request.url.path, "wards": f"{request.url.path}/wards"},
    )


@router.get(
    "/districts/{district_id}/wards",
    summary="List ward cards of a district",
    response_model=Envelope[list[WardCardOut]],
    responses=ERROR_RESPONSES,
)
def list_wards(
    request: Request,
    district_id: str = Path(pattern=LOCATION_ID),
    service: LocationService = Depends(get_service),
    q: str = Query("", max_length=100),
    sort: str = Query("-listing_count", max_length=32),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> Response:
    spec = SortSpec.parse(sort, SORT_FIELDS)
    result = service.list_wards(district_id, _text(q), spec, PageRequest(page, per_page))
    covers = _covers(request, "ward", [card.id for card in result.items])
    return ok_response(
        request,
        message="Ward cards retrieved",
        data=[ward_out(card, covers.get(card.id)) for card in result.items],
        resource="ward",
        snapshot=service.snapshot(),
        page=result,
        sort=spec,
        filters=_filters(q=_text(q)),
    )


@router.get(
    "/resolve",
    summary="Resolve a ward name to one card (300 when ambiguous)",
    response_model=Envelope[WardCardOut],
    responses={300: {"model": Envelope[ChoicesOut], "description": "Several wards share this name"}, **ERROR_RESPONSES},
)
def resolve_ward(
    request: Request,
    service: LocationService = Depends(get_service),
    ward: str = Query(..., min_length=1, max_length=100, description="Exact ward name, case-insensitive"),
    district_id: str | None = Query(None, pattern=LOCATION_ID, description="Narrow to one district"),
) -> Response:
    try:
        card = service.resolve_ward(_text(ward), district_id)
    except AmbiguousLocationError as exc:
        body = envelope(
            request,
            code=300,
            message="The ward name matches several places; pick one",
            data={"choices": [ward_out(choice) for choice in exc.choices]},
            resource="ward",
            filters=_filters(ward=_text(ward), district_id=district_id),
        )
        return JSONResponse(body, status_code=300, headers={"Cache-Control": "no-store"})
    return ok_response(
        request,
        message="Ward resolved",
        data=ward_out(card, _covers(request, "ward", [card.id]).get(card.id)),
        resource="ward",
        snapshot=service.snapshot(),
        filters=_filters(ward=_text(ward), district_id=district_id),
    )
