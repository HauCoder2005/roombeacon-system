"""Load versioned SQL files and publish DuckDB analytical views.

This module manages view definitions only; it does not create source database
connections or materialize Silver datasets.
"""

from pathlib import Path
from typing import Any
import logging
logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"


class DuckDBViewInitializationError(RuntimeError):
    """Báo lỗi khi không thể tạo đầy đủ analytical view bắt buộc."""


class DuckDBViewManager:
    """Quản lý nạp và tạo các Analytical Views trong DuckDB."""

    @classmethod
    def load_sql(cls, view_name: str) -> str:
        """Đọc nội dung file SQL theo tên view."""
        sql_path = SQL_DIR / f"{view_name}.sql"
        if not sql_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file SQL: {sql_path}")
        return sql_path.read_text(encoding="utf-8")

    @classmethod
    def create_views(cls, conn: Any, *, strict: bool = False) -> list[str]:
        """Tạo analytical view; ở chế độ strict, thất bại nếu thiếu bất kỳ view nào."""
        created = []
        failed = []
        sql_files = sorted(SQL_DIR.glob("*.sql"))
        for sql_file in sql_files:
            view_name = f"v_{sql_file.stem}"
            query = sql_file.read_text(encoding="utf-8")
            try:
                conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query}")
                created.append(view_name)
                logger.info("DuckDB: Đã tạo view %s", view_name)
            except Exception as exc:
                failed.append(view_name)
                logger.warning("DuckDB view creation failed (view=%s, error_class=%s)", view_name, type(exc).__name__)

        if strict and failed:
            raise DuckDBViewInitializationError(
                "Không thể tạo đầy đủ analytical view trong DuckDB: "
                + ", ".join(failed)
            )

        if strict and len(created) != len(sql_files):
            raise DuckDBViewInitializationError(
                f"Số analytical view đã tạo không hợp lệ: {len(created)}/{len(sql_files)}"
            )
        # Keep the source-only view independent to avoid a dependency cycle when
        # the canonical view overlays cached map addresses.
        optional_sql = SQL_DIR / "optional" / "latest_posts_enriched.sql"
        if optional_sql.exists() and "v_latest_posts" in created:
            try:
                conn.execute("SELECT 1 FROM mysql_db.map_geocodes LIMIT 0")
            except Exception as exc:
                logger.info("Address cache unavailable (error_class=%s)", type(exc).__name__)
            else:
                conn.execute("CREATE OR REPLACE VIEW v_latest_posts_source AS " + cls.load_sql("latest_posts"))
                conn.execute(
                    "CREATE OR REPLACE VIEW v_latest_posts_enriched AS "
                    + optional_sql.read_text(encoding="utf-8").replace(
                        "FROM v_latest_posts p", "FROM v_latest_posts_source p"
                    )
                )
                conn.execute("""
                    CREATE OR REPLACE VIEW v_latest_posts AS
                    SELECT * EXCLUDE (best_address_text, best_address_source),
                           enriched_address_text AS best_address_text,
                           enriched_address_source AS best_address_source
                    FROM v_latest_posts_enriched
                """)
                created.extend(["v_latest_posts_source", "v_latest_posts_enriched"])
        return created
