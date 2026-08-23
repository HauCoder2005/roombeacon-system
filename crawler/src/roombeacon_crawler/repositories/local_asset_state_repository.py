import json
import logging
from pathlib import Path
from typing import Any

from roombeacon_crawler.models.asset_item import AssetItem, AssetStatus

logger = logging.getLogger(__name__)


class LocalAssetStateRepository:
    """Quản lý trạng thái bền vững (durable state) của các tài nguyên hình ảnh trên ổ đĩa vật lý."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        if base_dir is None:
            candidate = Path("./data/state/assets").resolve()
            if candidate.parent.parent.exists():
                self.base_dir = candidate
            elif Path("/data/state/assets").exists():
                self.base_dir = Path("/data/state/assets")
            else:
                self.base_dir = candidate
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
            logger.warning("Không thể đọc asset state tại %s: %s", item_path, exc)
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
            logger.error("Không thể ghi asset state tại %s: %s", item_path, exc)
            if tmp_path.exists():
                tmp_path.unlink()

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
