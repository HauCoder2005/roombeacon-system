import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from analytics.bronze.snapshot import load_bronze_snapshot
from roombeacon_processing.contracts import SilverContract
from roombeacon_processing.golden import aggregate_row_hashes, hash_silver_rows
from roombeacon_processing.silver import build_silver_dataset


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "tests/fixtures/silver_golden_manifest.json"


def test_row_hashing_is_deterministic_and_type_aware():
    frame = pd.DataFrame(
        {
            "identity": [1, 1, 1],
            "value": [None, "", "1"],
        }
    )

    hashes = hash_silver_rows(frame)

    assert hashes == hash_silver_rows(frame.copy())
    assert len(hashes) == len(set(hashes)) == 3
    assert all(len(value) == 64 for value in hashes)


def test_row_hashing_normalizes_parquet_list_arrays():
    in_memory = pd.DataFrame({"candidates": [["Ward A", "Ward B"]]})
    parquet_readback = pd.DataFrame(
        {"candidates": [np.array(["Ward A", "Ward B"], dtype=object)]}
    )

    assert hash_silver_rows(in_memory) == hash_silver_rows(parquet_readback)


def test_new_package_build_matches_canonical_golden():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    contract = SilverContract.from_manifest(manifest)
    bronze, evidence, _ = load_bronze_snapshot(ROOT / "data/bronze/snapshot")

    actual = build_silver_dataset(bronze, evidence)
    canonical_path = ROOT / "data/silver/rental_listings.parquet"
    canonical = duckdb.connect(":memory:").execute(
        "SELECT * FROM read_parquet(?)", [str(canonical_path)]
    ).df()

    contract.validate(actual)
    contract.validate(canonical)
    actual_hashes = hash_silver_rows(actual)
    canonical_hashes = hash_silver_rows(canonical)
    assert actual_hashes == canonical_hashes
    assert manifest["row_hashes_sha256"] == aggregate_row_hashes(actual_hashes)
