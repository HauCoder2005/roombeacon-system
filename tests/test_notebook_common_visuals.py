"""Presentation contract for the canonical RoomBeacon notebook workflow."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
OFFICIAL = [
    NOTEBOOKS / "01_roombeacon_eda.ipynb",
    NOTEBOOKS / "02_roombeacon_silver.ipynb",
    NOTEBOOKS / "03_roombeacon_processing.ipynb",
]


def _source(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def test_official_notebooks_use_canonical_layer_names() -> None:
    assert all(path.exists() for path in OFFICIAL)
    assert not (NOTEBOOKS / "01_roombeacon_data_audit_and_eda.ipynb").exists()
    assert not (NOTEBOOKS / "02_roombeacon_cleaning_and_validation.ipynb").exists()
    readme = (NOTEBOOKS / "README.md").read_text(encoding="utf-8")
    assert "01_roombeacon_eda.ipynb" in readme
    assert "02_roombeacon_silver.ipynb" in readme
    assert "03_roombeacon_processing.ipynb" in readme
    assert "01_roombeacon_data_audit_and_eda.ipynb" not in readme
    assert "02_roombeacon_cleaning_and_validation.ipynb" not in readme


def test_official_notebooks_remove_the_three_rejected_visuals() -> None:
    combined = "\n".join(_source(path) for path in OFFICIAL)
    assert "px.box(" not in combined
    assert "Missingness matrix" not in combined
    assert "px.line(" not in combined
    assert "Pareto" not in combined
    assert "facet_col=" not in combined


def test_silver_and_processing_notebooks_exclude_market_visuals() -> None:
    source = "\n".join(_source(path) for path in OFFICIAL[1:])
    assert "local_price_band" not in source
    assert "rank(method=" not in source
    assert "px.histogram(" not in source


def test_notebook_eda_uses_friendly_missingness_and_location_visuals() -> None:
    source = _source(OFFICIAL[0])
    assert "Missing Data Analysis" in source
    assert "Address & Location Quality" in source
    assert "Coordinate" in source
    assert "Relationship Findings" in source


def test_visualization_vocabulary_stays_common() -> None:
    combined = "\n".join(_source(path) for path in OFFICIAL)
    rejected = [
        "px.violin(", "px.treemap(", "px.sunburst(", "px.funnel(",
        "px.scatter_3d(", "go.Sankey(", "secondary_y=", "px.density_",
    ]
    assert not [token for token in rejected if token in combined]
