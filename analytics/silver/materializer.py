"""Validate and atomically publish the latest-state Silver Parquet snapshot.

The materializer reads a fixed DuckDB view, validates one-row-per-listing and
required columns, then replaces the published file atomically. It does not clean
or enrich Bronze business fields beyond the documented snapshot semantics.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd

from analytics.duckdb.connection import create_analytics_connection

logger = logging.getLogger(__name__)

VALID_SOURCES = {"phongtro123", "nhatrovn", "nhatot", "batdongsan"}
REQUIRED_COLUMNS = [
    "source_code",
    "rental_post_id",
    "source_listing_id",
    "title_raw",
    "url",
    "price_amount",
    "area_value",
    "location_raw",
    "latest_observed_at",
]


@dataclass
class SilverMetadata:
    """Publication metadata written alongside a Silver Parquet snapshot."""

    generated_at: str
    row_count: int
    unique_listing_count: int
    source_view: str
    min_observed_at: str | None
    max_observed_at: str | None
    schema_version: str
    materializer_version: str
    columns: list[str]
    source_distribution: dict[str, int]


class SilverMaterializationError(Exception):
    """Lỗi xảy ra trong quá trình kiểm tra hoặc materialization tầng Silver."""
    pass


class SilverMaterializer:
    """Publish a validated DuckDB latest-state view as Silver Parquet.

    Materialization writes and validates a temporary file before atomic replace;
    failures leave the previously published snapshot intact.
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        source_view: str = "v_latest_posts",
    ) -> None:
        if output_dir is None:
            # Fallback path resolution: ưu tiên thư mục data trong repo
            candidate = Path("./data/silver").resolve()
            if candidate.parent.exists():
                self.output_dir = candidate
            elif Path("/data/silver").exists():
                self.output_dir = Path("/data/silver")
            else:
                self.output_dir = candidate
        else:
            self.output_dir = Path(output_dir).resolve()

        self.source_view = source_view
        self.output_file = self.output_dir / "rental_latest.parquet"
        self.metadata_file = self.output_dir / "rental_latest.metadata.json"
        self.tmp_file = self.output_dir / "rental_latest.parquet.tmp"

    def materialize(self, conn: Any | None = None) -> SilverMetadata:
        """Xuất bản snapshot Silver Parquet nguyên tử với đầy đủ validation."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if conn is None:
            conn = create_analytics_connection()

        logger.info("Bắt đầu trích xuất dữ liệu từ view %s...", self.source_view)

        # 1. Trích xuất dữ liệu từ DuckDB view sang DataFrame
        df = conn.execute(f"SELECT * FROM {self.source_view}").df()

        # 2. Validation sơ bộ trước khi ghi
        self._validate_dataframe(df)

        # 3. Ghi dữ liệu nguyên tử sang file .tmp
        if self.tmp_file.exists():
            self.tmp_file.unlink()

        try:
            df.to_parquet(self.tmp_file, index=False, engine="pyarrow")
            logger.info("Đã ghi tạm thời Silver dataset tại %s", self.tmp_file)

            # 4. Validation lại file Parquet vừa ghi
            self._validate_parquet_file(self.tmp_file, expected_rows=len(df))

            # 5. Atomic rename sang file chính
            self.tmp_file.replace(self.output_file)
            logger.info("Đã cập nhật nguyên tử Silver dataset tại %s", self.output_file)

            # 6. Tạo và lưu metadata sidecar
            metadata = self._build_metadata(df)
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(asdict(metadata), f, indent=2, ensure_ascii=False)
            logger.info("Đã lưu metadata sidecar tại %s", self.metadata_file)

            return metadata

        except Exception as exc:
            if self.tmp_file.exists():
                try:
                    self.tmp_file.unlink()
                except Exception:
                    pass
            logger.error("Silver materialization failed; previous snapshot preserved (error_class=%s)", type(exc).__name__)
            raise SilverMaterializationError("Silver materialization failed") from None

    def _validate_dataframe(self, df: pd.DataFrame) -> None:
        """Kiểm tra tính toàn vẹn của DataFrame trước khi ghi."""
        row_count = len(df)
        if row_count == 0:
            raise SilverMaterializationError("Tập dữ liệu rỗng (0 dòng).")

        # Kiểm tra cột bắt buộc
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                raise SilverMaterializationError(f"Thiếu cột bắt buộc: {col}")

        # Kiểm tra tính duy nhất (One-Row-Per-Listing)
        unique_listings = df["rental_post_id"].nunique()
        if unique_listings != row_count:
            dups = row_count - unique_listings
            raise SilverMaterializationError(
                f"Vi phạm tính duy nhất: {dups} dòng trùng rental_post_id (Tổng: {row_count}, Độc nhất: {unique_listings})."
            )

        # Kiểm tra nguồn hợp lệ (loại bỏ fake/test data)
        sources = set(df["source_code"].dropna().unique())
        invalid_sources = sources - VALID_SOURCES
        if invalid_sources:
            raise SilverMaterializationError(f"Phát hiện nguồn dữ liệu không hợp lệ: {invalid_sources}")

    def _validate_parquet_file(self, parquet_path: Path, expected_rows: int) -> None:
        """Xác nhận file Parquet có thể đọc lại trơn tru và khớp số lượng bản ghi."""
        if not parquet_path.exists() or parquet_path.stat().st_size == 0:
            raise SilverMaterializationError(f"File Parquet không tồn tại hoặc rỗng: {parquet_path}")

        try:
            readback_df = pd.read_parquet(parquet_path)
            if len(readback_df) != expected_rows:
                raise SilverMaterializationError(
                    f"Số dòng đọc lại ({len(readback_df)}) không khớp số dòng dự kiến ({expected_rows})."
                )
        except Exception:
            raise SilverMaterializationError("Silver Parquet read-back validation failed") from None

    def _build_metadata(self, df: pd.DataFrame) -> SilverMetadata:
        """Xây dựng metadata an toàn không chứa thông tin nhạy cảm."""
        now_iso = datetime.now(timezone.utc).astimezone().isoformat()

        min_obs = None
        max_obs = None
        if "latest_observed_at" in df.columns and not df["latest_observed_at"].dropna().empty:
            min_obs = str(df["latest_observed_at"].min())
            max_obs = str(df["latest_observed_at"].max())

        source_dist = df["source_code"].value_counts().to_dict()

        return SilverMetadata(
            generated_at=now_iso,
            row_count=len(df),
            unique_listing_count=int(df["rental_post_id"].nunique()),
            source_view=self.source_view,
            min_observed_at=min_obs,
            max_observed_at=max_obs,
            schema_version="1.0.0",
            materializer_version="1.0.0",
            columns=df.columns.tolist(),
            source_distribution={k: int(v) for k, v in source_dist.items()},
        )
