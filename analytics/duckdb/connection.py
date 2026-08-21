import logging
from typing import Any
import duckdb

from roombeacon_crawler.config.get_env import env

logger = logging.getLogger(__name__)


class DuckDBConnectionFactory:
    """Quản lý kết nối DuckDB và cơ chế Attach MySQL ở chế độ READ_ONLY."""

    _connection = None

    @classmethod
    def get_connection(cls, memory_limit: str = "2GB", db_path: str | None = None) -> Any:
        """Tạo hoặc trả về kết nối DuckDB, tự động attach MySQL theo cấu hình."""
        if cls._connection is None:
            if db_path is None:
                from pathlib import Path
                target_dir = Path("/data/analytics")
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    db_path = str(target_dir / "roombeacon_analytics.duckdb")
                except Exception:
                    fallback_dir = Path("./data/analytics").resolve()
                    fallback_dir.mkdir(parents=True, exist_ok=True)
                    db_path = str(fallback_dir / "roombeacon_analytics.duckdb")

            conn = duckdb.connect(database=db_path)
            conn.execute(f"SET memory_limit='{memory_limit}';")
            conn.execute("SET threads TO 4;")

            # Cài đặt và tải extension mysql
            try:
                conn.execute("INSTALL mysql; LOAD mysql;")
                mysql_cfg = env.mysql_bronze
                attach_sql = (
                    f"ATTACH 'host={mysql_cfg.host} port={mysql_cfg.port} "
                    f"user={mysql_cfg.user} password={mysql_cfg.password} "
                    f"database={mysql_cfg.database}' AS mysql_db (TYPE MYSQL, READ_ONLY);"
                )
                conn.execute(attach_sql)
                logger.info("DuckDB: Đã ATTACH thành công MySQL database ở chế độ READ_ONLY.")
            except Exception as exc:
                logger.warning(
                    "DuckDB: Không thể tự động ATTACH MySQL (%s). DuckDB chạy ở chế độ standalone.",
                    exc,
                )

            cls._connection = conn
        return cls._connection

    @classmethod
    def close(cls) -> None:
        if cls._connection is not None:
            cls._connection.close()
            cls._connection = None
