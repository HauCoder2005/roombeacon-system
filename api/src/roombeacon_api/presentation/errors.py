"""Map every error to the envelope with the matching HTTP status."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..domain.errors import DependencyUnavailableError, InvalidParameterError, NotFoundError
from .envelope import error_item, error_response
from .security import UnauthorizedError


RETRY_AFTER_SECONDS = "30"
HTTP_MESSAGES = {404: "Route not found", 405: "Method not allowed", 400: "Bad request"}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    async def unauthorized(request: Request, exc: UnauthorizedError):
        return error_response(
            request,
            401,
            "Missing or invalid API key",
            errors=[error_item("X-API-Key", "unauthorized", "Provide a valid X-API-Key header")],
            headers={"WWW-Authenticate": "ApiKey"},
        )

    @app.exception_handler(InvalidParameterError)
    async def invalid_parameter(request: Request, exc: InvalidParameterError):
        return error_response(request, 422, "Invalid request parameters", errors=[error_item(exc.field, exc.code, exc.message)])

    @app.exception_handler(RequestValidationError)
    async def request_validation(request: Request, exc: RequestValidationError):
        errors = [
            error_item(str(err["loc"][-1]) if err.get("loc") else None, str(err.get("type", "invalid")), str(err.get("msg", "")))
            for err in exc.errors()
        ]
        return error_response(request, 422, "Invalid request parameters", errors=errors)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return error_response(
            request,
            404,
            f"{exc.resource.capitalize()} not found",
            errors=[error_item(f"{exc.resource}_id" if exc.resource in {"district", "listing"} else exc.resource, "not_found", f"No {exc.resource} matches the request")],
            resource=exc.resource,
        )

    @app.exception_handler(DependencyUnavailableError)
    async def unavailable(request: Request, exc: DependencyUnavailableError):
        return error_response(
            request,
            503,
            f"Service temporarily unavailable; retry after {RETRY_AFTER_SECONDS} seconds",
            errors=[error_item(None, "dependency_unavailable", exc.dependency)],
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        message = HTTP_MESSAGES.get(exc.status_code, "Request failed")
        code = "not_found" if exc.status_code == 404 else "http_error"
        return error_response(
            request, exc.status_code, message, errors=[error_item(None, code, message)], headers=getattr(exc, "headers", None)
        )
