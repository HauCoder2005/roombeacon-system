import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class RateLimitPolicy:
    """Chính sách điều tiết tốc độ gửi request và giới hạn số lượng concurrency."""

    def __init__(
        self,
        delay_seconds: float = 1.5,
        max_concurrency: int = 1,
    ) -> None:
        self.delay_seconds = max(0.0, delay_seconds)
        self.semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def throttle(self) -> None:
        """Đảm bảo khoảng cách tối thiểu giữa các request liên tiếp."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.delay_seconds:
                wait_time = self.delay_seconds - elapsed
                logger.debug("Rate limit: Chờ %.2f giây trước request tiếp theo", wait_time)
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()
