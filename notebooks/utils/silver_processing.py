"""Deterministic Bronze-to-Silver transformations and invariant checks.

The module preserves every Bronze row and source field.  Clean values and
quality evidence are appended; statistical anomalies and duplicate candidates
are classified, never removed.
"""

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from .address_parser import apply_address_parsing
from .location_analysis import audit_coordinate_trust
from .notebook_audit import validate_numeric_candidates
from .text_standardization import apply_text_standardization
from .ward_normalization import apply_ward_mapping


STATUS_VALUES: Mapping[str, frozenset[str]] = {
    "title_quality_status": frozenset({"USABLE", "MISSING", "TOO_SHORT"}),
    "price_quality_status": frozenset(
        {"VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN", "MISSING_OR_REVIEW", "UNKNOWN_LINEAGE"}
    ),
    "area_quality_status": frozenset(
        {"VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN", "MISSING_OR_REVIEW", "UNKNOWN_LINEAGE"}
    ),
    "numeric_outlier_status": frozenset({"NOT_OUTLIER", "PRICE_OUTLIER", "AREA_OUTLIER", "PRICE_AND_AREA_OUTLIER"}),
    "coordinate_quality_status": frozenset({"USABLE", "INVALID", "UNTRUSTED"}),
    "cross_field_status": frozenset({"CONSISTENT", "REQUIRES_REVIEW", "INSUFFICIENT_DATA"}),
    "duplicate_candidate_status": frozenset({"UNIQUE_FINGERPRINT", "POSSIBLE_DUPLICATE", "INSUFFICIENT_DATA"}),
    "temporal_quality_status": frozenset({"VALID", "REQUIRES_REVIEW", "INSUFFICIENT_DATA"}),
    "row_quality_status": frozenset({"READY", "READY_WITH_FLAGS", "REQUIRES_REVIEW"}),
}


class SilverQualityGateError(ValueError):
    """Raised when one or more critical pre-Silver invariants fail."""


@dataclass(frozen=True)
class SilverQualityGateReport:
    """Named quality-gate results for display and machine assertions."""

    results: dict[str, bool]

    @property
    def passed(self) -> bool:
        return all(self.results.values())

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"invariant": name, "passed": passed} for name, passed in self.results.items()]
        )


def _iqr_outlier(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    present = numeric.dropna()
    if len(present) < 4:
        return pd.Series(False, index=values.index)
    q1, q3 = present.quantile([0.25, 0.75])
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr <= 0:
        return pd.Series(False, index=values.index)
    return numeric.lt(q1 - 1.5 * iqr) | numeric.gt(q3 + 1.5 * iqr)


def build_silver_dataset(bronze: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    """Return one enriched Silver row per Bronze ``rental_post_id``.

    ``bronze`` and its columns are copied verbatim.  ``evidence`` is used only
    by the existing numeric lineage validators and never enters the output as
    replacement raw data.
    """
    if bronze.empty:
        raise SilverQualityGateError("Bronze snapshot is empty")
    if bronze.rental_post_id.isna().any() or not bronze.rental_post_id.is_unique:
        raise SilverQualityGateError("Bronze rental_post_id must be non-null and unique")

    raw = bronze.reset_index(drop=True).copy(deep=True)
    evidence = evidence.reset_index(drop=True).copy(deep=True)
    if len(evidence) != len(raw) or not evidence.rental_post_id.equals(raw.rental_post_id):
        raise SilverQualityGateError("Numeric evidence must align one-to-one with Bronze identity")

    result = raw.copy(deep=True)
    for field in ["title_raw", "full_address_text", "location_raw", "best_address_text"]:
        result = apply_text_standardization(result, field, f"{field}_clean")

    title_length = result.title_raw_clean.astype("string").str.len()
    result["title_clean"] = result.pop("title_raw_clean")
    result["title_quality_status"] = np.select(
        [result.title_clean.isna(), title_length.lt(5).fillna(False)],
        ["MISSING", "TOO_SHORT"],
        default="USABLE",
    )

    parsed = apply_address_parsing(result, "best_address_text_clean")
    parsed_columns = [
        "street_text_extracted", "ward_text_extracted", "district_text_extracted",
        "province_text_extracted", "parse_status",
    ]
    result[parsed_columns] = parsed[parsed_columns]
    result = apply_ward_mapping(result, "ward_text_extracted", "district_text_extracted")

    price_audit = validate_numeric_candidates(raw, evidence, "price")
    area_audit = validate_numeric_candidates(raw, evidence, "area")
    for kind, audit, clean_col in [
        ("price", price_audit, "price_amount_clean"),
        ("area", area_audit, "area_value_clean"),
    ]:
        result[clean_col] = pd.to_numeric(audit.clean_candidate, errors="coerce")
        result[f"{kind}_quality_status"] = audit.action.replace({"KEEP_NULL_OR_FLAG": "MISSING_OR_REVIEW"})
        result[f"{kind}_lineage_aligned"] = audit.lineage_aligned.astype(bool)
        result[f"{kind}_regression_status"] = audit.regression

    price_outlier = _iqr_outlier(result.price_amount_clean)
    area_outlier = _iqr_outlier(result.area_value_clean)
    result["price_outlier_flag"] = price_outlier
    result["area_outlier_flag"] = area_outlier
    result["numeric_outlier_status"] = np.select(
        [price_outlier & area_outlier, price_outlier, area_outlier],
        ["PRICE_AND_AREA_OUTLIER", "PRICE_OUTLIER", "AREA_OUTLIER"],
        default="NOT_OUTLIER",
    )

    result = audit_coordinate_trust(result, address_col="full_address_text")
    result["coordinate_quality_status"] = np.select(
        [result.has_trusted_coordinate, ~result.coordinate_pair_valid],
        ["USABLE", "INVALID"],
        default="UNTRUSTED",
    )

    price = pd.to_numeric(result.price_amount_clean, errors="coerce")
    area = pd.to_numeric(result.area_value_clean, errors="coerce")
    price_per_area = price / area.where(area.gt(0))
    result["cross_field_status"] = np.select(
        [price.isna() | area.isna(), price_per_area.le(0) | ~np.isfinite(price_per_area)],
        ["INSUFFICIENT_DATA", "REQUIRES_REVIEW"],
        default="CONSISTENT",
    )

    fingerprint_fields = ["title_clean", "best_address_text_clean", "price_amount_clean", "area_value_clean"]
    sufficient = result[fingerprint_fields[:2]].notna().all(axis=1)
    fingerprint = (
        result[fingerprint_fields]
        .astype("string")
        .fillna("<NULL>")
        .agg("|".join, axis=1)
    )
    duplicate = sufficient & fingerprint.duplicated(keep=False)
    result["duplicate_candidate_group"] = fingerprint.where(duplicate, pd.NA)
    result["duplicate_candidate_status"] = np.select(
        [~sufficient, duplicate], ["INSUFFICIENT_DATA", "POSSIBLE_DUPLICATE"], default="UNIQUE_FINGERPRINT"
    )

    first = pd.to_datetime(result.first_observed_at, errors="coerce")
    last = pd.to_datetime(result.last_observed_at, errors="coerce")
    latest = pd.to_datetime(result.latest_observed_at, errors="coerce")
    insufficient_temporal = first.isna() | last.isna() | latest.isna()
    invalid_temporal = first.gt(last) | latest.lt(first) | latest.gt(last)
    result["temporal_quality_status"] = np.select(
        [insufficient_temporal, invalid_temporal], ["INSUFFICIENT_DATA", "REQUIRES_REVIEW"], default="VALID"
    )

    requires_review = (
        result.title_quality_status.ne("USABLE")
        | result.temporal_quality_status.eq("REQUIRES_REVIEW")
        | result.ward_mapping_status.eq("AMBIGUOUS")
    )
    has_flags = (
        result.numeric_outlier_status.ne("NOT_OUTLIER")
        | result.duplicate_candidate_status.ne("UNIQUE_FINGERPRINT")
        | result.coordinate_quality_status.ne("USABLE")
        | result.price_quality_status.ne("VALIDATED_EXISTING")
        | result.area_quality_status.ne("VALIDATED_EXISTING")
    )
    result["row_quality_status"] = np.select(
        [requires_review, has_flags], ["REQUIRES_REVIEW", "READY_WITH_FLAGS"], default="READY"
    )
    return result


def evaluate_pre_silver_quality_gate(
    bronze: pd.DataFrame,
    silver: pd.DataFrame,
) -> SilverQualityGateReport:
    """Validate critical preservation and documented-status invariants."""
    raw_columns = list(bronze.columns)
    same_identity = (
        "rental_post_id" in silver
        and silver.rental_post_id.tolist() == bronze.rental_post_id.tolist()
    )
    raw_unchanged = set(raw_columns) <= set(silver.columns) and len(bronze) == len(silver)
    if raw_unchanged and len(bronze) == len(silver):
        try:
            pd.testing.assert_frame_equal(
                silver[raw_columns].reset_index(drop=True),
                bronze.reset_index(drop=True),
                check_dtype=True,
            )
        except AssertionError:
            raw_unchanged = False

    status_valid = all(
        column in silver and set(silver[column].dropna().astype(str)).issubset(allowed)
        for column, allowed in STATUS_VALUES.items()
    )
    results = {
        "row_count_preserved": len(silver) == len(bronze),
        "rental_post_id_non_null": "rental_post_id" in silver and silver.rental_post_id.notna().all(),
        "rental_post_id_unique": "rental_post_id" in silver and silver.rental_post_id.is_unique,
        "source_identity_preserved": same_identity and silver.source_code.tolist() == bronze.source_code.tolist(),
        "raw_source_fields_unchanged": raw_unchanged,
        "no_row_multiplication_or_deletion": same_identity,
        "price_clean_contract_valid": "price_amount_clean" in silver and not (
            silver.price_amount_clean.notna() & silver.price_quality_status.eq("MISSING_OR_REVIEW")
        ).any(),
        "area_clean_contract_valid": "area_value_clean" in silver and not (
            silver.area_value_clean.notna() & silver.area_quality_status.eq("MISSING_OR_REVIEW")
        ).any(),
        "ambiguous_ward_not_truth": not (
            silver.ward_mapping_status.eq("AMBIGUOUS") & silver.ward_current.notna()
        ).any(),
        "invalid_coordinates_not_usable": not (
            silver.coordinate_quality_status.eq("INVALID") & silver.has_trusted_coordinate
        ).any(),
        "outliers_preserved_and_flagged": "numeric_outlier_status" in silver and len(silver) == len(bronze),
        "duplicate_candidates_preserved_and_flagged": "duplicate_candidate_status" in silver and len(silver) == len(bronze),
        "documented_status_values_only": status_valid,
    }
    report = SilverQualityGateReport(results)
    if not report.passed:
        failed = [name for name, passed in results.items() if not passed]
        raise SilverQualityGateError(f"Pre-Silver quality gate failed: {', '.join(failed)}")
    return report
