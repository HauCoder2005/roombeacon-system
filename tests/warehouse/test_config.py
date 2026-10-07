"""Warehouse settings come from .env.local only and never leak secrets."""

from pathlib import Path

import pytest

from roombeacon_warehouse.config import (
    WarehouseConfigError,
    load_warehouse_settings,
)


ROOT = Path(__file__).resolve().parents[2]

LOCAL = """
WAREHOUSE_ENABLED=true
WAREHOUSE_CLICKHOUSE_HOST=clickhouse
WAREHOUSE_CLICKHOUSE_HOST_ACCESS_HOST=127.0.0.1
WAREHOUSE_CLICKHOUSE_PORT=8123
WAREHOUSE_CLICKHOUSE_DATABASE=roombeacon_dw
WAREHOUSE_CLICKHOUSE_USER=roombeacon_loader
WAREHOUSE_CLICKHOUSE_PASSWORD=s3cr3t-loader
WAREHOUSE_CONNECT_TIMEOUT_SECONDS=7
WAREHOUSE_QUERY_TIMEOUT_SECONDS=120
"""


def _write(tmp_path: Path, text: str = LOCAL) -> Path:
    path = tmp_path / ".env.local"
    path.write_text(text)
    return path


def test_settings_are_read_from_env_local(tmp_path):
    settings = load_warehouse_settings(_write(tmp_path), environ={}, in_docker=False)

    assert settings.enabled is True
    assert settings.host == "127.0.0.1"  # host-side access address outside Docker
    assert settings.port == 8123
    assert settings.database == "roombeacon_dw"
    assert settings.user == "roombeacon_loader"
    assert settings.password.get_secret_value() == "s3cr3t-loader"
    assert settings.connect_timeout_seconds == 7
    assert settings.query_timeout_seconds == 120


def test_inside_docker_the_service_name_is_used(tmp_path):
    settings = load_warehouse_settings(_write(tmp_path), environ={}, in_docker=True)

    assert settings.host == "clickhouse"


def test_dotenv_file_is_never_read(tmp_path):
    (tmp_path / ".env").write_text("WAREHOUSE_ENABLED=true\nWAREHOUSE_CLICKHOUSE_PASSWORD=from-dotenv\n")

    settings = load_warehouse_settings(tmp_path / ".env.local", environ={}, in_docker=False)

    assert settings.enabled is False
    assert settings.password.get_secret_value() == ""


def test_env_local_file_takes_precedence_over_process_environment(tmp_path):
    environ = {"WAREHOUSE_CLICKHOUSE_PASSWORD": "from-process", "WAREHOUSE_ENABLED": "false"}

    settings = load_warehouse_settings(_write(tmp_path), environ=environ, in_docker=False)

    assert settings.enabled is True
    assert settings.password.get_secret_value() == "s3cr3t-loader"


def test_container_uses_variables_injected_from_env_local(tmp_path):
    environ = {
        "WAREHOUSE_ENABLED": "true",
        "WAREHOUSE_CLICKHOUSE_PASSWORD": "injected",
        "BRONZE_MYSQL_PASSWORD": "not-for-the-warehouse",
    }

    settings = load_warehouse_settings(tmp_path / ".env.local", environ=environ, in_docker=True)

    assert settings.enabled is True
    assert settings.password.get_secret_value() == "injected"


def test_secrets_are_redacted_everywhere(tmp_path):
    settings = load_warehouse_settings(_write(tmp_path), environ={}, in_docker=False)

    for rendered in (repr(settings), str(settings), str(settings.redacted())):
        assert "s3cr3t-loader" not in rendered
    assert settings.redacted()["password"] == "***"


@pytest.mark.parametrize(
    "line",
    [
        "WAREHOUSE_CLICKHOUSE_DATABASE=dw; DROP DATABASE system",
        "WAREHOUSE_CLICKHOUSE_PORT=99999",
        "WAREHOUSE_QUERY_TIMEOUT_SECONDS=0",
        "WAREHOUSE_QUERY_TIMEOUT_SECONDS=100000",
        "WAREHOUSE_CLICKHOUSE_USER=bad user",
    ],
)
def test_invalid_values_fail_closed(tmp_path, line):
    with pytest.raises(WarehouseConfigError):
        load_warehouse_settings(_write(tmp_path, LOCAL + line + "\n"), environ={}, in_docker=False)


def test_enabled_warehouse_requires_a_password(tmp_path):
    text = LOCAL.replace("WAREHOUSE_CLICKHOUSE_PASSWORD=s3cr3t-loader", "WAREHOUSE_CLICKHOUSE_PASSWORD=")
    settings = load_warehouse_settings(_write(tmp_path, text), environ={}, in_docker=False)

    with pytest.raises(WarehouseConfigError, match="WAREHOUSE_CLICKHOUSE_PASSWORD"):
        settings.require_enabled()


def test_warehouse_package_never_references_the_shared_dotenv():
    for path in (ROOT / "warehouse/src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert '".env"' not in source and "'.env'" not in source, path
        assert "roombeacon_crawler.config" not in source, path
