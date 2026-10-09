"""/api/v1/market: city or district summary and daily series."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from ...application.market_service import MarketService
from ..cards import day_out, summary_out
from ..envelope import ok_response
from ..params import LOCATION_ID, filters_of
from ..schemas import ERROR_RESPONSES, Envelope
from ..security import require_api_key


router = APIRouter(prefix="/api/v1/market", tags=["market"], dependencies=[Depends(require_api_key)])


def get_service(request: Request) -> MarketService:
    return request.app.state.market_service


@router.get("/summary", summary="Listing count and rent quantiles (city or one district)", response_model=Envelope[dict[str, Any]], responses=ERROR_RESPONSES)
def summary(
    request: Request,
    service: MarketService = Depends(get_service),
    district_id: str | None = Query(None, pattern=LOCATION_ID),
) -> Response:
    result, district = service.summary(district_id)
    return ok_response(
        request, message="Market summary retrieved", data=summary_out(result, district),
        resource="market_summary", snapshot=request.app.state.location_service.snapshot(),
        filters=filters_of(district_id=district_id),
    )


@router.get("/daily", summary="Daily observed listings, new listings, price changes and median rent", response_model=Envelope[list[dict[str, Any]]], responses=ERROR_RESPONSES)
def daily(
    request: Request,
    service: MarketService = Depends(get_service),
    district_id: str | None = Query(None, pattern=LOCATION_ID),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> Response:
    days = service.daily(district_id, date_from, date_to)
    return ok_response(
        request, message="Daily market series retrieved", data=[day_out(d) for d in days],
        resource="market_day", snapshot=request.app.state.location_service.snapshot(),
        filters=filters_of(
            district_id=district_id,
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
        ),
    )
