"""Deterministic Bronze-to-Silver transformations and invariant checks.

The module preserves every Bronze row and source field.  Clean values and
quality evidence are appended; statistical anomalies and duplicate candidates
are classified, never removed.
"""

from dataclasses import dataclass
import hashlib
from typing import Mapping

import numpy as np
import pandas as pd

from .address_parser import apply_address_parsing
from .location_analysis import audit_coordinate_trust
from .listing_semantics import INTENT_VALUES, SCOPE_VALUES, apply_listing_semantics
from .numeric_validation import validate_numeric_candidates
from .price_area_validation import (
    parse_rental_price_evidence,
    evaluate_area_model_suitability,
    evaluate_price_model_suitability,
    evaluate_price_target_trust,
)
from .text_standardization import apply_text_standardization_batch
from .ward_normalization import apply_admin_consistency_audit, apply_ward_mapping


STATUS_VALUES: Mapping[str, frozenset[str]] = {
    "title_quality_status": frozenset({"USABLE", "MISSING", "TOO_SHORT"}),
    "price_quality_status": frozenset(
        {"VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN", "MISSING_OR_REVIEW", "UNKNOWN_LINEAGE"}
    ),
    "area_quality_status": frozenset(
        {"VALIDATED_EXISTING", "REPARSE_ACCEPTED_CLEAN", "MISSING_OR_REVIEW", "UNKNOWN_LINEAGE"}
    ),
    "area_semantic_status": frozenset(
        {"EXPLICIT_AREA", "DERIVED_FROM_DIMENSIONS", "EXISTING_NUMERIC",
         "SUPPORTED_EXISTING_NUMERIC", "LINEAR_MEASUREMENT_CONTRADICTION",
         "CURRENCY_SHAPED_AREA_EVIDENCE", "INSUFFICIENT_EVIDENCE"}
    ),
    "area_model_suitability": frozenset({"SUPPORTED", "REVIEW"}),
    "price_parser_comparison_status": frozenset(
        {"MATCH", "DISAGREEMENT", "REPARSED_ONLY", "EXISTING_ONLY", "NO_PRICE_EVIDENCE", "UNCOMPARABLE"}
    ),
    "price_target_trust_status": frozenset(
        {"TRUSTED_EXISTING", "TRUSTED_REPARSED",
         "SUSPECT_UNIT_SCALE", "PARSER_DISAGREEMENT_REVIEW",
         "INSUFFICIENT_EVIDENCE", "MISSING"}
    ),
    "price_semantic_status": frozenset(
        {"SUPPORTED_MONTHLY_RENT", "ORDINARY_UNIT_OUTLIER_UNCORROBORATED",
         "CROSS_FIELD_CONTRADICTION", "INCOMPATIBLE_LISTING_SEMANTICS", "UNSUPPORTED_LINEAGE"}
    ),
    "price_model_suitability": frozenset({"SUPPORTED", "REVIEW", "EXCLUDED"}),
    "numeric_outlier_status": frozenset({"NOT_OUTLIER", "PRICE_OUTLIER", "AREA_OUTLIER", "PRICE_AND_AREA_OUTLIER"}),
    "coordinate_quality_status": frozenset({"USABLE", "INVALID", "UNTRUSTED"}),
    "price_area_availability_status": frozenset(
        {"AVAILABLE", "MISSING_PRICE", "MISSING_AREA", "MISSING_BOTH"}
    ),
    "price_area_quality_status": frozenset(
        {"CHECKED_NO_FLAG", "PRICE_OUTLIER_REVIEW", "AREA_OUTLIER_REVIEW",
         "BOTH_OUTLIERS_REVIEW", "EXTREME_PRICE_PER_AREA_REVIEW", "INSUFFICIENT_DATA"}
    ),
    "duplicate_candidate_status": frozenset({"UNIQUE_FINGERPRINT", "POSSIBLE_DUPLICATE", "INSUFFICIENT_DATA"}),
    "duplicate_match_reason": frozenset(
        {"EXACT_FINGERPRINT", "SAME_ADDRESS_PRICE_AREA", "SAME_TITLE_PRICE_WARD", "NO_MATCH"}
    ),
    "duplicate_scope": frozenset({"SAME_SOURCE", "CROSS_SOURCE", "NOT_APPLICABLE"}),
    "temporal_quality_status": frozenset({"VALID", "REQUIRES_REVIEW", "INSUFFICIENT_DATA"}),
    "row_quality_status": frozenset({"READY", "READY_WITH_FLAGS", "REQUIRES_REVIEW"}),
    "listing_intent": INTENT_VALUES,
    "rental_scope": SCOPE_VALUES,
    "admin_consistency_status": frozenset(
        {"CONSISTENT", "INCONSISTENT", "AMBIGUOUS", "UNVERIFIABLE", "MISSING_EVIDENCE"}
    ),
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


def _group_key(frame: pd.DataFrame, fields: list[str], rule: str) -> pd.Series:
    """Return deterministic, compact group IDs for complete blocking fields."""
    hashed = pd.util.hash_pandas_object(frame[fields].astype("string"), index=False)
    return hashed.map(lambda value: f"{rule}:{int(value):016x}")


def _compact_derived_strings(frame: pd.DataFrame, raw_columns: list[str]) -> None:
    """Use dictionary encoding when it reduces a derived string column in memory."""
    object_contract_columns = {
        "full_address_text_clean",
        "location_raw_clean",
        "best_address_text_clean",
        "title_clean",
        "ward_mapping_candidates",
        "admin_consistency_candidates",
    }
    for column in frame.columns:
        if column in raw_columns or column in object_contract_columns:
            continue
        series = frame[column]
        if not (
            pd.api.types.is_string_dtype(series.dtype)
            or pd.api.types.is_object_dtype(series.dtype)
        ):
            continue
        categorical = series.astype("category")
        if categorical.memory_usage(index=False, deep=True) < series.memory_usage(
            index=False, deep=True
        ):
            frame[column] = categorical


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

    canonical_index = pd.RangeIndex(len(bronze))
    raw = bronze if bronze.index.equals(canonical_index) else bronze.reset_index(drop=True)
    evidence = (
        evidence
        if evidence.index.equals(canonical_index)
        else evidence.reset_index(drop=True)
    )
    if len(evidence) != len(raw) or not evidence.rental_post_id.equals(raw.rental_post_id):
        raise SilverQualityGateError("Numeric evidence must align one-to-one with Bronze identity")

    result = raw.copy(deep=False)
    text_fields = ["title_raw", "full_address_text", "location_raw", "best_address_text"]
    result = apply_text_standardization_batch(
        result, {field: f"{field}_clean" for field in text_fields}
    )

    title_length = result.title_raw_clean.astype("string").str.len()
    result["title_clean"] = result.pop("title_raw_clean")
    result["title_quality_status"] = np.select(
        [result.title_clean.isna(), title_length.lt(5).fillna(False)],
        ["MISSING", "TOO_SHORT"],
        default="USABLE",
    )
    result = apply_listing_semantics(result, "title_clean")

    parsed = apply_address_parsing(result, "best_address_text_clean")
    parsed_columns = [
        "street_text_extracted", "ward_text_extracted", "district_text_extracted",
        "province_text_extracted", "parse_status",
    ]
    result[parsed_columns] = parsed[parsed_columns]
    result = apply_ward_mapping(result, "ward_text_extracted", "district_text_extracted")
    result = apply_admin_consistency_audit(
        result, "ward_text_extracted", "district_text_extracted", "ward_current"
    )
    _compact_derived_strings(result, list(raw.columns))

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

    area_evaluations = [
        evaluate_area_model_suitability(clean, status, raw_area, title)
        for clean, status, raw_area, title in zip(
            result.area_value_clean,
            result.area_quality_status,
            area_audit.raw,
            result.title_clean,
        )
    ]
    result["area_semantic_status"] = pd.Series([item[0] for item in area_evaluations], index=result.index, dtype="string")
    result["area_model_suitability"] = pd.Series([item[1] for item in area_evaluations], index=result.index, dtype="string")
    result["area_semantic_evidence"] = pd.Series([item[2] for item in area_evaluations], index=result.index, dtype="string")

    price_existing = price_audit.existing
    price_reparsed = price_audit.reparsed
    raw_price_missing = price_audit.raw.isna() | price_audit.raw.astype("string").str.strip().eq("").fillna(False)
    result["price_parser_comparison_status"] = np.select(
        [
            price_existing.notna() & price_reparsed.notna() & price_existing.eq(price_reparsed),
            price_existing.notna() & price_reparsed.notna() & ~price_existing.eq(price_reparsed),
            price_existing.isna() & price_reparsed.notna(),
            price_existing.notna() & price_reparsed.isna(),
            price_existing.isna() & price_reparsed.isna() & raw_price_missing,
        ],
        ["MATCH", "DISAGREEMENT", "REPARSED_ONLY", "EXISTING_ONLY", "NO_PRICE_EVIDENCE"],
        default="UNCOMPARABLE",
    )

    trust_evaluations = [
        evaluate_price_target_trust(
            clean_price=cp,
            price_quality_status=pqs,
            price_parser_comparison_status=ppcs,
            price_lineage_aligned=bool(pla),
            raw_price=rp,
            title=tc,
            listing_intent=li,
            rental_scope=rs,
        )
        for cp, pqs, ppcs, pla, rp, tc, li, rs in zip(
            result.price_amount_clean,
            result.price_quality_status,
            result.price_parser_comparison_status,
            result.price_lineage_aligned,
            price_audit.raw,
            result.title_clean,
            result.listing_intent,
            result.rental_scope,
        )
    ]
    trust_status = [t[0] for t in trust_evaluations]
    trust_reason = [t[1] for t in trust_evaluations]
    trust_evidence = [t[2] for t in trust_evaluations]
    model_values = [t[3] for t in trust_evaluations]

    result["price_target_trust_status"] = pd.Series(trust_status, index=result.index, dtype="string")
    result["price_target_trust_reason"] = pd.Series(trust_reason, index=result.index, dtype="string")
    result["price_target_trust_evidence"] = pd.Series(trust_evidence, index=result.index, dtype="string")
    result["price_model_value"] = pd.Series(model_values, index=result.index, dtype="Float64")
    result["price_target_model_value"] = result["price_model_value"]
    _compact_derived_strings(result, list(raw.columns))

    price_outlier = _iqr_outlier(result.price_amount_clean)
    area_outlier = _iqr_outlier(result.area_value_clean)
    result["price_outlier_flag"] = price_outlier
    result["area_outlier_flag"] = area_outlier
    result["numeric_outlier_status"] = np.select(
        [price_outlier & area_outlier, price_outlier, area_outlier],
        ["PRICE_AND_AREA_OUTLIER", "PRICE_OUTLIER", "AREA_OUTLIER"],
        default="NOT_OUTLIER",
    )

    price_suitability = [
        evaluate_price_model_suitability(value, trust, title, intent, scope, bool(outlier), clean_area=area)
        for value, trust, title, intent, scope, outlier, area in zip(
            result.price_model_value,
            result.price_target_trust_status,
            result.title_clean,
            result.listing_intent,
            result.rental_scope,
            price_outlier,
            result.area_value_clean,
        )
    ]
    result["price_semantic_status"] = pd.Series([item[0] for item in price_suitability], index=result.index, dtype="string")
    result["price_model_suitability"] = pd.Series([item[1] for item in price_suitability], index=result.index, dtype="string")
    result["price_semantic_evidence"] = pd.Series([item[2] for item in price_suitability], index=result.index, dtype="string")
    _compact_derived_strings(result, list(raw.columns))

    result = audit_coordinate_trust(result, address_col="full_address_text")
    result["coordinate_quality_status"] = np.select(
        [result.has_trusted_coordinate, ~result.coordinate_pair_valid],
        ["USABLE", "INVALID"],
        default="UNTRUSTED",
    )
    _compact_derived_strings(result, list(raw.columns))

    price = pd.to_numeric(result.price_amount_clean, errors="coerce")
    area = pd.to_numeric(result.area_value_clean, errors="coerce")
    result["price_area_availability_status"] = np.select(
        [price.isna() & area.isna(), price.isna(), area.isna()],
        ["MISSING_BOTH", "MISSING_PRICE", "MISSING_AREA"],
        default="AVAILABLE",
    )
    price_per_area = price / area.where(area.gt(0))
    ratio_outlier = _iqr_outlier(price_per_area)
    available = result.price_area_availability_status.eq("AVAILABLE")
    result["price_area_quality_status"] = np.select(
        [
            ~available,
            available & price_outlier & area_outlier,
            available & price_outlier,
            available & area_outlier,
            available & ratio_outlier,
        ],
        ["INSUFFICIENT_DATA", "BOTH_OUTLIERS_REVIEW", "PRICE_OUTLIER_REVIEW",
         "AREA_OUTLIER_REVIEW", "EXTREME_PRICE_PER_AREA_REVIEW"],
        default="CHECKED_NO_FLAG",
    )

    exact_fields = ["title_clean", "best_address_text_clean", "price_amount_clean", "area_value_clean"]
    address_fields = ["best_address_text_clean", "price_amount_clean", "area_value_clean"]
    title_fields = ["title_clean", "price_amount_clean", "ward_current"]
    exact_sufficient = result[exact_fields].notna().all(axis=1)
    address_sufficient = result[address_fields].notna().all(axis=1)
    title_sufficient = result[title_fields].notna().all(axis=1)
    exact_key = _group_key(result, exact_fields, "EXACT")
    address_key = _group_key(result, address_fields, "ADDRESS_PRICE_AREA")
    title_key = _group_key(result, title_fields, "TITLE_PRICE_WARD")
    exact_duplicate = exact_sufficient & exact_key.duplicated(keep=False)
    address_cross = address_sufficient & address_key.duplicated(keep=False) & result.groupby(address_key).source_code.transform("nunique").gt(1)
    title_cross = title_sufficient & title_key.duplicated(keep=False) & result.groupby(title_key).source_code.transform("nunique").gt(1)
    duplicate = exact_duplicate | address_cross | title_cross
    parent = {int(index): int(index) for index in result.index[duplicate]}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for key, mask in [(exact_key, exact_duplicate), (address_key, address_cross), (title_key, title_cross)]:
        for members in result.loc[mask].groupby(key[mask]).groups.values():
            member_list = [int(index) for index in members]
            for member in member_list[1:]:
                union(member_list[0], member)

    components: dict[int, list[int]] = {}
    for index in parent:
        components.setdefault(find(index), []).append(index)
    group = pd.Series(pd.NA, index=result.index, dtype="string")
    for members in components.values():
        identities = sorted(str(value) for value in result.loc[members, "rental_post_id"])
        digest = hashlib.sha256("|".join(identities).encode("utf-8")).hexdigest()[:16]
        group.loc[members] = f"CANDIDATE:{digest}"
    result["duplicate_candidate_group"] = group
    result["duplicate_match_reason"] = np.select(
        [exact_duplicate, address_cross, title_cross],
        ["EXACT_FINGERPRINT", "SAME_ADDRESS_PRICE_AREA", "SAME_TITLE_PRICE_WARD"],
        default="NO_MATCH",
    )
    group_source_count = result.loc[duplicate].groupby(group[duplicate]).source_code.transform("nunique")
    result["duplicate_scope"] = "NOT_APPLICABLE"
    result.loc[duplicate, "duplicate_scope"] = np.where(group_source_count.gt(1), "CROSS_SOURCE", "SAME_SOURCE")
    any_sufficient = exact_sufficient | address_sufficient | title_sufficient
    result["duplicate_candidate_status"] = np.select(
        [duplicate, ~any_sufficient], ["POSSIBLE_DUPLICATE", "INSUFFICIENT_DATA"], default="UNIQUE_FINGERPRINT"
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
        | result.admin_consistency_status.eq("INCONSISTENT")
    )
    has_flags = (
        result.numeric_outlier_status.ne("NOT_OUTLIER")
        | result.duplicate_candidate_status.ne("UNIQUE_FINGERPRINT")
        | result.coordinate_quality_status.ne("USABLE")
        | result.price_quality_status.ne("VALIDATED_EXISTING")
        | result.area_quality_status.ne("VALIDATED_EXISTING")
        | result.price_parser_comparison_status.eq("DISAGREEMENT")
        | result.price_model_suitability.ne("SUPPORTED")
        | result.area_model_suitability.ne("SUPPORTED")
        | result.price_area_quality_status.str.endswith("REVIEW")
    )
    result["row_quality_status"] = np.select(
        [requires_review, has_flags], ["REQUIRES_REVIEW", "READY_WITH_FLAGS"], default="READY"
    )
    _compact_derived_strings(result, list(raw.columns))
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
        "price_parser_disagreement_preserved": not (
            silver.price_regression_status.eq("DIFFERENT_REVIEW")
            & ~silver.price_parser_comparison_status.eq("DISAGREEMENT")
        ).any(),
        "price_area_status_domain_valid": (
            set(silver.price_area_availability_status.dropna()).issubset(STATUS_VALUES["price_area_availability_status"])
            and set(silver.price_area_quality_status.dropna()).issubset(STATUS_VALUES["price_area_quality_status"])
        ),
        "duplicate_scope_domain_valid": set(silver.duplicate_scope.dropna()).issubset(STATUS_VALUES["duplicate_scope"]),
        "duplicate_candidate_rows_preserved": len(silver) == len(bronze),
        "cross_source_duplicate_rule_deterministic": not (
            silver.duplicate_match_reason.isin(["SAME_ADDRESS_PRICE_AREA", "SAME_TITLE_PRICE_WARD"])
            & ~silver.duplicate_scope.eq("CROSS_SOURCE")
        ).any(),
        "documented_status_values_only": status_valid,
        "semantic_decisions_auditable": all(
            column in silver and silver[column].notna().all()
            for column in ["listing_intent", "listing_intent_reason", "listing_intent_evidence",
                           "rental_scope", "rental_scope_reason", "rental_scope_evidence"]
        ),
        "price_target_trust_domain_valid": (
            set(silver.price_target_trust_status.dropna()).issubset(
                STATUS_VALUES["price_target_trust_status"]
            )
        ),
        "price_target_trust_reason_evidence_consistent": (
            silver.price_target_trust_reason.notna().all()
            and silver.price_target_trust_evidence.notna().all()
        ),
        "no_trusted_missing_target": not (
            silver.price_target_trust_status.isin(["TRUSTED_EXISTING", "TRUSTED_REPARSED"])
            & silver.price_model_value.isna()
        ).any(),
        "trusted_reparsed_has_evidence": not (
            silver.price_target_trust_status.eq("TRUSTED_REPARSED")
            & silver.price_target_trust_evidence.eq("")
        ).any(),
        "untrusted_has_no_model_value": not (
            ~silver.price_target_trust_status.isin(["TRUSTED_EXISTING", "TRUSTED_REPARSED"])
            & silver.price_model_value.notna()
        ).any(),
    }
    report = SilverQualityGateReport(results)
    if not report.passed:
        failed = [name for name, passed in results.items() if not passed]
        raise SilverQualityGateError(f"Pre-Silver quality gate failed: {', '.join(failed)}")
    return report
