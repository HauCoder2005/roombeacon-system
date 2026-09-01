"""Đối chiếu trực tiếp địa chỉ cũ với phường hiện hành."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

import pandas as pd

from enums.ward_mapping import WARD_MAPPING


_NUMERIC_WARD_CONTEXT_PATTERN = re.compile(r"^\d+\s+quan\b")
_COMPATIBILITY_PATTERNS: dict[str, list[str]] = {
    # WARD_MAPPING hiện chưa khai báo Phường 11, Quận 10.
    "phuong 11 quan 10": ["Phường Hòa Hưng"],
}
_MATCH_PATTERNS = {
    (
        f"phuong {pattern}"
        if _NUMERIC_WARD_CONTEXT_PATTERN.match(pattern)
        else pattern
    ): current_wards
    for pattern, current_wards in {
        **_COMPATIBILITY_PATTERNS,
        **WARD_MAPPING,
    }.items()
}
_SORTED_LOCATION_PATTERNS = tuple(
    sorted(
        _MATCH_PATTERNS.items(),
        key=lambda item: (len(item[0].split()), len(item[0])),
        reverse=True,
    )
)


def remove_vietnamese_accents(value: object) -> Optional[str]:
    """Loại bỏ dấu tiếng Việt."""
    if not isinstance(value, str):
        return None

    decomposed = unicodedata.normalize("NFD", value)
    without_marks = "".join(
        c for c in decomposed if unicodedata.category(c) != "Mn"
    )
    return without_marks.replace("đ", "d").replace("Đ", "D")

def normalize_text(value: object) -> Optional[str]:
    without_accents = remove_vietnamese_accents(value)
    if without_accents is None:
        return None

    normalized = without_accents.strip().lower()
    if not normalized:
        return None

    # Xử lý viết tắt
    normalized = re.sub(
        r"\b(?:thanh\s+pho\s+)?ho\s+chi\s+minh\b|"
        r"\btp\.?\s*hcm\b|\btphcm\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"\bq(?:\s*\.\s*|\s+)(?=\w)", "quan ", normalized)
    normalized = re.sub(r"\bq(?=\d)", "quan ", normalized)
    normalized = re.sub(r"\bp(?:\s*\.\s*|\s+)(?=\w)", "phuong ", normalized)
    normalized = re.sub(r"\bp(?=\d)", "phuong ", normalized)

    # Quan trọng: bỏ phần trong ngoặc đơn (hay chứa thông tin cũ)
    normalized = re.sub(r"\([^)]*\)", " ", normalized)

    # Bỏ dấu câu + khoảng trắng thừa
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def normalize_location(text: object) -> list[str]:
    """Ánh xạ trực tiếp trên toàn bộ chuỗi địa chỉ đã chuẩn hóa."""
    normalized = normalize_text(text)
    if not normalized:
        return []

    matched_specificity = None
    result = []

    for pattern, wards in _SORTED_LOCATION_PATTERNS:
        specificity = len(pattern.split())
        if matched_specificity is not None and specificity < matched_specificity:
            break

        if _matches_pattern(normalized, pattern):
            matched_specificity = specificity
            for w in wards:
                if w not in result:
                    result.append(w)

    return result


def _matches_pattern(normalized_address: str, pattern: str) -> bool:
    """Đối chiếu pattern theo ranh giới token chữ và số."""
    expression = rf"(?<![a-z0-9]){re.escape(pattern)}(?![a-z0-9])"
    return re.search(expression, normalized_address) is not None


def apply_location_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Tạo bản sao DataFrame và thêm cột current_location."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    required_columns = {"address_clean"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise KeyError(f"Missing required columns: {sorted(missing_columns)}")

    result = df.copy()
    result["current_location"] = result["address_clean"].map(normalize_location)
    return result


def _run_verification_tests() -> None:
    """Chạy các trường hợp xác minh."""
    cases = (
        ("Phạm Ngũ Lão, Quận 1", ["Phường Bến Thành"]),
        ("Đường 16, Phường Tân Phú, Quận 7", ["Phường Tân Mỹ"]),
        (
            "Nguyễn Thị Minh Khai, Phường Đa Kao, Quận 1",
            ["Phường Sài Gòn", "Phường Tân Định"],
        ),
        ("Đường 3 Tháng 2, Phường 11, Quận 10, TPHCM", ["Phường Hòa Hưng"]),
        (
            "Tô Hiến Thành, Phường 14, Quận 10",
            ["Phường Diên Hồng", "Phường Hòa Hưng"],
        ),
        ("Trần Phú, Phường 4, Quận 5", ["Phường Chợ Quán"]),
        ("Phường 1, Quận 10", ["Phường Vườn Lài"]),
        ("Đường số 6, Phường Phước Bình, Quận 9", ["Phường Phước Long"]),
        (
            "Đinh Phong Phú, Phường Tăng Nhơn Phú B, Quận 9",
            ["Phường Tăng Nhơn Phú"],
        ),
    )

    debug_address = "Phạm Ngũ Lão, Phường Phạm Ngũ Lão, Quận 1, TPHCM"
    debug_normalized = normalize_text(debug_address)
    debug_patterns = (
        "pham ngu lao",
        "tan phu quan 7",
        "phuoc binh quan 9",
        "tang nhon phu b",
    )
    available_patterns = dict(_SORTED_LOCATION_PATTERNS)
    print("Normalized location:", debug_normalized)
    print(
        "Pattern availability:",
        {pattern: pattern in available_patterns for pattern in debug_patterns},
    )
    print(
        "Regex matches:",
        {
            pattern: _matches_pattern(debug_normalized or "", pattern)
            for pattern in debug_patterns
        },
    )

    for address, expected in cases:
        actual = normalize_location(address)
        assert actual == expected, f"{address}: expected {expected}, got {actual}"

    assert normalize_location(None) == []
    assert normalize_location(float("nan")) == []
    assert normalize_location("") == []

    # Kiểm tra không bị khớp nhầm Phường 1 với Phường 11
    assert normalize_location("Phường 1, Quận 10") == ["Phường Vườn Lài"]

    source = pd.DataFrame({"address_clean": [addr for addr, _ in cases]})
    snapshot = source.copy(deep=True)
    result = apply_location_mapping(source)
    pd.testing.assert_frame_equal(source, snapshot)
    assert result["current_location"].tolist() == [exp for _, exp in cases]


if __name__ == "__main__":
    _run_verification_tests()
    print("All verification tests passed.")
