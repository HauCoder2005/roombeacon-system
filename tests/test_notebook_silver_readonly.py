"""Notebooks audit Silver; only roombeacon_silver_build may publish it."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((ROOT / "notebooks").glob("[0-9][0-9]_*.ipynb"))
SILVER_NOTEBOOK = ROOT / "notebooks/02_roombeacon_silver.ipynb"

FORBIDDEN_SILVER_WRITES = (
    "_canonical_silver_write",
    "rental_listings.parquet.tmp",
    "rental_listings.metadata.json.tmp",
    "SilverMaterializer(",
    "build_silver(",
    ".replace(SILVER_PATH)",
    ".replace(METADATA_PATH)",
    "METADATA_PATH.write_text",
    "SILVER_PATH.unlink",
    "rental_latest.parquet",
)


def _code(path: Path) -> str:
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    return "\n".join("".join(c["source"]) for c in cells if c["cell_type"] == "code")


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda p: p.name)
def test_no_notebook_publishes_or_deletes_silver(notebook):
    code = _code(notebook)
    for pattern in FORBIDDEN_SILVER_WRITES:
        assert pattern not in code, f"{notebook.name} writes Silver via {pattern!r}"
    assert not ("COPY (" in code and "FORMAT PARQUET" in code), notebook.name


def test_silver_notebook_audits_the_published_canonical_file():
    code = _code(SILVER_NOTEBOOK)

    assert "read_parquet" in code
    assert "rental_listings.metadata.json" in code
    assert "hash_silver_rows" in code
    assert "roombeacon_silver_build" in code
