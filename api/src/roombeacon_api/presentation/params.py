"""Shared request-parameter helpers."""

from __future__ import annotations

import unicodedata
from typing import Any


LOCATION_ID = r"^[0-9a-f]{16}$"
LISTING_ID = r"^[0-9]{1,19}$"


def normalize_text(value: str) -> str:
    """NFC + trim: warehouse names are NFC, but some Vietnamese keyboards send NFD."""
    return unicodedata.normalize("NFC", value).strip()


def filters_of(**values: Any) -> dict[str, Any]:
    """Echo only the filters the caller actually set."""
    return {k: v for k, v in values.items() if v not in (None, "", False)}
