"""Bronze MySQL must not pile up connections: no per-run DDL, bounded asset queries, bounded server waits."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from roombeacon_crawler.application.assets.asset_reconciler import AssetReconcilerService
from roombeacon_crawler.infrastructure.mysql import schema

ROOT = Path(__file__).resolve().parents[1]


def _engine(column_exists: bool):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.return_value.scalar.return_value = 1 if column_exists else 0
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine, conn


def _statements(conn) -> list[str]:
    return [str(call.args[0]) for call in conn.execute.call_args_list]


def test_existing_column_is_not_altered_again():
    engine, conn = _engine(column_exists=True)
    with patch("roombeacon_crawler.infrastructure.mysql.repositories.geocode_repository.MySQLGeocodeRepository"):
        schema.ensure_mysql_schema(engine)

    assert not any(s.lstrip().upper().startswith("ALTER TABLE") for s in _statements(conn))


def test_missing_column_is_added_once():
    engine, conn = _engine(column_exists=False)
    with patch("roombeacon_crawler.infrastructure.mysql.repositories.geocode_repository.MySQLGeocodeRepository"):
        schema.ensure_mysql_schema(engine)

    alters = [s for s in _statements(conn) if s.lstrip().upper().startswith("ALTER TABLE")]
    assert len(alters) == 1 and "ingestion_origin" in alters[0]


def test_asset_reconciler_connections_are_time_bounded():
    service = AssetReconcilerService(state_repo=MagicMock(), bucket_name="b")
    with patch("roombeacon_crawler.application.assets.asset_reconciler.pymysql.connect") as connect:
        service.get_mysql_connection()

    kwargs = connect.call_args.kwargs
    assert kwargs["read_timeout"] <= 120 and kwargs["write_timeout"] <= 120
    assert "MAX_EXECUTION_TIME" in kwargs["init_command"]
    assert "lock_wait_timeout" in kwargs["init_command"]


def _bronze_block() -> str:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    start = text.index("\n  mysql-bronze:")
    end = text.index("\n  mysql-airflow:", start)
    return text[start:end]


def test_bronze_server_bounds_lock_and_idle_waits():
    block = _bronze_block()
    max_conn = int(re.search(r'"--max-connections=(\d+)"', block).group(1))

    assert max_conn >= 60
    assert '"--wait-timeout=600"' in block
    assert '"--lock-wait-timeout=120"' in block


def test_asset_accounting_does_not_scan_post_images():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchall.return_value = [{"source": "mogi"}, {"source": "tromoi"}]
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor
    state = MagicMock()
    state.base_dir = ROOT / "does-not-exist"
    service = AssetReconcilerService(state_repo=state, bucket_name="b")

    with patch.object(service, "get_mysql_connection", return_value=connection):
        accounting = service.get_source_accounting()

    sql = " ".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "post_images" not in sql
    assert sorted(accounting) == ["mogi", "tromoi"]
