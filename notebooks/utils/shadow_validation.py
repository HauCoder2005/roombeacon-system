"""Reusable, leakage-safe shadow inference and monitoring for RoomBeacon.

This module deliberately contains no model fitting or candidate-selection logic.
Notebook 04 owns training and model selection; Notebook 06 only resolves a locked
artifact, prepares its exact feature contract, predicts, evaluates, and persists
append-only monitoring evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score

from notebooks.utils.modeling_benchmark import (
    audit_features,
    build_inference_eligibility,
    build_modeling_eligibility,
    eligibility_funnel,
    engineer_safe_features,
    inference_eligibility_funnel,
    inverse_target,
)


F4_FEATURE_SET = "F4 — AREA + SOURCE + LOCATION"
F4_FEATURES = (
    "area_value_clean",
    "source_code",
    "ward_current",
    "district_text_extracted",
)
CATEGORICAL_FEATURES = (
    "source_code",
    "ward_current",
    "district_text_extracted",
)
ID_COLUMN = "rental_post_id"
TIMESTAMP_COLUMN = "latest_observed_at"
TARGET_COLUMN = "price_model_value"
PREDICTION_COLUMN = "predicted_monthly_rent"
HISTORICAL_DRY_RUN = "HISTORICAL_DRY_RUN"
FUTURE_SHADOW = "FUTURE_SHADOW"

CHAMPION_MODEL_FILENAME = "champion_model.joblib"
CHAMPION_METADATA_FILENAME = "champion_metadata.json"
REFERENCE_PROFILE_FILENAME = "champion_reference_profile.json"

__all__ = [
    "F4_FEATURE_SET",
    "F4_FEATURES",
    "CATEGORICAL_FEATURES",
    "ID_COLUMN",
    "TIMESTAMP_COLUMN",
    "TARGET_COLUMN",
    "PREDICTION_COLUMN",
    "HISTORICAL_DRY_RUN",
    "FUTURE_SHADOW",
    "CHAMPION_MODEL_FILENAME",
    "CHAMPION_METADATA_FILENAME",
    "REFERENCE_PROFILE_FILENAME",
    "LoadedChampion",
    "SchemaValidationResult",
    "ShadowPopulation",
    "EvaluationPopulation",
    "ValidationModeDecision",
    "file_sha256",
    "deterministic_model_id",
    "build_reference_profile",
    "persist_champion_artifact",
    "resolve_champion_artifact",
    "validate_shadow_schema",
    "prepare_shadow_population",
    "prepare_evaluation_population",
    "build_inference_matrix",
    "classify_validation_mode",
    "predict_shadow",
    "attach_actuals_for_evaluation",
    "evaluate_shadow_predictions",
    "prediction_distribution",
    "prediction_sanity_report",
    "category_drift_report",
    "feature_drift_report",
    "price_bucket_diagnostics",
    "area_bucket_diagnostics",
    "source_diagnostics",
    "ward_diagnostics",
    "district_diagnostics",
    "missing_location_summary",
    "location_diagnostics",
    "intent_diagnostics",
    "temporal_diagnostics",
    "prediction_compression_report",
    "build_readiness_scorecard",
    "make_shadow_run_id",
    "persist_shadow_run",
]



@dataclass(frozen=True)
class LoadedChampion:
    model: Any
    metadata: dict[str, Any]
    reference_profile: dict[str, Any]
    artifact_path: Path
    metadata_path: Path
    reference_profile_path: Path


@dataclass(frozen=True)
class SchemaValidationResult:
    status: pd.Series
    reason: pd.Series
    ready_mask: pd.Series
    summary: pd.DataFrame


@dataclass(frozen=True)
class ShadowPopulation:
    all_rows: pd.DataFrame
    ready_rows: pd.DataFrame
    funnel: pd.DataFrame
    schema_summary: pd.DataFrame


@dataclass(frozen=True)
class EvaluationPopulation:
    all_predictions: pd.DataFrame
    evaluation_rows: pd.DataFrame
    evaluation_predictions: pd.DataFrame
    funnel: pd.DataFrame
    exclusion_summary: pd.DataFrame


@dataclass(frozen=True)
class ValidationModeDecision:
    mode: str
    counts_toward_production: bool
    reason: str
    evidence_cutoff: str | None
    min_observed_at: str | None
    max_observed_at: str | None


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _model_slug(model_family: str) -> str:
    known = {"LightGBM Regressor": "lgbm"}
    return known.get(model_family, re.sub(r"[^a-z0-9]+", "-", model_family.lower()).strip("-"))


def deterministic_model_id(
    model_family: str,
    feature_set: str,
    target_transform: str,
    artifact_sha256: str,
) -> str:
    feature_slug = "f4" if feature_set == F4_FEATURE_SET else re.sub(
        r"[^a-z0-9]+", "-", feature_set.lower()
    ).strip("-")
    return (
        f"roombeacon-price-{_model_slug(model_family)}-{feature_slug}-"
        f"{target_transform.lower()}-{artifact_sha256[:12]}"
    )


def _validate_f4_contract(metadata: Mapping[str, Any]) -> list[str]:
    feature_set = metadata.get("feature_set")
    features = list(metadata.get("feature_names", []))
    audit_features(features)
    if feature_set != F4_FEATURE_SET or features != list(F4_FEATURES):
        raise ValueError(
            "F4 feature contract mismatch: expected "
            f"{F4_FEATURE_SET!r} / {list(F4_FEATURES)!r}, got "
            f"{feature_set!r} / {features!r}"
        )
    return features


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    series = pd.to_numeric(pd.Series(values), errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if series.empty:
        return {
            "count": 0,
            "min": None,
            "p01": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    quantiles = series.quantile([.01, .25, .50, .75, .95, .99])
    return {
        "count": int(series.size),
        "min": float(series.min()),
        "p01": float(quantiles.loc[.01]),
        "p25": float(quantiles.loc[.25]),
        "median": float(quantiles.loc[.50]),
        "p75": float(quantiles.loc[.75]),
        "p95": float(quantiles.loc[.95]),
        "p99": float(quantiles.loc[.99]),
        "max": float(series.max()),
    }


def build_reference_profile(
    frame: pd.DataFrame,
    predictions: Iterable[float] | None = None,
    *,
    target_column: str = TARGET_COLUMN,
    population_name: str = "DEVELOPMENT",
    uses_test: bool = False,
    timestamp_column: str = TIMESTAMP_COLUMN,
) -> dict[str, Any]:
    """Build aggregate monitoring reference from a non-TEST population."""
    if uses_test or population_name.upper() == "TEST":
        raise ValueError("TEST data cannot be used as the champion reference profile")
    missing = sorted(set(F4_FEATURES) - set(frame.columns))
    if missing:
        raise ValueError(f"Reference population is missing F4 fields: {missing}")
    rows = len(frame)
    area = pd.to_numeric(frame["area_value_clean"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    area_quantiles = area.dropna().quantile([.05, .25, .50, .75, .95]) if area.notna().any() else pd.Series(dtype=float)
    numeric = {
        "area_value_clean": {
            "count": int(area.notna().sum()),
            "missing_pct": float(area.isna().mean() * 100) if rows else 0.0,
            "p05": float(area_quantiles.get(.05, np.nan)) if not area_quantiles.empty else None,
            "p25": float(area_quantiles.get(.25, np.nan)) if not area_quantiles.empty else None,
            "median": float(area_quantiles.get(.50, np.nan)) if not area_quantiles.empty else None,
            "p75": float(area_quantiles.get(.75, np.nan)) if not area_quantiles.empty else None,
            "p95": float(area_quantiles.get(.95, np.nan)) if not area_quantiles.empty else None,
        }
    }
    categorical: dict[str, dict[str, Any]] = {}
    for column in CATEGORICAL_FEATURES:
        values = frame[column].astype("string").fillna("__MISSING__")
        shares = values.value_counts(normalize=True, dropna=False).mul(100).sort_values(ascending=False)
        categorical[column] = {
            "category_count": int(values.loc[values.ne("__MISSING__")].nunique()),
            "missing_pct": float(values.eq("__MISSING__").mean() * 100) if rows else 0.0,
            "unknown_pct": float(values.eq("__UNKNOWN__").mean() * 100) if rows else 0.0,
            "distribution_pct": {str(key): float(value) for key, value in shares.items()},
        }
    observed = pd.to_datetime(frame.get(timestamp_column), errors="coerce")
    target = _distribution(frame[target_column]) if target_column in frame else None
    if target is not None:
        target = {
            "count": target["count"],
            "median": target["median"],
            "p95": target["p95"],
            "p99": target["p99"],
        }
    profile = {
        "schema_version": "1.0.0",
        "population": population_name,
        "uses_test": False,
        "row_count": int(rows),
        "min_observed_at": observed.min().isoformat() if observed.notna().any() else None,
        "max_observed_at": observed.max().isoformat() if observed.notna().any() else None,
        "numeric": numeric,
        "categorical": categorical,
        "prediction": _distribution(predictions) if predictions is not None else None,
        "target": target,
    }
    return profile


def persist_champion_artifact(
    model: Any,
    artifact_dir: str | Path,
    *,
    model_family: str,
    target_transform: str,
    feature_set: str,
    feature_names: list[str],
    hyperparameters: Mapping[str, Any],
    random_seed: int,
    categorical_vocabularies: Mapping[str, list[str]],
    training_reference: Mapping[str, Any],
    expected_schema: Mapping[str, str],
    reference_profile: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Serialize an already-fitted locked champion and its inference contract."""
    contract = {"feature_set": feature_set, "feature_names": feature_names}
    _validate_f4_contract(contract)
    if model_family != "LightGBM Regressor" or target_transform != "RAW":
        raise ValueError("Locked champion must be LightGBM Regressor / RAW")
    if training_reference.get("uses_test") is not False:
        raise ValueError("Champion training reference must explicitly exclude TEST")
    if reference_profile.get("uses_test") is not False:
        raise ValueError("Champion reference profile must explicitly exclude TEST")

    output = Path(artifact_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifact_path = output / CHAMPION_MODEL_FILENAME
    temporary_path = output / f".{CHAMPION_MODEL_FILENAME}.tmp"
    joblib.dump(model, temporary_path)
    os.replace(temporary_path, artifact_path)
    artifact_hash = file_sha256(artifact_path)
    model_id = deterministic_model_id(model_family, feature_set, target_transform, artifact_hash)
    metadata = {
        "schema_version": "1.0.0",
        "model_id": model_id,
        "model_family": model_family,
        "model_class": f"{model.__class__.__module__}.{model.__class__.__name__}",
        "target_transform": target_transform,
        "feature_set": feature_set,
        "feature_names": list(feature_names),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "categorical_vocabularies": {key: list(value) for key, value in categorical_vocabularies.items()},
        "hyperparameters": dict(hyperparameters),
        "random_seed": int(random_seed),
        "expected_schema": dict(expected_schema),
        "training_reference": dict(training_reference),
        "artifact_path": CHAMPION_MODEL_FILENAME,
        "artifact_sha256": artifact_hash,
        "artifact_format": "joblib",
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
    }
    profile = dict(reference_profile)
    profile["model_id"] = model_id
    profile["artifact_sha256"] = artifact_hash
    _write_json(output / CHAMPION_METADATA_FILENAME, metadata)
    _write_json(output / REFERENCE_PROFILE_FILENAME, profile)
    return metadata


def _resolve_inside(base: Path, relative: str, label: str) -> Path:
    candidate = (base / relative).resolve()
    if base.resolve() not in candidate.parents and candidate != base.resolve():
        raise ValueError(f"{label} escapes benchmark artifact directory")
    if not candidate.is_file():
        raise FileNotFoundError(f"{label} not found: {candidate}")
    return candidate


def resolve_champion_artifact(benchmark_dir: str | Path) -> LoadedChampion:
    """Resolve and verify the locked LightGBM/RAW/F4 champion package."""
    base = Path(benchmark_dir)
    experiment_path = base / "experiment_metadata.json"
    if not experiment_path.is_file():
        raise FileNotFoundError(f"Benchmark metadata not found: {experiment_path}")
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    champion_pointer = experiment.get("champion")
    if not isinstance(champion_pointer, dict):
        raise FileNotFoundError("Benchmark metadata does not contain a serialized champion pointer")
    metadata_path = _resolve_inside(
        base,
        champion_pointer.get("metadata_path", CHAMPION_METADATA_FILENAME),
        "Champion metadata",
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pointer_artifact_path = champion_pointer.get("artifact_path")
    if pointer_artifact_path != metadata.get("artifact_path"):
        raise ValueError("Champion artifact path does not agree between experiment and champion metadata")
    artifact_path = _resolve_inside(base, metadata.get("artifact_path", ""), "Champion artifact")
    reference_path = _resolve_inside(
        base,
        champion_pointer.get("reference_profile_path", REFERENCE_PROFILE_FILENAME),
        "Champion reference profile",
    )
    reference = json.loads(reference_path.read_text(encoding="utf-8"))

    expected_pairs = {
        "model family": (experiment.get("locked_candidate"), metadata.get("model_family")),
        "target transform": (experiment.get("locked_transform"), metadata.get("target_transform")),
        "feature set": (experiment.get("selected_feature_set"), metadata.get("feature_set")),
        "hyperparameters": (experiment.get("locked_parameters"), metadata.get("hyperparameters")),
        "random seed": (experiment.get("seed"), metadata.get("random_seed")),
    }
    disagreements = [name for name, pair in expected_pairs.items() if pair[0] != pair[1]]
    if disagreements:
        raise ValueError(f"Champion metadata agreement failed for: {', '.join(disagreements)}")
    if metadata.get("model_family") != "LightGBM Regressor":
        raise ValueError("Champion model family is not the locked LightGBM Regressor")
    if metadata.get("target_transform") != "RAW":
        raise ValueError("Champion target transform is not RAW")
    _validate_f4_contract(metadata)
    if metadata.get("categorical_features") != list(CATEGORICAL_FEATURES):
        raise ValueError("Champion categorical feature contract disagreement")
    expected_schema = metadata.get("expected_schema", {})
    if list(expected_schema) != list(F4_FEATURES) or expected_schema.get("area_value_clean") != "numeric":
        raise ValueError("Champion expected schema does not agree with the ordered F4 contract")
    vocabularies = metadata.get("categorical_vocabularies", {})
    if set(vocabularies) != set(CATEGORICAL_FEATURES):
        raise ValueError("Champion category vocabularies do not cover the F4 categorical contract")
    for column in CATEGORICAL_FEATURES:
        if "__MISSING__" not in vocabularies[column] or "__UNKNOWN__" not in vocabularies[column]:
            raise ValueError(f"Champion category vocabulary lacks safe sentinels for {column}")

    observed_hash = file_sha256(artifact_path)
    expected_hash = metadata.get("artifact_sha256")
    if observed_hash != expected_hash or champion_pointer.get("artifact_sha256") != expected_hash:
        raise ValueError("Champion artifact SHA-256 does not agree with metadata")
    expected_id = deterministic_model_id(
        metadata["model_family"], metadata["feature_set"], metadata["target_transform"], observed_hash
    )
    if metadata.get("model_id") != expected_id or champion_pointer.get("model_id") != expected_id:
        raise ValueError("Champion model_id does not agree with the serialized artifact")

    model = joblib.load(artifact_path)
    actual_class = f"{model.__class__.__module__}.{model.__class__.__name__}"
    if actual_class != metadata.get("model_class") or model.__class__.__name__ != "LGBMRegressor":
        raise ValueError("Serialized champion class does not agree with champion metadata")
    booster = getattr(model, "booster_", None)
    if booster is None or list(booster.feature_name()) != list(F4_FEATURES):
        raise ValueError("Serialized champion feature names do not agree with the F4 contract")
    persisted_categories = getattr(booster, "pandas_categorical", None)
    expected_categories = [vocabularies[column] for column in CATEGORICAL_FEATURES]
    if persisted_categories is None or [list(values) for values in persisted_categories] != expected_categories:
        raise ValueError("Serialized champion category vocabularies disagree with metadata")
    actual_params = model.get_params()
    parameter_mismatch = {
        key: (value, actual_params.get(key))
        for key, value in metadata["hyperparameters"].items()
        if actual_params.get(key) != value
    }
    if parameter_mismatch:
        raise ValueError(f"Serialized champion parameters disagree with metadata: {parameter_mismatch}")
    if actual_params.get("random_state") != metadata.get("random_seed"):
        raise ValueError("Serialized champion random seed disagrees with metadata")
    if reference.get("uses_test") is not False or reference.get("population") != "DEVELOPMENT":
        raise ValueError("Champion reference must be development-only and must not use TEST")
    if reference.get("model_id") != expected_id or reference.get("artifact_sha256") != observed_hash:
        raise ValueError("Champion reference profile model_id disagreement")
    training_reference = metadata.get("training_reference", {})
    if training_reference.get("uses_test") is not False or not training_reference.get("evidence_cutoff"):
        raise ValueError("Champion training reference is incomplete or includes TEST")
    return LoadedChampion(model, metadata, reference, artifact_path, metadata_path, reference_path)


def validate_shadow_schema(frame: pd.DataFrame, metadata: Mapping[str, Any]) -> SchemaValidationResult:
    """Validate IDs/schema without dropping rows or exposing the target to the model."""
    features = _validate_f4_contract(metadata)
    required = [ID_COLUMN, TIMESTAMP_COLUMN, *features]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Shadow schema is missing required columns: {missing}")
    if frame[ID_COLUMN].isna().any():
        raise ValueError("Shadow schema contains missing rental_post_id")
    duplicates = frame[ID_COLUMN].duplicated(keep=False)
    if duplicates.any():
        examples = frame.loc[duplicates, ID_COLUMN].head(5).tolist()
        raise ValueError(f"Duplicate rental_post_id values are not supported: {examples}")

    status = pd.Series("READY_FOR_INFERENCE", index=frame.index, dtype="string", name="inference_status")
    reason = pd.Series("SCHEMA_VALID", index=frame.index, dtype="string", name="inference_reason")
    area = pd.to_numeric(frame["area_value_clean"], errors="coerce")
    invalid_area = area.isna() | ~np.isfinite(area) | area.le(0)
    status.loc[invalid_area] = "MISSING_REQUIRED_NUMERIC"
    reason.loc[invalid_area] = "area_value_clean must be finite and > 0"
    ready = status.eq("READY_FOR_INFERENCE")
    summary = (
        pd.DataFrame({"Status": status, "Reason": reason})
        .groupby(["Status", "Reason"], dropna=False)
        .size()
        .rename("Rows")
        .reset_index()
        .sort_values(["Status", "Rows"], ascending=[True, False])
        .reset_index(drop=True)
    )
    if len(status) != len(frame) or int(ready.sum()) + int((~ready).sum()) != len(frame):
        raise AssertionError("Schema validation did not preserve every input row")
    return SchemaValidationResult(status, reason, ready, summary)


def _eligibility_reason(frame: pd.DataFrame, masks: Any) -> pd.Series:
    reason = pd.Series("MODEL_ELIGIBLE", index=frame.index, dtype="string")
    reason.loc[~masks.numeric_target_candidate] = "NO_NUMERIC_TARGET_CANDIDATE"
    reason.loc[masks.numeric_target_candidate & ~masks.lineage_trusted] = "TARGET_LINEAGE_NOT_TRUSTED"
    reason.loc[masks.lineage_trusted & ~masks.semantic_target_supported] = "PRICE_SEMANTIC_NOT_SUPPORTED"
    reason.loc[masks.semantic_target_supported & ~masks.area_supported] = "AREA_NOT_SUPPORTED"
    reason.loc[masks.area_supported & ~masks.rental_compatible] = "NOT_RENTAL_COMPATIBLE"
    return reason


def _inference_eligibility_reason(frame: pd.DataFrame, masks: Any) -> pd.Series:
    reason = pd.Series("INFERENCE_ELIGIBLE", index=frame.index, dtype="string")
    reason.loc[~masks.area_supported] = "AREA_NOT_SUPPORTED"
    reason.loc[masks.area_supported & ~masks.rental_compatible] = "NOT_RENTAL_COMPATIBLE"
    return reason


def prepare_shadow_population(
    silver: pd.DataFrame,
    metadata: Mapping[str, Any],
    *,
    policy: str = "PERMISSIVE",
) -> ShadowPopulation:
    """Apply the shared target-free inference contract, then schema validation."""
    prepared = engineer_safe_features(silver) if "title_clean" in silver else silver.copy()
    if prepared[ID_COLUMN].duplicated(keep=False).any():
        raise ValueError("Duplicate rental_post_id values are not supported")
    masks = build_inference_eligibility(prepared, policy=policy)
    reasons = _inference_eligibility_reason(prepared, masks)
    all_rows = prepared.copy()
    all_rows["inference_status"] = "UNSUPPORTED"
    all_rows["inference_reason"] = reasons
    eligible = prepared.loc[masks.final_eligible].copy()
    schema = validate_shadow_schema(eligible, metadata)
    all_rows.loc[eligible.index, "inference_status"] = schema.status
    all_rows.loc[eligible.index, "inference_reason"] = schema.reason
    ready_index = schema.ready_mask.index[schema.ready_mask]
    ready_rows = prepared.loc[ready_index].copy()
    funnel = inference_eligibility_funnel(masks)
    funnel = pd.concat(
        [
            funnel,
            pd.DataFrame(
                [{
                    "Stage": "Inference-ready",
                    "Rows": len(ready_rows),
                    "Removed / reviewed": int(masks.final_eligible.sum()) - len(ready_rows),
                    "Percent of Silver": len(ready_rows) / len(prepared) * 100 if len(prepared) else 0.0,
                    "Policy": policy,
                }]
            ),
        ],
        ignore_index=True,
    )
    if len(all_rows) != len(silver) or all_rows["inference_status"].isna().any():
        raise AssertionError("Shadow population lost or failed to classify Silver rows")
    return ShadowPopulation(all_rows, ready_rows, funnel, schema.summary)


def prepare_evaluation_population(
    predictions: pd.DataFrame,
    silver: pd.DataFrame,
    *,
    policy: str = "PERMISSIVE",
    target_column: str = TARGET_COLUMN,
) -> EvaluationPopulation:
    """Apply full target trust only after predictions already exist.

    The returned ``all_predictions`` preserves every inference row. Trusted
    actuals are attached only to the full Notebook 04 model-eligible subset;
    unsupported rows retain a missing actual and remain auditable.
    """
    required_prediction = {ID_COLUMN, PREDICTION_COLUMN}
    missing_prediction = sorted(required_prediction - set(predictions.columns))
    if missing_prediction:
        raise ValueError(f"Post-inference evaluation is missing fields: {missing_prediction}")
    if predictions[ID_COLUMN].duplicated().any():
        raise ValueError("Post-inference evaluation requires unique prediction IDs")
    if silver[ID_COLUMN].duplicated().any():
        raise ValueError("Post-inference evaluation requires unique Silver IDs")
    masks = build_modeling_eligibility(silver, policy=policy)
    eligible_rows = silver.loc[masks.final_eligible].copy()
    predicted_ids = set(predictions[ID_COLUMN].tolist())
    missing_eligible_ids = [
        value for value in eligible_rows[ID_COLUMN].tolist() if value not in predicted_ids
    ]
    if missing_eligible_ids:
        raise AssertionError(
            "Model-eligible rows are missing predictions: "
            f"{missing_eligible_ids[:5]}"
        )

    result = predictions.copy()
    actual_lookup = eligible_rows.set_index(ID_COLUMN)[target_column]
    result["actual_monthly_rent"] = pd.to_numeric(
        result[ID_COLUMN].map(actual_lookup), errors="coerce"
    )
    result["residual"] = result[PREDICTION_COLUMN] - result["actual_monthly_rent"]
    result["absolute_error"] = result["residual"].abs()
    if "listing_intent" in silver:
        result["listing_intent"] = result[ID_COLUMN].map(
            silver.set_index(ID_COLUMN)["listing_intent"]
        )
    eligible_ids = set(eligible_rows[ID_COLUMN].tolist())
    evaluation_predictions = result.loc[result[ID_COLUMN].isin(eligible_ids)].copy()
    if evaluation_predictions[ID_COLUMN].tolist() != [
        value for value in predictions[ID_COLUMN].tolist() if value in eligible_ids
    ]:
        raise AssertionError("Post-inference evaluation reordered prediction IDs")
    reasons = _eligibility_reason(silver, masks)
    exclusion_summary = (
        reasons.rename("Reason")
        .to_frame()
        .groupby("Reason", dropna=False)
        .size()
        .rename("Rows")
        .reset_index()
        .sort_values("Rows", ascending=False)
        .reset_index(drop=True)
    )
    return EvaluationPopulation(
        result,
        eligible_rows,
        evaluation_predictions,
        eligibility_funnel(masks),
        exclusion_summary,
    )


def build_inference_matrix(frame: pd.DataFrame, metadata: Mapping[str, Any]) -> pd.DataFrame:
    """Build the exact target-free F4 matrix with persisted category vocabularies."""
    features = _validate_f4_contract(metadata)
    missing = sorted(set(features) - set(frame.columns))
    if missing:
        raise ValueError(f"Inference frame is missing F4 features: {missing}")
    matrix = frame.loc[:, features].copy()
    matrix["area_value_clean"] = pd.to_numeric(matrix["area_value_clean"], errors="coerce").astype(float)
    numeric = matrix["area_value_clean"]
    if numeric.isna().any() or (~np.isfinite(numeric)).any() or numeric.le(0).any():
        raise ValueError("Inference matrix contains invalid area_value_clean")
    vocabularies = metadata.get("categorical_vocabularies", {})
    for column in CATEGORICAL_FEATURES:
        categories = list(vocabularies.get(column, []))
        if "__MISSING__" not in categories or "__UNKNOWN__" not in categories:
            raise ValueError(f"Champion metadata lacks safe category sentinels for {column}")
        raw = matrix[column].astype("string").fillna("__MISSING__")
        mapped = raw.where(raw.isin(categories), "__UNKNOWN__")
        matrix[column] = pd.Categorical(mapped, categories=categories)
    if matrix.columns.tolist() != features or len(matrix) != len(frame):
        raise AssertionError("Inference matrix did not preserve the F4 column/row contract")
    if TARGET_COLUMN in matrix.columns:
        raise AssertionError("Actual target reached the inference matrix")
    return matrix


def classify_validation_mode(
    observed_at: Iterable[Any],
    evidence_cutoff: Any,
) -> ValidationModeDecision:
    """Classify conservatively; only an entirely post-cutoff batch is future evidence."""
    observed = pd.to_datetime(pd.Series(observed_at), errors="coerce", utc=True)
    cutoff = pd.to_datetime(evidence_cutoff, errors="coerce", utc=True)
    valid = observed.dropna()
    minimum = valid.min().isoformat() if not valid.empty else None
    maximum = valid.max().isoformat() if not valid.empty else None
    cutoff_text = cutoff.isoformat() if not pd.isna(cutoff) else None
    if pd.isna(cutoff):
        return ValidationModeDecision(
            HISTORICAL_DRY_RUN, False, "Missing or invalid champion evidence cutoff", None, minimum, maximum
        )
    if len(valid) != len(observed) or valid.empty:
        return ValidationModeDecision(
            HISTORICAL_DRY_RUN,
            False,
            "Missing observation timestamps prevent future-evidence classification",
            cutoff_text,
            minimum,
            maximum,
        )
    if bool(valid.gt(cutoff).all()):
        return ValidationModeDecision(
            FUTURE_SHADOW,
            True,
            "Every observation is strictly after the recorded model-lock evidence cutoff",
            cutoff_text,
            minimum,
            maximum,
        )
    return ValidationModeDecision(
        HISTORICAL_DRY_RUN,
        False,
        "Batch is historical or mixed relative to the model-lock evidence cutoff",
        cutoff_text,
        minimum,
        maximum,
    )


def predict_shadow(
    model: Any,
    frame: pd.DataFrame,
    metadata: Mapping[str, Any],
    validation_mode: str,
    inference_timestamp: str | None = None,
) -> pd.DataFrame:
    """Predict from F4 only; actual price is never passed to the model."""
    if validation_mode not in {HISTORICAL_DRY_RUN, FUTURE_SHADOW}:
        raise ValueError(f"Unsupported validation mode: {validation_mode}")
    if frame[ID_COLUMN].duplicated().any():
        raise ValueError("Duplicate prediction IDs are not supported")
    matrix = build_inference_matrix(frame, metadata)
    raw_prediction = np.asarray(model.predict(matrix), dtype=float)
    prediction = inverse_target(raw_prediction, metadata.get("target_transform", "RAW"))
    if len(prediction) != len(frame):
        raise AssertionError("Prediction count does not match inference-ready rows")
    if not np.isfinite(prediction).all():
        raise AssertionError("Predictions contain NaN or infinite values")
    if np.any(prediction < 0):
        raise AssertionError("Predictions contain negative monthly rent")
    timestamp = inference_timestamp or datetime.now(timezone.utc).isoformat()
    output = frame.loc[:, [ID_COLUMN, TIMESTAMP_COLUMN, *F4_FEATURES]].copy().reset_index(drop=True)
    output = output.rename(columns={TIMESTAMP_COLUMN: "observed_at"})
    output[PREDICTION_COLUMN] = prediction
    output["model_version"] = metadata["model_id"]
    output["model_id"] = metadata["model_id"]
    output["validation_mode"] = validation_mode
    output["inference_timestamp"] = timestamp
    if output[ID_COLUMN].tolist() != frame[ID_COLUMN].tolist():
        raise AssertionError("Prediction output IDs were reordered or misaligned")
    return output


def attach_actuals_for_evaluation(
    predictions: pd.DataFrame,
    source: pd.DataFrame,
    *,
    target_column: str = TARGET_COLUMN,
) -> pd.DataFrame:
    """Join actuals by preserved ID only after inference is complete."""
    if target_column not in source:
        return predictions.copy()
    if source[ID_COLUMN].duplicated().any() or predictions[ID_COLUMN].duplicated().any():
        raise ValueError("Evaluation join requires unique rental_post_id values")
    actual = source.set_index(ID_COLUMN)[target_column]
    result = predictions.copy()
    result["actual_monthly_rent"] = pd.to_numeric(
        result[ID_COLUMN].map(actual), errors="coerce"
    )
    result["residual"] = result[PREDICTION_COLUMN] - result["actual_monthly_rent"]
    result["absolute_error"] = result["residual"].abs()
    return result


def evaluate_shadow_predictions(frame: pd.DataFrame) -> dict[str, float | int]:
    required = {"actual_monthly_rent", PREDICTION_COLUMN}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Evaluation requires post-inference fields: {missing}")
    actual = pd.to_numeric(frame["actual_monthly_rent"], errors="coerce")
    predicted = pd.to_numeric(frame[PREDICTION_COLUMN], errors="coerce")
    valid = actual.notna() & predicted.notna() & np.isfinite(actual) & np.isfinite(predicted) & actual.ge(0)
    if not valid.any():
        return {"Rows": 0}
    y = actual.loc[valid].to_numpy(float)
    p = predicted.loc[valid].to_numpy(float)
    delta = p - y
    return {
        "Rows": int(valid.sum()),
        "MAE": float(mean_absolute_error(y, p)),
        "MedianAE": float(median_absolute_error(y, p)),
        "RMSE": float(np.sqrt(mean_squared_error(y, p))),
        "RMSLE": float(np.sqrt(np.mean((np.log1p(np.clip(p, 0, None)) - np.log1p(y)) ** 2))),
        "R²": float(r2_score(y, p)) if len(y) > 1 else float("nan"),
        "Signed Bias": float(delta.mean()),
        "Underprediction %": float(np.mean(p < y) * 100),
        "Overprediction %": float(np.mean(p > y) * 100),
        "Exact Match %": float(np.mean(p == y) * 100),
    }


def prediction_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    values = frame[PREDICTION_COLUMN] if PREDICTION_COLUMN in frame else frame
    return pd.DataFrame([_distribution(values)])


def prediction_sanity_report(predictions: pd.DataFrame, expected_rows: int) -> pd.DataFrame:
    values = pd.to_numeric(predictions[PREDICTION_COLUMN], errors="coerce")
    checks = [
        ("Prediction count matches inference-ready rows", len(predictions) == expected_rows),
        ("Prediction IDs are unique", not predictions[ID_COLUMN].duplicated().any()),
        ("No missing predictions", values.notna().all()),
        ("All predictions are finite", np.isfinite(values).all()),
        ("No negative predictions", values.ge(0).all()),
    ]
    return pd.DataFrame(
        [{"Check": name, "Status": "PASS" if bool(passed) else "FAIL"} for name, passed in checks]
    )


def category_drift_report(shadow: pd.DataFrame, reference_profile: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in CATEGORICAL_FEATURES:
        reference = reference_profile["categorical"][column]
        distribution = reference.get("distribution_pct", {})
        known = set(distribution)
        raw = shadow[column].astype("string").fillna("__MISSING__")
        unseen_mask = ~raw.isin(known)
        unseen_values = sorted(raw.loc[unseen_mask].dropna().unique().tolist())
        rows.append(
            {
                "Feature": column,
                "Reference Category Count": int(reference.get("category_count", 0)),
                "Shadow Category Count": int(raw.loc[raw.ne("__MISSING__")].nunique()),
                "Unseen Category Count": len(unseen_values),
                "Unseen Categories": json.dumps(unseen_values, ensure_ascii=False),
                "Unseen Rows": int(unseen_mask.sum()),
                "Unseen Row %": float(unseen_mask.mean() * 100) if len(raw) else 0.0,
                "Reference Missing %": float(reference.get("missing_pct", 0.0)),
                "Shadow Missing %": float(raw.eq("__MISSING__").mean() * 100) if len(raw) else 0.0,
                "Missing Shift pp": (
                    float(raw.eq("__MISSING__").mean() * 100) - float(reference.get("missing_pct", 0.0))
                    if len(raw)
                    else -float(reference.get("missing_pct", 0.0))
                ),
            }
        )
    return pd.DataFrame(rows)


def feature_drift_report(
    shadow: pd.DataFrame,
    reference_profile: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return interpretable numeric and categorical-share drift tables."""
    reference_area = reference_profile["numeric"]["area_value_clean"]
    area = pd.to_numeric(shadow["area_value_clean"], errors="coerce").replace([np.inf, -np.inf], np.nan)
    quantiles = area.dropna().quantile([.25, .50, .75, .95]) if area.notna().any() else pd.Series(dtype=float)
    shadow_median = float(quantiles.get(.50, np.nan)) if not quantiles.empty else np.nan
    shadow_iqr = float(quantiles.get(.75, np.nan) - quantiles.get(.25, np.nan)) if not quantiles.empty else np.nan
    reference_iqr = float(reference_area["p75"] - reference_area["p25"])
    shadow_p95 = float(quantiles.get(.95, np.nan)) if not quantiles.empty else np.nan
    shadow_missing = float(area.isna().mean() * 100) if len(area) else 0.0
    numeric = pd.DataFrame(
        [{
            "Feature": "area_value_clean",
            "Reference Median": reference_area["median"],
            "Shadow Median": shadow_median,
            "Median Shift": shadow_median - reference_area["median"],
            "Reference IQR": reference_iqr,
            "Shadow IQR": shadow_iqr,
            "IQR Shift": shadow_iqr - reference_iqr,
            "Reference P95": reference_area["p95"],
            "Shadow P95": shadow_p95,
            "P95 Shift": shadow_p95 - reference_area["p95"],
            "Reference Missing %": reference_area["missing_pct"],
            "Shadow Missing %": shadow_missing,
            "Missing Shift pp": shadow_missing - reference_area["missing_pct"],
        }]
    )
    share_rows: list[dict[str, Any]] = []
    for column in CATEGORICAL_FEATURES:
        values = shadow[column].astype("string").fillna("__MISSING__")
        shadow_shares = values.value_counts(normalize=True).mul(100).to_dict()
        reference_shares = reference_profile["categorical"][column]["distribution_pct"]
        for category in sorted(set(reference_shares) | set(shadow_shares)):
            reference_share = float(reference_shares.get(category, 0.0))
            shadow_share = float(shadow_shares.get(category, 0.0))
            share_rows.append(
                {
                    "Feature": column,
                    "Category": category,
                    "Reference Share %": reference_share,
                    "Shadow Share %": shadow_share,
                    "Delta pp": shadow_share - reference_share,
                    "Shadow Rows": int(values.eq(category).sum()),
                }
            )
    return numeric, pd.DataFrame(share_rows)


def _group_diagnostics(
    frame: pd.DataFrame,
    groups: pd.Series,
    *,
    dimension: str,
    min_support: int = 1,
) -> pd.DataFrame:
    work = frame.copy()
    work["_segment"] = groups.astype("string").fillna("__MISSING__")
    work["actual_monthly_rent"] = pd.to_numeric(work.get("actual_monthly_rent"), errors="coerce")
    work[PREDICTION_COLUMN] = pd.to_numeric(work[PREDICTION_COLUMN], errors="coerce")
    work = work.loc[work["actual_monthly_rent"].notna() & work[PREDICTION_COLUMN].notna()].copy()
    if work.empty:
        return pd.DataFrame(
            columns=["Dimension", "Segment", "Rows", "Share %", "Actual Median", "Prediction Median", "MAE", "MedianAE", "Signed Bias"]
        )
    work["_error"] = work[PREDICTION_COLUMN] - work["actual_monthly_rent"]
    work["_absolute_error"] = work["_error"].abs()
    total = len(work)
    result = (
        work.groupby("_segment", dropna=False, observed=False)
        .agg(
            Rows=(ID_COLUMN, "size"),
            **{
                "Actual Median": ("actual_monthly_rent", "median"),
                "Prediction Median": (PREDICTION_COLUMN, "median"),
                "MAE": ("_absolute_error", "mean"),
                "MedianAE": ("_absolute_error", "median"),
                "Signed Bias": ("_error", "mean"),
            },
        )
        .reset_index()
        .rename(columns={"_segment": "Segment"})
    )
    result = result.loc[result["Rows"] >= min_support].copy()
    result.insert(0, "Dimension", dimension)
    result.insert(3, "Share %", result["Rows"] / total * 100)
    return result.sort_values(["Rows", "Segment"], ascending=[False, True]).reset_index(drop=True)


PRICE_BUCKET_ORDER = (
    "< 2.5M",
    "2.5M–<4.0M",
    "4.0M–<6.0M",
    "6.0M–10.0M",
    "> 10.0M",
)

AREA_BUCKET_ORDER = (
    "Small <15m²",
    "Compact 15–<25m²",
    "Standard 25–<40m²",
    "Large 40–80m²",
    "Very large >80m²",
)

# Provisional monitoring thresholds (engineering heuristics; not validated business SLAs)
PROVISIONAL_MIN_SAMPLE_ROWS: int = 1_000
PROVISIONAL_MIN_FUTURE_DAYS: int = 30
PROVISIONAL_AREA_MEDIAN_SHIFT_MAX_M2: float = 5.0
PROVISIONAL_AREA_MEDIAN_SHIFT_PCT: float = 0.25
PROVISIONAL_AREA_MISSING_SHIFT_PP: float = 5.0
PROVISIONAL_MAX_SOURCE_SHIFT_PP: float = 15.0
PROVISIONAL_MAX_UNSEEN_CATEGORY_PCT: float = 10.0
PROVISIONAL_CORE_MAE_RATIO_MAX: float = 0.25
PROVISIONAL_CORE_BIAS_RATIO_MAX: float = 0.15
PROVISIONAL_TAIL_BIAS_RATIO_MAX: float = 0.25
PROVISIONAL_SOURCE_BIAS_RATIO_MAX: float = 0.35
PROVISIONAL_LOCATION_BIAS_RATIO_MAX: float = 0.35


def price_bucket_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    actual = pd.to_numeric(frame.get("actual_monthly_rent"), errors="coerce")
    buckets = pd.cut(
        actual,
        [-np.inf, 2_500_000, 4_000_000, 6_000_000, 10_000_000, np.inf],
        labels=list(PRICE_BUCKET_ORDER),
        right=False,
        include_lowest=True,
    )
    res = _group_diagnostics(frame, pd.Series(buckets, index=frame.index), dimension="Actual Price Bucket")
    cat_map = {name: i for i, name in enumerate(PRICE_BUCKET_ORDER)}
    res["_order"] = res["Segment"].map(cat_map).fillna(999)
    return res.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)


def area_bucket_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    area = pd.to_numeric(frame["area_value_clean"], errors="coerce")
    buckets = pd.cut(
        area,
        [0, 15, 25, 40, 80, np.inf],
        labels=list(AREA_BUCKET_ORDER),
        right=False,
        include_lowest=True,
    )
    res = _group_diagnostics(frame, pd.Series(buckets, index=frame.index), dimension="Area Bucket")
    cat_map = {name: i for i, name in enumerate(AREA_BUCKET_ORDER)}
    res["_order"] = res["Segment"].map(cat_map).fillna(999)
    return res.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)


def source_diagnostics(frame: pd.DataFrame, min_support: int = 100) -> pd.DataFrame:
    return _group_diagnostics(frame, frame["source_code"], dimension="Source", min_support=min_support)


def ward_diagnostics(frame: pd.DataFrame, min_support: int = 100, include_missing: bool = False) -> pd.DataFrame:
    res = _group_diagnostics(frame, frame["ward_current"], dimension="Ward", min_support=min_support)
    if not include_missing:
        res = res.loc[~res["Segment"].isin({"__MISSING__", "<NA>", "None"})].reset_index(drop=True)
    return res


def district_diagnostics(frame: pd.DataFrame, min_support: int = 100, include_missing: bool = False) -> pd.DataFrame:
    res = _group_diagnostics(frame, frame["district_text_extracted"], dimension="District", min_support=min_support)
    if not include_missing:
        res = res.loc[~res["Segment"].isin({"__MISSING__", "<NA>", "None"})].reset_index(drop=True)
    return res


def missing_location_summary(frame: pd.DataFrame) -> pd.DataFrame:
    ward_res = _group_diagnostics(frame, frame["ward_current"], dimension="Ward", min_support=1)
    district_res = _group_diagnostics(frame, frame["district_text_extracted"], dimension="District", min_support=1)
    missing_ward = ward_res.loc[ward_res["Segment"].isin({"__MISSING__", "<NA>", "None"})].copy()
    missing_district = district_res.loc[district_res["Segment"].isin({"__MISSING__", "<NA>", "None"})].copy()
    return pd.concat([missing_ward, missing_district], ignore_index=True)


def location_diagnostics(frame: pd.DataFrame, min_support: int = 100) -> pd.DataFrame:
    ward = ward_diagnostics(frame, min_support=min_support, include_missing=True)
    district = district_diagnostics(frame, min_support=min_support, include_missing=True)
    return pd.concat([ward, district], ignore_index=True)


def intent_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    if "listing_intent" not in frame:
        return pd.DataFrame()
    monitored = frame["listing_intent"].where(frame["listing_intent"].isin(["RENT", "UNKNOWN"]), "OTHER")
    return _group_diagnostics(frame, monitored, dimension="Listing Intent")


def temporal_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(frame["observed_at"], errors="coerce").dt.strftime("%Y-%m-%d")
    return _group_diagnostics(frame, dates, dimension="Observation Date")


def prediction_compression_report(frame: pd.DataFrame) -> pd.DataFrame:
    predicted = _distribution(frame[PREDICTION_COLUMN])
    actual = _distribution(frame["actual_monthly_rent"]) if "actual_monthly_rent" in frame else None
    rows = [{"Population": "PREDICTION", **predicted}]
    if actual is not None:
        rows.insert(0, {"Population": "ACTUAL", **actual})
    result = pd.DataFrame(rows)
    if actual and actual["p99"] is not None and actual["p01"] is not None:
        actual_span = actual["p99"] - actual["p01"]
        prediction_span = predicted["p99"] - predicted["p01"]
        result["P01–P99 Span"] = result["p99"] - result["p01"]
        result["Prediction / Actual Span"] = prediction_span / actual_span if actual_span else np.nan
    return result


def build_readiness_scorecard(
    *,
    validation_mode: str,
    sample_rows: int,
    temporal_coverage_days: float,
    artifact_loaded: bool,
    inference_contract_valid: bool,
    no_leakage: bool,
    unknown_categories_safe: bool,
    prediction_sanity_pass: bool,
    drift_within_threshold: bool,
    core_market_error_stable: bool,
    budget_calibration_acceptable: bool,
    upper_tail_calibration_acceptable: bool,
    source_stability: bool,
    location_stability: bool,
    minimum_sample_rows: int = PROVISIONAL_MIN_SAMPLE_ROWS,
    minimum_future_days: int = PROVISIONAL_MIN_FUTURE_DAYS,
) -> tuple[pd.DataFrame, dict[str, str]]:
    checks = [
        ("Champion artifact loads", artifact_loaded, "Required"),
        ("Inference contract valid", inference_contract_valid, "Required"),
        ("No target leakage", no_leakage, "Required"),
        ("Unseen categories handled", unknown_categories_safe, "Required"),
        ("Prediction sanity", prediction_sanity_pass, "Required"),
        ("Drift within configured tolerance", drift_within_threshold, "Provisional monitoring threshold"),
        ("Sufficient shadow sample", sample_rows >= minimum_sample_rows, f">={minimum_sample_rows:,} rows (Provisional)"),
        ("Sufficient future temporal coverage", validation_mode == FUTURE_SHADOW and temporal_coverage_days >= minimum_future_days, f">={minimum_future_days} future days (Provisional)"),
        ("Core-market error stable", core_market_error_stable, "Provisional monitoring threshold"),
        ("Budget calibration acceptable", budget_calibration_acceptable, "Provisional monitoring threshold"),
        ("Upper-tail calibration acceptable", upper_tail_calibration_acceptable, "Provisional monitoring threshold"),
        ("Source stability", source_stability, "Provisional monitoring threshold"),
        ("Location stability", location_stability, "Provisional monitoring threshold"),
    ]
    scorecard = pd.DataFrame(
        [
            {"Dimension": name, "Status": "PASS" if bool(value) else "NOT MET", "Requirement": requirement}
            for name, value, requirement in checks
        ]
    )
    all_met = scorecard["Status"].eq("PASS").all()
    sufficient = validation_mode == FUTURE_SHADOW and bool(all_met)
    decision = {
        "model_readiness": "CANDIDATE",
        "deployment_lifecycle": "SHADOW",
        "production_evidence": "SUFFICIENT" if sufficient else "INSUFFICIENT",
        # Automated evidence keeps candidate in shadow; production promotion requires human review and 30-60d live evidence
        "recommended_status": "CANDIDATE",
        "automatic_production_promotion": "DISABLED",
        "threshold_governance": "PROVISIONAL_MONITORING_ONLY",
    }
    return scorecard, decision


def make_shadow_run_id(validation_mode: str, inference_timestamp: str | None = None) -> str:
    timestamp = pd.Timestamp(inference_timestamp or datetime.now(timezone.utc)).tz_convert("UTC")
    prefix = "future" if validation_mode == FUTURE_SHADOW else "historical"
    return f"{prefix}-{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}"


def persist_shadow_run(
    output_root: str | Path,
    run_id: str,
    run_metadata: Mapping[str, Any],
    predictions: pd.DataFrame,
    tables: Mapping[str, pd.DataFrame],
) -> Path:
    """Persist an immutable run directory; existing evidence is never overwritten."""
    root = Path(output_root)
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "run_metadata.json", dict(run_metadata))
    with duckdb.connect(":memory:") as connection:
        connection.register("_shadow_predictions", predictions)
        connection.execute(
            "COPY _shadow_predictions TO ? (FORMAT PARQUET)",
            [str(run_dir / "predictions.parquet")],
        )
    for name, table in tables.items():
        filename = name if name.endswith(".csv") else f"{name}.csv"
        table.to_csv(run_dir / filename, index=False)
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": file_sha256(path)}
            for path in sorted(run_dir.iterdir())
            if path.is_file()
        },
    }
    _write_json(run_dir / "manifest.json", manifest)

    summary_dir = root / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    index_path = summary_dir / "run_index.csv"
    index_row = pd.DataFrame(
        [{
            "run_id": run_id,
            "model_id": run_metadata.get("model_id"),
            "validation_mode": run_metadata.get("validation_mode"),
            "inference_rows": len(predictions),
            "created_at": manifest["created_at"],
            "run_path": str(run_dir),
        }]
    )
    if index_path.exists():
        existing = pd.read_csv(index_path)
        if run_id in set(existing["run_id"].astype(str)):
            raise FileExistsError(f"Shadow run is already indexed: {run_id}")
        index_row = pd.concat([existing, index_row], ignore_index=True)
    index_row.to_csv(index_path, index=False)
    return run_dir


__all__ = [
    "F4_FEATURE_SET",
    "F4_FEATURES",
    "CATEGORICAL_FEATURES",
    "ID_COLUMN",
    "TIMESTAMP_COLUMN",
    "TARGET_COLUMN",
    "PREDICTION_COLUMN",
    "HISTORICAL_DRY_RUN",
    "FUTURE_SHADOW",
    "LoadedChampion",
    "SchemaValidationResult",
    "ShadowPopulation",
    "EvaluationPopulation",
    "ValidationModeDecision",
    "file_sha256",
    "deterministic_model_id",
    "build_reference_profile",
    "persist_champion_artifact",
    "resolve_champion_artifact",
    "validate_shadow_schema",
    "prepare_shadow_population",
    "prepare_evaluation_population",
    "build_inference_matrix",
    "classify_validation_mode",
    "predict_shadow",
    "attach_actuals_for_evaluation",
    "evaluate_shadow_predictions",
    "prediction_distribution",
    "prediction_sanity_report",
    "category_drift_report",
    "feature_drift_report",
    "PRICE_BUCKET_ORDER",
    "AREA_BUCKET_ORDER",
    "PROVISIONAL_MIN_SAMPLE_ROWS",
    "PROVISIONAL_MIN_FUTURE_DAYS",
    "PROVISIONAL_AREA_MEDIAN_SHIFT_MAX_M2",
    "PROVISIONAL_AREA_MEDIAN_SHIFT_PCT",
    "PROVISIONAL_AREA_MISSING_SHIFT_PP",
    "PROVISIONAL_MAX_SOURCE_SHIFT_PP",
    "PROVISIONAL_MAX_UNSEEN_CATEGORY_PCT",
    "PROVISIONAL_CORE_MAE_RATIO_MAX",
    "PROVISIONAL_CORE_BIAS_RATIO_MAX",
    "PROVISIONAL_TAIL_BIAS_RATIO_MAX",
    "PROVISIONAL_SOURCE_BIAS_RATIO_MAX",
    "PROVISIONAL_LOCATION_BIAS_RATIO_MAX",
    "price_bucket_diagnostics",
    "area_bucket_diagnostics",
    "source_diagnostics",
    "location_diagnostics",
    "ward_diagnostics",
    "district_diagnostics",
    "missing_location_summary",
    "intent_diagnostics",
    "temporal_diagnostics",
    "prediction_compression_report",
    "build_readiness_scorecard",
    "make_shadow_run_id",
    "persist_shadow_run",
]
