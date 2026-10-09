"""/api/v1/price-estimates: rent estimate from the locked champion model."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ...application.price_estimate_service import PriceEstimateService
from ..cards import estimate_out, model_info_out
from ..envelope import ok_response
from ..params import LOCATION_ID
from ..schemas import ERROR_RESPONSES, Envelope
from ..security import require_api_key


router = APIRouter(prefix="/api/v1/price-estimates", tags=["price estimates"], dependencies=[Depends(require_api_key)])


class EstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_m2: float = Field(ge=5, le=500, description="Room area in m²")
    district_id: str = Field(pattern=LOCATION_ID, description="From /api/v1/locations/districts")
    ward_id: str | None = Field(None, pattern=LOCATION_ID, description="Optional; must belong to district_id")


def get_service(request: Request) -> PriceEstimateService:
    return request.app.state.estimate_service


@router.get("/model", summary="Champion model card", response_model=Envelope[dict[str, Any]], responses=ERROR_RESPONSES)
def model_card(request: Request, service: PriceEstimateService = Depends(get_service)) -> Response:
    return ok_response(
        request, message="Model information retrieved", data=model_info_out(service.model_info()),
        resource="price_model", snapshot=None,
    )


@router.post("", summary="Estimate monthly rent for an area and location", response_model=Envelope[dict[str, Any]], responses=ERROR_RESPONSES)
def estimate(request: Request, body: EstimateRequest, service: PriceEstimateService = Depends(get_service)) -> Response:
    result = service.estimate(body.area_m2, body.district_id, body.ward_id)
    return ok_response(
        request,
        message="Rent estimated",
        data=estimate_out(result),
        resource="price_estimate",
        snapshot=request.app.state.location_service.snapshot(),
        cacheable=False,
    )
