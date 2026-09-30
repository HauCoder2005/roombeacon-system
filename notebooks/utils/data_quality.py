"""Data quality profiling, coverage analysis, and reporting utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_missing_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Tính toán bảng missing count / rate cho từng cột."""
    total = len(df)
    missing = df.isnull().sum().reset_index()
    missing.columns = ["column", "missing_count"]
    missing["missing_rate_pct"] = (missing["missing_count"] / total * 100).round(2)
    missing["present_count"] = total - missing["missing_count"]
    missing["present_rate_pct"] = (100 - missing["missing_rate_pct"]).round(2)
    return (
        missing.sort_values("missing_rate_pct", ascending=False)
        .reset_index(drop=True)
    )


def compute_coverage_by_source(
    df: pd.DataFrame,
    columns: list[str],
    source_col: str = "source",
) -> pd.DataFrame:
    """Tính coverage % cho các cột chính, tách theo source."""
    rows: list[dict] = []
    for src, group in df.groupby(source_col, sort=True):
        n = len(group)
        row: dict = {"source": src, "total": n}
        for col in columns:
            if col not in group.columns:
                row[f"{col}_count"] = 0
                row[f"{col}_pct"] = 0.0
                continue
            present = int(group[col].notna().sum())
            row[f"{col}_count"] = present
            row[f"{col}_pct"] = round(present / n * 100, 2) if n > 0 else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def compute_quality_score(
    row: pd.Series,
    columns: list[str] | None = None,
) -> float:
    """Tính điểm chất lượng dữ liệu cho một dòng (0.0 – 1.0)."""
    if columns is None:
        columns = ["price", "area", "address", "title_raw"]
    present = sum(1 for col in columns if pd.notna(row.get(col)))
    return round(present / len(columns), 2)


def generate_quality_report(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """So sánh coverage Before vs After cho các cột chính."""
    rows: list[dict] = []
    n_before = len(df_before)
    n_after = len(df_after)
    for col in key_columns:
        bp = int(df_before[col].notna().sum()) if col in df_before.columns else 0
        ap = int(df_after[col].notna().sum()) if col in df_after.columns else 0
        bp_pct = round(bp / n_before * 100, 2) if n_before > 0 else 0.0
        ap_pct = round(ap / n_after * 100, 2) if n_after > 0 else 0.0
        rows.append(
            {
                "column": col,
                "before_total": n_before,
                "before_present": bp,
                "before_pct": bp_pct,
                "after_total": n_after,
                "after_present": ap,
                "after_pct": ap_pct,
                "delta_pct": round(ap_pct - bp_pct, 2),
            }
        )
    return pd.DataFrame(rows)


def detect_duplicates(
    df: pd.DataFrame,
    subset_cols: list[str],
) -> pd.DataFrame:
    """Tìm các bản ghi trùng lặp theo tập cột cho trước."""
    dupes = df[df.duplicated(subset=subset_cols, keep=False)]
    return dupes.sort_values(subset_cols).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    test_df = pd.DataFrame(
        {
            "price": [1.0, None, 3.0, 4.0],
            "area": [None, None, 30.0, 40.0],
            "address": ["A", "B", None, "D"],
            "title_raw": ["T1", "T2", "T3", None],
            "source": ["s1", "s1", "s2", "s2"],
        }
    )

    # Missing profile
    profile = compute_missing_profile(test_df)
    assert profile.iloc[0]["missing_count"] >= 1

    # Coverage by source
    coverage = compute_coverage_by_source(test_df, ["price", "area", "address"])
    assert len(coverage) == 2
    assert "price_pct" in coverage.columns

    # Quality score
    row = pd.Series({"price": 1.0, "area": None, "address": "abc", "title_raw": "t"})
    score = compute_quality_score(row)
    assert score == 0.75

    # Quality report
    df_a = pd.DataFrame({"price": [1, None], "area": [10, 20]})
    df_b = pd.DataFrame({"price": [1, 2], "area": [10, None]})
    report = generate_quality_report(df_a, df_b, ["price", "area"])
    assert len(report) == 2
    assert "delta_pct" in report.columns

    # Duplicates
    df_dup = pd.DataFrame({"id": [1, 1, 2, 3], "val": ["a", "a", "b", "c"]})
    dupes = detect_duplicates(df_dup, ["id"])
    assert len(dupes) == 2

    print("All data_quality tests passed. ✓")
