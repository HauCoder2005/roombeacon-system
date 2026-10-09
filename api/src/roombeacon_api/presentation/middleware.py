"""Request context: request id, timing, security headers, access log, last-resort 500."""

from __future__ import annotations

import logging
import re
import time
import traceback
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .envelope import error_item, error_response


logger = logging.getLogger("roombeacon_api.access")
error_logger = logging.getLogger("roombeacon_api.error")
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
DOCS_PATHS = ("/docs", "/openapi.json")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}
JSON_CSP = "default-src 'none'; frame-ancestors 'none'"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if SAFE_REQUEST_ID.fullmatch(incoming) else f"req_{uuid4().hex[:20]}"
        request.state.request_id = rid
        request.state.started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Type and stack frames only: exception messages may carry DSNs or secrets.
            error_logger.error(
                "unhandled error request_id=%s type=%s\n%s",
                rid,
                type(exc).__name__,
                "".join(traceback.format_tb(exc.__traceback__)),
                extra={"request_id": rid},
            )
            response = error_response(
                request,
                500,
                "Internal server error; quote the request_id when reporting it",
                errors=[error_item(None, "internal_error", "Unexpected server error")],
            )
        response.headers["X-Request-ID"] = rid
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith(DOCS_PATHS):
            response.headers.setdefault("Content-Security-Policy", JSON_CSP)
        response.headers.setdefault("Cache-Control", "no-store")
        if "server" in response.headers:
            del response.headers["server"]
        logger.info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "request_id": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": int((time.perf_counter() - request.state.started) * 1000),
                "client": request.client.host if request.client else None,
            },
        )
        return response
