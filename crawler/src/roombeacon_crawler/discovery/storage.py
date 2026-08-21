from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from roombeacon_crawler.discovery.models import (
    DiscoveredUrl,
    DiscoveryArtifact,
    DiscoveryTargetState,
)

logger = logging.getLogger(__name__)


class DiscoveryStorage:
    """Component chuyên trách lưu trữ và đọc Artifact & State khám phá URL tại /data/discovery/."""

    DEFAULT_DISCOVERY_ROOT: str = "/data/discovery"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or self.DEFAULT_DISCOVERY_ROOT)
        self.state_dir = self.base_dir / "state"

    def save_artifact(
        self,
        source: str,
        run_id: str,
        urls: list[DiscoveredUrl],
    ) -> DiscoveryArtifact:
        """Lưu danh sách DiscoveredUrl xuống artifact JSON an toàn (Atomic write)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        artifact_dir = self.base_dir / source / run_id
        artifact_file = artifact_dir / "discovered_urls.json"

        artifact_dict = {
            "source": source,
            "run_id": run_id,
            "discovered_at": now_iso,
            "count": len(urls),
            "urls": [u.to_dict() for u in urls],
            "artifact_path": str(artifact_file),
        }

        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = artifact_dir / f".tmp_{artifact_file.name}"
            tmp_file.write_text(
                json.dumps(artifact_dict, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_file, artifact_file)
            logger.info("DiscoveryStorage: Đã lưu %d URLs tại %s", len(urls), artifact_file)
        except Exception as exc:
            logger.warning("DiscoveryStorage: Không thể lưu artifact tại %s: %s", artifact_file, exc)

        return DiscoveryArtifact.from_dict(artifact_dict)

    def load_artifact(self, artifact_path: str | Path) -> DiscoveryArtifact | None:
        """Đọc và chuyển đổi file artifact JSON thành DiscoveryArtifact."""
        path = Path(artifact_path)
        if not path.exists():
            logger.warning("DiscoveryStorage: File artifact không tồn tại: %s", path)
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DiscoveryArtifact.from_dict(data)
        except Exception as exc:
            logger.error("DiscoveryStorage: Lỗi đọc file artifact %s: %s", path, exc)
            return None

    def get_seen_urls(self, source: str) -> set[str]:
        """Lấy tập hợp các candidate URL đã thấy trong các lần discovery trước."""
        state_file = self.state_dir / f"{source}__seen_urls.json"
        if not state_file.exists():
            return set()
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return set(data)
            return set()
        except Exception as exc:
            logger.warning("DiscoveryStorage: Lỗi đọc seen URLs của %s: %s", source, exc)
            return set()

    def record_seen_urls(self, source: str, urls: list[str] | set[str]) -> None:
        """Ghi nhận thêm các candidate URL mới vào kho lưu vết seen URLs của nguồn."""
        if not urls:
            return
        current_seen = self.get_seen_urls(source)
        updated_seen = sorted(list(current_seen.union(urls)))
        state_file = self.state_dir / f"{source}__seen_urls.json"
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = self.state_dir / f".tmp_{state_file.name}"
            tmp_file.write_text(
                json.dumps(updated_seen, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_file, state_file)
        except Exception as exc:
            logger.warning("DiscoveryStorage: Lỗi lưu seen URLs của %s: %s", source, exc)

    def get_target_state(self, source: str) -> DiscoveryTargetState | None:
        """Đọc trạng thái DiscoveryTargetState của nguồn."""
        state_file = self.state_dir / f"{source}__state.json"
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return DiscoveryTargetState.from_dict(data)
        except Exception as exc:
            logger.warning("DiscoveryStorage: Lỗi đọc DiscoveryTargetState của %s: %s", source, exc)
            return None

    def save_target_state(self, state: DiscoveryTargetState) -> None:
        """Lưu DiscoveryTargetState an toàn."""
        state_file = self.state_dir / f"{state.source}__state.json"
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = self.state_dir / f".tmp_{state_file.name}"
            tmp_file.write_text(
                json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_file, state_file)
        except Exception as exc:
            logger.warning("DiscoveryStorage: Lỗi lưu DiscoveryTargetState của %s: %s", state.source, exc)
