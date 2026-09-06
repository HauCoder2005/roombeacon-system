"""Validation and classification rules for rental listing areas."""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Plausibility bounds (m²)
# ---------------------------------------------------------------------------
MIN_AREA_M2 = 5.0  # phòng trọ nhỏ nhất hợp lý
MAX_AREA_M2 = 1_000.0  # biệt thự / kho xưởng cho thuê

# ---------------------------------------------------------------------------
# Area bands
# ---------------------------------------------------------------------------
AREA_BANDS: list[tuple[float, float, str]] = [
    (0, 20, "< 20 m²"),
    (20, 30, "20–30 m²"),
    (30, 50, "30–50 m²"),
    (50, 100, "50–100 m²"),
    (100, float("inf"), "> 100 m²"),
]


def validate_area(area_m2: object) -> bool:
    """Kiểm tra diện tích nằm trong khoảng hợp lý."""
    if area_m2 is None:
        return False
    try:
        val = float(area_m2)
    except (TypeError, ValueError):
        return False
    if np.isnan(val) or np.isinf(val):
        return False
    return MIN_AREA_M2 <= val <= MAX_AREA_M2


def classify_area_band(area_m2: object) -> str | None:
    """Phân loại diện tích theo nhóm."""
    if area_m2 is None:
        return None
    try:
        val = float(area_m2)
    except (TypeError, ValueError):
        return None
    if np.isnan(val) or np.isinf(val):
        return None
    for low, high, label in AREA_BANDS:
        if low <= val < high:
            return label
    return None


def detect_area_outliers_iqr(
    series: pd.Series,
    multiplier: float = 1.5,
) -> pd.Series:
    """Trả về boolean mask (True = outlier) dùng phương pháp IQR."""
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return (series < lower) | (series > upper)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    assert validate_area(25.0) is True
    assert validate_area(5.0) is True
    assert validate_area(1000.0) is True
    assert validate_area(3.0) is False
    assert validate_area(0) is False
    assert validate_area(2000.0) is False
    assert validate_area(None) is False
    assert validate_area(float("nan")) is False

    assert classify_area_band(15.0) == "< 20 m²"
    assert classify_area_band(25.0) == "20–30 m²"
    assert classify_area_band(40.0) == "30–50 m²"
    assert classify_area_band(75.0) == "50–100 m²"
    assert classify_area_band(150.0) == "> 100 m²"
    assert classify_area_band(None) is None

    s = pd.Series([10.0, 20.0, 25.0, 30.0, 500.0])
    mask = detect_area_outliers_iqr(s)
    assert mask.iloc[-1] == True  # 500 is outlier

    print("All area_validator tests passed. ✓")
