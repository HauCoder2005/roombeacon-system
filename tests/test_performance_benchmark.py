"""Unit and integration tests for RoomBeacon performance benchmark infrastructure."""

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from notebooks.utils.performance_benchmark import (
    BENCHMARK_RANDOM_SEED,
    build_performance_scorecard,
    compute_latency_statistics,
    compute_throughput,
    get_benchmark_environment,
    get_champion_quality_context,
    get_process_memory_mb,
    hash_workload_ids,
    make_performance_run_id,
    persist_performance_run,
    run_base_benchmark,
    run_pipeline_stage_breakdown,
    run_robustness_benchmark,
    run_scaling_benchmark,
    run_standard_benchmark,
    sample_workload,
)
from notebooks.utils.shadow_validation import (
    F4_FEATURES,
    ID_COLUMN,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    build_inference_matrix,
    file_sha256,
    resolve_champion_artifact,
)


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "data" / "modeling" / "roombeacon_price_benchmark_v3"


@pytest.fixture(scope="module")
def champion():
    """Resolve and verify the locked champion artifact."""
    return resolve_champion_artifact(BENCHMARK_DIR)


@pytest.fixture(scope="module")
def sample_data():
    """Create deterministic synthetic inference-ready data."""
    np.random.seed(BENCHMARK_RANDOM_SEED)
    n = 200
    return pd.DataFrame({
        ID_COLUMN: range(1, n + 1),
        TIMESTAMP_COLUMN: ["2026-10-05T00:00:00Z"] * n,
        "area_value_clean": np.random.uniform(15.0, 120.0, size=n),
        "source_code": np.random.choice(["phongtro123", "cafeland", "mogi"], size=n),
        "ward_current": np.random.choice(["Phường Bến Nghé", "Phường 1", "Phường Tân Định"], size=n),
        "district_text_extracted": np.random.choice(["Quận 1", "Quận 3", "Quận 10"], size=n),
        "title_clean": ["Phòng trọ cho thuê giá tốt"] * n,
        "listing_intent": ["RENT"] * n,
        "rental_scope": ["SINGLE_OR_ORDINARY_UNIT"] * n,
        "area_model_suitability": ["SUPPORTED"] * n,
    })


def test_champion_artifact_resolution_and_hash(champion):
    """Verify champion resolves cleanly and SHA-256 matches metadata."""
    assert champion.metadata["model_family"] == "LightGBM Regressor"
    assert champion.metadata["target_transform"] == "RAW"
    assert champion.metadata["feature_names"] == list(F4_FEATURES)
    assert file_sha256(champion.artifact_path) == champion.metadata["artifact_sha256"]


def test_get_benchmark_environment():
    """Verify environment capture schema and fingerprint determinism."""
    env = get_benchmark_environment()
    assert "os" in env
    assert "processor" in env
    assert "logical_cpus" in env and env["logical_cpus"] > 0
    assert "total_ram_gb" in env and env["total_ram_gb"] > 0
    assert "packages" in env
    assert "lightgbm" in env["packages"]
    assert "environment_fingerprint" in env
    assert len(env["environment_fingerprint"]) == 16


def test_get_process_memory_mb():
    """Verify process RSS memory reporting is a positive float."""
    rss = get_process_memory_mb()
    assert isinstance(rss, float)
    assert rss > 10.0  # At least 10 MB in Python process


def test_compute_latency_statistics():
    """Verify percentile and statistical calculations on millisecond timings."""
    timings = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = compute_latency_statistics(timings)
    assert stats["count"] == 5
    assert stats["min_ms"] == 10.0
    assert stats["max_ms"] == 50.0
    assert stats["mean_ms"] == 30.0
    assert stats["p50_ms"] == 30.0
    assert stats["p95_ms"] == 48.0
    assert stats["iqr_ms"] == 20.0

    # Test empty input handling
    empty_stats = compute_latency_statistics([])
    assert empty_stats["count"] == 0
    assert empty_stats["p50_ms"] == 0.0


def test_compute_throughput():
    """Verify throughput calculations for normal and edge cases."""
    # 1000 rows in 100ms -> 10,000 rows/s
    thr = compute_throughput(1000, 100.0)
    assert np.isclose(thr, 10000.0)

    # 0 ms duration -> 0.0
    assert compute_throughput(100, 0.0) == 0.0
    # 0 rows -> 0.0
    assert compute_throughput(0, 50.0) == 0.0


def test_sample_workload_and_hash(sample_data):
    """Verify deterministic sampling and ID hashing."""
    s1 = sample_workload(sample_data, 50, seed=42)
    s2 = sample_workload(sample_data, 50, seed=42)
    assert len(s1) == 50
    assert s1[ID_COLUMN].tolist() == s2[ID_COLUMN].tolist()
    assert hash_workload_ids(s1) == hash_workload_ids(s2)

    # Full sample when size is None
    s_full = sample_workload(sample_data, None)
    assert len(s_full) == len(sample_data)


def test_build_inference_matrix_no_target_and_contract(champion, sample_data):
    """Verify target-free matrix construction and column preservation."""
    matrix = build_inference_matrix(sample_data, champion.metadata)
    assert matrix.columns.tolist() == list(F4_FEATURES)
    assert TARGET_COLUMN not in matrix.columns
    assert len(matrix) == len(sample_data)
    for col in ["source_code", "ward_current", "district_text_extracted"]:
        assert isinstance(matrix[col].dtype, pd.CategoricalDtype)


def test_run_base_benchmark(champion, sample_data):
    """Verify Level 1 BASE benchmark outputs valid schema and passes sanity."""
    res_df = run_base_benchmark(champion, sample_data, sizes=(1, 10, 50), seed=42)
    assert len(res_df) == 3
    assert "Feature Prep ms" in res_df.columns
    assert "Predict ms" in res_df.columns
    assert "Throughput (rows/s)" in res_df.columns
    assert (res_df["Sanity"] == "PASS").all()


def test_run_standard_benchmark(champion, sample_data):
    """Verify Level 2 STANDARD benchmark outputs required percentiles and timings."""
    reps_map = {1: (1, 5), 10: (1, 3), None: (1, 2)}
    res_df = run_standard_benchmark(
        champion,
        sample_data,
        workloads=(1, 10, None),
        repetitions_map=reps_map,
        seed=42,
    )
    assert len(res_df) == 3
    assert "Hot Path P50 ms" in res_df.columns
    assert "Hot Path P95 ms" in res_df.columns
    assert "Hot Path P99 ms" in res_df.columns
    assert "Hot Path Throughput (rows/s)" in res_df.columns
    assert "Hot Path ms / 1,000 rows" in res_df.columns
    assert (res_df["Hot Path Throughput (rows/s)"] > 0).all()


def test_run_pipeline_stage_breakdown(champion, sample_data):
    """Verify 7-stage breakdown covers all stages and sums logically."""
    stages_df = run_pipeline_stage_breakdown(
        champion, sample_data, sample_size=50, repetitions=2, seed=42
    )
    assert len(stages_df) == 7
    expected_stages = [
        "1. Input selection",
        "2. Schema validation",
        "3. Inference eligibility",
        "4. F4 feature construction",
        "5. Categorical preparation",
        "6. LightGBM predict",
        "7. Prediction sanity & post-processing",
    ]
    assert stages_df["Stage"].tolist() == expected_stages
    assert np.isclose(stages_df["Share of Full Pipeline %"].sum(), 100.0, atol=2.0)


def test_run_scaling_benchmark(champion, sample_data):
    """Verify scaling benchmark output schema and positive throughput."""
    scaling_df = run_scaling_benchmark(
        champion, sample_data, sizes=(1, 10, 50), repetitions=2, seed=42
    )
    assert len(scaling_df) == 3
    assert "Median Hot Path ms" in scaling_df.columns
    assert "Hot Path Throughput (rows/s)" in scaling_df.columns
    assert "RSS MB" in scaling_df.columns
    assert (scaling_df["Median Hot Path ms"] > 0).all()


def test_run_robustness_benchmark(champion, sample_data):
    """Verify that all 8 valid edge cases pass without crashing or invalid values."""
    rob_df = run_robustness_benchmark(champion, sample_data)
    assert len(rob_df) == 8
    assert (rob_df["Status"] == "PASS").all()
    assert rob_df["Predicted Monthly Rent"].notna().all()
    assert (rob_df["Predicted Monthly Rent"] > 0).all()


def test_persistence_and_run_id_generation(tmp_path, champion, sample_data):
    """Verify deterministic run ID format and append-only directory creation."""
    env = get_benchmark_environment()
    run_id = make_performance_run_id(
        champion.metadata["model_id"],
        env["environment_fingerprint"],
        datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc),
    )
    assert run_id.startswith("perf-0b0c9d9fa450-")
    assert run_id.endswith("-20261005T140000Z")

    dummy_payload = {
        "environment": env,
        "artifact_metadata": champion.metadata,
        "base_results": pd.DataFrame([{"Workload": "1 row", "Throughput": 100.0}]),
        "summary": {"scorecard": "COMPLETE"},
    }

    run_path = persist_performance_run(tmp_path, run_id, dummy_payload)
    assert run_path.is_dir()
    assert (run_path / "environment.json").is_file()
    assert (run_path / "artifact_metadata.json").is_file()
    assert (run_path / "base_results.csv").is_file()
    assert (run_path / "summary.json").is_file()
    assert (run_path / "manifest.json").is_file()

    # Verify manifest hashes
    manifest = json.loads((run_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_id
    assert "base_results.csv" in manifest["files"]
    assert manifest["files"]["base_results.csv"] == file_sha256(run_path / "base_results.csv")


def test_get_champion_quality_context():
    """Verify dynamic loading of model quality context from Benchmark V3 final_test.csv."""
    ctx = get_champion_quality_context(BENCHMARK_DIR)
    assert "test_mae" in ctx
    assert ctx["test_mae"] > 0
    assert "test_median_ae" in ctx
    assert "test_rmse" in ctx
    assert "test_r2" in ctx
    assert ctx["test_r2"] > 0
    assert "baseline_model" in ctx
    assert ctx["baseline_model"] == "Hierarchical Segment Median"
    assert "baseline_improvement_vnd" in ctx


def test_build_performance_scorecard():
    """Verify scorecard generator reports COMPLETE and IN-PROCESS PERFORMANCE BASELINE = ESTABLISHED."""
    base_df = pd.DataFrame([{"Sanity": "PASS"}])
    std_df = pd.DataFrame([{"Hot Path Throughput (rows/s)": 150000.0}])
    adv_summary = {"robustness_pass": True, "stability_cv": 3.5}

    sc = build_performance_scorecard(base_df, std_df, adv_summary)
    assert len(sc) == 4
    statuses = sc.set_index("Benchmark Level")["Status"].to_dict()
    assert statuses["BASE"] == "COMPLETE"
    assert statuses["STANDARD"] == "COMPLETE"
    assert statuses["ADVANCED"] == "COMPLETE"
    assert statuses["OVERALL"] == "IN-PROCESS PERFORMANCE BASELINE = ESTABLISHED"


def test_performance_benchmark_notebook_architecture():
    """Verify Notebook 07 satisfies architectural and behavioral invariants."""
    nb_path = ROOT / "notebooks" / "07_roombeacon_performance_benchmark.ipynb"
    assert nb_path.is_file(), "07_roombeacon_performance_benchmark.ipynb must exist"
    nb = json.loads(nb_path.read_text(encoding="utf-8"))

    text = "\n".join("".join(c.get("source", [])) for c in nb["cells"])
    code_text = "\n".join(
        "".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type") == "code"
    )

    expected_headings = [
        "## 01. Purpose and Frozen Champion Contract",
        "## 02. Benchmark Environment",
        "## 03. Load and Verify Champion Artifact",
        "## 04. Build Target-Free Benchmark Population",
        "## 05. Benchmark Methodology",
        "## 06. BASE Benchmark",
        "## 07. STANDARD Benchmark",
        "## 08. ADVANCED Benchmark",
        "## 09. Cold vs Warm Inference",
        "## 10. Batch Scaling",
        "## 11. Pipeline Stage Breakdown",
        "## 12. Memory Profile",
        "## 13. CPU / Runtime Resource Profile",
        "## 14. Latency Distribution",
        "## 15. Throughput Analysis",
        "## 16. Repeated-Run Stability",
        "## 17. Robustness Inputs",
        "## 18. Optional Concurrency Benchmark",
        "## 19. Persist Benchmark Artifacts",
        "## 20. Performance Baseline Summary",
        "## 21. Engineering Readiness",
    ]
    positions = [text.index(heading) for heading in expected_headings]
    assert positions == sorted(positions), "Headings must appear in strict numerical order"
    assert "## 00." not in text, "No 00 section permitted"

    for forbidden in [
        ".fit(", "GridSearch", "RandomizedSearch",
        "lock_candidate(", "candidate_pool", "model-family benchmark",
    ]:
        assert forbidden not in code_text, f"Forbidden modeling keyword '{forbidden}' found in code"

    assert "resolve_champion_artifact" in code_text
    assert "run_base_benchmark" in code_text
    assert "run_standard_benchmark" in code_text
    assert "run_scaling_benchmark" in code_text
    assert "persist_performance_run" in code_text
    assert "build_performance_scorecard" in code_text


def test_performance_benchmark_narrative_semantics():
    """Verify Notebook 07 does not contain overclaims or unsupported causal assertions."""
    nb_path = ROOT / "notebooks" / "07_roombeacon_performance_benchmark.ipynb"

    for path in [nb_path]:
        text = path.read_text(encoding="utf-8")

        # Prohibited overclaims and unsupported causal assertions
        prohibited_phrases = [
            "spent entirely",
            "all cores saturated",
            "fully utilizes all cores",
            "all cores are saturated",
            "GIL contention",
            "GIL lock contention",
            "HTTP SLA",
            "Leak-Free Memory Profile",
            "zero memory leak",
        ]
        for phrase in prohibited_phrases:
            assert phrase.lower() not in text.lower(), (
                f"Prohibited overclaim phrase '{phrase}' found in {path.name}"
            )

        # Required precise semantic terminology
        assert "IN-PROCESS PERFORMANCE BASELINE = ESTABLISHED" in text
        assert "descriptive comparison rather than an exact additive decomposition" in text
        assert "No material persistent RSS growth was observed across the measured repeated-run window" in text


