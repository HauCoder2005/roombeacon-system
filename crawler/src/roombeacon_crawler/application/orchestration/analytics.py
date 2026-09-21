"""Refresh analytics after scheduled crawler checkpoints complete.

This module is Airflow-free and composes runtime adapters at the use-case boundary.
"""

import logging

from roombeacon_crawler.application.orchestration.errors import CrawlerWorkflowError

logger = logging.getLogger(__name__)


def refresh_duckdb_analytics(checkpoints: list[dict], **context) -> dict:
    """Khởi tạo/cập nhật Analytical Views trong DuckDB từ dữ liệu MySQL Bronze (READ_ONLY)."""
    logger.info("=" * 60)
    logger.info("STAGE 7: REFRESH DUCKDB ANALYTICS")
    logger.info("=" * 60)

    from analytics.duckdb.bootstrap import bootstrap_analytics

    try:
        views = bootstrap_analytics()
        logger.info("DuckDB Analytics views refreshed successfully: %d views.", len(views))
        return {"status": "SUCCESS", "views_created": views}
    except Exception as exc:
        logger.error(
            "DuckDB analytics refresh failed (error_class=%s)",
            type(exc).__name__,
        )
        raise CrawlerWorkflowError("DuckDB analytics refresh failed") from None
