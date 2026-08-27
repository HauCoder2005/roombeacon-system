"""Command-line bootstrap for the DuckDB analytical catalog and views."""

import logging
from analytics.duckdb.connection import DuckDBConnectionFactory
from analytics.duckdb.views import DuckDBViewManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DUCKDB_BOOTSTRAP")


def bootstrap_analytics() -> None:
    """Open the analytics connection and ensure all configured views exist."""
    logger.info("=" * 60)
    logger.info("ROOMBEACON DUCKDB ANALYTICS BOOTSTRAP")
    logger.info("=" * 60)

    conn = DuckDBConnectionFactory.get_connection()
    views = DuckDBViewManager.create_views(conn)
    logger.info("Đã tạo %d analytical views thành công: %s", len(views), views)


if __name__ == "__main__":
    bootstrap_analytics()
