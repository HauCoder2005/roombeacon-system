"""Collect aggregate, parameter-free SQL timing for one persistence batch."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import time

from sqlalchemy import event


_KNOWN_TABLES = (
    "platforms",
    "rental_post_versions",
    "rental_posts",
    "post_prices",
    "post_addresses",
    "post_details",
    "post_images",
    "post_amenities",
    "post_fees",
    "post_contacts",
    "post_attributes",
    "post_status_history",
)


@dataclass
class _TableStats:
    rows: int = 0
    executions: int = 0
    seconds: float = 0.0


class MySQLQueryProfiler:
    """Profile executions by known table without retaining SQL or parameters."""

    def __init__(self, connection) -> None:
        self.connection = connection
        self._starts: list[float] = []
        self._tables: dict[str, _TableStats] = defaultdict(_TableStats)

    @staticmethod
    def _table(statement: str) -> str:
        lowered = statement.lower()
        for table in _KNOWN_TABLES:
            if re.search(rf"\b{re.escape(table)}\b", lowered):
                return table
        return "other"

    def _before(self, _conn, _cursor, statement, _parameters, _context, _many):
        self._starts.append(time.perf_counter())

    def _after(self, _conn, cursor, statement, parameters, _context, executemany):
        started = self._starts.pop() if self._starts else time.perf_counter()
        stats = self._tables[self._table(statement)]
        stats.executions += 1
        stats.seconds += time.perf_counter() - started
        if executemany and isinstance(parameters, (list, tuple)):
            stats.rows += len(parameters)
        elif statement.lstrip().lower().startswith(("insert", "update", "delete")):
            stats.rows += max(0, int(getattr(cursor, "rowcount", 0)))

    def __enter__(self):
        event.listen(self.connection, "before_cursor_execute", self._before)
        event.listen(self.connection, "after_cursor_execute", self._after)
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        event.remove(self.connection, "before_cursor_execute", self._before)
        event.remove(self.connection, "after_cursor_execute", self._after)

    def as_dict(self) -> dict[str, dict[str, float | int]]:
        """Return JSON-safe aggregates with no statement or parameter content."""
        return {
            table: {
                "rows": stats.rows,
                "executions": stats.executions,
                "total_seconds": round(stats.seconds, 6),
                "avg_seconds": round(stats.seconds / stats.executions, 6)
                if stats.executions
                else 0.0,
            }
            for table, stats in sorted(self._tables.items())
        }
