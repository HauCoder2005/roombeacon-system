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
        return created
