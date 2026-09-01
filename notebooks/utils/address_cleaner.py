"""Làm sạch định dạng địa chỉ thô trước bước chuẩn hóa vị trí."""

from __future__ import annotations

import math
import re

_HCMC_PATTERN = re.compile(
    r"\b(?:thành\s+phố\s+hồ\s+chí\s+minh|tp\s*\.?\s*hcm|hcm)\b",
    flags=re.IGNORECASE,
)
_WARD_ABBREVIATION_PATTERN = re.compile(
    r"\bP(?:\s*\.\s*|\s+|(?=\d))",
    flags=re.IGNORECASE,
)
_DISTRICT_ABBREVIATION_PATTERN = re.compile(
    r"\bQ(?:\s*\.\s*|\s+|(?=\d))",
    flags=re.IGNORECASE,
)


def clean_address(address: str) -> str | None:
    """Chuẩn hóa định dạng địa chỉ mà không thay đổi thông tin vị trí."""
    if address is None:
        return None
    if isinstance(address, float) and math.isnan(address):
        return None
    if not isinstance(address, str):
        return None

    cleaned = address.strip()
    if not cleaned:
        return None

    # Xóa toàn bộ nội dung trong ngoặc đơn (và cả ngoặc)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)  # phòng trường hợp dùng []

    cleaned = _HCMC_PATTERN.sub("TPHCM", cleaned)
    cleaned = re.sub(r"[-/|]+", ",", cleaned)
    cleaned = _WARD_ABBREVIATION_PATTERN.sub("Phường ", cleaned)
    cleaned = _DISTRICT_ABBREVIATION_PATTERN.sub("Quận ", cleaned)
    cleaned = re.sub(r"\bPhường\s*(?=\d)", "Phường ", cleaned)
    cleaned = re.sub(r"\bQuận\s*(?=\d)", "Quận ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(?:\s*,\s*)+", ", ", cleaned)
    cleaned = cleaned.strip(" ,")
    return cleaned or None