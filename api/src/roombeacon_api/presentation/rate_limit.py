"""Sliding-window rate limiting for /api/* routes.

Valid API keys get their own bucket; everything else (no key, wrong key) is
bucketed by client IP so key guessing is throttled too. State is in-process,
so the container runs a single uvicorn worker.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
import hashlib
import math
import threading
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from .envelope import error_item, error_response
from .security import API_KEY_HEADER


WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 10_000


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float = WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key: str) -> RateDecision:
        now = self._clock()
        with self._lock:
            hits = self._hits.pop(key, None) or deque()
            while hits and now - hits[0] >= self._window:
                hits.popleft()
            allowed = len(hits) < self.limit
            if allowed:
                hits.append(now)
            self._hits[key] = hits
            while len(self._hits) > MAX_TRACKED_CLIENTS:
                self._hits.popitem(last=False)
            retry_after = 0 if allowed else max(1, math.ceil(self._window - (now - hits[0])))
            return RateDecision(allowed, self.limit, max(0, self.limit - len(hits)), retry_after)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: SlidingWindowRateLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)
        decision = self._limiter.hit(self._bucket(request))
        headers = {"X-RateLimit-Limit": str(decision.limit), "X-RateLimit-Remaining": str(decision.remaining)}
        if not decision.allowed:
            return error_response(
                request,
                429,
                f"Too many requests; retry after {decision.retry_after} seconds",
                errors=[error_item(None, "rate_limited", f"limit is {decision.limit} requests per minute")],
                headers={**headers, "Retry-After": str(decision.retry_after)},
            )
        response = await call_next(request)
        response.headers.update(headers)
        return response

    @staticmethod
    def _bucket(request: Request) -> str:
        presented = request.headers.get(API_KEY_HEADER)
        if presented and request.app.state.api_key_verifier.verify(presented):
            return "key:" + hashlib.sha256(presented.encode("utf-8")).hexdigest()[:32]
        return "ip:" + (request.client.host if request.client else "unknown")
