"""Validation and classification rules for rental listing prices."""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Plausibility bounds (VND / month)
# ---------------------------------------------------------------------------
MIN_PRICE_VND = 300_000  # 300K — mức giá sàn phòng trọ rẻ nhất
MAX_PRICE_VND = 200_000_000  # 200 triệu — biệt thự / penthouse cho thuê

# ---------------------------------------------------------------------------
# Price bands (triệu VND)
# ---------------------------------------------------------------------------
PRICE_BANDS: list[tuple[float, float, str]] = [
    (0, 2, "< 2 triệu"),
    (2, 5, "2–5 triệu"),
    (5, 10, "5–10 triệu"),
    (10, 20, "10–20 triệu"),
    (20, float("inf"), "> 20 triệu"),
]


def validate_price(price_vnd: object) -> bool:
    """Kiểm tra giá nằm trong khoảng hợp lý cho thuê nhà ở Việt Nam."""
    if price_vnd is None:
        return False
    try:
        val = float(price_vnd)
    except (TypeError, ValueError):
        return False
    if np.isnan(val) or np.isinf(val):
        return False
    return MIN_PRICE_VND <= val <= MAX_PRICE_VND


def classify_price_band(price_million: object) -> str | None:
    """Phân loại giá thuê theo mức (đơn vị: triệu VND)."""
    if price_million is None:
        return None
    try:
        val = float(price_million)
    except (TypeError, ValueError):
        return None
    if np.isnan(val) or np.isinf(val):
        return None
    for low, high, label in PRICE_BANDS:
        if low <= val < high:
            return label
    return None


def detect_price_outliers_iqr(
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


def get_price_summary(series: pd.Series) -> dict:
    """Thống kê mô tả cho chuỗi giá."""
    clean = series.dropna()
    if clean.empty:
        return {"count": 0, "missing": series.isna().sum()}
    return {
        "count": int(len(clean)),
        "missing": int(series.isna().sum()),
        "mean": round(float(clean.mean()), 2),
        "median": round(float(clean.median()), 2),
        "std": round(float(clean.std()), 2),
        "min": round(float(clean.min()), 2),
        "max": round(float(clean.max()), 2),
        "q25": round(float(clean.quantile(0.25)), 2),
        "q75": round(float(clean.quantile(0.75)), 2),
        "skew": round(float(clean.skew()), 4),
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    assert validate_price(1_000_000) is True
    assert validate_price(300_000) is True
    assert validate_price(200_000_000) is True
    assert validate_price(0) is False
    assert validate_price(250_000) is False
    assert validate_price(300_000_000) is False
    assert validate_price(None) is False
    assert validate_price(float("nan")) is False

    assert classify_price_band(1.5) == "< 2 triệu"
    assert classify_price_band(3.0) == "2–5 triệu"
    assert classify_price_band(7.0) == "5–10 triệu"
    assert classify_price_band(15.0) == "10–20 triệu"
    assert classify_price_band(25.0) == "> 20 triệu"
    assert classify_price_band(None) is None
    assert classify_price_band(float("nan")) is None

    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 100.0])
    mask = detect_price_outliers_iqr(s)
    assert mask.iloc[-1] == True  # 100 is outlier

    summary = get_price_summary(pd.Series([1e6, 2e6, 3e6, None]))
    assert summary["count"] == 3
    assert summary["missing"] == 1

    print("All price_validator tests passed. ✓")
