"""Unversioned /api/... paths answer 301 to their /api/v1/... equivalent."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..envelope import envelope


router = APIRouter(include_in_schema=False)


@router.get("/api/{rest:path}")
def moved(request: Request, rest: str) -> JSONResponse:
    if rest == "v1" or rest.startswith("v1/"):
        raise StarletteHTTPException(status_code=404)
    target = "/api/v1/" + rest.lstrip("/")
    if request.url.query:
        target += "?" + request.url.query
    body = envelope(request, code=301, message=f"Endpoint moved to {target}", links={"location": target})
    return JSONResponse(body, status_code=301, headers={"Location": target, "Cache-Control": "no-store"})
