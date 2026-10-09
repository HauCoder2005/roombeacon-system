"""Composition root: wires settings, adapters, use cases and HTTP middleware.

Run: uvicorn roombeacon_api.main:app_factory --factory
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .application.location_service import LocationService
from .application.ports import LocationRepository
from .config import ApiSettings
from .infrastructure.clickhouse import LazyClickHouseClient
from .infrastructure.location_repository import ClickHouseLocationRepository
from .infrastructure.logging import configure_logging
from .presentation.errors import register_exception_handlers
from .presentation.middleware import RequestContextMiddleware
from .presentation.rate_limit import RateLimitMiddleware, SlidingWindowRateLimiter
from .presentation.routers import health, legacy, locations
from .presentation.security import API_KEY_HEADER, ApiKeyVerifier


def create_app(settings: ApiSettings | None = None, *, repository: LocationRepository | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    if repository is None:
        repository = ClickHouseLocationRepository(LazyClickHouseClient(settings.clickhouse), settings.clickhouse.database)

    app = FastAPI(
        title="RoomBeacon API",
        version=__version__,
        description="Read-only RoomBeacon data. Every response uses the same envelope.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.location_service = LocationService(repository)
    app.state.api_key_verifier = ApiKeyVerifier(settings.api_key_sha256)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(locations.router)
    app.include_router(legacy.router)  # last: catch-all for unversioned /api/... paths

    # Added innermost first: RequestContext wraps everything, so even 400/429/500 carry headers.
    app.add_middleware(RateLimitMiddleware, limiter=SlidingWindowRateLimiter(settings.rate_limit_per_minute))
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET"],
            allow_headers=[API_KEY_HEADER, "X-Request-ID", "If-None-Match"],
            expose_headers=["ETag", "X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
            allow_credentials=False,
            max_age=600,
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(RequestContextMiddleware)
    return app


def app_factory() -> FastAPI:
    configure_logging()
    return create_app()
