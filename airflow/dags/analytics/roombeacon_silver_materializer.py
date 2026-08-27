"""Schedule validated publication of the latest-state Silver Parquet snapshot.

Airflow owns ordering and retries; DuckDB extraction, validation and atomic file
publication remain in the analytics materializer.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from airflow.sdk import dag, task

logger = logging.getLogger("airflow.task")

DAG_ID = "roombeacon_silver_materializer"
DEFAULT_ARGS = {
    "owner": "roombeacon",
    "depends_on_past": False,
    "retries": 2,
}


@dag(
    dag_id=DAG_ID,
    description="Tự động materialization snapshot tầng Silver Parquet từ DuckDB v_latest_posts",
    default_args=DEFAULT_ARGS,
    schedule="0 2 * * *",
    start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["roombeacon", "analytics", "silver", "parquet", "duckdb"],
)
def roombeacon_silver_materializer():
    """Build verification, materialization, validation and summary tasks."""

    @task
    def verify_analytics_connection() -> dict:
        """1. Kiểm tra kết nối DuckDB Analytics và tính khả dụng của view v_latest_posts."""
        from analytics.duckdb.connection import create_analytics_connection

        logger.info("=" * 60)
        logger.info("STAGE 1: VERIFY DUCKDB ANALYTICS & V_LATEST_POSTS")
        logger.info("=" * 60)

        conn = create_analytics_connection()
        res = conn.execute("""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT rental_post_id) AS unique_posts
            FROM v_latest_posts
        """).fetchone()

        total_rows = res[0]
        unique_posts = res[1]

        logger.info("v_latest_posts: %d dòng, %d tin độc nhất.", total_rows, unique_posts)
        if total_rows == 0:
            raise ValueError("View v_latest_posts rỗng.")
        if total_rows != unique_posts:
            raise ValueError(f"Vi phạm one-row-per-listing: {total_rows} != {unique_posts}")

        return {"total_rows": total_rows, "unique_posts": unique_posts}

    @task
    def materialize_silver(verification_info: dict) -> dict:
        """2. Thực thi materialization nguyên tử sang file Parquet và ghi metadata."""
        from analytics.silver.materializer import SilverMaterializer

        logger.info("=" * 60)
        logger.info("STAGE 2: MATERIALIZE SILVER PARQUET")
        logger.info("=" * 60)

        materializer = SilverMaterializer()
        metadata = materializer.materialize()

        logger.info("Materialization thành công: %d dòng, %d tin độc nhất.", metadata.row_count, metadata.unique_listing_count)
        return {
            "generated_at": metadata.generated_at,
            "row_count": metadata.row_count,
            "unique_listing_count": metadata.unique_listing_count,
            "source_distribution": metadata.source_distribution,
            "output_file": str(materializer.output_file),
            "metadata_file": str(materializer.metadata_file),
        }

    @task
    def validate_silver_output(materialization_info: dict) -> dict:
        """3. Kiểm tra tính toàn vẹn và khả năng đọc lại của file Silver Parquet vừa xuất bản."""
        import pandas as pd

        logger.info("=" * 60)
        logger.info("STAGE 3: VALIDATE SILVER PARQUET OUTPUT")
        logger.info("=" * 60)

        parquet_path = Path(materialization_info["output_file"])
        meta_path = Path(materialization_info["metadata_file"])

        if not parquet_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file Silver Parquet tại {parquet_path}")
        if not meta_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file Metadata tại {meta_path}")

        file_size_bytes = parquet_path.stat().st_size
        logger.info("Kích thước file Silver Parquet: %d bytes (%.2f KB)", file_size_bytes, file_size_bytes / 1024)

        df = pd.read_parquet(parquet_path)
        if len(df) != materialization_info["row_count"]:
            raise ValueError(f"Số dòng đọc lại ({len(df)}) != metadata ({materialization_info['row_count']})")

        return {
            "status": "VALID",
            "file_size_kb": round(file_size_bytes / 1024, 2),
            "columns_count": len(df.columns),
        }

    @task
    def summarize_silver_run(materialization_info: dict, validation_info: dict) -> None:
        """4. Báo cáo tổng kết quá trình xuất bản Silver snapshot."""
        logger.info("=" * 60)
        logger.info("ROOMBEACON SILVER MATERIALIZATION SUMMARY")
        logger.info("=" * 60)
        logger.info("Snapshot File       : %s", materialization_info["output_file"])
        logger.info("Metadata File       : %s", materialization_info["metadata_file"])
        logger.info("Total Rows          : %d", materialization_info["row_count"])
        logger.info("Unique Listings     : %d", materialization_info["unique_listing_count"])
        logger.info("File Size           : %.2f KB", validation_info["file_size_kb"])
        logger.info("Columns Count       : %d", validation_info["columns_count"])
        logger.info("Source Distribution : %s", json.dumps(materialization_info["source_distribution"]))
        logger.info("Validation Status   : %s", validation_info["status"])
        logger.info("=" * 60)

    # Workflow dependencies
    verify_data = verify_analytics_connection()
    mat_info = materialize_silver(verify_data)
    val_info = validate_silver_output(mat_info)
    summarize_silver_run(mat_info, val_info)


dag_instance = roombeacon_silver_materializer()
