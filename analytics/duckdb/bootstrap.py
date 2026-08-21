import logging
from analytics.duckdb.connection import DuckDBConnectionFactory
from analytics.duckdb.views import DuckDBViewManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DUCKDB_BOOTSTRAP")


def bootstrap_analytics() -> None:
    """Khởi tạo toàn bộ tầng DuckDB Analytics."""
    logger.info("=" * 60)
    logger.info("ROOMBEACON DUCKDB ANALYTICS BOOTSTRAP")
    logger.info("=" * 60)

    conn = DuckDBConnectionFactory.get_connection()
    views = DuckDBViewManager.create_views(conn)
    logger.info("Đã tạo %d analytical views thành công: %s", len(views), views)


if __name__ == "__main__":
    bootstrap_analytics()
