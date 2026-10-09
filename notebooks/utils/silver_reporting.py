"""Lightweight, presentation-only summaries for the Silver notebook.

These functions do not clean, parse, map, classify, or materialize data. They
summarize fields already produced by canonical processing helpers.
"""

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from .notebook_audit import validate_numeric_candidates


def status_summary(series: pd.Series, label: str = "Status") -> pd.DataFrame:
    """Return count and percentage for an existing status series."""
    counts = series.fillna("(missing)").astype(str).value_counts(dropna=False)
    result = counts.rename_axis(label).reset_index(name="Rows")
    result["Percentage (%)"] = (result["Rows"] / len(series) * 100).round(2)
    return result


def text_change_summary(
    bronze: pd.DataFrame,
    silver: pd.DataFrame,
    fields: Mapping[str, tuple[str, str]],
) -> pd.DataFrame:
    """Summarize raw/clean availability and null-safe value changes."""
    rows = []
    for label, (raw_field, clean_field) in fields.items():
        raw = bronze[raw_field]
        clean = silver[clean_field]
        same = raw.eq(clean).fillna(False) | (raw.isna() & clean.isna())
        changed = ~same
        rows.append({
            "Field": label,
            "Total Rows": len(raw),
            "Raw Available": int(raw.notna().sum()),
            "Clean Available": int(clean.notna().sum()),
            "Changed Rows": int(changed.sum()),
            "Unchanged Rows": int(same.sum()),
            "Changed (%)": round(float(changed.mean() * 100), 2),
            "Cleaned to NULL": int((raw.notna() & clean.isna()).sum()),
            "Recovered": int((raw.isna() & clean.notna()).sum()),
        })
    return pd.DataFrame(rows)


def changed_text_examples(
    bronze: pd.DataFrame,
    silver: pd.DataFrame,
    fields: Mapping[str, tuple[str, str]],
    limit: int = 16,
) -> pd.DataFrame:
    """Return representative runtime rows whose text representation changed."""
    examples = []
    per_field = max(1, limit // max(1, len(fields)))
    for label, (raw_field, clean_field) in fields.items():
        raw = bronze[raw_field]
        clean = silver[clean_field]
        changed = ~(raw.eq(clean).fillna(False) | (raw.isna() & clean.isna()))
        sample = pd.DataFrame({
            "Field": label,
            "Raw Text": raw[changed],
            "Clean Text": clean[changed],
        }).head(per_field)
        examples.append(sample)
    return pd.concat(examples, ignore_index=True).head(limit) if examples else pd.DataFrame()


def sample_status_rows(
    frame: pd.DataFrame,
    status_field: str,
    statuses: Sequence[str],
    columns: Sequence[str],
    per_status: int = 4,
) -> pd.DataFrame:
    """Select deterministic, bounded examples for requested existing statuses."""
    samples = []
    for status in statuses:
        current = frame.loc[frame[status_field].eq(status), list(columns)].head(per_status).copy()
        if not current.empty:
            current.insert(0, "Example Status", status)
            samples.append(current)
    return pd.concat(samples, ignore_index=True) if samples else pd.DataFrame(columns=["Example Status", *columns])


def numeric_audit_report(
    bronze: pd.DataFrame,
    evidence: pd.DataFrame,
    silver: pd.DataFrame,
    kind: str,
) -> pd.DataFrame:
    """Expose the canonical numeric validator's intermediate evidence for reporting."""
    audit = validate_numeric_candidates(bronze, evidence, kind).copy()
    clean_field = "price_amount_clean" if kind == "price" else "area_value_clean"
    status_field = f"{kind}_quality_status"
    audit["final_clean"] = silver[clean_field].to_numpy()
    audit["quality_status"] = silver[status_field].to_numpy()
    return audit


def iqr_threshold_diagnostics(values: pd.Series, metric: str) -> pd.DataFrame:
    """Describe the exact 1.5×IQR thresholds used by canonical outlier flags."""
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if len(numeric) < 4:
        return pd.DataFrame([{
            "Metric": metric, "Threshold Method": "1.5 × IQR (inactive: <4 values)",
            "Q1": np.nan, "Q3": np.nan, "Lower Threshold": np.nan, "Upper Threshold": np.nan,
        }])
    q1, q3 = numeric.quantile([0.25, 0.75])
    iqr = q3 - q1
    active = bool(np.isfinite(iqr) and iqr > 0)
    return pd.DataFrame([{
        "Metric": metric,
        "Threshold Method": "1.5 × IQR" if active else "1.5 × IQR (inactive: zero/non-finite IQR)",
        "Q1": q1, "Q3": q3,
        "Lower Threshold": q1 - 1.5 * iqr if active else np.nan,
        "Upper Threshold": q3 + 1.5 * iqr if active else np.nan,
    }])


def flag_reason_breakdown(silver: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return actual contributing condition masks and their prevalence."""
    reason_masks = {
        "Price Outlier": silver.price_outlier_flag.fillna(False),
        "Area Outlier": silver.area_outlier_flag.fillna(False),
        "Coordinate Missing": silver.coordinate_trust_reason.eq("MISSING_COORDINATE_PAIR"),
        "Coordinate Invalid": silver.coordinate_trust_reason.isin(
            ["NONFINITE_COORDINATE", "OUT_OF_BOUNDS", "ZERO_COORDINATE"]
        ),
        "Coordinate Untrusted": silver.coordinate_trust_reason.isin(
            ["UNTRUSTED_PROVIDER", "SHARED_POINT_CONFLICTING_ADDRESSES"]
        ),
        "Ward Unmapped / Ambiguous": silver.ward_mapping_status.isin(["UNMAPPED", "AMBIGUOUS"]),
        "Possible Duplicate": silver.duplicate_candidate_status.eq("POSSIBLE_DUPLICATE"),
        "Temporal Review": silver.temporal_quality_status.eq("REQUIRES_REVIEW"),
        "Price Review / Unavailable": ~silver.price_quality_status.isin(
            ["VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN"]
        ),
        "Area Review / Unavailable": ~silver.area_quality_status.isin(
            ["VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN"]
        ),
        "Price Parser Disagreement": silver.price_parser_comparison_status.eq("DISAGREEMENT"),
        "Price × Area Review": silver.price_area_quality_status.str.endswith("REVIEW"),
        "Cross-source Duplicate Candidate": (
            silver.duplicate_candidate_status.eq("POSSIBLE_DUPLICATE")
            & silver.duplicate_scope.eq("CROSS_SOURCE")
        ),
    }
    flags = pd.DataFrame(reason_masks, index=silver.index).fillna(False).astype(bool)
    ready_with_flags = silver.row_quality_status.eq("READY_WITH_FLAGS")
    denominator = max(1, int(ready_with_flags.sum()))
    result = pd.DataFrame({
        "Flag Reason": flags.columns,
        "Affected Rows": [int(flags[column].sum()) for column in flags],
        "Percentage of Dataset (%)": [round(float(flags[column].mean() * 100), 2) for column in flags],
        "Percentage of READY_WITH_FLAGS (%)": [
            round(float((flags[column] & ready_with_flags).sum() / denominator * 100), 2)
            for column in flags
        ],
    }).sort_values("Affected Rows", ascending=False, ignore_index=True)
    return result, flags


def multi_flag_distribution(flags: pd.DataFrame) -> pd.DataFrame:
    """Bucket the number of diagnostic conditions per row; this is not a score."""
    count = flags.astype(bool).sum(axis=1)
    buckets = pd.Categorical(
        np.select([count.eq(0), count.eq(1), count.eq(2), count.eq(3)], ["0", "1", "2", "3"], default="4+"),
        categories=["0", "1", "2", "3", "4+"],
        ordered=True,
    )
    rows = pd.Series(buckets).value_counts(sort=False).reindex(["0", "1", "2", "3", "4+"], fill_value=0)
    result = rows.rename_axis("Flag Count").reset_index(name="Rows")
    result["Percentage (%)"] = (result.Rows / len(flags) * 100).round(2)
    return result


def duplicate_group_summary(silver: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize existing duplicate candidate groups without confirming duplicates."""
    candidates = silver.loc[silver.duplicate_candidate_status.eq("POSSIBLE_DUPLICATE")].copy()
    if candidates.empty:
        return pd.DataFrame(), pd.DataFrame()
    grouped = candidates.groupby("duplicate_candidate_group", dropna=True)
    groups = grouped.agg(
        Listings=("rental_post_id", "size"),
        Sources=("source_code", "nunique"),
        Candidate_Scope=("duplicate_scope", "first"),
    ).reset_index().rename(columns={"duplicate_candidate_group": "Group ID"})
    groups["Candidate Scope"] = groups.pop("Candidate_Scope").astype("string").replace(
        {"CROSS_SOURCE": "Cross-source", "SAME_SOURCE": "Same-source"}
    )
    distribution = groups.Listings.value_counts().sort_index().rename_axis("Group Size").reset_index(name="Candidate Groups")
    return groups.sort_values(["Listings", "Group ID"], ascending=[False, True]), distribution


# Chart tier for each Silver status value (see notebook_style.status_chart).
# "Missing / no evidence" values stay untiered (neutral): absence of evidence is
# not a cleaning defect. Only a failed invariant is critical.
STATUS_TIERS = {
    **dict.fromkeys(
        [
            "USABLE", "PARSED", "MAPPED", "UNCHANGED", "VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN",
            "MATCH", "NOT_OUTLIER", "TRUSTED_UNIQUE_POINT", "TRUSTED_SHARED_ADDRESS", "AVAILABLE",
            "CHECKED_NO_FLAG", "UNIQUE_FINGERPRINT", "VALID", "READY", "CONSISTENT", "PASS",
        ],
        "good",
    ),
    **dict.fromkeys(
        [
            "TOO_SHORT", "PARTIALLY_PARSED", "AMBIGUOUS", "UNMAPPED", "DISAGREEMENT", "REPARSED_ONLY",
            "PRICE_OUTLIER", "AREA_OUTLIER", "PRICE_OUTLIER_REVIEW", "AREA_OUTLIER_REVIEW",
            "POSSIBLE_DUPLICATE", "READY_WITH_FLAGS", "UNVERIFIABLE", "SHARED_POINT_CONFLICTING_ADDRESSES",
            "MISSING_PRICE", "MISSING_AREA",
        ],
        "warning",
    ),
    **dict.fromkeys(
        [
            "PRICE_AND_AREA_OUTLIER", "BOTH_OUTLIERS_REVIEW", "EXTREME_PRICE_PER_AREA_REVIEW",
            "REQUIRES_REVIEW", "UNRECOGNIZED_FORMAT", "UNKNOWN_LINEAGE",
        ],
        "serious",
    ),
    "FAIL": "critical",
}
