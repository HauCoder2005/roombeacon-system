"""DEPRECATED: legacy direct-database Silver materializer; retain but pause manually.

Airflow owns ordering and retries. The shared notebook utilities own Bronze
cleaning and the pre-Silver gate; Parquet is the persistent Silver checkpoint.

Use ``roombeacon_silver_build`` after rebuilding the Airflow image. This DAG is
kept for rollback visibility and is intentionally not deleted or auto-paused.
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
    description="Build canonical data/silver/rental_listings.parquet",
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
        """2. Build, gate, and publish canonical Silver Parquet."""
        from pathlib import Path

        from analytics.duckdb.connection import create_analytics_connection
        from analytics.silver.materializer import SilverMaterializer
        from notebooks.utils.notebook_audit import load_snapshot
        from notebooks.utils.silver_processing import (
            build_silver_dataset,
            evaluate_pre_silver_quality_gate,
        )

        logger.info("=" * 60)
        logger.info("STAGE 2: BUILD AND MATERIALIZE CANONICAL SILVER")
        logger.info("=" * 60)

        project_root = Path(__file__).resolve().parents[3]
        conn = create_analytics_connection()
        bronze_df, raw_evidence, _ = load_snapshot(conn, project_root)
        if len(bronze_df) != verification_info["total_rows"]:
            raise ValueError("Bronze snapshot changed between verification and materialization")
        processed_df = build_silver_dataset(bronze_df, raw_evidence)
        quality_gate = evaluate_pre_silver_quality_gate(bronze_df, processed_df)
        if not quality_gate.passed:
            raise ValueError("Pre-Silver quality gate failed")
        materializer = SilverMaterializer()
        metadata = materializer.materialize(
            processed_df,
            quality_gate_passed=quality_gate.passed,
            source_snapshot=verification_info,
        )

        logger.info("Canonical Silver materialized: %d rows, %d unique listings.", metadata.row_count, metadata.distinct_rental_post_id)
        return {
            "generated_at": metadata.generated_at,
            "row_count": metadata.row_count,
            "unique_listing_count": metadata.distinct_rental_post_id,
            "source_distribution": metadata.source_distribution,
            "output_file": str(materializer.output_file),
            "metadata_file": str(materializer.metadata_file),
        }

    @task
    def validate_silver_output(materialization_info: dict) -> dict:
        """3. Read back and verify canonical Silver Parquet."""

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

        canonical = pd.read_parquet(parquet_path)
        if len(canonical) != materialization_info["row_count"]:
            raise ValueError("Canonical Silver row count differs from publication result")
        if canonical.rental_post_id.isna().any() or not canonical.rental_post_id.is_unique:
            raise ValueError("Canonical Silver violates rental_post_id grain")
        columns_count = len(canonical.columns)

        return {
            "status": "VALID",
            "file_size_kb": round(file_size_bytes / 1024, 2),
            "columns_count": columns_count,
        }

    @task
    def summarize_silver_run(materialization_info: dict, validation_info: dict) -> None:
        """4. Báo cáo tổng kết quá trình xuất bản Silver snapshot."""
        logger.info("=" * 60)
        logger.info("ROOMBEACON SILVER MATERIALIZATION SUMMARY")
        logger.info("=" * 60)
        logger.info("Canonical Silver    : %s", materialization_info["output_file"])
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
