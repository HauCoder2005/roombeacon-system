import logging
from pathlib import Path
from typing import Any
import duckdb

from roombeacon_crawler.config.get_env import env
from analytics.duckdb.views import DuckDBViewManager

logger = logging.getLogger(__name__)


class DuckDBConnectionFactory:
    """Quản lý kết nối DuckDB và cơ chế Attach MySQL ở chế độ READ_ONLY."""

    _connection = None

    @classmethod
    def get_connection(
        cls,
        memory_limit: str = "2GB",
        db_path: str | None = None,
        create_views: bool = True,
    ) -> Any:
        """Tạo hoặc trả về kết nối DuckDB, tự động attach MySQL theo cấu hình và nạp analytical views."""
        if cls._connection is None:
            if db_path is None:
                target_dir = Path("/data/analytics")
                if target_dir.exists() or (Path("/data").exists() and not Path("./data").resolve().exists()):
                    try:
                        target_dir.mkdir(parents=True, exist_ok=True)
                        resolved_db_path = str(target_dir / "roombeacon_analytics.duckdb")
                    except Exception:
                        fallback_dir = Path("./data/analytics").resolve()
                        fallback_dir.mkdir(parents=True, exist_ok=True)
                        resolved_db_path = str(fallback_dir / "roombeacon_analytics.duckdb")
                else:
                    fallback_dir = Path("./data/analytics").resolve()
                    fallback_dir.mkdir(parents=True, exist_ok=True)
                    resolved_db_path = str(fallback_dir / "roombeacon_analytics.duckdb")
            try:
                conn = duckdb.connect(database=resolved_db_path)
            except Exception as exc:
                logger.info(
                    "DuckDB: Không thể lock file %s (%s). Khởi tạo in-memory DuckDB connection.",
                    resolved_db_path,
                    exc,
                )
                conn = duckdb.connect(database=":memory:")
            conn.execute(f"SET memory_limit='{memory_limit}';")
            conn.execute("SET threads TO 4;")

            # Cài đặt và tải extension mysql
            try:
                conn.execute("INSTALL mysql; LOAD mysql;")
                mysql_cfg = env.mysql_bronze

                attached = False
                candidates = [
                    (mysql_cfg.host, mysql_cfg.port),
                    ("127.0.0.1", 3307),
                    ("localhost", 3307),
                    ("127.0.0.1", 3306),
                ]
                seen_candidates = set()
                unique_candidates = []
                for h, p in candidates:
                    if (h, p) not in seen_candidates:
                        seen_candidates.add((h, p))
                        unique_candidates.append((h, p))

                last_exc = None
                for host, port in unique_candidates:
                    try:
                        attach_sql = (
                            f"ATTACH 'host={host} port={port} "
                            f"user={mysql_cfg.user} password={mysql_cfg.password} "
                            f"database={mysql_cfg.database}' AS mysql_db (TYPE MYSQL, READ_ONLY);"
                        )
                        conn.execute(attach_sql)
                        logger.info(
                            "DuckDB: Đã ATTACH thành công MySQL database tại %s:%s ở chế độ READ_ONLY.",
                            host,
                            port,
                        )
                        attached = True
                        break
                    except Exception as e:
                        last_exc = e

                if not attached:
                    logger.warning(
                        "DuckDB: Không thể tự động ATTACH MySQL (%s). DuckDB chạy ở chế độ standalone.",
                        last_exc,
                    )

            except Exception as exc:
                logger.warning(
                    "DuckDB: Không thể tải extension mysql (%s). DuckDB chạy ở chế độ standalone.",
                    exc,
                )

            if create_views:
                try:
                    DuckDBViewManager.create_views(conn)
                except Exception as exc:
                    logger.warning(
                        "DuckDB: Không thể tự động tạo analytical views (%s).", exc
                    )

            cls._connection = conn
        return cls._connection

    @classmethod
    def close(cls) -> None:
        if cls._connection is not None:
            cls._connection.close()
            cls._connection = None


def create_analytics_connection(
    memory_limit: str = "2GB",
    db_path: str | None = None,
    create_views: bool = True,
) -> Any:
    """Tạo và khởi tạo kết nối DuckDB kết hợp gắn kết MySQL Bronze (READ_ONLY) và nạp analytical views."""
    DuckDBConnectionFactory.close()
    return DuckDBConnectionFactory.get_connection(
        memory_limit=memory_limit,
        db_path=db_path,
        create_views=create_views,
    )
