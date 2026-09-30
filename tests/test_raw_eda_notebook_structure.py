import json
from pathlib import Path


NOTEBOOK_PATH = Path(__file__).parents[1] / "notebooks" / "01_roombeacon_eda.ipynb"


def _notebook_text() -> str:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    return "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_raw_eda_has_final_relationship_and_readiness_architecture():
    text = _notebook_text()

    required_headings = [
        "# 08. Cross-variable Relationship Analysis",
        "## 08.1 Price × Area Relationship",
        "## 08.2 Location × Price",
        "## 08.3 Location × Area",
        "## 08.4 Location × Price per Area",
        "## 08.5 Source × Price",
        "## 08.6 Source × Area",
        "## 08.7 Source × Location",
        "## 08.8 Source × Location × Price",
        "## 08.9 Address Resolution × Critical Fields",
        "## 08.10 Price × Area × Location",
        "## 08.11 Relationship Findings",
        "# 09. RoomBeacon Data Readiness",
        "## 09.1 Critical Field Readiness",
        "## 09.2 Rental Title Usability",
        "## 09.3 Price & Area Usability",
        "## 09.4 Location Resolution Readiness",
        "## 09.5 Coordinate Trust Readiness",
        "## 09.6 Source-specific Readiness",
        "## 09.7 Duplicate / Repost Evidence",
        "## 09.8 Overall Readiness Summary",
        "# 10. Data Quality Findings",
        "# 11. Cleaning & Processing Requirements",
    ]
    for heading in required_headings:
        assert text.count(heading) == 1, heading


def test_section_09_contains_readiness_not_market_style_analysis():
    text = _notebook_text()
    readiness = _section(text, "# 09. RoomBeacon Data Readiness", "# 10. Data Quality Findings")

    forbidden = [
        "listing_type_audit",
        "price_band_audit",
        "area_band_audit",
        "Price by Location",
        "Area by Location",
        "Source × Location Composition",
    ]
    for term in forbidden:
        assert term not in readiness, term

    required_evidence = [
        "readiness_funnel",
        "title_usability",
        "price_area_usability",
        "location_resolution_funnel",
        "coordinate_trust_state",
        "source_readiness",
        "duplicate_candidate_summary",
        "overall_readiness",
    ]
    for term in required_evidence:
        assert term in readiness, term


def test_relationship_section_uses_thresholds_and_both_correlations():
    text = _notebook_text()
    relationships = _section(
        text,
        "# 08. Cross-variable Relationship Analysis",
        "# 09. RoomBeacon Data Readiness",
    )

    for term in [
        "MIN_LOCATION_SAMPLE",
        "MIN_LOCATION_SOURCE_SAMPLE",
        "Pearson Correlation",
        "Spearman Correlation",
        "Valid Price Records",
        "Valid Area Records",
        "relationship_issue_summary",
    ]:
        assert term in relationships, term


def test_notebook_contains_no_database_write_statements():
    text = _notebook_text().lower()
    for statement in ["insert into", "update mysql_db", "delete from", "drop table", "copy to"]:
        assert statement not in text, statement
