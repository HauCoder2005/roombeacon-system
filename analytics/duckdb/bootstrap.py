"""Command-line bootstrap for the DuckDB analytical catalog and views."""

import logging
from analytics.duckdb.connection import DuckDBConnectionFactory
from analytics.duckdb.views import DuckDBViewManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DUCKDB_BOOTSTRAP")


def bootstrap_analytics() -> list[str]:
    """Mở DuckDB, bắt buộc attach MySQL Bronze và tạo đủ analytical view."""
    logger.info("=" * 60)
    logger.info("ROOMBEACON DUCKDB ANALYTICS BOOTSTRAP")
    logger.info("=" * 60)

    conn = DuckDBConnectionFactory.get_connection(create_views=False)
    attached_databases = {
        row[0] for row in conn.execute("SHOW DATABASES").fetchall()
    }
    if "mysql_db" not in attached_databases:
        raise RuntimeError(
            "DuckDB chưa attach được MySQL Bronze với alias mysql_db."
        )

    views = DuckDBViewManager.create_views(conn, strict=True)
    logger.info("Đã tạo %d analytical views thành công: %s", len(views), views)
    return views


if __name__ == "__main__":
    bootstrap_analytics()
