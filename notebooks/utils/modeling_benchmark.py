"""Leakage-safe methodology helpers for the RoomBeacon price benchmark."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score

TARGET = "price_model_value"
FULL_SAFE_FEATURES = ["area_value_clean", "source_code", "ward_current", "district_text_extracted", "province_text_extracted", "title_length"]
FORBIDDEN_PREDICTORS = {
    TARGET, "price_amount_clean", "price_amount", "price_raw", "price_per_area", "price_per_area_analysis",
    "price_per_area_audit", "price_reparsed", "reparsed_price", "target", "target_price",
    "rental_post_id", "source_listing_id", "duplicate_candidate_group", "group_key",
    "price_model_value", "price_target_model_value", "price_target_trust_status",
    "price_target_trust_reason", "price_target_trust_evidence",
}

__all__ = [
    "TARGET",
    "FULL_SAFE_FEATURES",
    "FORBIDDEN_PREDICTORS",
    "SplitResult",
    "TemporalFold",
    "build_feature_sets",
    "engineer_safe_features",
    "audit_features",
    "prepare_lightgbm_categories",
    "unique_price_bands",
    "lightgbm_gain_importance",
    "build_group_key",
    "group_aware_split",
    "build_expanding_group_time_folds",
    "assert_group_isolation",
    "assert_split_chronology",
    "add_train_only_area_band",
    "hierarchical_segment_median",
    "hierarchical_location_median",
    "regression_metrics",
    "summarize_development",
    "lock_candidate",
    "transform_target",
    "inverse_target",
]

@dataclass(frozen=True)
class SplitResult:
    labels: pd.Series
    strategy: str
    reason: str
    group_timestamps: pd.Series

@dataclass(frozen=True)
class TemporalFold:
    fold: int
    train_index: pd.Index
    validation_index: pd.Index
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    train_groups: int
    validation_groups: int

def build_feature_sets(columns: Iterable[str]) -> dict[str, list[str]]:
    available = set(columns)
    missing = sorted(set(FULL_SAFE_FEATURES) - available)
    if missing:
        raise ValueError(f"Canonical Silver is missing benchmark fields: {missing}")
    return {
        "F1 — AREA ONLY": ["area_value_clean"],
        "F2 — AREA + SOURCE": ["area_value_clean", "source_code"],
        "F3 — AREA + LOCATION": ["area_value_clean", "ward_current", "district_text_extracted"],
        "F4 — AREA + SOURCE + LOCATION": ["area_value_clean", "source_code", "ward_current", "district_text_extracted"],
        "F5 — FULL SAFE TABULAR": FULL_SAFE_FEATURES.copy(),
    }

def engineer_safe_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["title_length"] = result["title_clean"].astype("string").str.len().astype("Float64")
    return result

def audit_features(features: Iterable[str]) -> None:
    fields = list(features)
    violations = set(fields) & FORBIDDEN_PREDICTORS
    violations |= {field for field in fields if field.startswith("price_") or field.endswith("_price")}
    if violations:
        raise ValueError(f"Forbidden/leaking predictors: {sorted(violations)}")

def prepare_lightgbm_categories(
    train: pd.DataFrame,
    score: pd.DataFrame,
    columns: Iterable[str],
    return_vocabularies: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame] | tuple[pd.DataFrame, pd.DataFrame, dict[str, list[str]]]:
    """Apply train-defined categorical vocabularies with explicit unknown and missing levels."""
    fit, out, vocabularies = train.copy(), score.copy(), {}
    for column in columns:
        if column not in fit.columns or column not in out.columns:
            continue
        observed = fit[column].astype("string").fillna("__MISSING__")
        categories = sorted(observed.unique().tolist())
        if "__MISSING__" not in categories:
            categories.append("__MISSING__")
        if "__UNKNOWN__" not in categories:
            categories.append("__UNKNOWN__")
        vocabularies[column] = categories
        fit_values = observed.where(observed.isin(categories), "__UNKNOWN__")
        score_raw = out[column].astype("string").fillna("__MISSING__")
        score_values = score_raw.where(score_raw.isin(categories), "__UNKNOWN__")
        fit[column] = pd.Categorical(fit_values, categories=categories)
        out[column] = pd.Categorical(score_values, categories=categories)
    if return_vocabularies:
        return fit, out, vocabularies
    return fit, out

def unique_price_bands(reference: Iterable[float], values: Iterable[float], quantiles: tuple[float, ...] = (.50, .75, .95, .99)) -> tuple[pd.Categorical, np.ndarray]:
    """Build non-zero-width diagnostic bands from reference targets only."""
    ref = pd.Series(reference, dtype=float).dropna()
    internal = np.unique(ref.quantile(list(quantiles)).to_numpy(float))
    edges = np.concatenate(([-np.inf], internal, [np.inf]))
    if not np.all(np.diff(edges) > 0):
        raise AssertionError("Price-band edges must be strictly increasing")
    labels = [f"Band {i + 1}" for i in range(len(edges) - 1)]
    return pd.cut(pd.Series(values, dtype=float), edges, labels=labels, include_lowest=True), edges

def lightgbm_gain_importance(model, features: Iterable[str]) -> pd.DataFrame:
    """Return supported gain importance for a fitted LightGBM sklearn model."""
    booster = getattr(model, "booster_", None)
    if booster is None:
        raise ValueError("A fitted LightGBM model is required")
    names = list(booster.feature_name())
    gains = booster.feature_importance(importance_type="gain")
    splits = booster.feature_importance(importance_type="split")
    if len(names) != len(gains):
        names = list(features)
    result = pd.DataFrame({"Feature": names, "Gain": gains, "Split Count": splits})
    total = result["Gain"].sum()
    result["Gain %"] = np.where(total > 0, result["Gain"] / total * 100, 0.0)
    return result.sort_values("Gain", ascending=False).reset_index(drop=True)

def build_group_key(frame: pd.DataFrame) -> pd.Series:
    duplicate = frame["duplicate_candidate_group"].astype("string")
    listing = frame["rental_post_id"].astype("string")
    has_group = duplicate.notna() & duplicate.str.strip().ne("")
    return pd.Series(np.where(has_group, "duplicate:" + duplicate.fillna(""), "listing:" + listing), index=frame.index, dtype="string", name="group_key")

def _ordered_groups(frame: pd.DataFrame, group_key: pd.Series, timestamp_column: str) -> pd.Series:
    table = pd.DataFrame({"group": group_key, "timestamp": pd.to_datetime(frame[timestamp_column], errors="coerce")})
    representative = table.groupby("group", sort=False)["timestamp"].max()
    if representative.isna().any():
        raise ValueError("Strict chronological splitting requires timestamps for every group")
    ordered = representative.rename("timestamp").reset_index().sort_values(["timestamp", "group"], kind="mergesort")
    return ordered.set_index("group")["timestamp"]

def _move_cut_past_ties(values: np.ndarray, cut: int) -> int:
    cut = min(max(1, cut), len(values) - 1)
    while cut < len(values) - 1 and values[cut - 1] == values[cut]:
        cut += 1
    return cut

def group_aware_split(frame: pd.DataFrame, group_key: pd.Series, timestamp_column: str = "latest_observed_at", seed: int = 42, train_fraction: float = .70, validation_fraction: float = .15) -> SplitResult:
    """Split whole groups chronologically; equal timestamps never cross boundaries."""
    del seed
    ordered = _ordered_groups(frame, group_key, timestamp_column)
    if len(ordered) < 20:
        raise ValueError("At least 20 groups are required")
    values = ordered.to_numpy()
    train_end = _move_cut_past_ties(values, int(len(ordered) * train_fraction))
    validation_end = _move_cut_past_ties(values, int(len(ordered) * (train_fraction + validation_fraction)))
    if validation_end <= train_end or validation_end >= len(ordered):
        raise ValueError("Timestamp ties leave no independent validation/test groups")
    mapping = pd.Series("TEST", index=ordered.index, dtype="string")
    mapping.iloc[:train_end] = "TRAIN"
    mapping.iloc[train_end:validation_end] = "VALIDATION"
    labels = group_key.map(mapping).astype("string")
    assert_group_isolation(group_key, labels)
    return SplitResult(labels, "GROUP_LEVEL_CHRONOLOGICAL_70_15_15", "Whole duplicate groups ordered by representative max latest_observed_at; equal representative timestamps kept together. This does not claim row-level temporal isolation.", ordered)

def build_expanding_group_time_folds(frame: pd.DataFrame, group_key: pd.Series, timestamp_column: str = "latest_observed_at", n_splits: int = 3, initial_fraction: float = .55) -> list[TemporalFold]:
    ordered = _ordered_groups(frame, group_key, timestamp_column)
    n = len(ordered); initial = int(n * initial_fraction); block = max(1, (n - initial) // n_splits)
    folds = []
    for number in range(1, n_splits + 1):
        train_end = _move_cut_past_ties(ordered.to_numpy(), initial + (number - 1) * block)
        score_end = n if number == n_splits else _move_cut_past_ties(ordered.to_numpy(), min(n - 1, train_end + block))
        train_groups, score_groups = ordered.index[:train_end], ordered.index[train_end:score_end]
        if not len(score_groups):
            raise ValueError("Empty chronological validation fold")
        train_times, score_times = ordered.loc[train_groups], ordered.loc[score_groups]
        if train_times.max() >= score_times.min():
            raise AssertionError("Development fold is not strictly chronological")
        folds.append(TemporalFold(number, frame.index[group_key.isin(train_groups)], frame.index[group_key.isin(score_groups)], train_times.min(), train_times.max(), score_times.min(), score_times.max(), len(train_groups), len(score_groups)))
    return folds

def assert_group_isolation(group_key: pd.Series, labels: pd.Series) -> None:
    memberships = pd.DataFrame({"group": group_key, "split": labels}).groupby("group")["split"].nunique()
    if not memberships.eq(1).all():
        raise AssertionError("Duplicate/repost group leakage across partitions")

def assert_split_chronology(frame: pd.DataFrame, group_key: pd.Series, split: SplitResult) -> None:
    by_group = pd.DataFrame({"group": group_key, "label": split.labels}).groupby("group")["label"].first()
    times = split.group_timestamps
    if not (times.loc[by_group.eq("TRAIN")].max() < times.loc[by_group.eq("VALIDATION")].min() < times.loc[by_group.eq("TEST")].min()):
        raise AssertionError("Split boundaries are not strictly chronological")

def add_train_only_area_band(train: pd.DataFrame, score: pd.DataFrame, bins: int = 6) -> tuple[pd.Series, pd.Series, np.ndarray]:
    numeric = pd.to_numeric(train["area_value_clean"], errors="coerce")
    edges = np.unique(numeric.dropna().quantile(np.linspace(0, 1, bins + 1)).to_numpy(float))
    if len(edges) < 3:
        edges = np.array([-np.inf, np.inf])
    else:
        edges[0], edges[-1] = -np.inf, np.inf
    train_band = pd.cut(numeric, edges, include_lowest=True).astype("string").fillna("__MISSING__")
    score_band = pd.cut(pd.to_numeric(score["area_value_clean"], errors="coerce"), edges, include_lowest=True).astype("string").fillna("__MISSING__")
    return train_band, score_band, edges

def hierarchical_segment_median(train: pd.DataFrame, score: pd.DataFrame, target: str = TARGET, min_rows: int = 8) -> np.ndarray:
    target = target if target in train.columns else "price_amount_clean"
    fit, out = train.copy(), score.copy()
    fit["_area_band"], out["_area_band"], _ = add_train_only_area_band(train, score)
    prediction = pd.Series(np.nan, index=out.index, dtype=float)
    for keys in [["ward_current", "_area_band", "source_code"], ["district_text_extracted", "_area_band"], ["_area_band"]]:
        stats = fit.groupby(keys, dropna=False)[target].agg(["median", "count"]).reset_index()
        stats = stats.loc[stats["count"] >= min_rows, keys + ["median"]]
        lookup = out[keys].merge(stats, on=keys, how="left")["median"]; lookup.index = out.index
        prediction = prediction.fillna(lookup)
    return prediction.fillna(float(fit[target].median())).to_numpy(float)

def hierarchical_location_median(train: pd.DataFrame, score: pd.DataFrame, target: str = TARGET, ward_column: str = "ward_current", district_column: str = "district_text_extracted", min_ward_rows: int = 5, min_district_rows: int = 10) -> np.ndarray:
    target = target if target in train.columns else "price_amount_clean"
    global_median = float(train[target].median())
    ward = train.groupby(ward_column, dropna=True)[target].agg(["median", "count"])
    district = train.groupby(district_column, dropna=True)[target].agg(["median", "count"])
    return score[ward_column].map(ward.loc[ward["count"] >= min_ward_rows, "median"]).fillna(score[district_column].map(district.loc[district["count"] >= min_district_rows, "median"])).fillna(global_median).to_numpy(float)

def regression_metrics(actual: Iterable[float], predicted: Iterable[float]) -> dict[str, float | int]:
    y_true, y_pred = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if np.any(y_true < 0):
        raise ValueError("RMSLE requires non-negative targets")
    clipped = np.clip(y_pred, 0, None)
    return {"MAE": float(mean_absolute_error(y_true, y_pred)), "Median AE": float(median_absolute_error(y_true, y_pred)), "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))), "RMSLE": float(np.sqrt(np.mean((np.log1p(clipped) - np.log1p(y_true)) ** 2))), "R²": float(r2_score(y_true, y_pred)), "Negative Predictions": int(np.sum(y_pred < 0))}

def summarize_development(results: pd.DataFrame) -> pd.DataFrame:
    keys = ["Model", "Target Transform", "Feature Set", "Parameters"]
    return results.groupby(keys, dropna=False).agg(Folds=("Fold", "nunique"), MAE_Mean=("MAE", "mean"), MAE_Median=("MAE", "median"), MAE_Std=("MAE", "std"), MedianAE_Mean=("Median AE", "mean"), RMSLE_Mean=("RMSLE", "mean"), Fit_Time_Mean=("Fit Time", "mean")).reset_index().sort_values(["MAE_Mean", "MAE_Median", "MAE_Std", "MedianAE_Mean", "RMSLE_Mean"])

def lock_candidate(summary: pd.DataFrame, complexity_order: dict[str, int], tolerance: float = .01) -> pd.Series:
    forbidden = [c for c in summary.columns if "test" in c.lower()]
    if forbidden:
        raise ValueError(f"TEST evidence cannot enter candidate selection: {forbidden}")
    best = float(summary["MAE_Mean"].min())
    near = summary.loc[summary["MAE_Mean"] <= best * (1 + tolerance)].copy()
    near["Complexity"] = near["Model"].map(complexity_order).fillna(999)
    return near.sort_values(["Complexity", "MAE_Std", "MAE_Median", "MedianAE_Mean", "RMSLE_Mean", "Fit_Time_Mean"]).iloc[0]

def transform_target(values: Iterable[float], transform: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if transform == "RAW": return array.copy()
    if transform == "LOG1P":
        if np.any(array < 0): raise ValueError("LOG1P target transform requires non-negative values")
        return np.log1p(array)
    raise ValueError(f"Unknown target transform: {transform}")

def inverse_target(values: Iterable[float], transform: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if transform == "RAW": return array.copy()
    if transform == "LOG1P": return np.expm1(array)
    raise ValueError(f"Unknown target transform: {transform}")
