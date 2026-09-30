"""Persist and fairly retrieve deferred detail jobs from local JSON state.

The adapter owns backlog durability and retry status, not detail acquisition or
request-budget decisions.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.deferred_detail_item import DeferredDetailItem
from roombeacon_crawler.repositories.deferred_detail_repository import (
    DeferredDetailRepository,
)

logger = logging.getLogger(__name__)


class LocalDeferredDetailRepository(DeferredDetailRepository):
    """Triển khai hàng đợi hoãn cào chi tiết bền vững lưu trên host disk.

    Đường dẫn lưu trữ:
    <base_dir>/state/deferred/{source}__{target_id}.json
    """

    def __init__(self, base_data_dir: str | Path | None = None) -> None:
        raw_dir = base_data_dir or env.crawler.data_dir
        self.base_dir = Path(raw_dir).resolve() / "state"
        try:
            self.deferred_dir = self.base_dir / "deferred"
            self.deferred_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            fallback_base = Path("./data/state").resolve()
            self.base_dir = fallback_base
            self.deferred_dir = self.base_dir / "deferred"
            self.deferred_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}
        self._dirty = set()

    def _file_path(self, source: str, target_id: str) -> Path:
        return self.deferred_dir / f"{source}__{target_id}.json"

    def _load(self, source: str, target_id: str) -> dict[str, dict[str, Any]]:
        cache_key = f"{source}__{target_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]
            
        path = self._file_path(source, target_id)
        if not path.is_file():
            self._cache[cache_key] = {}
            return self._cache[cache_key]
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._cache[cache_key] = data
            elif isinstance(data, list):
                self._cache[cache_key] = {item.get("platform_post_id"): item for item in data if isinstance(item, dict) and "platform_post_id" in item}
            else:
                self._cache[cache_key] = {}
            return self._cache[cache_key]
        except Exception as exc:
            logger.warning("Deferred backlog read failed; using empty state (path=%s, error_class=%s)", path, type(exc).__name__)
            self._cache[cache_key] = {}
            return self._cache[cache_key]

    def _save(self, source: str, target_id: str, data: dict[str, dict[str, Any]]) -> None:
        cache_key = f"{source}__{target_id}"
        self._cache[cache_key] = data
        self._dirty.add(cache_key)
        
        # Throttled flush (optional, we will rely on explicit flush)
        if len(self._dirty) > 100:  # Just a safety valve, but actually we want to flush explicitly
            pass 

    def flush(self) -> None:
        for cache_key in list(self._dirty):
            source, target_id = cache_key.split("__", 1)
            path = self._file_path(source, target_id)
            temp_file = path.with_suffix(".tmp")
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self._cache[cache_key], f, indent=2, ensure_ascii=False)
                temp_file.replace(path)
                self._dirty.remove(cache_key)
            except Exception as exc:
                logger.error("Deferred backlog write failed (path=%s, error_class=%s)", path, type(exc).__name__)
                if temp_file.exists():
                    temp_file.unlink(missing_ok=True)

    def get_backlog(
        self,
        source: str,
        target_id: str,
        *,
        now: datetime | None = None,
    ) -> list[DeferredDetailItem]:
        """Return retry-eligible detail jobs in fair FIFO order."""
        data = self._load(source, target_id)
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        pending_items = [
            DeferredDetailItem.from_dict(v)
            for v in data.values()
            if v.get("status") == "PENDING"
        ]
        eligible_items = []
        for item in pending_items:
            if item.next_attempt_at:
                try:
                    eligible_at = datetime.fromisoformat(item.next_attempt_at)
                    if eligible_at.tzinfo is None:
                        eligible_at = eligible_at.replace(tzinfo=timezone.utc)
                    if eligible_at > current_time:
                        continue
                except (TypeError, ValueError):
                    pass
            eligible_items.append(item)
        # Never-attempted FIFO items precede retries. A transiently failing item
        # therefore cannot monopolize the head of a large enrichment queue.
        eligible_items.sort(
            key=lambda item: (
                item.attempt_count > 0,
                item.first_deferred_at,
                item.last_attempt_at or "",
            )
        )
        return eligible_items

    def count_backlog(self, source: str, target_id: str) -> int:
        """Count pending jobs without applying retry-time eligibility."""
        data = self._load(source, target_id)
        return sum(1 for v in data.values() if v.get("status") == "PENDING")

    def enqueue(
        self, source: str, target_id: str, items: list[DeferredDetailItem]
    ) -> int:
        """Add new detail jobs idempotently and return the number accepted."""
        if not items:
            return 0
        data = self._load(source, target_id)
        added_count = 0
        for item in items:
            lid = item.platform_post_id
            if not lid:
                continue
            if lid in data:
                existing = data[lid]
                # Nếu đã PENDING hoặc đã hoàn thành, không tạo trùng lặp
                if existing.get("status") in ("PENDING", "COMPLETED"):
                    continue
            data[lid] = item.to_dict()
            added_count += 1

        if added_count > 0:
            self._save(source, target_id, data)
            logger.info("Đã thêm %d tin vào Deferred Detail Backlog cho %s/%s", added_count, source, target_id)
        return added_count

    def record_success(
        self, source: str, target_id: str, platform_post_id: str
    ) -> None:
        """Remove a completed job so the durable backlog remains compact."""
        data = self._load(source, target_id)
        if platform_post_id in data:
            # Xóa khỏi danh sách chờ để giữ file gọn gàng
            del data[platform_post_id]
            self._save(source, target_id, data)
            logger.debug("Đã hoàn tất deferred detail cho %s (%s/%s)", platform_post_id, source, target_id)

    def record_failure(
        self,
        source: str,
        target_id: str,
        platform_post_id: str,
        error: str,
        is_terminal: bool = False,
        max_retries: int = 3,
        now: datetime | None = None,
        retry_backoff_seconds: int = 900,
    ) -> None:
        """Record retry metadata or make an exhausted job terminal."""
        data = self._load(source, target_id)
        if platform_post_id in data:
            item_dict = data[platform_post_id]
            attempt_count = int(item_dict.get("attempt_count", 0)) + 1
            item_dict["attempt_count"] = attempt_count
            attempted_at = now or datetime.now(timezone.utc)
            if attempted_at.tzinfo is None:
                attempted_at = attempted_at.replace(tzinfo=timezone.utc)
            item_dict["last_attempt_at"] = attempted_at.isoformat()
            item_dict["last_error"] = str(error)

            if is_terminal or attempt_count >= max_retries:
                item_dict["status"] = "TERMINAL_FAILED"
                logger.warning(
                    "Deferred item became terminal (post_id=%s, attempts=%d, error_class=%s)",
                    platform_post_id,
                    attempt_count,
                    type(error).__name__,
                )
            else:
                item_dict["status"] = "PENDING"
                delay = max(0, int(retry_backoff_seconds)) * (2 ** (attempt_count - 1))
                item_dict["next_attempt_at"] = (
                    attempted_at + timedelta(seconds=delay)
                ).isoformat()

            data[platform_post_id] = item_dict
            self._save(source, target_id, data)
