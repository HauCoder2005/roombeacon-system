from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from roombeacon_crawler.config.get_env import env
from roombeacon_crawler.models.crawl_metadata import CrawlMetadata
from roombeacon_crawler.models.crawl_run_result import CrawlRunResult
from roombeacon_crawler.models.listing_card_raw import ListingCardRaw
from roombeacon_crawler.models.listing_detail_raw import ListingDetailRaw
from roombeacon_crawler.models.rental_bronze_record import RentalBronzeRecord

logger = logging.getLogger(__name__)


class LocalStorageWriter:
    """Quản lý việc lưu trữ cục bộ (filesystem) phân tách rõ ràng giữa:

    1. Run Manifest (metadata phiên crawl - luôn được lưu cho mọi run).
    2. Bronze Dataset (dữ liệu thô - chỉ được lưu khi có dữ liệu thực tế: records_created > 0).
       - listings.json: Dữ liệu thô từ listing cards.
       - details.json: Dữ liệu thô chi tiết từ detail pages (chỉ lưu khi có details).
       - metadata.json: Metadata quá trình crawl.

    Root path luôn được phân giải tuyệt đối từ cấu hình CRAWLER_DATA_DIR (env.crawler.data_dir).
    """

    def __init__(self, base_data_dir: str | Path | None = None) -> None:
        raw_dir = base_data_dir or env.crawler.data_dir
        self.base_data_dir = Path(raw_dir).resolve()

    def save_manifest(self, result: CrawlRunResult) -> str:
        """Lưu Manifest của phiên crawl vào <data_dir>/manifests/<source>/<date>/<run_id>.json.

        Luôn được ghi cho mọi phiên crawl (kể cả ROBOTS_DENIED, UNSUPPORTED_SOURCE, ERROR).
        Gán result.manifest_path trước khi serialize để JSON file chứa đường dẫn chính xác.
        """
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        manifest_dir = self.base_data_dir / "manifests" / result.source / date_str
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = manifest_dir / f"{result.run_id}.json"

        orig_manifest_path = result.manifest_path
        try:
            # Gán manifest_path trước khi chuyển đổi sang dict
            result.manifest_path = str(manifest_file)

            # Chuyển đổi an toàn các trường enum/dataclass
            manifest_data = asdict(result)
            if hasattr(result.status, "value"):
                manifest_data["status"] = result.status.value
            if result.stop_reason and hasattr(result.stop_reason, "value"):
                manifest_data["stop_reason"] = result.stop_reason.value

            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, ensure_ascii=False, indent=2)

            logger.info("Đã lưu Run Manifest tại: %s", str(manifest_file))
            return str(manifest_file)
        except Exception:
            result.manifest_path = orig_manifest_path
            raise

    def save_bronze_dataset(
        self,
        run_id: str,
        source: str,
        records: list[RentalBronzeRecord] | list[ListingCardRaw] | list[Any],
        metadata: list[CrawlMetadata],
        details: list[ListingDetailRaw] | None = None,
    ) -> str | None:
        """Lưu Bronze dataset vào <data_dir>/bronze/<source>/<date>/<run_id>/.

        QUY TẮC BẢO TOÀN KIẾN TRÚC:
        - Chỉ tạo thư mục và ghi file khi có ít nhất 1 record (len(records) > 0).
        - Tuyệt đối không tạo thư mục hoặc file rỗng khi records_created == 0.
        - listings.json: Lưu danh sách listing records.
        - details.json: Lưu danh sách detail records chỉ khi có ít nhất 1 detail thành công.
        - metadata.json: Lưu thông tin metadata phiên crawl.
        """
        if not records:
            logger.info(
                "Bronze dataset không được tạo vì không có record nào (records_created=0)."
            )
            return None

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_dir = self.base_data_dir / "bronze" / source / date_str / run_id
        output_dir.mkdir(parents=True, exist_ok=True)

        listings_path = output_dir / "listings.json"
        metadata_path = output_dir / "metadata.json"

        with open(listings_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in records], f, ensure_ascii=False, indent=2)

        if details:
            details_path = output_dir / "details.json"
            with open(details_path, "w", encoding="utf-8") as f:
                json.dump([asdict(d) for d in details], f, ensure_ascii=False, indent=2)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump([asdict(m) for m in metadata], f, ensure_ascii=False, indent=2)

        logger.info(
            "Đã lưu Bronze dataset tại: %s (Listings: %d, Details: %d)",
            str(output_dir),
            len(records),
            len(details) if details else 0,
        )
        return str(output_dir)
