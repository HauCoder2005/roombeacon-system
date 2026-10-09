"""API runtime settings, read only from the process environment.

Inside Docker, Compose injects them from ``.env.local``. API keys are stored
as SHA-256 hex digests (``API_KEY_SHA256``, comma separated) so the raw keys
never live on the server. ClickHouse is reached with the read-only
``WAREHOUSE_READER_*`` account, never the loader or admin account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Mapping


SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
HOSTNAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
ORIGIN = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?$")
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


class ApiConfigError(ValueError):
    """Raised for missing or unsafe API configuration."""


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
class ClickHouseSettings:
    host: str
    port: int
    database: str
    user: str
    password: Secret = field(repr=False)
    secure: bool
    connect_timeout_seconds: int
    query_timeout_seconds: int


@dataclass(frozen=True)
class ApiSettings:
    api_key_sha256: tuple[str, ...] = field(repr=False)
    auth_enabled: bool
    rate_limit_per_minute: int
    cors_origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    docs_enabled: bool
    clickhouse: ClickHouseSettings

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ApiSettings":
        env = os.environ if environ is None else environ
        auth_enabled = _bool(env, "API_AUTH_ENABLED", True)
        keys = tuple(k.strip().lower() for k in env.get("API_KEY_SHA256", "").split(",") if k.strip())
        if any(not SHA256_HEX.fullmatch(k) for k in keys):
            raise ApiConfigError("API_KEY_SHA256 must be comma-separated SHA-256 hex digests")
        if auth_enabled and not keys:
            raise ApiConfigError("API_KEY_SHA256 must be set when API_AUTH_ENABLED is true")
        origins = _list(env, "API_CORS_ORIGINS", "")
        if any(not ORIGIN.fullmatch(o) for o in origins):
            raise ApiConfigError("API_CORS_ORIGINS must list explicit http(s) origins (no wildcards)")
        hosts = _list(env, "API_ALLOWED_HOSTS", "localhost,127.0.0.1")
        if not hosts or any(not HOSTNAME.fullmatch(h) for h in hosts):
            raise ApiConfigError("API_ALLOWED_HOSTS must list hostnames")
        password = env.get("WAREHOUSE_READER_PASSWORD", "")
        if not password:
            raise ApiConfigError("WAREHOUSE_READER_PASSWORD must be set")
        return cls(
            api_key_sha256=keys,
            auth_enabled=auth_enabled,
            rate_limit_per_minute=_int(env, "API_RATE_LIMIT_PER_MINUTE", 60, 1, 100_000),
            cors_origins=origins,
            allowed_hosts=hosts,
            docs_enabled=_bool(env, "API_DOCS_ENABLED", False),
            clickhouse=ClickHouseSettings(
                host=_host(env, "API_CLICKHOUSE_HOST", "127.0.0.1"),
                port=_int(env, "WAREHOUSE_CLICKHOUSE_PORT", 8123, 1, 65535),
                database=_identifier(env, "WAREHOUSE_CLICKHOUSE_DATABASE", "roombeacon_dw"),
                user=_identifier(env, "WAREHOUSE_READER_USER", ""),
                password=Secret(password),
                secure=_bool(env, "WAREHOUSE_CLICKHOUSE_SECURE", False),
                connect_timeout_seconds=_int(env, "API_CLICKHOUSE_CONNECT_TIMEOUT_SECONDS", 5, 1, 60),
                query_timeout_seconds=_int(env, "API_QUERY_TIMEOUT_SECONDS", 10, 1, 120),
            ),
        )


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise ApiConfigError(f"{key} must be a boolean")


def _int(env: Mapping[str, str], key: str, default: int, low: int, high: int) -> int:
    raw = env.get(key)
    try:
        value = default if raw in (None, "") else int(raw)
    except ValueError as exc:
        raise ApiConfigError(f"{key} must be an integer") from exc
    if not low <= value <= high:
        raise ApiConfigError(f"{key} must be between {low} and {high}")
    return value


def _identifier(env: Mapping[str, str], key: str, default: str) -> str:
    value = (env.get(key) or default).strip()
    if not IDENTIFIER.fullmatch(value):
        raise ApiConfigError(f"{key} must be a plain identifier")
    return value


def _host(env: Mapping[str, str], key: str, default: str) -> str:
    value = (env.get(key) or default).strip()
    if not HOSTNAME.fullmatch(value):
        raise ApiConfigError(f"{key} must be a hostname or IP address")
    return value


def _list(env: Mapping[str, str], key: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in env.get(key, default).split(",") if item.strip())
