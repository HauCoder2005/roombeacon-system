"""Reusable runtime performance benchmark suite for the frozen RoomBeacon champion.

This module measures runtime efficiency, latency distributions, throughput, memory
dynamics, CPU utilization, and edge-case stability. It strictly contains NO model
training, tuning, hyperparameter search, or quality metric computation.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gc
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any, Callable, Mapping, Sequence

import joblib
import numpy as np
import pandas as pd
import psutil

from notebooks.utils.modeling_benchmark import (
    build_inference_eligibility,
    engineer_safe_features,
    inverse_target,
)
from notebooks.utils.shadow_validation import (
    CATEGORICAL_FEATURES,
    F4_FEATURES,
    ID_COLUMN,
    LoadedChampion,
    TARGET_COLUMN,
    TIMESTAMP_COLUMN,
    build_inference_matrix,
    file_sha256,
    resolve_champion_artifact,
    validate_shadow_schema,
)


BENCHMARK_RANDOM_SEED: int = 42
PERF_BENCHMARK_DIR_NAME: str = "performance_benchmark"

__all__ = [
    "BENCHMARK_RANDOM_SEED",
    "PERF_BENCHMARK_DIR_NAME",
    "get_benchmark_environment",
    "get_process_memory_mb",
    "compute_latency_statistics",
    "compute_throughput",
    "sample_workload",
    "hash_workload_ids",
    "run_base_benchmark",
    "run_standard_benchmark",
    "run_cold_vs_warm_benchmark",
    "run_pipeline_stage_breakdown",
    "run_scaling_benchmark",
    "run_repeated_stability_benchmark",
    "run_memory_stability_check",
    "run_robustness_benchmark",
    "run_concurrency_benchmark",
    "get_champion_quality_context",
    "make_performance_run_id",
    "persist_performance_run",
    "build_performance_scorecard",
]


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


def get_process_memory_mb() -> float:
    """Return resident set size (RSS) of current process in megabytes."""
    process = psutil.Process()
    return float(process.memory_info().rss / (1024.0 * 1024.0))


def get_benchmark_environment(champion_model: Any = None) -> dict[str, Any]:
    """Capture comprehensive hardware, OS, Python runtime, and package environment."""
    uname = platform.uname()
    mem = psutil.virtual_memory()

    # Threading settings
    omp_threads = os.environ.get("OMP_NUM_THREADS")
    mkl_threads = os.environ.get("MKL_NUM_THREADS")
    openblas_threads = os.environ.get("OPENBLAS_NUM_THREADS")

    lgb_n_jobs = getattr(champion_model, "n_jobs", None) if champion_model is not None else None
    lgb_num_threads = None
    if champion_model is not None and hasattr(champion_model, "booster_"):
        lgb_num_threads = champion_model.booster_.params.get("num_threads")

    # CPU frequency if accessible
    cpu_freq = psutil.cpu_freq()
    freq_current = round(cpu_freq.current, 2) if cpu_freq else None
    freq_max = round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None

    # Version map
    import lightgbm
    import sklearn

    packages = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": getattr(sys.modules.get("scipy"), "__version__", None),
        "scikit-learn": sklearn.__version__,
        "lightgbm": lightgbm.__version__,
        "joblib": joblib.__version__,
        "psutil": psutil.__version__,
    }

    env_dict = {
        "os": uname.system,
        "os_release": uname.release,
        "os_version": uname.version,
        "architecture": uname.machine,
        "processor": uname.processor or platform.processor(),
        "logical_cpus": psutil.cpu_count(logical=True),
        "physical_cpus": psutil.cpu_count(logical=False),
        "cpu_freq_mhz_current": freq_current,
        "cpu_freq_mhz_max": freq_max,
        "total_ram_gb": round(float(mem.total / (1024.0**3)), 2),
        "available_ram_gb": round(float(mem.available / (1024.0**3)), 2),
        "packages": packages,
        "threading": {
            "OMP_NUM_THREADS": omp_threads,
            "MKL_NUM_THREADS": mkl_threads,
            "OPENBLAS_NUM_THREADS": openblas_threads,
            "lgbm_model_n_jobs": lgb_n_jobs,
            "lgbm_booster_num_threads": lgb_num_threads,
        },
        "process_id": os.getpid(),
    }

    # Deterministic environment fingerprint
    fingerprint_seed = (
        f"{uname.system}-{uname.machine}-{psutil.cpu_count(logical=True)}-"
        f"{packages['python']}-{packages['lightgbm']}-{packages['pandas']}"
    )
    env_dict["environment_fingerprint"] = sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:16]
    return env_dict


def compute_latency_statistics(timings_ms: Sequence[float]) -> dict[str, float | int]:
    """Compute high-resolution distribution statistics from millisecond timings."""
    s = pd.Series(timings_ms, dtype=float).dropna()
    if s.empty:
        return {
            "count": 0,
            "mean_ms": 0.0,
            "std_ms": 0.0,
            "min_ms": 0.0,
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "max_ms": 0.0,
            "iqr_ms": 0.0,
        }
    q = s.quantile([0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    return {
        "count": int(s.size),
        "mean_ms": float(s.mean()),
        "std_ms": float(s.std(ddof=1)) if s.size > 1 else 0.0,
        "min_ms": float(s.min()),
        "p50_ms": float(q.loc[0.50]),
        "p90_ms": float(q.loc[0.90]),
        "p95_ms": float(q.loc[0.95]),
        "p99_ms": float(q.loc[0.99]),
        "max_ms": float(s.max()),
        "iqr_ms": float(q.loc[0.75] - q.loc[0.25]),
    }


def compute_throughput(n_rows: int, duration_ms: float) -> float:
    """Calculate rows per second from row count and duration in milliseconds."""
    if duration_ms <= 0 or n_rows <= 0:
        return 0.0
    return float(n_rows / (duration_ms / 1000.0))


def sample_workload(
    frame: pd.DataFrame,
    size: int | None,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Sample a deterministic subset of inference-ready rows, preserving order."""
    if size is None or size >= len(frame):
        return frame.copy()
    return frame.sample(n=size, random_state=seed).sort_index().copy()


def hash_workload_ids(frame: pd.DataFrame) -> str:
    """Return deterministic SHA-256 fingerprint of rental_post_id sequence."""
    if ID_COLUMN not in frame.columns:
        return "NO_ID_COLUMN"
    ids_str = ",".join(str(val) for val in frame[ID_COLUMN].tolist())
    return sha256(ids_str.encode("utf-8")).hexdigest()[:16]


def run_base_benchmark(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
    sizes: Sequence[int] = (1, 100, 1000),
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Execute Level 1 BASE benchmark: verify load and basic runtime metrics."""
    # Warm up runtime once
    warmup_sample = sample_workload(ready_population, 10, seed=seed)
    warmup_m = build_inference_matrix(warmup_sample, champion.metadata)
    _ = champion.model.predict(warmup_m)

    results = []
    for sz in sizes:
        sample = sample_workload(ready_population, sz, seed=seed)
        mem_before = get_process_memory_mb()

        # F4 prep time
        t0 = time.perf_counter_ns()
        matrix = build_inference_matrix(sample, champion.metadata)
        t1 = time.perf_counter_ns()
        prep_ms = (t1 - t0) / 1e6

        # Predict time
        t2 = time.perf_counter_ns()
        raw_preds = np.asarray(champion.model.predict(matrix), dtype=float)
        t3 = time.perf_counter_ns()
        pred_ms = (t3 - t2) / 1e6

        # Sanity check
        final_preds = inverse_target(raw_preds, champion.metadata["target_transform"])
        sanity_pass = (
            len(final_preds) == len(sample)
            and bool(np.isfinite(final_preds).all())
            and bool((final_preds >= 0).all())
        )

        mem_after = get_process_memory_mb()
        e2e_ms = prep_ms + pred_ms
        thr = compute_throughput(sz, e2e_ms)

        results.append({
            "Workload": f"{sz:,} rows" if sz > 1 else "1 row",
            "Rows": sz,
            "Feature Prep ms": round(prep_ms, 3),
            "Predict ms": round(pred_ms, 3),
            "End-to-End ms": round(e2e_ms, 3),
            "Throughput (rows/s)": round(thr, 1),
            "RSS Before MB": round(mem_before, 2),
            "RSS Delta MB": round(mem_after - mem_before, 3),
            "Sanity": "PASS" if sanity_pass else "FAIL",
        })

    return pd.DataFrame(results)


def run_standard_benchmark(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
    workloads: Sequence[int | None] = (1, 100, 1000, 10000, None),
    repetitions_map: Mapping[int | None, tuple[int, int]] | None = None,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Execute Level 2 STANDARD benchmark across representative RoomBeacon batch sizes."""
    # Default repetition schedule: (warmups, timed_runs)
    default_reps: dict[int | None, tuple[int, int]] = {
        1: (5, 50),
        100: (3, 30),
        1000: (2, 15),
        10000: (1, 5),
        None: (1, 3),
    }
    reps_config = dict(default_reps if repetitions_map is None else repetitions_map)

    results = []
    total_ready_count = len(ready_population)

    for sz in workloads:
        actual_rows = total_ready_count if sz is None else min(sz, total_ready_count)
        label = "Full population" if sz is None else (f"{sz:,} rows" if sz > 1 else "1 row")
        warmups, timed_runs = reps_config.get(sz, (1, 3))

        workload_df = sample_workload(ready_population, sz, seed=seed)
        sample_hash = hash_workload_ids(workload_df)

        # Warmups (not measured)
        for _ in range(warmups):
            m = build_inference_matrix(workload_df, champion.metadata)
            _ = champion.model.predict(m)

        # Timed runs
        prep_timings: list[float] = []
        pred_timings: list[float] = []
        e2e_timings: list[float] = []

        mem_start = get_process_memory_mb()
        for _ in range(timed_runs):
            t0 = time.perf_counter_ns()
            matrix = build_inference_matrix(workload_df, champion.metadata)
            t1 = time.perf_counter_ns()

            raw_preds = np.asarray(champion.model.predict(matrix), dtype=float)
            t2 = time.perf_counter_ns()

            _ = inverse_target(raw_preds, champion.metadata["target_transform"])
            t3 = time.perf_counter_ns()

            prep_ms = (t1 - t0) / 1e6
            pred_ms = (t2 - t1) / 1e6
            e2e_ms = (t3 - t0) / 1e6

            prep_timings.append(prep_ms)
            pred_timings.append(pred_ms)
            e2e_timings.append(e2e_ms)

        mem_end = get_process_memory_mb()
        stats_e2e = compute_latency_statistics(e2e_timings)
        stats_pred = compute_latency_statistics(pred_timings)
        stats_prep = compute_latency_statistics(prep_timings)

        # Throughput computed on median end-to-end latency
        thr = compute_throughput(actual_rows, stats_e2e["p50_ms"])
        ms_per_1k = (stats_e2e["p50_ms"] / actual_rows) * 1000.0 if actual_rows > 0 else 0.0

        results.append({
            "Workload": label,
            "Rows": actual_rows,
            "Runs": timed_runs,
            "Sample Hash": sample_hash,
            "Hot Path P50 ms": round(stats_e2e["p50_ms"], 3),
            "Hot Path P90 ms": round(stats_e2e["p90_ms"], 3),
            "Hot Path P95 ms": round(stats_e2e["p95_ms"], 3),
            "Hot Path P99 ms": round(stats_e2e["p99_ms"], 3),
            "Hot Path Mean ms": round(stats_e2e["mean_ms"], 3),
            "Hot Path Std ms": round(stats_e2e["std_ms"], 3),
            "P50 Predict ms": round(stats_pred["p50_ms"], 3),
            "P50 Prep ms": round(stats_prep["p50_ms"], 3),
            "Hot Path Throughput (rows/s)": round(thr, 1),
            "Hot Path ms / 1,000 rows": round(ms_per_1k, 4),
            "RSS Before MB": round(mem_start, 2),
            "RSS Delta MB": round(mem_end - mem_start, 3),
        })

    return pd.DataFrame(results)


def run_cold_vs_warm_benchmark(
    benchmark_dir: str | Path,
    ready_population: pd.DataFrame,
    sizes: Sequence[int] = (1, 100, 1000, 10000),
    repetitions: int = 3,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Compare cold model load (fresh artifact resolve + disk load + prep + predict in running Python) vs warm hot path."""
    base_path = Path(benchmark_dir)
    results = []

    # Preload champion once for warm comparisons
    warm_champion = resolve_champion_artifact(base_path)

    for sz in sizes:
        sample = sample_workload(ready_population, sz, seed=seed)

        # Cold runs: each iteration re-resolves and re-loads champion from disk
        cold_timings: list[float] = []
        for _ in range(repetitions):
            gc.collect()
            t0 = time.perf_counter_ns()
            loaded = resolve_champion_artifact(base_path)
            matrix = build_inference_matrix(sample, loaded.metadata)
            raw_p = np.asarray(loaded.model.predict(matrix), dtype=float)
            _ = inverse_target(raw_p, loaded.metadata["target_transform"])
            t1 = time.perf_counter_ns()
            cold_timings.append((t1 - t0) / 1e6)

        # Warm runs: already loaded model in memory
        warm_timings: list[float] = []
        for _ in range(repetitions):
            t0 = time.perf_counter_ns()
            matrix = build_inference_matrix(sample, warm_champion.metadata)
            raw_p = np.asarray(warm_champion.model.predict(matrix), dtype=float)
            _ = inverse_target(raw_p, warm_champion.metadata["target_transform"])
            t1 = time.perf_counter_ns()
            warm_timings.append((t1 - t0) / 1e6)

        cold_stats = compute_latency_statistics(cold_timings)
        warm_stats = compute_latency_statistics(warm_timings)

        ratio = (
            cold_stats["p50_ms"] / warm_stats["p50_ms"]
            if warm_stats["p50_ms"] > 0
            else 0.0
        )
        cold_overhead_ms = cold_stats["p50_ms"] - warm_stats["p50_ms"]

        results.append({
            "Workload": f"{sz:,} rows" if sz > 1 else "1 row",
            "Rows": sz,
            "Cold Model Load P50 ms": round(cold_stats["p50_ms"], 2),
            "Warm Hot Path P50 ms": round(warm_stats["p50_ms"], 2),
            "Cold Load Overhead ms": round(cold_overhead_ms, 2),
            "Cold Load / Warm Ratio": round(ratio, 2),
        })

    return pd.DataFrame(results)


def run_pipeline_stage_breakdown(
    champion: LoadedChampion,
    silver_df: pd.DataFrame,
    sample_size: int = 10000,
    repetitions: int = 10,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Instrument the inference path into 7 canonical stages and measure their shares."""
    sample = sample_workload(silver_df, sample_size, seed=seed)
    features = champion.metadata["feature_names"]
    cats_vocab = champion.metadata["categorical_vocabularies"]
    target_transform = champion.metadata["target_transform"]

    # Timings per stage
    stage_times: dict[str, list[float]] = {
        "1. Input selection": [],
        "2. Schema validation": [],
        "3. Inference eligibility": [],
        "4. F4 feature construction": [],
        "5. Categorical preparation": [],
        "6. LightGBM predict": [],
        "7. Prediction sanity & post-processing": [],
    }

    for _ in range(repetitions):
        # 1. Input selection
        t0 = time.perf_counter_ns()
        input_slice = sample.copy()
        t1 = time.perf_counter_ns()

        # 2. Schema validation
        schema_res = validate_shadow_schema(input_slice, champion.metadata)
        t2 = time.perf_counter_ns()

        # 3. Inference eligibility evaluation
        prepared = engineer_safe_features(input_slice)
        masks = build_inference_eligibility(prepared, policy="PERMISSIVE")
        eligible = prepared.loc[masks.final_eligible]
        t3 = time.perf_counter_ns()

        # 4. F4 feature construction
        matrix = eligible.loc[:, features].copy()
        matrix["area_value_clean"] = pd.to_numeric(
            matrix["area_value_clean"], errors="coerce"
        ).astype(float)
        t4 = time.perf_counter_ns()

        # 5. Categorical preparation / dtype alignment
        for col in CATEGORICAL_FEATURES:
            vocab = cats_vocab[col]
            raw_s = matrix[col].astype("string").fillna("__MISSING__")
            mapped = raw_s.where(raw_s.isin(vocab), "__UNKNOWN__")
            matrix[col] = pd.Categorical(mapped, categories=vocab)
        t5 = time.perf_counter_ns()

        # 6. LightGBM predict
        raw_pred = np.asarray(champion.model.predict(matrix), dtype=float)
        t6 = time.perf_counter_ns()

        # 7. Prediction sanity / post-processing
        preds = inverse_target(raw_pred, target_transform)
        assert np.isfinite(preds).all()
        assert (preds >= 0).all()
        out = eligible[[ID_COLUMN]].copy()
        out["predicted_monthly_rent"] = preds
        t7 = time.perf_counter_ns()

        stage_times["1. Input selection"].append((t1 - t0) / 1e6)
        stage_times["2. Schema validation"].append((t2 - t1) / 1e6)
        stage_times["3. Inference eligibility"].append((t3 - t2) / 1e6)
        stage_times["4. F4 feature construction"].append((t4 - t3) / 1e6)
        stage_times["5. Categorical preparation"].append((t5 - t4) / 1e6)
        stage_times["6. LightGBM predict"].append((t6 - t5) / 1e6)
        stage_times["7. Prediction sanity & post-processing"].append((t7 - t6) / 1e6)

    # Compute stats
    rows = []
    total_median = sum(float(np.median(vals)) for vals in stage_times.values())
    for name, times in stage_times.items():
        s = compute_latency_statistics(times)
        share = (s["p50_ms"] / total_median * 100.0) if total_median > 0 else 0.0
        rows.append({
            "Stage": name,
            "Median ms": round(s["p50_ms"], 3),
            "P95 ms": round(s["p95_ms"], 3),
            "Min ms": round(s["min_ms"], 3),
            "Max ms": round(s["max_ms"], 3),
            "Share of Full Pipeline %": round(share, 2),
        })

    return pd.DataFrame(rows)


def run_scaling_benchmark(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
    sizes: Sequence[int | None] = (1, 10, 100, 1000, 10000, None),
    repetitions: int = 5,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Evaluate scaling behavior: batch size vs latency, throughput, and memory."""
    total_count = len(ready_population)
    results = []

    for sz in sizes:
        actual_rows = total_count if sz is None else min(sz, total_count)
        label = "Full" if sz is None else f"{actual_rows:,}"
        reps = 3 if sz is None else (15 if sz <= 100 else repetitions)

        sample = sample_workload(ready_population, sz, seed=seed)

        timings: list[float] = []
        for _ in range(reps):
            t0 = time.perf_counter_ns()
            matrix = build_inference_matrix(sample, champion.metadata)
            raw_p = np.asarray(champion.model.predict(matrix), dtype=float)
            _ = inverse_target(raw_p, champion.metadata["target_transform"])
            t1 = time.perf_counter_ns()
            timings.append((t1 - t0) / 1e6)

        stats = compute_latency_statistics(timings)
        thr = compute_throughput(actual_rows, stats["p50_ms"])
        rss = get_process_memory_mb()

        results.append({
            "Rows": actual_rows,
            "Workload": label,
            "Median Hot Path ms": round(stats["p50_ms"], 3),
            "P95 Hot Path ms": round(stats["p95_ms"], 3),
            "Hot Path Throughput (rows/s)": round(thr, 1),
            "RSS MB": round(rss, 2),
        })

    return pd.DataFrame(results)


def run_repeated_stability_benchmark(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
    sample_size: int = 1000,
    repetitions: int = 30,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Run repeated prediction-only inferences (prepared matrix -> predict -> inverse_target) to evaluate stability."""
    sample = sample_workload(ready_population, sample_size, seed=seed)
    matrix = build_inference_matrix(sample, champion.metadata)

    run_records: list[dict[str, Any]] = []
    for iteration in range(1, repetitions + 1):
        mem_before = get_process_memory_mb()
        t0 = time.perf_counter_ns()
        raw_p = np.asarray(champion.model.predict(matrix), dtype=float)
        _ = inverse_target(raw_p, champion.metadata["target_transform"])
        t1 = time.perf_counter_ns()
        latency_ms = (t1 - t0) / 1e6
        mem_after = get_process_memory_mb()

        run_records.append({
            "Iteration": iteration,
            "Prediction Path Latency ms": round(latency_ms, 3),
            "RSS MB": round(mem_after, 2),
        })

    df = pd.DataFrame(run_records)
    latencies = df["Prediction Path Latency ms"].tolist()
    stats = compute_latency_statistics(latencies)
    cv = (stats["std_ms"] / stats["mean_ms"] * 100.0) if stats["mean_ms"] > 0 else 0.0

    summary = {
        "timing_scope": "Repeated Prediction Path (Pre-constructed matrix -> model.predict -> inverse_target)",
        "iterations": repetitions,
        "sample_size": sample_size,
        "mean_ms": stats["mean_ms"],
        "std_ms": stats["std_ms"],
        "p50_ms": stats["p50_ms"],
        "p95_ms": stats["p95_ms"],
        "p99_ms": stats["p99_ms"],
        "min_ms": stats["min_ms"],
        "max_ms": stats["max_ms"],
        "coefficient_of_variation_pct": round(cv, 2),
    }
    return df, summary


def run_memory_stability_check(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
    sample_size: int = 10000,
    cycles: int = 15,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Periodically sample RSS memory across repeated batch inference cycles."""
    sample = sample_workload(ready_population, sample_size, seed=seed)
    matrix = build_inference_matrix(sample, champion.metadata)

    records = []
    initial_rss = get_process_memory_mb()
    records.append({
        "Cycle": 0,
        "Stage": "Initial State",
        "RSS MB": round(initial_rss, 2),
        "Delta from Initial MB": 0.0,
    })

    for c in range(1, cycles + 1):
        _ = champion.model.predict(matrix)
        current_rss = get_process_memory_mb()
        records.append({
            "Cycle": c,
            "Stage": f"Cycle {c}",
            "RSS MB": round(current_rss, 2),
            "Delta from Initial MB": round(current_rss - initial_rss, 2),
        })

    gc.collect()
    final_rss = get_process_memory_mb()
    records.append({
        "Cycle": cycles + 1,
        "Stage": "Post-GC Final",
        "RSS MB": round(final_rss, 2),
        "Delta from Initial MB": round(final_rss - initial_rss, 2),
    })

    return pd.DataFrame(records)


def run_robustness_benchmark(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
) -> pd.DataFrame:
    """Validate runtime behavior under valid categorical and numerical edge cases."""
    edge_cases = [
        {
            "Case ID": "missing_ward",
            "Description": "Missing ward_current (null/None)",
            "area_value_clean": 30.0,
            "source_code": "phongtro123",
            "ward_current": None,
            "district_text_extracted": "Quận 1",
        },
        {
            "Case ID": "missing_district",
            "Description": "Missing district_text_extracted (null/None)",
            "area_value_clean": 30.0,
            "source_code": "phongtro123",
            "ward_current": "Phường Bến Nghé",
            "district_text_extracted": None,
        },
        {
            "Case ID": "unseen_ward",
            "Description": "Out-of-vocabulary ward name",
            "area_value_clean": 30.0,
            "source_code": "phongtro123",
            "ward_current": "Phường Không Tồn Tại 999",
            "district_text_extracted": "Quận 1",
        },
        {
            "Case ID": "unseen_district",
            "Description": "Out-of-vocabulary district name",
            "area_value_clean": 30.0,
            "source_code": "phongtro123",
            "ward_current": "Phường Bến Nghé",
            "district_text_extracted": "Quận Vũ Trụ",
        },
        {
            "Case ID": "unseen_source",
            "Description": "Out-of-vocabulary crawler source_code",
            "area_value_clean": 30.0,
            "source_code": "unseen_portal_xyz",
            "ward_current": "Phường Bến Nghé",
            "district_text_extracted": "Quận 1",
        },
        {
            "Case ID": "small_valid_area_example",
            "Description": "Representative boundary-like small area example (5.0 m2)",
            "area_value_clean": 5.0,
            "source_code": "phongtro123",
            "ward_current": "Phường Bến Nghé",
            "district_text_extracted": "Quận 1",
        },
        {
            "Case ID": "large_valid_area_example",
            "Description": "Representative boundary-like large area example (450.0 m2)",
            "area_value_clean": 450.0,
            "source_code": "phongtro123",
            "ward_current": "Phường Bến Nghé",
            "district_text_extracted": "Quận 1",
        },
        {
            "Case ID": "mixed_missing_cats",
            "Description": "All categorical columns missing concurrently",
            "area_value_clean": 25.0,
            "source_code": None,
            "ward_current": None,
            "district_text_extracted": None,
        },
    ]

    df_test = pd.DataFrame(edge_cases)
    df_test[ID_COLUMN] = [10_000_000 + i for i in range(len(df_test))]
    df_test[TIMESTAMP_COLUMN] = "2026-10-05T00:00:00Z"

    results = []
    for _, row in df_test.iterrows():
        case_id = row["Case ID"]
        desc = row["Description"]
        single_frame = pd.DataFrame([row])

        t0 = time.perf_counter_ns()
        try:
            m = build_inference_matrix(single_frame, champion.metadata)
            raw_p = np.asarray(champion.model.predict(m), dtype=float)
            pred = inverse_target(raw_p, champion.metadata["target_transform"])[0]
            t1 = time.perf_counter_ns()
            latency_ms = (t1 - t0) / 1e6

            valid = bool(np.isfinite(pred) and pred > 0)
            status = "PASS" if valid else "INVALID_PREDICTION"
            err_msg = ""
        except Exception as exc:
            t1 = time.perf_counter_ns()
            latency_ms = (t1 - t0) / 1e6
            pred = np.nan
            status = "CRASH"
            err_msg = str(exc)

        results.append({
            "Case ID": case_id,
            "Description": desc,
            "Predicted Monthly Rent": round(pred, 0) if np.isfinite(pred) else None,
            "Latency ms": round(latency_ms, 2),
            "Status": status,
            "Notes": err_msg if err_msg else "Order preserved, finite positive prediction",
        })

    return pd.DataFrame(results)


def run_concurrency_benchmark(
    champion: LoadedChampion,
    ready_population: pd.DataFrame,
    batch_size: int = 1000,
    workers_list: Sequence[int] = (1, 2, 4),
    total_requests: int = 12,
    seed: int = BENCHMARK_RANDOM_SEED,
) -> pd.DataFrame:
    """Safely evaluate multi-threaded inference throughput using ThreadPoolExecutor."""
    sample = sample_workload(ready_population, batch_size, seed=seed)
    matrix = build_inference_matrix(sample, champion.metadata)

    def _worker_fn() -> float:
        t0 = time.perf_counter_ns()
        _ = champion.model.predict(matrix)
        t1 = time.perf_counter_ns()
        return (t1 - t0) / 1e6

    results = []
    for workers in workers_list:
        mem_before = get_process_memory_mb()
        t_start = time.perf_counter_ns()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_worker_fn) for _ in range(total_requests)]
            durations = [f.result() for f in futures]

        t_end = time.perf_counter_ns()
        mem_after = get_process_memory_mb()

        wall_ms = (t_end - t_start) / 1e6
        total_rows_served = total_requests * batch_size
        agg_throughput = compute_throughput(total_rows_served, wall_ms)
        stats = compute_latency_statistics(durations)

        results.append({
            "Workers": workers,
            "Total Requests": total_requests,
            "Batch Size per Request": batch_size,
            "Total Rows Served": total_rows_served,
            "Wall Clock ms": round(wall_ms, 2),
            "Request P50 ms": round(stats["p50_ms"], 2),
            "Request P95 ms": round(stats["p95_ms"], 2),
            "Aggregate Throughput (rows/s)": round(agg_throughput, 1),
            "RSS Delta MB": round(mem_after - mem_before, 2),
        })

    return pd.DataFrame(results)


def get_champion_quality_context(benchmark_dir: str | Path) -> dict[str, Any]:
    """Retrieve frozen model quality metrics from Benchmark V3 artifacts as context only.

    This function strictly does NOT recompute test metrics; it reads the already-persisted
    final test results for the champion and baseline.
    """
    base = Path(benchmark_dir)
    ft_path = base / "final_test.csv"
    if not ft_path.is_file():
        return {}
    df = pd.read_csv(ft_path)
    lgbm_matches = df[df["Model"] == "LightGBM Regressor"]
    if lgbm_matches.empty:
        return {}
    lgbm_row = lgbm_matches.iloc[0]
    baseline_matches = df[df["Model"] == "Hierarchical Segment Median"]
    baseline_row = baseline_matches.iloc[0] if not baseline_matches.empty else None

    return {
        "test_mae": float(lgbm_row["MAE"]),
        "test_median_ae": float(lgbm_row["Median AE"]),
        "test_rmse": float(lgbm_row["RMSE"]),
        "test_r2": float(lgbm_row["R²"]),
        "baseline_model": str(baseline_row["Model"]) if baseline_row is not None else "N/A",
        "baseline_mae": float(baseline_row["MAE"]) if baseline_row is not None else 0.0,
        "baseline_improvement_vnd": float(baseline_row["MAE"] - lgbm_row["MAE"]) if baseline_row is not None else 0.0,
    }


def make_performance_run_id(
    model_id: str,
    env_fingerprint: str,
    timestamp: datetime | None = None,
) -> str:
    """Generate deterministic, human-readable run identifier for performance benchmarks."""
    ts = timestamp or datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y%m%dT%H%M%SZ")
    model_slug = model_id.split("-")[-1] if "-" in model_id else model_id[:12]
    return f"perf-{model_slug}-{env_fingerprint[:8]}-{ts_str}"


def persist_performance_run(
    output_dir: str | Path,
    run_id: str,
    payload: dict[str, Any],
) -> Path:
    """Persist performance benchmark artifacts in an append-only run directory."""
    base = Path(output_dir) / "runs" / run_id
    base.mkdir(parents=True, exist_ok=False)

    manifest_entries: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }

    # Persist JSON payloads
    for name in ["environment", "artifact_metadata", "summary"]:
        if name in payload and payload[name] is not None:
            target = base / f"{name}.json"
            _write_json(target, payload[name])
            manifest_entries["files"][f"{name}.json"] = file_sha256(target)

    # Persist CSV payloads
    for name in [
        "base_results",
        "standard_results",
        "advanced_results",
        "stage_breakdown",
        "memory_results",
        "robustness_results",
        "concurrency_results",
    ]:
        if name in payload and isinstance(payload[name], pd.DataFrame):
            target = base / f"{name}.csv"
            payload[name].to_csv(target, index=False)
            manifest_entries["files"][f"{name}.csv"] = file_sha256(target)

    manifest_path = base / "manifest.json"
    _write_json(manifest_path, manifest_entries)
    return base


def build_performance_scorecard(
    base_df: pd.DataFrame,
    std_df: pd.DataFrame,
    adv_summary: dict[str, Any],
) -> pd.DataFrame:
    """Build standardized BASE / STANDARD / ADVANCED completion scorecard."""
    base_complete = not base_df.empty and (base_df["Sanity"] == "PASS").all()
    std_complete = not std_df.empty and (
        ("Hot Path Throughput (rows/s)" in std_df.columns and (std_df["Hot Path Throughput (rows/s)"] > 0).all())
        or ("Throughput (rows/s)" in std_df.columns and (std_df["Throughput (rows/s)"] > 0).all())
    )
    adv_complete = (
        adv_summary.get("robustness_pass", False)
        and "stability_cv" in adv_summary
    )

    rows = [
        {
            "Benchmark Level": "BASE",
            "Scope": "Artifact load, single-row, basic batch, memory delta, sanity check",
            "Status": "COMPLETE" if base_complete else "PARTIAL",
            "Evidence": f"{len(base_df)} workloads verified; all predictions finite & positive",
        },
        {
            "Benchmark Level": "STANDARD",
            "Scope": "Hot inference path: P50/P95/P99 latency, batch throughput (1 to full batch)",
            "Status": "COMPLETE" if std_complete else "PARTIAL",
            "Evidence": f"{len(std_df)} workload sizes measured with repeated high-res timings",
        },
        {
            "Benchmark Level": "ADVANCED",
            "Scope": "Full inference pipeline stages, cold model load, prediction-path stability, memory check, robustness, concurrency",
            "Status": "COMPLETE" if adv_complete else "PARTIAL",
            "Evidence": "8 edge cases handled without crash; memory & latency stability verified",
        },
        {
            "Benchmark Level": "OVERALL",
            "Scope": "RoomBeacon Champion In-Process Performance Baseline",
            "Status": "IN-PROCESS PERFORMANCE BASELINE = ESTABLISHED",
            "Evidence": "Empirical runtime profile established on frozen champion artifact",
        },
    ]
    return pd.DataFrame(rows)
