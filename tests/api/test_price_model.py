"""The locked champion adapter: verification, exact reproduction, source policy, intervals."""

import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pytest

from roombeacon_api.domain.errors import DependencyUnavailableError
from roombeacon_api.domain.models import ModelInput
from roombeacon_api.infrastructure.price_model import ChampionPriceModel


ROOT = Path(__file__).resolve().parents[2]
CHAMPION_DIR = ROOT / "data/modeling/roombeacon_price_benchmark_v3"
needs_champion = pytest.mark.skipif(
    not (CHAMPION_DIR / "champion_model.joblib").is_file(), reason="locked champion artifact not present"
)


@needs_champion
def test_reproduces_the_stored_test_predictions_exactly():
    rows = duckdb.sql(
        "SELECT area_value_clean, district_text_extracted, ward_current, source_code, \"LightGBM Regressor\" "
        f"FROM read_parquet('{CHAMPION_DIR / 'test_predictions.parquet'}') ORDER BY rental_post_id LIMIT 300"
    ).fetchall()
    model = ChampionPriceModel(CHAMPION_DIR)

    predictions = model.predict([ModelInput(r[0], r[1], r[2], r[3]) for r in rows])

    assert np.allclose([p.value for p in predictions], [r[4] for r in rows], rtol=1e-9)


@needs_champion
def test_model_info_and_reference_source_policy():
    info = ChampionPriceModel(CHAMPION_DIR).info()

    assert info.model_id == "roombeacon-price-lgbm-f4-raw-4c203abb3b62"
    assert info.family == "LightGBM Regressor" and info.target_transform == "RAW"
    assert info.reference_source == "phongtro123"  # modal source of the DEVELOPMENT population
    assert round(info.test_mae) == 916127
    assert info.interval_coverage == 0.5


@needs_champion
def test_intervals_bracket_the_estimate_and_unknown_locations_are_flagged():
    model = ChampionPriceModel(CHAMPION_DIR)
    known, unknown = model.predict(
        [ModelInput(25.0, "Quận 7", "Phường Tân Hưng", None), ModelInput(25.0, "Quận Không Có", "Phường Không Có", None)]
    )

    assert known.low < known.value < known.high
    assert known.unknown_features == ()
    assert set(unknown.unknown_features) == {"district", "ward"}


def test_missing_artifact_is_a_dependency_outage(tmp_path):
    with pytest.raises(DependencyUnavailableError):
        ChampionPriceModel(tmp_path).info()


@needs_champion
def test_tampered_metadata_is_rejected(tmp_path):
    copy = tmp_path / "champion"
    copy.mkdir()
    for name in ("champion_model.joblib", "champion_metadata.json", "champion_reference_profile.json",
                 "experiment_metadata.json", "final_test.csv"):
        shutil.copy(CHAMPION_DIR / name, copy / name)
    metadata = json.loads((copy / "champion_metadata.json").read_text(encoding="utf-8"))
    metadata["artifact_sha256"] = "0" * 64
    (copy / "champion_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(DependencyUnavailableError):
        ChampionPriceModel(copy).info()
