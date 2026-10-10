"""Persist local asset reconciliation status with atomic JSON updates.

The repository records outcomes only; URL validation, downloads and MinIO writes
belong to the asset reconciliation service.
"""

import json
import logging
from pathlib import Path
from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.asset_item import AssetItem, AssetStatus

logger = logging.getLogger(__name__)


class LocalAssetStateRepository:
    """Quản lý trạng thái bền vững (durable state) của các tài nguyên hình ảnh trên ổ đĩa vật lý."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            # Same mounted root as the crawl state, so asset outcomes survive container restarts.
            self.base_dir = (Path(env.crawler.data_dir) / "state" / "assets").resolve()
            try:
                self.base_dir.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError):
                self.base_dir = Path("./data/state/assets").resolve()
        else:
            self.base_dir = Path(base_dir).resolve()

        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_item_path(self, source: str, asset_id: str) -> Path:
        source_dir = self.base_dir / source
        source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir / f"{asset_id}.json"

    def get_asset(self, source: str, asset_id: str) -> AssetItem | None:
        """Đọc trạng thái asset từ file JSON."""
        item_path = self._get_item_path(source, asset_id)
        if not item_path.exists():
            return None
        try:
            with open(item_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AssetItem.from_dict(data)
        except Exception as exc:
            logger.warning("Asset state read failed (path=%s, error_class=%s)", item_path, type(exc).__name__)
            return None

    def save_asset(self, item: AssetItem) -> None:
        """Ghi trạng thái asset nguyên tử vào file JSON."""
        item_path = self._get_item_path(item.source, item.asset_id)
        tmp_path = item_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)
            tmp_path.replace(item_path)
        except Exception as exc:
            logger.error("Asset state write failed (path=%s, error_class=%s)", item_path, type(exc).__name__)
            if tmp_path.exists():
                tmp_path.unlink()

    def _cursor_path(self, source: str) -> Path:
        # Not *.json and outside the per-source folders, so status scans never see it.
        return self.base_dir / "_cursors" / f"{source}.cursor"

    def get_cursor(self, source: str) -> tuple[str, int] | None:
        """Where the backfill scan of a source stopped: (last_observed_at, rental_post_id)."""
        path = self._cursor_path(source)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data["last_observed_at"]), int(data["rental_post_id"])
        except Exception as exc:
            logger.warning("Asset cursor read failed (path=%s, error_class=%s)", path, type(exc).__name__)
            return None

    def save_cursor(self, source: str, cursor: tuple[str, int] | None) -> None:
        """Persist the backfill position; None restarts the next backfill from the newest posts."""
        path = self._cursor_path(source)
        if cursor is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps({"last_observed_at": str(cursor[0]), "rental_post_id": int(cursor[1])}), encoding="utf-8"
        )
        tmp_path.replace(path)

    def is_success(self, source: str, asset_id: str) -> bool:
        """Kiểm tra xem asset đã hoàn thành tải và upload MinIO thành công chưa."""
        item = self.get_asset(source, asset_id)
        return item is not None and item.status == AssetStatus.SUCCESS

    def is_terminal_failure(self, source: str, asset_id: str) -> bool:
        """Kiểm tra xem asset có bị lỗi vĩnh viễn không thể retry không."""
        item = self.get_asset(source, asset_id)
        return item is not None and item.status == AssetStatus.TERMINAL_FAILURE

    def count_by_status(self) -> dict[str, int]:
        """Thống kê số lượng asset theo từng trạng thái."""
        counts = {status.value: 0 for status in AssetStatus}
        for json_file in self.base_dir.glob("*/*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                st = data.get("status", AssetStatus.PENDING.value)
                counts[st] = counts.get(st, 0) + 1
            except Exception:
                pass
        return counts
