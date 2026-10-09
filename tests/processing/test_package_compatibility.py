from __future__ import annotations

import importlib
from pathlib import Path

import pytest


MODULE_SYMBOLS = {
    "text_standardization": ("standardize_text", "apply_text_standardization"),
    "address_parser": ("parse_address_text", "apply_address_parsing"),
    "ward_normalization": ("map_ward", "apply_ward_mapping"),
    "price_area_validation": ("parse_price", "parse_area"),
    "listing_semantics": ("classify_listing_semantics", "apply_listing_semantics"),
    "location_analysis": ("audit_coordinate_trust",),
    "silver": ("build_silver_dataset", "evaluate_pre_silver_quality_gate"),
}


@pytest.mark.parametrize(("module_name", "symbols"), MODULE_SYMBOLS.items())
def test_notebook_modules_reexport_processing_implementations(module_name, symbols):
    production = importlib.import_module(f"roombeacon_processing.{module_name}")
    legacy_name = "silver_processing" if module_name == "silver" else module_name
    legacy = importlib.import_module(f"notebooks.utils.{legacy_name}")

    for symbol in symbols:
        assert getattr(legacy, symbol) is getattr(production, symbol)


@pytest.mark.parametrize(
    "module_name",
    [
        "text_standardization",
        "address_parser",
        "ward_normalization",
        "price_area_validation",
        "listing_semantics",
        "location_analysis",
        "silver_processing",
    ],
)
def test_notebook_compatibility_modules_are_small_reexport_shims(module_name):
    path = Path("notebooks/utils") / f"{module_name}.py"

    assert len(path.read_text(encoding="utf-8").splitlines()) <= 12


def test_processing_package_exposes_the_canonical_silver_api():
    package = importlib.import_module("roombeacon_processing")

    assert callable(package.build_silver_dataset)
    assert callable(package.evaluate_pre_silver_quality_gate)


def test_airflow_image_installs_the_processing_package():
    dockerfile = Path("airflow/Dockerfile").read_text(encoding="utf-8")

    assert "processing/pyproject.toml" in dockerfile
    assert "processing/src/" in dockerfile
    assert "-e /opt/roombeacon/processing" in dockerfile
