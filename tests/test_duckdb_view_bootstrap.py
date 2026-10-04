from pathlib import Path

import duckdb
import pytest

from analytics.duckdb import views


def test_required_view_order_covers_every_project_definition():
    definitions = {path.stem for path in views.DEFAULT_SQL_DIR.glob("*.sql")}
    assert tuple(views.REQUIRED_VIEW_ORDER)
    assert set(views.REQUIRED_VIEW_ORDER) == definitions


def test_custom_view_bootstrap_is_deterministic(tmp_path, monkeypatch):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "zeta.sql").write_text("SELECT 2 AS value")
    (sql_dir / "alpha.sql").write_text("SELECT 1 AS value")
    monkeypatch.setattr(views, "SQL_DIR", sql_dir)
    with duckdb.connect() as conn:
        assert views.DuckDBViewManager.create_views(conn) == ["v_alpha", "v_zeta"]


def test_missing_required_dependency_fails_with_full_context(tmp_path, monkeypatch):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    sql_file = sql_dir / "broken.sql"
    sql_file.write_text("SELECT * FROM missing_relation")
    monkeypatch.setattr(views, "SQL_DIR", sql_dir)
    with duckdb.connect() as conn:
        with pytest.raises(views.DuckDBViewInitializationError) as captured:
            views.DuckDBViewManager.create_views(conn)
    message = str(captured.value)
    assert "view=v_broken" in message
    assert f"sql_file={sql_file}" in message
    assert "missing_relation" in message
    assert "CatalogException" in message


def test_missing_ingestion_origin_uses_read_only_compatibility_view(
    tmp_path, monkeypatch
):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "observations.sql").write_text(
        "SELECT id, ingestion_origin FROM mysql_db.rental_post_versions"
    )
    monkeypatch.setattr(views, "SQL_DIR", sql_dir)
    with duckdb.connect() as conn:
        conn.execute("CREATE SCHEMA mysql_db")
        conn.execute("CREATE TABLE mysql_db.rental_post_versions(id INTEGER)")
        conn.execute("INSERT INTO mysql_db.rental_post_versions VALUES (1)")
        assert views.DuckDBViewManager.create_views(conn) == ["v_observations"]
        assert conn.execute("SELECT * FROM v_observations").fetchall() == [(1, "UNKNOWN")]

