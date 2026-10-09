"""The response "ID card": every body has the same keys, success or error.

    {success, code, status, message, data, errors, meta, links}

``meta`` always carries request_id, timestamp, api_version, method, path,
duration_ms, resource, data_snapshot, cache, pagination, sort and filters;
absent values are null, never missing. 304 is the only body-less response.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from ..application.pagination import Page
from ..application.sorting import SortSpec
from ..domain.models import DataSnapshot


API_VERSION = "v1"
CACHE_SECONDS = 300
STATUS_NAMES = {
    200: "OK",
    300: "MULTIPLE_CHOICES",
    301: "MOVED_PERMANENTLY",
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid is None:
        rid = request.state.request_id = f"req_{uuid4().hex[:20]}"
    return rid


def iso(moment: datetime | None) -> str | None:
    return None if moment is None else _iso(moment)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def envelope(
    request: Request,
    *,
    code: int,
    message: str,
    data: Any = None,
    errors: Sequence[Mapping[str, Any]] | None = None,
    resource: str | None = None,
    snapshot: DataSnapshot | None = None,
    etag: str | None = None,
    pagination: Mapping[str, Any] | None = None,
    sort: SortSpec | None = None,
    filters: Mapping[str, Any] | None = None,
    links: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    started = getattr(request.state, "started", None)
    return {
        "success": 200 <= code < 300,
        "code": code,
        "status": STATUS_NAMES.get(code, "ERROR"),
        "message": message,
        "data": data,
        "errors": list(errors) if errors is not None else None,
        "meta": {
            "request_id": request_id(request),
            "timestamp": _iso(now),
            "api_version": API_VERSION,
            "method": request.method,
            "path": request.url.path,
            "duration_ms": int((time.perf_counter() - started) * 1000) if started else 0,
            "resource": resource,
            "data_snapshot": (
                {"snapshot_id": snapshot.snapshot_id, "loaded_at": _iso(snapshot.loaded_at)} if snapshot else None
            ),
            "cache": (
                {"etag": etag, "expires_at": _iso(now + timedelta(seconds=CACHE_SECONDS))} if etag else None
            ),
            "pagination": dict(pagination) if pagination is not None else None,
            "sort": [sort.token] if sort is not None else None,
            "filters": dict(filters) if filters is not None else None,
        },
        "links": dict(links) if links is not None else None,
    }


def error_response(
    request: Request,
    code: int,
    message: str,
    errors: Sequence[Mapping[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
    data: Any = None,
    links: Mapping[str, Any] | None = None,
    resource: str | None = None,
) -> JSONResponse:
    body = envelope(request, code=code, message=message, errors=errors, data=data, links=links, resource=resource)
    return JSONResponse(body, status_code=code, headers={"Cache-Control": "no-store", **(headers or {})})


def error_item(field: str | None, code: str, message: str) -> dict[str, Any]:
    return {"field": field, "code": code, "message": message}


def compute_etag(request: Request, snapshot: DataSnapshot) -> str:
    query = sorted(request.query_params.multi_items())
    raw = f"{API_VERSION}|{snapshot.snapshot_id}|{request.url.path}?{urlencode(query)}"
    return '"' + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] + '"'


def _not_modified(request: Request, etag: str) -> bool:
    presented = request.headers.get("If-None-Match", "")
    return etag in {tag.strip() for tag in presented.split(",")} or presented.strip() == "*"


def ok_response(
    request: Request,
    *,
    message: str,
    data: Any,
    resource: str,
    snapshot: DataSnapshot | None,
    page: Page | None = None,
    sort: SortSpec | None = None,
    filters: Mapping[str, Any] | None = None,
    links: Mapping[str, Any] | None = None,
    cacheable: bool = True,
) -> Response:
    """200 with ETag; 304 when the client already holds this snapshot's version."""
    etag = compute_etag(request, snapshot) if snapshot and cacheable else None
    cache_headers = {"Cache-Control": f"private, max-age={CACHE_SECONDS}"}
    if etag:
        cache_headers["ETag"] = etag
        if _not_modified(request, etag):
            return Response(status_code=304, headers=cache_headers)
    body = envelope(
        request,
        code=200,
        message=message,
        data=data,
        resource=resource,
        snapshot=snapshot,
        etag=etag,
        pagination=pagination_meta(page) if page else None,
        sort=sort,
        filters=filters,
        links=page_links(request, page, sort) if page else links,
    )
    return JSONResponse(body, status_code=200, headers=cache_headers if etag else {"Cache-Control": "no-store"})


def pagination_meta(page: Page) -> dict[str, Any]:
    return {
        "page": page.request.page,
        "per_page": page.request.per_page,
        "total_items": page.total,
        "total_pages": page.total_pages,
        "has_next": page.has_next,
        "has_prev": page.has_prev,
    }


def page_links(request: Request, page: Page, sort: SortSpec | None) -> dict[str, str | None]:
    extra = [(k, v) for k, v in request.query_params.multi_items() if k not in {"page", "per_page", "sort"}]

    def link(number: int) -> str:
        params = [("page", str(number)), ("per_page", str(page.request.per_page))]
        if sort is not None:
            params.append(("sort", sort.token))
        return f"{request.url.path}?{urlencode(params + extra)}"

    last = max(page.total_pages, 1)
    return {
        "self": link(page.request.page),
        "first": link(1),
        "prev": link(page.request.page - 1) if page.has_prev else None,
        "next": link(page.request.page + 1) if page.has_next else None,
        "last": link(last),
    }
