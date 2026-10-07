"""Warehouse runtime settings, sourced only from ``.env.local``.

Resolution order:

1. ``.env.local`` (path from ``ROOMBEACON_ENV_LOCAL`` or the project root).
   When the file exists, it is the only source of settings.
2. Otherwise ``WAREHOUSE_*`` variables already in the process environment.
   Inside Docker these are injected by Compose ``env_file: .env.local``.

The shared dotenv file that holds the other services' secrets is never read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any, Mapping

from dotenv import dotenv_values


ENV_LOCAL_FILENAME = ".env.local"
PREFIX = "WAREHOUSE_"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
HOSTNAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


class WarehouseConfigError(ValueError):
    """Raised for missing or unsafe warehouse configuration."""


class Secret:
    """String wrapper that never renders its value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "Secret('***')"

    __str__ = __repr__


@dataclass(frozen=True)
class WarehouseSettings:
    enabled: bool
    host: str
    port: int
    database: str
    user: str
    password: Secret = field(repr=False)
    secure: bool
    connect_timeout_seconds: int
    query_timeout_seconds: int
    source: str

    def redacted(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": "***" if self.password else "",
            "secure": self.secure,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "query_timeout_seconds": self.query_timeout_seconds,
            "source": self.source,
        }

    def require_enabled(self) -> "WarehouseSettings":
        if not self.enabled:
            raise WarehouseConfigError(f"WAREHOUSE_ENABLED is not true ({self.source})")
        if not self.password:
            raise WarehouseConfigError(
                f"WAREHOUSE_CLICKHOUSE_PASSWORD must be set in {ENV_LOCAL_FILENAME}"
            )
        return self


def default_env_local_path() -> Path:
    configured = os.getenv("ROOMBEACON_ENV_LOCAL")
    if configured:
        return Path(configured)
    for parent in [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]:
        if (parent / "warehouse").is_dir() and (parent / "analytics").is_dir():
            return parent / ENV_LOCAL_FILENAME
    return Path.cwd() / ENV_LOCAL_FILENAME


def _bool(values: Mapping[str, str], key: str, default: bool) -> bool:
    raw = values.get(key)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise WarehouseConfigError(f"{key} must be a boolean")


def _int(values: Mapping[str, str], key: str, default: int, low: int, high: int) -> int:
    raw = values.get(key)
    try:
        value = default if raw in (None, "") else int(raw)
    except ValueError as exc:
        raise WarehouseConfigError(f"{key} must be an integer") from exc
    if not low <= value <= high:
        raise WarehouseConfigError(f"{key} must be between {low} and {high}")
    return value


def _identifier(values: Mapping[str, str], key: str, default: str) -> str:
    value = (values.get(key) or default).strip()
    if not IDENTIFIER.fullmatch(value):
        raise WarehouseConfigError(f"{key} must be a plain identifier")
    return value


def _host(values: Mapping[str, str], key: str, default: str) -> str:
    value = (values.get(key) or default).strip()
    if not HOSTNAME.fullmatch(value):
        raise WarehouseConfigError(f"{key} must be a hostname or IP address")
    return value


def load_warehouse_settings(
    env_file: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    in_docker: bool | None = None,
) -> WarehouseSettings:
    path = Path(env_file) if env_file is not None else default_env_local_path()
    if path.is_file():
        values = {k: v for k, v in dotenv_values(path).items() if v is not None}
        source = ENV_LOCAL_FILENAME
    else:
        environment = os.environ if environ is None else environ
        values = {k: v for k, v in environment.items() if k.startswith(PREFIX)}
        source = f"process environment (injected from {ENV_LOCAL_FILENAME})"
    docker = Path("/.dockerenv").exists() if in_docker is None else in_docker

    service_host = _host(values, "WAREHOUSE_CLICKHOUSE_HOST", "clickhouse")
    access_host = _host(values, "WAREHOUSE_CLICKHOUSE_HOST_ACCESS_HOST", "127.0.0.1")
    return WarehouseSettings(
        enabled=_bool(values, "WAREHOUSE_ENABLED", False),
        host=service_host if docker else access_host,
        port=_int(values, "WAREHOUSE_CLICKHOUSE_PORT", 8123, 1, 65535),
        database=_identifier(values, "WAREHOUSE_CLICKHOUSE_DATABASE", "roombeacon_dw"),
        user=_identifier(values, "WAREHOUSE_CLICKHOUSE_USER", "roombeacon_loader"),
        password=Secret(values.get("WAREHOUSE_CLICKHOUSE_PASSWORD", "")),
        secure=_bool(values, "WAREHOUSE_CLICKHOUSE_SECURE", False),
        connect_timeout_seconds=_int(values, "WAREHOUSE_CONNECT_TIMEOUT_SECONDS", 10, 1, 120),
        query_timeout_seconds=_int(values, "WAREHOUSE_QUERY_TIMEOUT_SECONDS", 300, 1, 3600),
        source=source,
    )
