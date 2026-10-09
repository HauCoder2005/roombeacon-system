"""Lazily connected, read-only ClickHouse client.

Connecting on first use lets the API start (and report 503 on /ready) while
ClickHouse is still booting instead of crash-looping.
"""

from __future__ import annotations

import threading
from typing import Any, Mapping

from ..config import ClickHouseSettings


class LazyClickHouseClient:
    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings
        self._client: Any = None
        self._lock = threading.Lock()

    def query(self, sql: str, parameters: Mapping[str, Any] | None = None) -> Any:
        return self._get().query(sql, parameters=dict(parameters or {}))

    def _get(self) -> Any:
        with self._lock:
            if self._client is None:
                import clickhouse_connect

                s = self._settings
                self._client = clickhouse_connect.get_client(
                    host=s.host,
                    port=s.port,
                    username=s.user,
                    password=s.password.get_secret_value(),
                    database=s.database,
                    secure=s.secure,
                    connect_timeout=s.connect_timeout_seconds,
                    send_receive_timeout=s.query_timeout_seconds,
                    # Shared across request threads: no server session state.
                    autogenerate_session_id=False,
                    settings={"max_execution_time": s.query_timeout_seconds},
                )
            return self._client
