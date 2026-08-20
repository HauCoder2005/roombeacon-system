import json
import logging
import os
from pathlib import Path
from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.repositories.crawl_state_repository import (
    CrawlStateRepository,
)

logger = logging.getLogger(__name__)


class LocalCrawlStateRepository(CrawlStateRepository):
    """Triển khai lưu vết cục bộ filesystem dưới /data/state (hoặc <CRAWLER_DATA_DIR>/state).

    Cấu trúc thư mục:
    <base_dir>/state/
    ├── targets/
    │   └── {source}__{target_id}.json
    └── seen/
        └── {source}__{target_id}.json
    """

    def __init__(self, base_data_dir: str | Path | None = None) -> None:
        raw_dir = base_data_dir or env.crawler.data_dir
        self.base_dir = Path(raw_dir).resolve() / "state"
        try:
            self.targets_dir = self.base_dir / "targets"
            self.seen_dir = self.base_dir / "seen"
            self.targets_dir.mkdir(parents=True, exist_ok=True)
            self.seen_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            # Fallback an toàn cho môi trường test/local khi /data không ghi được
            fallback_base = Path("./data/state").resolve()
            self.base_dir = fallback_base
            self.targets_dir = self.base_dir / "targets"
            self.seen_dir = self.base_dir / "seen"
            self.targets_dir.mkdir(parents=True, exist_ok=True)
            self.seen_dir.mkdir(parents=True, exist_ok=True)

    def _target_file(self, source: str, target_id: str) -> Path:
        return self.targets_dir / f"{source}__{target_id}.json"

    def _seen_file(self, source: str, target_id: str) -> Path:
        return self.seen_dir / f"{source}__{target_id}.json"

    def get_state(self, source: str, target_id: str) -> CrawlTargetState | None:
        path = self._target_file(source, target_id)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CrawlTargetState.from_dict(data)
        except Exception as exc:
            logger.warning(
                "Lỗi khi đọc state từ %s: %s. Khởi tạo trạng thái rỗng.",
                path,
                exc,
            )
            return None

    def save_state(self, state: CrawlTargetState) -> None:
        path = self._target_file(state.source, state.target_id)
        temp_file = path.with_suffix(".tmp")
        data = state.to_dict()
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, path)
            logger.info(
                "Đã lưu state an toàn cho %s/%s tại %s",
                state.source,
                state.target_id,
                path,
            )
        except Exception as exc:
            if temp_file.is_file():
                temp_file.unlink(missing_ok=True)
            logger.error("Lỗi khi lưu state tại %s: %s", path, exc)
            raise

    def get_seen_listing_ids(self, source: str, target_id: str) -> set[str]:
        path = self._seen_file(source, target_id)
        if not path.is_file():
            return set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data) if isinstance(data, list) else set()
        except Exception as exc:
            logger.warning("Lỗi khi đọc seen listing ids từ %s: %s", path, exc)
            return set()

    def record_seen_listing_ids(
        self, source: str, target_id: str, listing_ids: set[str] | list[str]
    ) -> None:
        if not listing_ids:
            return
        current_seen = self.get_seen_listing_ids(source, target_id)
        current_seen.update(listing_ids)
        path = self._seen_file(source, target_id)
        temp_file = path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(current_seen)), f, ensure_ascii=False, indent=2)
            os.replace(temp_file, path)
        except Exception as exc:
            if temp_file.is_file():
                temp_file.unlink(missing_ok=True)
            logger.error("Lỗi khi lưu seen ids tại %s: %s", path, exc)
            raise
