"""Serving adapter for the locked LightGBM / RAW / F4 champion.

Loads the artifact published by notebook 04 and refuses to serve unless the
package agrees with itself: artifact SHA-256 and model_id match the metadata,
the class is LGBMRegressor, booster feature names and persisted category
vocabularies match the F4 contract. The model is never retrained or reselected.

Inference reproduces notebook 04/06 exactly: categories outside the persisted
vocabulary map to "__UNKNOWN__", missing ones to "__MISSING__".

Free-form estimates (no listing, so no source) use the modal source of the
DEVELOPMENT population, read from the reference profile, as the reference
source. Intervals are the 25th-75th percentile of actual/predicted ratios on
the held-out TEST predictions (50% empirical coverage), computed separately
for own-source and reference-source predictions.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import threading
from typing import Any

from ..domain.errors import DependencyUnavailableError
from ..domain.models import ModelInfo, ModelInput, PricePrediction


logger = logging.getLogger(__name__)
F4_FEATURES = ("area_value_clean", "source_code", "ward_current", "district_text_extracted")
CATEGORICAL = ("source_code", "ward_current", "district_text_extracted")
INTERVAL = (0.25, 0.75)
# Shadow validation: predictions are compressed; actual rents below ~2.5M or
# above ~6M are badly estimated. Estimates outside this band get a warning.
RELIABLE_PRICE_RANGE = (3_000_000.0, 5_500_000.0)


class _Loaded:
    def __init__(self, model, metadata, info, ratios) -> None:
        self.model = model
        self.metadata = metadata
        self.info = info
        self.ratios = ratios  # {"own": (q25, q75), "reference": (q25, q75)}


class ChampionPriceModel:
    def __init__(self, model_dir: str | Path) -> None:
        self._dir = Path(model_dir)
        self._lock = threading.Lock()
        self._loaded: _Loaded | None = None

    # -- port implementation -------------------------------------------------

    def info(self) -> ModelInfo:
        return self._get().info

    def predict(self, inputs: list[ModelInput]) -> list[PricePrediction]:
        loaded = self._get()
        if not inputs:
            return []
        import numpy as np

        reference = loaded.info.reference_source
        frame = self._frame(
            loaded.metadata,
            [(i.area_m2, i.source_code or reference, i.ward, i.district) for i in inputs],
        )
        unknown = self._unknown(loaded.metadata, inputs)
        values = np.asarray(loaded.model.predict(frame), dtype=float)
        out = []
        for item, value, missing in zip(inputs, values, unknown):
            q25, q75 = loaded.ratios["own" if item.source_code else "reference"]
            value = max(float(value), 0.0)
            out.append(PricePrediction(value, value * q25, value * q75, missing))
        return out

    # -- loading ---------------------------------------------------------------

    def _get(self) -> _Loaded:
        with self._lock:
            if self._loaded is None:
                try:
                    self._loaded = self._load()
                except DependencyUnavailableError:
                    raise
                except Exception as exc:  # corrupt package, missing file, wrong library version
                    logger.error("price model failed to load: %s", type(exc).__name__)
                    raise DependencyUnavailableError("price_model") from exc
            return self._loaded

    def _load(self) -> _Loaded:
        experiment_path = self._dir / "experiment_metadata.json"
        if not experiment_path.is_file():
            logger.error("price model package not found in %s", self._dir)
            raise DependencyUnavailableError("price_model")
        experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
        pointer = experiment["champion"]
        metadata = json.loads(self._inside(pointer["metadata_path"]).read_text(encoding="utf-8"))
        reference = json.loads(self._inside(pointer["reference_profile_path"]).read_text(encoding="utf-8"))
        artifact = self._inside(metadata["artifact_path"])

        observed = _sha256(artifact)
        if not (observed == metadata["artifact_sha256"] == pointer["artifact_sha256"]):
            raise ValueError("artifact sha256 disagrees with metadata")
        if not (metadata["model_id"] == pointer["model_id"] == reference["model_id"]) or not metadata["model_id"].endswith(observed[:12]):
            raise ValueError("model_id disagrees with the artifact")
        if metadata["model_family"] != "LightGBM Regressor" or metadata["target_transform"] != "RAW":
            raise ValueError("not the locked LightGBM/RAW champion")
        if tuple(metadata["feature_names"]) != F4_FEATURES:
            raise ValueError("feature contract is not F4")

        import joblib

        model = joblib.load(artifact)
        if model.__class__.__name__ != "LGBMRegressor":
            raise ValueError("artifact is not an LGBMRegressor")
        booster = model.booster_
        if tuple(booster.feature_name()) != F4_FEATURES:
            raise ValueError("booster feature names disagree with F4")
        vocabularies = metadata["categorical_vocabularies"]
        if [list(v) for v in booster.pandas_categorical] != [vocabularies[c] for c in CATEGORICAL]:
            raise ValueError("persisted category vocabularies disagree with metadata")

        shares = reference["categorical"]["source_code"]["distribution_pct"]
        reference_source = max(shares, key=shares.get)
        metrics = self._test_metrics()
        ratios = self._calibrate(model, metadata, reference_source)
        cutoff = metadata.get("training_reference", {}).get("training_cutoff")
        area = reference.get("numeric", {}).get("area_value_clean", {})
        info = ModelInfo(
            model_id=metadata["model_id"],
            family=metadata["model_family"],
            feature_set=metadata["feature_set"],
            target_transform=metadata["target_transform"],
            trained_until=datetime.fromisoformat(cutoff).replace(tzinfo=timezone.utc) if cutoff else None,
            test_mae=metrics.get("MAE"),
            test_median_ae=metrics.get("Median AE"),
            test_r2=metrics.get("R²"),
            readiness="experimental",
            reference_source=reference_source,
            interval_coverage=INTERVAL[1] - INTERVAL[0],
            typical_area_range=(float(area.get("p05", 15.0)), float(area.get("p95", 50.0))),
            reliable_price_range=RELIABLE_PRICE_RANGE,
        )
        logger.info("price model loaded: %s", info.model_id)
        return _Loaded(model, metadata, info, ratios)

    def _inside(self, relative: str) -> Path:
        path = (self._dir / relative).resolve()
        if self._dir.resolve() not in path.parents:
            raise ValueError("model package path escapes its directory")
        return path

    def _test_metrics(self) -> dict[str, float]:
        path = self._dir / "final_test.csv"
        if not path.is_file():
            return {}
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("Model") == "LightGBM Regressor" and row.get("Target Transform") == "RAW":
                    return {k: float(v) for k, v in row.items() if k in {"MAE", "Median AE", "R²"} and v}
        return {}

    def _calibrate(self, model, metadata, reference_source: str) -> dict[str, tuple[float, float]]:
        """Interval ratios from TEST predictions; a missing file falls back to MAE-free wide bounds."""
        path = self._dir / "test_predictions.parquet"
        if not path.is_file():
            return {"own": (0.5, 1.5), "reference": (0.5, 1.5)}
        import duckdb
        import numpy as np

        rows = duckdb.sql(
            "SELECT actual_price, area_value_clean, ward_current, district_text_extracted, \"LightGBM Regressor\" "
            "FROM read_parquet($path) WHERE actual_price > 0 AND area_value_clean > 0",
            params={"path": str(path)},
        ).fetchall()
        actual = np.array([r[0] for r in rows], dtype=float)
        own = np.array([r[4] for r in rows], dtype=float)
        frame = self._frame(metadata, [(r[1], reference_source, r[2], r[3]) for r in rows])
        reference = np.asarray(model.predict(frame), dtype=float)

        def bounds(predicted):
            ratio = actual / np.clip(predicted, 1.0, None)
            return tuple(float(x) for x in np.quantile(ratio, INTERVAL))

        return {"own": bounds(own), "reference": bounds(reference)}

    @staticmethod
    def _frame(metadata, rows):
        import pandas as pd

        frame = pd.DataFrame(rows, columns=list(F4_FEATURES))
        frame["area_value_clean"] = pd.to_numeric(frame["area_value_clean"], errors="coerce").astype(float)
        vocabularies = metadata["categorical_vocabularies"]
        for column in CATEGORICAL:
            raw = frame[column].astype("string").fillna("__MISSING__")
            frame[column] = pd.Categorical(raw.where(raw.isin(vocabularies[column]), "__UNKNOWN__"), categories=vocabularies[column])
        return frame

    @staticmethod
    def _unknown(metadata, inputs: list[ModelInput]) -> list[tuple[str, ...]]:
        districts = set(metadata["categorical_vocabularies"]["district_text_extracted"])
        wards = set(metadata["categorical_vocabularies"]["ward_current"])
        out = []
        for item in inputs:
            missing = []
            if item.district not in districts:
                missing.append("district")
            if item.ward is not None and item.ward not in wards:
                missing.append("ward")
            out.append(tuple(missing))
        return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
