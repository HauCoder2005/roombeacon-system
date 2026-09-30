import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"


def _text(path: Path) -> str:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def test_canonical_notebook_files_are_present_without_legacy_processing_name():
    assert (NOTEBOOKS / "01_roombeacon_eda.ipynb").exists()
    assert (NOTEBOOKS / "02_roombeacon_silver.ipynb").exists()
    assert (NOTEBOOKS / "03_roombeacon_processing.ipynb").exists()
    assert not (NOTEBOOKS / "02_roombeacon_processing.ipynb").exists()


def test_silver_notebook_contains_complete_executable_pipeline():
    text = _text(NOTEBOOKS / "02_roombeacon_silver.ipynb")
    expected_sections = [
        "01. Load Bronze Snapshot", "02. Processing Contract Matrix",
        "03. General Text Standardization", "04. Title Quality Processing",
        "05. Address Standardization & Parsing", "06. Administrative Unit Mapping",
        "07. Price Validation", "08. Area Validation", "09. Numeric Outlier Flags",
        "10. Coordinate Trust Classification", "11. Cross-field Consistency",
        "12. Duplicate / Repost Candidate Hardening", "13. Temporal Semantics Validation",
        "14. Final Row Quality Status", "15. Silver Dataset Contract",
        "16. Pre-Silver Quality Gate", "17. Save Canonical Silver Dataset",
        "18. Final Silver Validation",
    ]
    for section in expected_sections:
        assert section in text
    assert "build_silver_dataset" in text
    assert "evaluate_pre_silver_quality_gate" in text
    assert "COPY (SELECT * FROM _canonical_silver_write)" in text
    assert "rental_listings.parquet" in text
    assert "rental_listings.metadata.json" in text
    assert "SilverMaterializer" not in text
    assert "TEMPORARY COMPATIBILITY MIRROR" not in text
    assert "CREATE TABLE silver.rental_listings" not in text
    assert ".fit(" not in text and ".predict(" not in text


def test_processing_notebook_reads_only_canonical_silver_and_does_not_clean_it():
    text = _text(NOTEBOOKS / "03_roombeacon_processing.ipynb")
    assert "rental_listings.parquet" in text
    assert "read_parquet" in text
    for forbidden in [
        "v_latest_posts", "load_snapshot(", "apply_text_standardization(",
        "apply_address_parsing(", "apply_ward_mapping(", "validate_numeric_candidates(",
        "SilverMaterializer(", "CREATE TABLE silver.rental_listings",
        "FROM silver.rental_listings",
        "derive_local_price_bands(", "summarize_local_price_by_radius(",
    ]:
        assert forbidden not in text
    assert "price_per_area" in text
    assert ".fit(" not in text and ".predict(" not in text


def test_notebook_readme_documents_canonical_layers_in_order():
    readme = (NOTEBOOKS / "README.md").read_text(encoding="utf-8")
    expected = [
        "01_roombeacon_eda.ipynb",
        "02_roombeacon_silver.ipynb",
        "03_roombeacon_processing.ipynb",
    ]
    positions = [readme.index(name) for name in expected]
    assert positions == sorted(positions)
    assert "02_roombeacon_processing.ipynb" not in readme


def test_silver_notebook_is_an_auditable_processing_report():
    text = _text(NOTEBOOKS / "02_roombeacon_silver.ipynb")
    required = [
        "Silver Processing Pipeline Overview",
        "Processing Contract Matrix",
        "Before → After Examples",
        "Raw Price Evidence",
        "Reparsed Price",
        "Raw Area Evidence",
        "Reparsed Area",
        "Top Flag Reasons",
        "Number of Flags per Row",
        "Raw → Silver Lineage Examples",
        "What It Protects",
        "Final Silver Health Summary",
    ]
    for label in required:
        assert label in text
    assert "matplotlib.pyplot" in text
    assert text.count("plt.") >= 15
    assert "numeric_audit_report" in text
    assert "flag_reason_breakdown" in text
    assert "multi_flag_distribution" in text
    assert "market analysis" not in text.lower()
