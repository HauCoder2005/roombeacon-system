from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from roombeacon_crawler.discovery.models import DiscoveredUrl, DiscoveryArtifact

logger = logging.getLogger(__name__)


class DiscoveryStorage:
    """Component chuyên trách lưu trữ và đọc Artifact khám phá URL tại /data/discovery/<source>/<run_id>/."""

    DEFAULT_DISCOVERY_ROOT: str = "/data/discovery"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or self.DEFAULT_DISCOVERY_ROOT)

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
