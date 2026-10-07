"""Deterministic, type-aware row hashing for Silver golden verification."""

import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

import numpy as np
import pandas as pd


def _canonical_scalar(value: Any) -> bytes:
    if value is None or value is pd.NA or value is pd.NaT:
        return b"null"
    if isinstance(value, (float, np.floating)) and math.isnan(float(value)):
        return b"null"
    if isinstance(value, (bool, np.bool_)):
        return b"bool:1" if bool(value) else b"bool:0"
    if isinstance(value, (int, np.integer)):
        return f"int:{int(value)}".encode("utf-8")
    if isinstance(value, Decimal):
        return f"decimal:{format(value, 'f')}".encode("utf-8")
    if isinstance(value, (float, np.floating)):
        return f"float:{float(value).hex()}".encode("ascii")
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        return f"datetime:{pd.Timestamp(value).isoformat()}".encode("utf-8")
    if isinstance(value, bytes):
        return b"bytes:" + value.hex().encode("ascii")
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple, dict)):
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        return f"json:{encoded}".encode("utf-8")
    return f"string:{value}".encode("utf-8")


def hash_silver_rows(frame: pd.DataFrame) -> list[str]:
    """Return a SHA-256 digest for every row, preserving row and column order."""
    hashes: list[str] = []
    for row in frame.itertuples(index=False, name=None):
        digest = hashlib.sha256()
        for value in row:
            token = _canonical_scalar(value)
            digest.update(len(token).to_bytes(8, "big"))
            digest.update(token)
        hashes.append(digest.hexdigest())
    return hashes


def aggregate_row_hashes(row_hashes: Iterable[str]) -> str:
    """Return one compact digest over an ordered sequence of row digests."""
    digest = hashlib.sha256()
    for row_hash in row_hashes:
        digest.update(bytes.fromhex(row_hash))
    return digest.hexdigest()
