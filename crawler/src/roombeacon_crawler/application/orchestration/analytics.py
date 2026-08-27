"""Refresh analytics after scheduled crawler checkpoints complete.

This module is deliberately Airflow-free. Runtime adapters are composed inside the
relevant use-case boundary until Phase 3 introduces explicit composition roots.
"""

import logging

logger = logging.getLogger(__name__)


def refresh_duckdb_analytics(checkpoints: list[dict], **context) -> dict:
    """7. Khởi tạo/cập nhật Analytical Views trong DuckDB từ dữ liệu MySQL Bronze (READ_ONLY)."""
    logger.info("=" * 60)
    logger.info("STAGE 7: REFRESH DUCKDB ANALYTICS")
    logger.info("=" * 60)

    from analytics.duckdb.bootstrap import bootstrap_analytics

    try:
        bootstrap_analytics()
        logger.info("DuckDB Analytics views refreshed successfully.")
        return {"status": "SUCCESS"}
    except Exception as exc:
        logger.error(
            "DuckDB analytics refresh failed (error_class=%s)",
            type(exc).__name__,
        )
        return {"status": "FAILED", "error_class": type(exc).__name__}


# --------------------------------------------------------------------------
# Task 8: Summarize Run (Finalization)
# --------------------------------------------------------------------------
