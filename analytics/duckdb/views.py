"""Load versioned SQL files and publish DuckDB analytical views.

This module manages view definitions only; it does not create source database
connections or materialize Silver datasets.
"""

from pathlib import Path
from typing import Any
import logging
logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).parent / "sql"


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
    def create_views(cls, conn: Any) -> list[str]:
        """Tạo tất cả các analytical views trong connection hiện tại."""
        created = []
        for sql_file in SQL_DIR.glob("*.sql"):
            view_name = f"v_{sql_file.stem}"
            query = sql_file.read_text(encoding="utf-8")
            try:
                conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query}")
                created.append(view_name)
                logger.info("DuckDB: Đã tạo view %s", view_name)
            except Exception as exc:
                logger.warning("DuckDB view creation failed (view=%s, error_class=%s)", view_name, type(exc).__name__)
        return created
