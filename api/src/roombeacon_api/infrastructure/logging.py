"""Structured JSON logs with secret redaction."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
import sys


REDACT = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b(\s*[=:]\s*)(\S+)")
REDACT_URL_CREDENTIALS = re.compile(r"(?i)(\w+://[^:/\s]+:)[^@\s]+@")


def redact(text: str) -> str:
    return REDACT_URL_CREDENTIALS.sub(r"\1***@", REDACT.sub(r"\1\2***", text))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms", "client"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("roombeacon_api")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
