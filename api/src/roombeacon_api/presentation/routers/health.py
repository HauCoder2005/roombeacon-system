"""Liveness (/health, process only) and readiness (/ready, warehouse reachable). No auth."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..envelope import envelope


router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness probe")
def health(request: Request) -> JSONResponse:
    return JSONResponse(envelope(request, code=200, message="Service is alive", data={"status": "ok"}, resource="health"))


@router.get("/ready", summary="Readiness probe (checks the warehouse)")
def ready(request: Request) -> JSONResponse:
    request.app.state.location_service.ready()
    return JSONResponse(
        envelope(
            request,
            code=200,
            message="Service is ready",
            data={"status": "ready", "checks": {"warehouse": "ok"}},
            resource="health",
        )
    )
