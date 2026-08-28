"""Create and reuse the RoomBeacon DuckDB analytics connection.

The factory configures DuckDB, attaches Bronze MySQL read-only when available,
and installs analytical views. It never owns crawler writes or schema mutation.
"""

import logging
from pathlib import Path
from typing import Any
import duckdb

from roombeacon_crawler.config.get_env import env
from analytics.duckdb.views import DuckDBViewManager

logger = logging.getLogger(__name__)


def _find_project_root() -> Path:
    """Xác định thư mục gốc của project bằng cách tìm marker (.git, docker-compose.yml, Makefile)."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "docker-compose.yml").exists() or (parent / "Makefile").exists():
            return parent
    return Path.cwd().resolve()


def _resolve_default_db_path() -> str:
    """Xác định đường dẫn lưu trữ DuckDB ưu tiên thư mục root data/duckdb."""
    # 1. Kiểm tra môi trường Docker container nơi /data hoặc /data/duckdb được mount
    container_duckdb_dir = Path("/data/duckdb")
    if container_duckdb_dir.exists() or (Path("/data").exists() and not Path("./data").resolve().exists()):
        try:
            container_duckdb_dir.mkdir(parents=True, exist_ok=True)
            return str(container_duckdb_dir / "roombeacon_analytics.duckdb")
        except Exception:
            pass

    # 2. Môi trường Host / Local / Notebook: định vị chính xác <PROJECT_ROOT>/data/duckdb
    project_root = _find_project_root()
    host_duckdb_dir = project_root / "data" / "duckdb"
    try:
        host_duckdb_dir.mkdir(parents=True, exist_ok=True)
        return str(host_duckdb_dir / "roombeacon_analytics.duckdb")
    except Exception:
        fallback_dir = Path("./data/duckdb").resolve()
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return str(fallback_dir / "roombeacon_analytics.duckdb")


class DuckDBConnectionFactory:
    """Manage the process-wide DuckDB connection and read-only MySQL attach.

    Connection creation may create the local catalog and DuckDB views. Failed
    MySQL attachment degrades safely without logging credential-bearing SQL.
    """

    _connection = None

    @classmethod
    def get_connection(
        cls,
        memory_limit: str = "2GB",
        db_path: str | None = None,
        create_views: bool = True,
    ) -> Any:
        """Return the cached connection, creating and configuring it if needed."""
        if cls._connection is None:
            resolved_db_path = db_path if db_path is not None else _resolve_default_db_path()
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
                    except Exception:
                        # DuckDB may echo the full ATTACH statement (including
                        # credentials) in its exception text. Never retain/log it.
                        continue

                if not attached:
                    logger.warning(
                        "DuckDB MySQL attachment failed; continuing in standalone mode "
                        "(event=duckdb_mysql_attach_failed, alias=mysql_db)"
                    )

            except Exception as exc:
                logger.warning(
                    "DuckDB MySQL extension initialization failed; continuing in standalone mode "
                    "(event=duckdb_mysql_extension_failed, error_class=%s)",
                    type(exc).__name__,
                )

            if create_views:
                try:
                    DuckDBViewManager.create_views(conn)
                except Exception as exc:
                    logger.warning(
                        "DuckDB analytical view initialization failed (error_class=%s)",
                        type(exc).__name__,
                    )

            cls._connection = conn
        return cls._connection

    @classmethod
    def close(cls) -> None:
        """Release the cached catalog handle so the next call opens a fresh one."""
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
