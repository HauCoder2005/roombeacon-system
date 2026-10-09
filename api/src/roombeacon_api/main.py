"""Composition root: wires settings, adapters, use cases and HTTP middleware.

Run: uvicorn roombeacon_api.main:app_factory --factory
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .application.listing_service import ListingService
from .application.location_service import LocationService
from .application.market_service import MarketService
from .application.ports import HistoryRepository, ImageStore, ListingRepository, LocationRepository, MarketRepository, PriceModel
from .application.price_estimate_service import PriceEstimateService
from .config import ApiSettings
from .infrastructure.clickhouse import LazyClickHouseClient
from .infrastructure.location_repository import ClickHouseLocationRepository
from .infrastructure.market_repository import ClickHouseHistoryRepository, ClickHouseMarketRepository
from .infrastructure.minio_image_store import MinioImageStore
from .infrastructure.price_model import ChampionPriceModel
from .infrastructure.silver_listing_repository import SilverListingRepository
from .infrastructure.logging import configure_logging
from .presentation.errors import register_exception_handlers
from .presentation.middleware import RequestContextMiddleware
from .presentation.rate_limit import RateLimitMiddleware, SlidingWindowRateLimiter
from .presentation.routers import health, legacy, listings, locations, market, price_estimates
from .presentation.security import API_KEY_HEADER, ApiKeyVerifier


def create_app(
    settings: ApiSettings | None = None,
    *,
    repository: LocationRepository | None = None,
    listing_repository: ListingRepository | None = None,
    history_repository: HistoryRepository | None = None,
    market_repository: MarketRepository | None = None,
    price_model: PriceModel | None = None,
    image_store: ImageStore | None = None,
) -> FastAPI:
    """Adapters are lazy: nothing connects or loads until the first request needs it."""
    settings = settings or ApiSettings.from_env()
    client = LazyClickHouseClient(settings.clickhouse)
    database = settings.clickhouse.database
    repository = repository or ClickHouseLocationRepository(client, database)
    listing_repository = listing_repository or SilverListingRepository(settings.silver_path)
    history_repository = history_repository or ClickHouseHistoryRepository(client, database)
    market_repository = market_repository or ClickHouseMarketRepository(client, database)
    price_model = price_model or ChampionPriceModel(settings.model_dir)
    if not settings.images_enabled:
        image_store = None
    elif image_store is None:
        image_store = MinioImageStore(settings.minio)

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
    app.state.listing_service = ListingService(listing_repository, history_repository, repository, price_model, image_store)
    app.state.estimate_service = PriceEstimateService(repository, price_model)
    app.state.market_service = MarketService(market_repository, repository)
    app.state.api_key_verifier = ApiKeyVerifier(settings.api_key_sha256)

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(locations.router)
    app.include_router(listings.router)
    app.include_router(price_estimates.router)
    app.include_router(market.router)
    app.include_router(legacy.router)  # last: catch-all for unversioned /api/... paths

    # Added innermost first: RequestContext wraps everything, so even 400/429/500 carry headers.
    app.add_middleware(RateLimitMiddleware, limiter=SlidingWindowRateLimiter(settings.rate_limit_per_minute))
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=[API_KEY_HEADER, "X-Request-ID", "If-None-Match", "Content-Type"],
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
