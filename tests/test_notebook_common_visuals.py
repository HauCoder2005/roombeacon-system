"""Presentation contract for the two official RoomBeacon notebooks."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
OFFICIAL = [
    NOTEBOOKS / "01_roombeacon_eda.ipynb",
    NOTEBOOKS / "02_roombeacon_processing.ipynb",
]


def _source(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def test_official_notebooks_use_plain_eda_and_processing_names() -> None:
    assert all(path.exists() for path in OFFICIAL)
    assert not (NOTEBOOKS / "01_roombeacon_data_audit_and_eda.ipynb").exists()
    assert not (NOTEBOOKS / "02_roombeacon_cleaning_and_validation.ipynb").exists()
    readme = (NOTEBOOKS / "README.md").read_text(encoding="utf-8")
    assert "01_roombeacon_eda.ipynb" in readme
    assert "02_roombeacon_processing.ipynb" in readme
    assert "01_roombeacon_data_audit_and_eda.ipynb" not in readme
    assert "02_roombeacon_cleaning_and_validation.ipynb" not in readme


def test_official_notebooks_remove_the_three_rejected_visuals() -> None:
    combined = "\n".join(_source(path) for path in OFFICIAL)
    assert "px.box(" not in combined
    assert "Missingness matrix" not in combined
    assert "px.line(" not in combined
    assert "Pareto" not in combined
    assert "facet_col=" not in combined


def test_radius_visuals_use_median_bar_histogram_and_simple_scatter() -> None:
    source = _source(OFFICIAL[1])
    assert "median_validated_price" in source
    assert "px.histogram(" in source
    assert "Phân bố giá phòng trong bán kính" in source
    assert "px.scatter(" in source
    assert "color='source_code'" not in source


def test_notebook_eda_uses_friendly_missingness_and_location_visuals() -> None:
    source = _source(OFFICIAL[0])
    assert "Nguồn nào có dữ liệu tọa độ đáng tin cậy?" in source
    assert "Những trường nào thường thiếu cùng nhau?" in source
    assert "Không dùng" in source
    assert "Có điều kiện" in source
    assert "Dùng được" in source


def test_visualization_vocabulary_stays_common() -> None:
    combined = "\n".join(_source(path) for path in OFFICIAL)
    rejected = [
        "px.violin(", "px.treemap(", "px.sunburst(", "px.funnel(",
        "px.scatter_3d(", "go.Sankey(", "secondary_y=", "px.density_",
    ]
    assert not [token for token in rejected if token in combined]
