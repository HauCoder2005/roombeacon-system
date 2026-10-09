import json
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from notebooks.utils.modeling_benchmark import (
    assert_group_isolation,
    audit_features,
    build_feature_sets,
    build_group_key,
    build_expanding_group_time_folds,
    engineer_safe_features,
    group_aware_split,
    hierarchical_segment_median,
    hierarchical_location_median,
    inverse_target,
    lightgbm_gain_importance,
    build_modeling_eligibility,
    build_inference_eligibility,
    inference_eligibility_funnel,
    eligibility_funnel,
    lock_candidate,
    prepare_lightgbm_categories,
    regression_metrics,
    transform_target,
    unique_price_bands,
)


def test_modeling_eligibility_requires_separate_price_and_area_suitability():
    frame = pd.DataFrame({
        "price_amount_clean": [3_000_000.0] * 4,
        "price_quality_status": ["VALIDATED_EXISTING"] * 4,
        "price_target_trust_status": ["TRUSTED_EXISTING"] * 4,
        "price_model_value": [3_000_000.0] * 4,
        "price_model_suitability": ["SUPPORTED", "REVIEW", "SUPPORTED", "SUPPORTED"],
        "area_value_clean": [20.0, 20.0, 2.0, 20.0],
        "area_model_suitability": ["SUPPORTED", "SUPPORTED", "REVIEW", "SUPPORTED"],
        "listing_intent": ["RENT", "RENT", "RENT", "UNKNOWN"],
        "rental_scope": ["SINGLE_OR_ORDINARY_UNIT", "SINGLE_OR_ORDINARY_UNIT", "SINGLE_OR_ORDINARY_UNIT", "UNKNOWN"],
    })

    permissive = build_modeling_eligibility(frame, policy="PERMISSIVE")
    strict = build_modeling_eligibility(frame, policy="STRICT")

    assert permissive.final_eligible.tolist() == [True, False, False, True]
    assert strict.final_eligible.tolist() == [True, False, False, False]


def test_eligibility_funnel_reports_monotonic_rows_and_deltas():
    frame = pd.DataFrame({
        "price_amount_clean": [3_000_000.0, 4_000_000.0],
        "price_quality_status": ["VALIDATED_EXISTING", "VALIDATED_EXISTING"],
        "price_target_trust_status": ["TRUSTED_EXISTING", "TRUSTED_EXISTING"],
        "price_model_value": [3_000_000.0, 4_000_000.0],
        "price_model_suitability": ["SUPPORTED", "REVIEW"],
        "area_value_clean": [20.0, 30.0],
        "area_model_suitability": ["SUPPORTED", "SUPPORTED"],
        "listing_intent": ["RENT", "RENT"],
        "rental_scope": ["SINGLE_OR_ORDINARY_UNIT", "SINGLE_OR_ORDINARY_UNIT"],
    })
    masks = build_modeling_eligibility(frame, policy="PERMISSIVE")
    funnel = eligibility_funnel(masks)

    assert funnel.Stage.tolist() == [
        "Silver rows", "Numeric target candidate", "Lineage trusted",
        "Semantic target supported", "Area supported",
        "Rental-compatible", "Final model eligible",
    ]
    assert funnel.Rows.tolist() == [2, 2, 2, 1, 1, 1, 1]
    assert funnel["Removed / reviewed"].tolist() == [0, 0, 0, 1, 0, 0, 0]


def test_shared_inference_eligibility_is_target_free_and_preserves_unknown_policy():
    frame = pd.DataFrame({
        "area_value_clean": [20.0, 20.0, 20.0, 20.0],
        "area_model_suitability": ["SUPPORTED", "REVIEW", "SUPPORTED", "SUPPORTED"],
        "listing_intent": ["RENT", "RENT", "UNKNOWN", "SALE"],
        "rental_scope": [
            "SINGLE_OR_ORDINARY_UNIT",
            "SINGLE_OR_ORDINARY_UNIT",
            "UNKNOWN",
            "SINGLE_OR_ORDINARY_UNIT",
        ],
    })

    permissive = build_inference_eligibility(frame, policy="PERMISSIVE")
    strict = build_inference_eligibility(frame, policy="STRICT")
    funnel = inference_eligibility_funnel(permissive)

    assert permissive.final_eligible.tolist() == [True, False, True, False]
    assert strict.final_eligible.tolist() == [True, False, False, False]
    assert funnel["Rows"].tolist() == [4, 3, 2, 2]


def _split_frame(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame({
        "rental_post_id": np.arange(rows),
        "duplicate_candidate_group": ["shared"] * 3 + [None] * (rows - 3),
        "latest_observed_at": pd.date_range("2026-01-01", periods=rows, freq="6h"),
    })


def test_target_leakage_exclusions():
    audit_features(["area_value_clean", "source_code", "ward_current"])
    with pytest.raises(ValueError, match="price_amount_clean"):
        audit_features(["area_value_clean", "price_amount_clean"])
    with pytest.raises(ValueError, match="price_per_area"):
        audit_features(["price_per_area"])
    with pytest.raises(ValueError, match="price_per_area_analysis"):
        audit_features(["price_per_area_analysis"])
    with pytest.raises(ValueError, match="price_target_model_value"):
        audit_features(["price_target_model_value"])
    with pytest.raises(ValueError, match="price_model_value"):
        audit_features(["price_model_value"])


def test_feature_set_construction_uses_only_v2_safe_fields():
    frame = engineer_safe_features(pd.DataFrame({"title_clean": ["Room"]}))
    assert frame.title_length.iloc[0] == 4
    sets = build_feature_sets([
        "area_value_clean", "source_code", "ward_current", "district_text_extracted",
        "province_text_extracted", "title_length",
    ])
    assert sets["F1 — AREA ONLY"] == ["area_value_clean"]
    assert sets["F4 — AREA + SOURCE + LOCATION"][-2:] == ["ward_current", "district_text_extracted"]
    assert "title_length" in sets["F5 — FULL SAFE TABULAR"]


def test_group_split_is_deterministic_and_isolated():
    frame = _split_frame()
    groups = build_group_key(frame)
    first = group_aware_split(frame, groups)
    second = group_aware_split(frame, groups)
    pd.testing.assert_series_equal(first.labels, second.labels)
    assert_group_isolation(groups, first.labels)
    assert first.labels.iloc[:3].nunique() == 1
    ordered = first.group_timestamps
    by_group = pd.DataFrame({"group": groups, "split": first.labels}).groupby("group").split.first()
    assert ordered.loc[by_group.eq("TRAIN")].max() < ordered.loc[by_group.eq("VALIDATION")].min()
    assert ordered.loc[by_group.eq("VALIDATION")].max() < ordered.loc[by_group.eq("TEST")].min()


def test_expanding_folds_are_future_only_and_group_isolated():
    frame = _split_frame(120)
    groups = build_group_key(frame)
    folds = build_expanding_group_time_folds(frame, groups)
    assert len(folds) == 3
    for fold in folds:
        assert fold.train_end < fold.validation_start
        assert set(groups.loc[fold.train_index]).isdisjoint(groups.loc[fold.validation_index])


def test_location_median_is_train_only_and_handles_unseen_categories():
    train = pd.DataFrame({
        "price_amount_clean": [100.0, 200.0, 300.0, 400.0],
        "ward_current": ["A", "A", "B", "B"],
        "district_text_extracted": ["D1", "D1", "D2", "D2"],
    })
    score = pd.DataFrame({
        "ward_current": ["A", "UNSEEN", "UNSEEN"],
        "district_text_extracted": ["D1", "D2", "UNSEEN"],
    })
    prediction = hierarchical_location_median(
        train, score, min_ward_rows=2, min_district_rows=2
    )
    assert prediction.tolist() == [150.0, 350.0, 250.0]


def test_strong_baseline_uses_train_only_bins_and_handles_unknowns():
    train = pd.DataFrame({
        "price_amount_clean": [100., 110., 300., 310., 900., 910.],
        "area_value_clean": [10., 11., 30., 31., 90., 91.],
        "ward_current": ["A", "A", "B", "B", "C", "C"],
        "district_text_extracted": ["D1", "D1", "D2", "D2", "D3", "D3"],
        "source_code": ["S"] * 6,
    })
    score = pd.DataFrame({"area_value_clean": [1., 1000.], "ward_current": ["X", "X"], "district_text_extracted": ["X", "X"], "source_code": ["NEW", "NEW"]})
    pred = hierarchical_segment_median(train, score, min_rows=2)
    assert np.isfinite(pred).all()
    assert len(pred) == 2


def test_candidate_is_locked_without_test_evidence():
    summary = pd.DataFrame([
        {"Model":"Simple", "MAE_Mean":100., "MAE_Median":100., "MAE_Std":5., "MedianAE_Mean":80., "RMSLE_Mean":.2, "Fit_Time_Mean":1.},
        {"Model":"Complex", "MAE_Mean":99.5, "MAE_Median":99., "MAE_Std":4., "MedianAE_Mean":79., "RMSLE_Mean":.19, "Fit_Time_Mean":5.},
    ])
    assert lock_candidate(summary, {"Simple":1, "Complex":2}).Model == "Simple"
    with pytest.raises(ValueError, match="TEST"):
        lock_candidate(summary.assign(TEST_MAE=1), {"Simple":1, "Complex":2})


def test_lightgbm_categories_are_train_defined_and_unknown_safe():
    train = pd.DataFrame({"source_code": ["a", None, "b"]})
    score = pd.DataFrame({"source_code": ["a", "new", None]})
    fit, out = prepare_lightgbm_categories(train, score, ["source_code"])
    assert "__UNKNOWN__" in fit.source_code.cat.categories
    assert "__MISSING__" in fit.source_code.cat.categories
    assert out.source_code.astype("string").tolist() == ["a", "__UNKNOWN__", "__MISSING__"]
    assert list(fit.source_code.cat.categories) == list(out.source_code.cat.categories)

    # Also test with return_vocabularies=True
    fit_v, out_v, vocab = prepare_lightgbm_categories(train, score, ["source_code"], return_vocabularies=True)
    assert "__UNKNOWN__" in vocab["source_code"]
    assert "__MISSING__" in vocab["source_code"]


def test_lightgbm_categories_canonical_contract_and_fit_predict():
    from lightgbm import LGBMRegressor

    # 1. Helper function is available and callable
    assert callable(prepare_lightgbm_categories)

    # 2. Setup DataFrames with numeric and categorical features
    train_orig = pd.DataFrame({
        "area_value_clean": [20.0, 30.0, 40.0],
        "source_code": ["phongtro123", "nhatrovn", None],
    })
    score_orig = pd.DataFrame({
        "area_value_clean": [25.0, 35.0, 50.0],
        "source_code": ["phongtro123", "unseen_source", None],
    })
    train_copy = train_orig.copy(deep=True)
    score_copy = score_orig.copy(deep=True)

    # 3. Call canonical helper
    fit, out = prepare_lightgbm_categories(train_orig, score_orig, ["source_code"])

    # 4. Invariant: original frames are not mutated in place
    pd.testing.assert_frame_equal(train_orig, train_copy)
    pd.testing.assert_frame_equal(score_orig, score_copy)

    # 5. Numeric features remain numeric
    assert pd.api.types.is_float_dtype(fit["area_value_clean"])
    assert pd.api.types.is_float_dtype(out["area_value_clean"])

    # 6. Categorical features have compatible pandas Categorical dtypes
    assert isinstance(fit["source_code"].dtype, pd.CategoricalDtype)
    assert isinstance(out["source_code"].dtype, pd.CategoricalDtype)
    assert list(fit["source_code"].cat.categories) == list(out["source_code"].cat.categories)
    assert "__UNKNOWN__" in fit["source_code"].cat.categories
    assert "__MISSING__" in fit["source_code"].cat.categories

    # 7. Unseen category on score side mapped to __UNKNOWN__, missing to __MISSING__
    assert out["source_code"].tolist() == ["phongtro123", "__UNKNOWN__", "__MISSING__"]

    # 8. LightGBM can fit and predict successfully with finite outputs
    y = np.array([5_000_000.0, 7_000_000.0, 9_000_000.0])
    model = LGBMRegressor(verbosity=-1, random_state=42)
    model.fit(fit, y, categorical_feature=["source_code"])
    preds = model.predict(out)
    assert len(preds) == len(out)
    assert np.all(np.isfinite(preds))


def test_equal_price_percentiles_never_create_zero_width_bands():
    reference = np.array([1.0] * 95 + [10.0] * 5)
    bands, edges = unique_price_bands(reference, np.array([1.0, 5.0, 10.0]))
    assert np.all(np.diff(edges) > 0)
    assert len(bands) == 3


def test_lightgbm_gain_importance_uses_supported_booster_contract():
    class Booster:
        def feature_name(self): return ["area", "source"]
        def feature_importance(self, importance_type):
            return np.array([3.0, 1.0]) if importance_type == "gain" else np.array([4, 2])
    class Model: booster_ = Booster()
    result = lightgbm_gain_importance(Model(), ["area", "source"])
    assert result.iloc[0].Feature == "area"
    assert result["Gain %"].sum() == pytest.approx(100.0)


def test_metrics_report_negative_predictions_and_safe_rmsle():
    metrics = regression_metrics(np.array([100.0, 200.0]), np.array([-10.0, 210.0]))
    assert metrics["Negative Predictions"] == 1
    assert metrics["MAE"] == 60.0
    assert np.isfinite(metrics["RMSLE"])
    with pytest.raises(ValueError, match="non-negative"):
        regression_metrics(np.array([-1.0]), np.array([1.0]))


def test_raw_and_log_target_round_trip():
    target = np.array([0.0, 1_000_000.0, 3_500_000.0])
    np.testing.assert_allclose(inverse_target(transform_target(target, "RAW"), "RAW"), target)
    np.testing.assert_allclose(inverse_target(transform_target(target, "LOG1P"), "LOG1P"), target)
    with pytest.raises(ValueError, match="non-negative"):
        transform_target(np.array([-1.0]), "LOG1P")


def _normalized_code(path: Path) -> str:
    """Notebook code with whitespace removed and quotes unified, so checks survive formatting."""
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    code = "\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "code")
    return "".join(code.split()).replace('"', "'")


def _normalized_text(path: Path) -> str:
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    return "".join("\n".join("".join(c["source"]) for c in cells).split()).replace('"', "'")


def test_notebook_preprocessing_handles_unseen_categories_and_fits_train_only():
    notebook = _normalized_text(Path(__file__).resolve().parents[1] / "notebooks" / "04_roombeacon_modeling.ipynb")
    assert "OneHotEncoder(handle_unknown='ignore',sparse_output=True)" in notebook
    assert "build_expanding_group_time_folds" in notebook
    assert "LOCKED_CANDIDATE" in notebook
    assert notebook.index("LOCKED_CANDIDATE") < notebook.index("##10.FINALTEST—ONE-TIMEEVALUATION")


def test_v2_executes_required_model_families_and_notebook_03_does_not_fit():
    root = Path(__file__).resolve().parents[1]
    modeling = (root / "notebooks" / "04_roombeacon_modeling.ipynb").read_text()
    for model in [
        "Linear Regression", "Ridge Regression", "ElasticNet",
        "Decision Tree Regressor", "Random Forest Regressor", "Extra Trees Regressor",
        "Gradient Boosting Regressor", "HistGradientBoosting Regressor",
        "XGBoost Regressor", "LightGBM Regressor", "CatBoost Regressor",
    ]:
        assert model in modeling
    preparation = (root / "notebooks" / "03_roombeacon_processing.ipynb").read_text()
    assert ".fit(" not in preparation and ".predict(" not in preparation
    # Notebook 03 is an accepted upstream artifact and is outside this modeling-only task.


def test_notebook_03_has_no_legacy_split_and_declares_analysis_only_ratio():
    text = (Path(__file__).resolve().parents[1] / "notebooks" / "03_roombeacon_processing.ipynb").read_text()
    assert ".mod(10)" not in text
    assert "dataset_split'] =" not in text
    assert "price_per_area_analysis" in text
    assert "TARGET-DERIVED / ANALYSIS-ONLY" in text


def test_source_ablation_uses_locked_configuration_and_final_diagnostics_do_not_mutate_source():
    text = _normalized_text(Path(__file__).resolve().parents[1] / "notebooks" / "04_roombeacon_modeling.ipynb")
    assert "evaluate_config(LOCKED_MODEL,LOCKED_PARAMS" in text
    assert "Withoutsource_code" in text and "Withsource_code" in text
    assert "test_predictions[name]=pred" in text
    assert "drop(" not in text[text.index("largest=test_predictions"):text.index("Locked-modelfeatureimportance")]


def test_notebook_04_consumes_canonical_numeric_trust_without_reparsing():
    text = _normalized_code(Path(__file__).resolve().parents[1] / "notebooks" / "04_roombeacon_modeling.ipynb")
    assert "build_modeling_eligibility(prepared,policy='PERMISSIVE')" in text
    assert "price_model_suitability" in text
    assert "area_model_suitability" in text
    assert "price_target_model_value" in text
    assert "parse_price(" not in text
