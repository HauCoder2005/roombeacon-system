from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path

logger = logging.getLogger("BRONZE_DISCOVERY")


@dataclass(frozen=True)
class BronzeRunInfo:
    """Thông tin siêu dữ liệu của một phiên cào Bronze trên đĩa vật lý."""
    source: str
    date: str
    run_id: str
    run_path: str
    listings_path: str
    details_path: str | None = None
    metadata_path: str | None = None
    record_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BronzeRunInfo":
        return cls(**d)


class BronzeRunDiscoveryService:
    """Dịch vụ quét và phát hiện các Bronze runs hợp lệ từ kho lưu trữ vật lý /data/bronze."""

    @classmethod
    def discover_bronze_runs(cls, bronze_root: str | Path = "/data/bronze") -> list[BronzeRunInfo]:
        root = Path(bronze_root)
        if not root.exists() or not root.is_dir():
            logger.warning("Thư mục Bronze root không tồn tại: %s", root)
            return []

        discovered: list[BronzeRunInfo] = []

        # Quét cấu trúc: /data/bronze/<source>/<date>/<run_id>/
        for source_dir in sorted(root.iterdir()):
            if not source_dir.is_dir() or source_dir.name.startswith("."):
                continue
            source = source_dir.name

            for date_dir in sorted(source_dir.iterdir()):
                if not date_dir.is_dir() or date_dir.name.startswith("."):
                    continue
                date_str = date_dir.name

                for run_dir in sorted(date_dir.iterdir()):
                    if not run_dir.is_dir() or run_dir.name.startswith("."):
                        continue
                    run_id = run_dir.name

                    listings_file = run_dir / "listings.json"
                    if not listings_file.exists():
                        continue

                    # Đếm số lượng record dự kiến và kiểm tra tính hợp lệ của JSON
                    try:
                        with open(listings_file, "r", encoding="utf-8") as f:
                            listings_data = json.load(f)
                        if not isinstance(listings_data, list):
                            logger.warning("File listings.json tại %s không phải là list JSON, bỏ qua.", run_dir)
                            continue
                        record_count = len(listings_data)
                    except Exception as err:
                        logger.warning("Lỗi đọc JSON tại %s (bỏ qua run bị lỗi): %s", listings_file, err)
                        continue

                    details_file = run_dir / "details.json"
                    details_path = str(details_file) if details_file.exists() else None

                    meta_file = run_dir / "metadata.json"
                    if not meta_file.exists():
                        meta_file = run_dir / "manifest.json"
                    metadata_path = str(meta_file) if meta_file.exists() else None

                    run_info = BronzeRunInfo(
                        source=source,
                        date=date_str,
                        run_id=run_id,
                        run_path=str(run_dir),
                        listings_path=str(listings_file),
                        details_path=details_path,
                        metadata_path=metadata_path,
                        record_count=record_count,
                    )
                    discovered.append(run_info)

        logger.info("Đã phát hiện tổng cộng %d Bronze runs hợp lệ trên đĩa vật lý.", len(discovered))
        return discovered
