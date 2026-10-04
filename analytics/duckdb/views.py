"""Load versioned SQL files and publish DuckDB analytical views.

This module manages view definitions only; it does not create source database
connections or materialize Silver datasets.
"""

from pathlib import Path
from typing import Any
import logging
import re
logger = logging.getLogger(__name__)

DEFAULT_SQL_DIR = Path(__file__).parent / "sql"
SQL_DIR = DEFAULT_SQL_DIR

# Root SQL definitions are required analytical views. Keep their bootstrap order
# explicit so adding or renaming a file cannot silently change initialization.
REQUIRED_VIEW_ORDER = (
    "acquisition_efficiency",
    "content_changes",
    "data_quality",
    "fresh_health_matrix",
    "latest_posts",
    "listing_lifetime",
    "location_summary",
    "observation_provenance",
    "observations",
    "price_history",
    "replay_summary",
    "source_activity",
    "unknown_summary",
)

BRONZE_VERSION_RELATION = "_bronze_rental_post_versions"
BRONZE_SOURCE_TABLES = (
    "platforms",
    "rental_posts",
    "rental_post_versions",
    "post_prices",
    "post_addresses",
    "post_details",
)


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
    def _create_bronze_compatibility_relations(
        cls, conn: Any, required_tables: set[str]
    ) -> None:
        """Expose the current Bronze schema without mutating the source database."""
        database_types = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT database_name, type FROM duckdb_databases()"
            ).fetchall()
        }
        mysql_attached = database_types.get("mysql_db") == "mysql"
        for table_name in BRONZE_SOURCE_TABLES:
            if table_name not in required_tables:
                continue
            source = (
                f"mysql_query('mysql_db', 'SELECT * FROM `{table_name}`')"
                if mysql_attached
                else f"mysql_db.{table_name}"
            )
            conn.execute(
                # Freeze each required Bronze table once per in-memory runtime.
                # Downstream views then share one coherent local source instead
                # of opening repeated remote scans for every analytical query.
                f"CREATE OR REPLACE TEMP TABLE _bronze_source_{table_name} AS "
                f"SELECT * FROM {source}"
            )

        if "rental_post_versions" not in required_tables:
            return

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info('_bronze_source_rental_post_versions')"
            ).fetchall()
        }
        if not columns:
            raise DuckDBViewInitializationError(
                "Required Bronze table mysql_db.rental_post_versions is missing or has no columns"
            )
        provenance = (
            ""
            if "ingestion_origin" in columns
            else ", CAST('UNKNOWN' AS VARCHAR) AS ingestion_origin"
        )
        conn.execute(
            f"CREATE OR REPLACE TEMP VIEW {BRONZE_VERSION_RELATION} AS "
            f"SELECT *{provenance} FROM _bronze_source_rental_post_versions"
        )

    @classmethod
    def create_views(cls, conn: Any, *, strict: bool = False) -> list[str]:
        """Create every required analytical view in deterministic order."""
        created = []
        expected_files = {path.stem for path in SQL_DIR.glob("*.sql")}
        configured_files = set(REQUIRED_VIEW_ORDER)
        using_project_definitions = SQL_DIR.resolve() == DEFAULT_SQL_DIR.resolve()
        if using_project_definitions and expected_files != configured_files:
            raise DuckDBViewInitializationError(
                "Required view order does not match SQL definitions; "
                f"missing_from_order={sorted(expected_files - configured_files)}, "
                f"missing_sql={sorted(configured_files - expected_files)}"
            )

        definition_order = (
            REQUIRED_VIEW_ORDER if using_project_definitions else tuple(sorted(expected_files))
        )
        definitions = {
            name: (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
            for name in definition_order
        }
        required_tables = {
            table_name
            for table_name in BRONZE_SOURCE_TABLES
            if any(
                f"mysql_db.{table_name}" in query
                for query in definitions.values()
            )
        }
        if required_tables:
            cls._create_bronze_compatibility_relations(conn, required_tables)

        for definition_name in definition_order:
            sql_file = SQL_DIR / f"{definition_name}.sql"
            view_name = f"v_{definition_name}"
            query = definitions[definition_name]
            for table_name in BRONZE_SOURCE_TABLES:
                target = (
                    BRONZE_VERSION_RELATION
                    if table_name == "rental_post_versions"
                    else f"_bronze_source_{table_name}"
                )
                query = query.replace(f"mysql_db.{table_name}", target)
            try:
                conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS {query}")
                created.append(view_name)
                logger.info("DuckDB: Đã tạo view %s", view_name)
            except Exception as exc:
                dependencies = sorted(
                    set(re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)", query, re.I))
                )
                message = (
                    "Required DuckDB view creation failed: "
                    f"view={view_name}, sql_file={sql_file}, "
                    f"dependencies={dependencies}, "
                    f"error_class={type(exc).__name__}, error={exc}"
                )
                logger.error(message)
                raise DuckDBViewInitializationError(message) from exc
        # Keep the source-only view independent to avoid a dependency cycle when
        # the canonical view overlays cached map addresses.
        optional_sql = SQL_DIR / "optional" / "latest_posts_enriched.sql"
        # Temporarily disabled dynamic enrichment because mysql_scanner hangs or returns empty rows
        # on complex cross-table FLOAT/DECIMAL joins in MySQL 8.4
        pass
        return created
