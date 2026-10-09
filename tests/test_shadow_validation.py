import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMRegressor

from notebooks.utils.modeling_benchmark import prepare_lightgbm_categories
from notebooks.utils.shadow_validation import (
    AREA_BUCKET_ORDER,
    CATEGORICAL_FEATURES,
    F4_FEATURES,
    F4_FEATURE_SET,
    HISTORICAL_DRY_RUN,
    FUTURE_SHADOW,
    PRICE_BUCKET_ORDER,
    PROVISIONAL_MIN_FUTURE_DAYS,
    PROVISIONAL_MIN_SAMPLE_ROWS,
    area_bucket_diagnostics,
    attach_actuals_for_evaluation,
    build_inference_matrix,
    build_readiness_scorecard,
    build_reference_profile,
    category_drift_report,
    classify_validation_mode,
    district_diagnostics,
    evaluate_shadow_predictions,
    missing_location_summary,
    persist_champion_artifact,
    persist_shadow_run,
    predict_shadow,
    prepare_evaluation_population,
    prepare_shadow_population,
    price_bucket_diagnostics,
    resolve_champion_artifact,
    validate_shadow_schema,
    ward_diagnostics,
)


def _training_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rental_post_id": [1, 2, 3, 4, 5, 6],
            "latest_observed_at": pd.date_range("2026-09-20", periods=6, freq="D"),
            "area_value_clean": [18.0, 22.0, 28.0, 35.0, 45.0, 60.0],
            "source_code": ["a", "a", "b", "b", "c", "c"],
            "ward_current": ["w1", "w1", "w2", "w2", None, "w3"],
            "district_text_extracted": ["d1", "d1", "d2", "d2", "d3", "d3"],
            "price_model_value": [2e6, 2.5e6, 3e6, 4e6, 5e6, 7e6],
        }
    )


def _persist_test_champion(tmp_path: Path):
    train = _training_frame()
    fit, _, vocab = prepare_lightgbm_categories(
        train[list(F4_FEATURES)],
        train[list(F4_FEATURES)],
        CATEGORICAL_FEATURES,
        return_vocabularies=True,
    )
    params = {
        "learning_rate": 0.05,
        "min_child_samples": 2,
        "n_estimators": 5,
        "num_leaves": 7,
        "objective": "mae",
    }
    model = LGBMRegressor(random_state=42, verbosity=-1, **params)
    model.fit(fit, train["price_model_value"], categorical_feature=list(CATEGORICAL_FEATURES))
    reference_prediction = model.predict(fit)
    profile = build_reference_profile(
        train,
        reference_prediction,
        target_column="price_model_value",
        population_name="DEVELOPMENT",
        uses_test=False,
    )
    champion = persist_champion_artifact(
        model,
        tmp_path,
        model_family="LightGBM Regressor",
        target_transform="RAW",
        feature_set=F4_FEATURE_SET,
        feature_names=list(F4_FEATURES),
        hyperparameters=params,
        random_seed=42,
        categorical_vocabularies=vocab,
        training_reference={
            "population": "DEVELOPMENT",
            "row_count": len(train),
            "min_observed_at": "2026-09-20T00:00:00",
            "max_observed_at": "2026-09-25T00:00:00",
            "evidence_cutoff": "2026-09-30T00:00:00",
            "uses_test": False,
        },
        expected_schema={
            "area_value_clean": "numeric",
            "source_code": "categorical",
            "ward_current": "categorical",
            "district_text_extracted": "categorical",
        },
        reference_profile=profile,
        created_at="2026-10-05T00:00:00+07:00",
    )
    experiment = {
        "locked_candidate": "LightGBM Regressor",
        "locked_transform": "RAW",
        "selected_feature_set": F4_FEATURE_SET,
        "locked_parameters": params,
        "seed": 42,
        "champion": {
            "model_id": champion["model_id"],
            "artifact_path": champion["artifact_path"],
            "metadata_path": "champion_metadata.json",
            "reference_profile_path": "champion_reference_profile.json",
            "artifact_sha256": champion["artifact_sha256"],
        },
    }
    (tmp_path / "experiment_metadata.json").write_text(json.dumps(experiment), encoding="utf-8")
    return train, champion


def _eligible_silver() -> pd.DataFrame:
    frame = _training_frame().copy()
    frame["price_amount_clean"] = frame["price_model_value"]
    frame["price_quality_status"] = "VALIDATED_EXISTING"
    frame["price_target_trust_status"] = "TRUSTED_EXISTING"
    frame["price_model_suitability"] = "SUPPORTED"
    frame["area_model_suitability"] = "SUPPORTED"
    frame["listing_intent"] = ["RENT", "RENT", "UNKNOWN", "RENT", "UNKNOWN", "RENT"]
    frame["rental_scope"] = "SINGLE_OR_ORDINARY_UNIT"
    frame["title_clean"] = "room"
    return frame


def test_champion_artifact_resolves_and_agrees_with_metadata(tmp_path):
    _, persisted = _persist_test_champion(tmp_path)

    loaded = resolve_champion_artifact(tmp_path)

    assert loaded.metadata["model_id"] == persisted["model_id"]
    assert loaded.metadata["model_family"] == "LightGBM Regressor"
    assert loaded.metadata["target_transform"] == "RAW"
    assert loaded.metadata["feature_set"] == F4_FEATURE_SET
    assert loaded.metadata["feature_names"] == list(F4_FEATURES)
    assert loaded.artifact_path.exists()
    assert loaded.reference_profile["population"] == "DEVELOPMENT"
    assert loaded.reference_profile["uses_test"] is False


def test_champion_hash_or_selection_mismatch_fails_loudly(tmp_path):
    _persist_test_champion(tmp_path)
    metadata_path = tmp_path / "champion_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["target_transform"] = "LOG1P"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="target transform|metadata agreement"):
        resolve_champion_artifact(tmp_path)


def test_champion_pointer_and_persisted_category_contract_must_agree(tmp_path):
    _persist_test_champion(tmp_path)
    experiment_path = tmp_path / "experiment_metadata.json"
    experiment = json.loads(experiment_path.read_text())
    experiment["champion"]["artifact_path"] = "some-other-model.joblib"
    experiment_path.write_text(json.dumps(experiment), encoding="utf-8")

    with pytest.raises(ValueError, match="artifact path"):
        resolve_champion_artifact(tmp_path)


def test_f4_contract_rejects_forbidden_or_target_derived_predictors(tmp_path):
    _persist_test_champion(tmp_path)
    loaded = resolve_champion_artifact(tmp_path)
    frame = _training_frame()
    matrix = build_inference_matrix(frame, loaded.metadata)
    assert matrix.columns.tolist() == list(F4_FEATURES)
    assert "price_model_value" not in matrix

    leaking = dict(loaded.metadata)
    leaking["feature_names"] = [*F4_FEATURES[:-1], "price_model_value"]
    with pytest.raises(ValueError, match="Forbidden|F4 feature contract"):
        build_inference_matrix(frame, leaking)


def test_schema_validation_rejects_duplicates_and_tracks_missing_numeric():
    frame = _training_frame().iloc[:3].copy()
    metadata = {
        "feature_set": F4_FEATURE_SET,
        "feature_names": list(F4_FEATURES),
        "expected_schema": {
            "area_value_clean": "numeric",
            "source_code": "categorical",
            "ward_current": "categorical",
            "district_text_extracted": "categorical",
        },
    }
    frame.loc[frame.index[1], "area_value_clean"] = np.nan
    result = validate_shadow_schema(frame, metadata)
    assert result.status.tolist() == ["READY_FOR_INFERENCE", "MISSING_REQUIRED_NUMERIC", "READY_FOR_INFERENCE"]
    assert result.ready_mask.sum() == 2

    duplicate = frame.copy()
    duplicate.loc[duplicate.index[1], "rental_post_id"] = duplicate.iloc[0].rental_post_id
    with pytest.raises(ValueError, match="Duplicate rental_post_id"):
        validate_shadow_schema(duplicate, metadata)


def test_inference_population_is_target_free_and_evaluation_uses_full_contract_after_prediction():
    silver = _eligible_silver()
    silver.loc[1, "price_model_suitability"] = "REVIEW"
    silver.loc[2, "area_model_suitability"] = "REVIEW"
    metadata = {"feature_set": F4_FEATURE_SET, "feature_names": list(F4_FEATURES)}

    population = prepare_shadow_population(silver, metadata)

    assert len(population.all_rows) == len(silver)
    assert len(population.ready_rows) == len(silver) - 1
    assert population.all_rows["inference_status"].value_counts().to_dict() == {
        "READY_FOR_INFERENCE": len(silver) - 1,
        "UNSUPPORTED": 1,
    }
    assert population.funnel.iloc[0]["Rows"] == len(silver)
    assert population.funnel.iloc[-1]["Rows"] == len(silver) - 1
    # Price trust/suitability is deliberately not read before inference.
    assert silver.loc[1, "rental_post_id"] in set(population.ready_rows["rental_post_id"])

    target_free = silver.drop(
        columns=[
            "price_amount_clean",
            "price_quality_status",
            "price_target_trust_status",
            "price_model_value",
            "price_model_suitability",
        ]
    )
    target_free_population = prepare_shadow_population(target_free, metadata)
    assert len(target_free_population.ready_rows) == len(silver) - 1

    predictions = pd.DataFrame(
        {
            "rental_post_id": population.ready_rows["rental_post_id"].tolist(),
            "predicted_monthly_rent": [3_000_000.0] * len(population.ready_rows),
        }
    )
    evaluation = prepare_evaluation_population(predictions, silver)
    assert len(evaluation.evaluation_predictions) == len(silver) - 2
    assert silver.loc[1, "rental_post_id"] not in set(
        evaluation.evaluation_predictions["rental_post_id"]
    )
    assert len(evaluation.all_predictions) == len(predictions)
    assert evaluation.all_predictions["actual_monthly_rent"].notna().sum() == len(silver) - 2


def test_unknown_categories_are_mapped_safely_and_predictions_preserve_id_order(tmp_path):
    _, _ = _persist_test_champion(tmp_path)
    loaded = resolve_champion_artifact(tmp_path)
    score = _training_frame().iloc[:3].copy()
    score["rental_post_id"] = [101, 102, 103]
    score["source_code"] = ["new-source", "a", None]
    score["ward_current"] = ["new-ward", None, "w1"]

    matrix = build_inference_matrix(score, loaded.metadata)
    assert matrix.loc[score.index[0], "source_code"] == "__UNKNOWN__"
    assert matrix.loc[score.index[2], "source_code"] == "__MISSING__"

    prediction = predict_shadow(
        loaded.model,
        score,
        loaded.metadata,
        validation_mode=HISTORICAL_DRY_RUN,
        inference_timestamp="2026-10-05T01:02:03+07:00",
    )
    assert prediction["rental_post_id"].tolist() == [101, 102, 103]
    assert prediction["predicted_monthly_rent"].notna().all()
    assert np.isfinite(prediction["predicted_monthly_rent"]).all()
    assert prediction["predicted_monthly_rent"].ge(0).all()
    assert prediction["model_id"].nunique() == 1


def test_target_is_excluded_during_prediction_and_joined_only_afterward():
    class InspectingModel:
        def predict(self, matrix):
            assert matrix.columns.tolist() == list(F4_FEATURES)
            assert "price_model_value" not in matrix
            return np.full(len(matrix), 3_000_000.0)

    frame = _training_frame().iloc[:2].copy()
    metadata = {
        "model_id": "roombeacon-price-lgbm-f4-raw-test",
        "target_transform": "RAW",
        "feature_set": F4_FEATURE_SET,
        "feature_names": list(F4_FEATURES),
        "categorical_vocabularies": {
            name: ["__MISSING__", "__UNKNOWN__", *sorted(frame[name].dropna().unique().tolist())]
            for name in CATEGORICAL_FEATURES
        },
    }
    predicted = predict_shadow(InspectingModel(), frame, metadata, HISTORICAL_DRY_RUN)
    assert "actual_monthly_rent" not in predicted

    evaluated = attach_actuals_for_evaluation(predicted, frame, target_column="price_model_value")
    assert evaluated["actual_monthly_rent"].tolist() == frame["price_model_value"].tolist()
    metrics = evaluate_shadow_predictions(evaluated)
    assert metrics["Rows"] == 2
    assert metrics["Signed Bias"] == pytest.approx(750_000.0)


def test_mode_classification_is_conservative_and_historical_never_counts_as_evidence():
    cutoff = "2026-09-30T00:00:00"
    historical = classify_validation_mode(
        pd.to_datetime(["2026-09-29", "2026-10-01"]), cutoff
    )
    entirely_known = classify_validation_mode(
        pd.to_datetime(["2026-09-28", "2026-09-30"]), cutoff
    )
    future = classify_validation_mode(
        pd.to_datetime(["2026-10-01", "2026-10-05"]), cutoff
    )
    missing = classify_validation_mode(pd.Series([pd.NaT]), cutoff)

    assert historical.mode == HISTORICAL_DRY_RUN
    assert historical.counts_toward_production is False
    assert entirely_known.mode == HISTORICAL_DRY_RUN
    assert entirely_known.counts_toward_production is False
    assert future.mode == FUTURE_SHADOW
    assert future.counts_toward_production is True
    assert missing.mode == HISTORICAL_DRY_RUN

    scorecard, decision = build_readiness_scorecard(
        validation_mode=HISTORICAL_DRY_RUN,
        sample_rows=50_000,
        temporal_coverage_days=60,
        artifact_loaded=True,
        inference_contract_valid=True,
        no_leakage=True,
        unknown_categories_safe=True,
        prediction_sanity_pass=True,
        drift_within_threshold=True,
        core_market_error_stable=True,
        budget_calibration_acceptable=True,
        upper_tail_calibration_acceptable=True,
        source_stability=True,
        location_stability=True,
    )
    assert not scorecard.empty
    assert decision["production_evidence"] == "INSUFFICIENT"
    assert decision["recommended_status"] == "CANDIDATE"


def test_reference_and_category_drift_are_development_only_and_report_unseen_rows():
    train = _training_frame()
    profile = build_reference_profile(
        train,
        np.linspace(2e6, 6e6, len(train)),
        target_column="price_model_value",
        population_name="DEVELOPMENT",
        uses_test=False,
    )
    shadow = train.iloc[:3].copy()
    shadow.loc[shadow.index[0], "source_code"] = "new-source"

    drift = category_drift_report(shadow, profile)

    source = drift.loc[drift["Feature"].eq("source_code")].iloc[0]
    assert profile["population"] == "DEVELOPMENT"
    assert profile["uses_test"] is False
    assert source["Unseen Rows"] == 1
    assert source["Unseen Row %"] == pytest.approx(100 / 3)


def test_shadow_run_persistence_is_append_only(tmp_path):
    prediction = pd.DataFrame({"rental_post_id": [1], "predicted_monthly_rent": [3e6]})
    tables = {"overall_metrics": pd.DataFrame([{"MAE": 1.0}])}
    metadata = {"model_id": "model-1", "validation_mode": HISTORICAL_DRY_RUN}

    first = persist_shadow_run(
        tmp_path, "historical-20261005-000001", metadata, prediction, tables
    )
    second = persist_shadow_run(
        tmp_path, "historical-20261005-000002", metadata, prediction, tables
    )

    assert first.exists() and second.exists() and first != second
    assert (first / "run_metadata.json").exists()
    assert (first / "predictions.parquet").exists()
    with pytest.raises(FileExistsError):
        persist_shadow_run(
            tmp_path, "historical-20261005-000001", metadata, prediction, tables
        )


def test_notebook_06_has_no_training_or_selection_calls():
    root = Path(__file__).resolve().parents[1]
    notebook = root / "notebooks" / "06_roombeacon_shadow_validation.ipynb"
    if not notebook.exists():
        pytest.fail("Notebook 06 has not been generated")
    payload = json.loads(notebook.read_text(encoding="utf-8"))
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in payload["cells"]
        if cell["cell_type"] == "code"
    )
    forbidden = [".fit(", "GridSearch", "RandomizedSearch", "cross_val", "lock_candidate("]
    for token in forbidden:
        assert token not in code
    assert code.index("predict_shadow(") < code.index("prepare_evaluation_population(")
    for index, cell in enumerate(payload["cells"]):
        if cell["cell_type"] == "code":
            compile("".join(cell.get("source", [])), f"shadow-cell-{index}", "exec")
        assert not any(output.get("output_type") == "error" for output in cell.get("outputs", []))


def test_residual_sign_convention():
    predictions = pd.DataFrame({
        "rental_post_id": [1, 2],
        "predicted_monthly_rent": [4_000_000.0, 2_000_000.0],
    })
    silver = pd.DataFrame({
        "rental_post_id": [1, 2],
        "price_model_value": [3_000_000.0, 3_000_000.0],
        "price_amount_clean": [3_000_000.0, 3_000_000.0],
        "price_quality_status": ["VALIDATED_EXISTING", "VALIDATED_EXISTING"],
        "price_target_trust_status": ["TRUSTED_EXISTING", "TRUSTED_EXISTING"],
        "price_model_suitability": ["SUPPORTED", "SUPPORTED"],
        "area_model_suitability": ["SUPPORTED", "SUPPORTED"],
        "area_value_clean": [20.0, 20.0],
        "listing_intent": ["RENT", "RENT"],
        "rental_scope": ["SINGLE_OR_ORDINARY_UNIT", "SINGLE_OR_ORDINARY_UNIT"],
        "title_clean": ["room", "room"],
    })
    eval_pop = prepare_evaluation_population(predictions, silver)
    eval_df = eval_pop.evaluation_predictions
    
    # Standard: residual = prediction - actual
    # Row 1: 4M - 3M = +1M (overprediction > 0)
    # Row 2: 2M - 3M = -1M (underprediction < 0)
    assert eval_df.loc[eval_df["rental_post_id"] == 1, "residual"].iloc[0] == 1_000_000.0
    assert eval_df.loc[eval_df["rental_post_id"] == 2, "residual"].iloc[0] == -1_000_000.0
    
    # Signed bias matches residual mean
    metrics = evaluate_shadow_predictions(eval_df)
    assert metrics["Signed Bias"] == 0.0
    assert metrics["Overprediction %"] == 50.0
    assert metrics["Underprediction %"] == 50.0


def test_price_bucket_order():
    frame = pd.DataFrame({
        "rental_post_id": [1, 2, 3, 4, 5],
        "actual_monthly_rent": [1_500_000, 3_000_000, 5_000_000, 8_000_000, 15_000_000],
        "predicted_monthly_rent": [2_000_000, 3_500_000, 5_500_000, 7_500_000, 12_000_000],
    })
    diag = price_bucket_diagnostics(frame)
    assert diag["Segment"].tolist() == list(PRICE_BUCKET_ORDER)


def test_area_bucket_order():
    frame = pd.DataFrame({
        "rental_post_id": [1, 2, 3, 4, 5],
        "area_value_clean": [10.0, 20.0, 30.0, 50.0, 100.0],
        "actual_monthly_rent": [2e6, 3e6, 4e6, 6e6, 10e6],
        "predicted_monthly_rent": [2e6, 3e6, 4e6, 6e6, 10e6],
    })
    diag = area_bucket_diagnostics(frame)
    assert diag["Segment"].tolist() == list(AREA_BUCKET_ORDER)


def test_location_ward_district_separation_and_missing_excluded():
    frame = pd.DataFrame({
        "rental_post_id": [1, 2, 3, 4],
        "ward_current": ["Phường A", "Phường B", None, "__MISSING__"],
        "district_text_extracted": ["Quận 1", None, "Quận 1", "__MISSING__"],
        "actual_monthly_rent": [3e6, 4e6, 5e6, 6e6],
        "predicted_monthly_rent": [3.5e6, 4.5e6, 5.5e6, 6.5e6],
    })
    wards = ward_diagnostics(frame, min_support=1, include_missing=False)
    assert "__MISSING__" not in wards["Segment"].tolist()
    assert set(wards["Segment"]).issubset({"Phường A", "Phường B"})

    districts = district_diagnostics(frame, min_support=1, include_missing=False)
    assert "__MISSING__" not in districts["Segment"].tolist()
    assert districts["Segment"].tolist() == ["Quận 1"]

    missing = missing_location_summary(frame)
    assert len(missing) == 2
    assert set(missing["Dimension"]) == {"Ward", "District"}


def test_readiness_scorecard_provisional_thresholds_and_status():
    scorecard, decision = build_readiness_scorecard(
        validation_mode=HISTORICAL_DRY_RUN,
        sample_rows=50_000,
        temporal_coverage_days=60,
        artifact_loaded=True,
        inference_contract_valid=True,
        no_leakage=True,
        unknown_categories_safe=True,
        prediction_sanity_pass=True,
        drift_within_threshold=True,
        core_market_error_stable=True,
        budget_calibration_acceptable=True,
        upper_tail_calibration_acceptable=True,
        source_stability=True,
        location_stability=True,
    )
    assert decision["model_readiness"] == "CANDIDATE"
    assert decision["deployment_lifecycle"] == "SHADOW"
    assert decision["production_evidence"] == "INSUFFICIENT"
    assert decision["threshold_governance"] == "PROVISIONAL_MONITORING_ONLY"
    
    # Requirements mention provisional threshold
    reqs = scorecard["Requirement"].tolist()
    assert any("Provisional" in r for r in reqs)


def test_area_inference_eligibility_inherits_semantic_suitability():
    from notebooks.utils.modeling_benchmark import build_inference_eligibility
    df = pd.DataFrame({
        "area_model_suitability": ["SUPPORTED", "REVIEW", "SUPPORTED", "SUPPORTED"],
        "area_value_clean": [25.0, 25.0, 0.0, -5.0],
        "listing_intent": ["RENT", "RENT", "RENT", "RENT"],
        "rental_scope": ["SINGLE_OR_ORDINARY_UNIT"] * 4,
    })
    masks = build_inference_eligibility(df)
    assert masks.final_eligible.tolist() == [True, False, False, False]

