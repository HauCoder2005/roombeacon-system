import json
import logging
from datetime import datetime, timezone
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

    def _file_path(self, source: str, target_id: str) -> Path:
        return self.deferred_dir / f"{source}__{target_id}.json"

    def _load(self, source: str, target_id: str) -> dict[str, dict[str, Any]]:
        path = self._file_path(source, target_id)
        if not path.is_file():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            elif isinstance(data, list):
                # Hỗ trợ tương thích nếu file lưu dạng list
                return {item.get("platform_post_id"): item for item in data if isinstance(item, dict) and "platform_post_id" in item}
            return {}
        except Exception as exc:
            logger.warning("Lỗi đọc deferred backlog từ %s: %s. Khởi tạo rỗng.", path, exc)
            return {}

    def _save(self, source: str, target_id: str, data: dict[str, dict[str, Any]]) -> None:
        path = self._file_path(source, target_id)
        temp_file = path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(path)
        except Exception as exc:
            logger.error("Lỗi khi ghi deferred backlog vào %s: %s", path, exc)
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def get_backlog(self, source: str, target_id: str) -> list[DeferredDetailItem]:
        data = self._load(source, target_id)
        pending_items = [
            DeferredDetailItem.from_dict(v)
            for v in data.values()
            if v.get("status") == "PENDING"
        ]
        # Sắp xếp FIFO theo thời gian đầu tiên bị hoãn
        pending_items.sort(key=lambda x: x.first_deferred_at)
        return pending_items

    def count_backlog(self, source: str, target_id: str) -> int:
        data = self._load(source, target_id)
        return sum(1 for v in data.values() if v.get("status") == "PENDING")

    def enqueue(
        self, source: str, target_id: str, items: list[DeferredDetailItem]
    ) -> int:
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
    ) -> None:
        data = self._load(source, target_id)
        if platform_post_id in data:
            item_dict = data[platform_post_id]
            attempt_count = int(item_dict.get("attempt_count", 0)) + 1
            item_dict["attempt_count"] = attempt_count
            item_dict["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
            item_dict["last_error"] = str(error)

            if is_terminal or attempt_count >= max_retries:
                item_dict["status"] = "TERMINAL_FAILED"
                logger.warning(
                    "Deferred item %s chuyển sang trạng thái TERMINAL_FAILED (attempts=%d, error=%s)",
                    platform_post_id, attempt_count, error
                )
            else:
                item_dict["status"] = "PENDING"

            data[platform_post_id] = item_dict
            self._save(source, target_id, data)
