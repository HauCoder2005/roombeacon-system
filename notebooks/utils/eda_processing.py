"""Evidence-led, non-destructive processing helpers for RoomBeacon EDA.

These helpers annotate a current-state analytical snapshot. They never rewrite
Bronze-derived columns and never turn repeated observations into listing rows.
"""

from __future__ import annotations

import math
import re
from typing import Iterable

import numpy as np
import pandas as pd

from .address_cleaner import clean_address
from .location_normalizer import normalize_location


_COMPOSITE_PRICE_PATTERN = re.compile(
    r"(?<!\d)(?P<millions>\d+(?:[.,]\d+)?)\s*triệu\s+"
    r"(?P<thousands>\d{1,3})\s*nghìn(?!\w)",
    flags=re.IGNORECASE,
)
_AMBIGUOUS_COMPOSITE_PATTERN = re.compile(
    r"(?<!\d)\d+(?:[.,]\d+)?\s*triệu\s+\d{1,3}(?!\s*nghìn)",
    flags=re.IGNORECASE,
)
_DAILY_PERIOD_PATTERN = re.compile(
    r"(?:/\s*ngày|mỗi\s+ngày|theo\s+ngày|đồng\s*/\s*ngày|thuê\s+ngày)",
    flags=re.IGNORECASE,
)

_HCMC_DISTRICT_NAMES = (
    "Bình Chánh",
    "Bình Tân",
    "Bình Thạnh",
    "Cần Giờ",
    "Củ Chi",
    "Gò Vấp",
    "Hóc Môn",
    "Nhà Bè",
    "Phú Nhuận",
    "Tân Bình",
    "Tân Phú",
    "Thủ Đức",
)
_HCMC_DISTRICT_PATTERN = re.compile(
    r"\b(?P<prefix>Quận|Huyện)\s+"
    r"(?P<name>1[0-2]|[1-9]|"
    + "|".join(re.escape(name) for name in _HCMC_DISTRICT_NAMES)
    + r")\b",
    flags=re.IGNORECASE,
)
_THU_DUC_CITY_PATTERN = re.compile(
    r"\bThành\s+phố\s+Thủ\s+Đức\b",
    flags=re.IGNORECASE,
)

_PROPERTY_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "ROOM_INFERRED": re.compile(
        r"\b(?:phòng\s+trọ|phòng\s+cho\s+thuê|cho\s+thuê\s+phòng|thuê\s+phòng)\b",
        flags=re.IGNORECASE,
    ),
    "APARTMENT_INFERRED": re.compile(
        r"\b(?:căn\s+hộ|studio|chdv|duplex|apartment)\b",
        flags=re.IGNORECASE,
    ),
    "HOUSE_INFERRED": re.compile(
        r"\b(?:nhà\s+nguyên\s+căn|nguyên\s+căn|cho\s+thuê\s+nhà|nhà\s+cho\s+thuê)\b",
        flags=re.IGNORECASE,
    ),
    "DORMITORY_INFERRED": re.compile(
        r"\b(?:ký\s+túc\s+xá|kí\s+túc\s+xá|ktx|sleepbox)\b",
        flags=re.IGNORECASE,
    ),
}


def _finite_number(value: object) -> float | None:
    """Return a finite float or ``None`` without treating booleans as numbers."""
    if value is None or isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def correct_composite_vnd_price(
    price_raw: object,
    price_original: object,
) -> tuple[float | None, str]:
    """Correct only explicit ``X triệu Y nghìn`` source strings.

    Other formats are returned unchanged. A bare number after ``triệu`` is
    intentionally not interpreted because the unit of that component is not
    explicit.
    """
    original = _finite_number(price_original)
    if not isinstance(price_raw, str):
        return original, "UNCHANGED"

    match = _COMPOSITE_PRICE_PATTERN.search(price_raw.strip())
    if match:
        millions = float(match.group("millions").replace(",", "."))
        thousands = float(match.group("thousands"))
        corrected = millions * 1_000_000.0 + thousands * 1_000.0
        return corrected, "CORRECTED_COMPOSITE_MILLION_THOUSAND"

    if _AMBIGUOUS_COMPOSITE_PATTERN.search(price_raw.strip()):
        return original, "AMBIGUOUS_UNCHANGED"

    return original, "UNCHANGED"


def annotate_price_quality(
    frame: pd.DataFrame,
    *,
    original_col: str = "price_amount",
    raw_col: str = "price_raw",
    title_col: str = "title_raw",
) -> pd.DataFrame:
    """Add derived price values, quality states, period states, and reasons."""
    required = {original_col, raw_col, title_col}
    missing = required.difference(frame.columns)
    if missing:
        raise KeyError(f"Missing required price columns: {sorted(missing)}")

    result = frame.copy(deep=True)
    originals: list[float | None] = []
    analytical: list[float | None] = []
    statuses: list[str] = []
    correction_reasons: list[str] = []
    period_statuses: list[str] = []

    for original_value, raw_value, title_value in result[
        [original_col, raw_col, title_col]
    ].itertuples(index=False, name=None):
        original = _finite_number(original_value)
        raw_text = raw_value if isinstance(raw_value, str) else ""
        title_text = title_value if isinstance(title_value, str) else ""
        originals.append(original)

        is_daily = bool(_DAILY_PERIOD_PATTERN.search(f"{raw_text} {title_text}"))
        period_statuses.append(
            "EXPLICIT_DAILY" if is_daily else "MONTHLY_OR_SOURCE_IMPLICIT"
        )

        corrected, correction = correct_composite_vnd_price(raw_value, original)
        if is_daily:
            analytical.append(None)
            statuses.append("PERIOD_INCOMPATIBLE_DAILY")
            correction_reasons.append("EXPLICIT_DAILY_PERIOD")
        elif original is None and not raw_text.strip():
            analytical.append(None)
            statuses.append("MISSING")
            correction_reasons.append("NONE")
        elif original is None:
            analytical.append(None)
            statuses.append("REVIEW_AMBIGUOUS")
            correction_reasons.append("RAW_PRICE_PRESENT_BUT_NUMERIC_MISSING")
        elif original <= 0:
            analytical.append(None)
            statuses.append("INVALID_NON_POSITIVE")
            correction_reasons.append("NON_POSITIVE_NUMERIC_PRICE")
        elif correction == "CORRECTED_COMPOSITE_MILLION_THOUSAND":
            analytical.append(corrected)
            statuses.append("CORRECTED_COMPOSITE")
            correction_reasons.append("RAW_COMPOSITE_MILLION_THOUSAND")
        elif correction == "AMBIGUOUS_UNCHANGED":
            analytical.append(corrected)
            statuses.append("REVIEW_AMBIGUOUS")
            correction_reasons.append("AMBIGUOUS_COMPOSITE_FORMAT")
        else:
            analytical.append(corrected)
            statuses.append("VALID_ORIGINAL")
            correction_reasons.append("NONE")

    result["price_original"] = pd.Series(originals, index=result.index, dtype="Float64")
    result["price_analytical"] = pd.Series(
        analytical, index=result.index, dtype="Float64"
    )
    result["price_quality_status"] = statuses
    result["price_correction_reason"] = correction_reasons
    result["price_period_status"] = period_statuses
    return result


def _same_number_in_distance_phrase(title: object, area: float) -> bool:
    """Detect an explicit distance phrase containing the parsed area number."""
    if not isinstance(title, str) or not math.isfinite(area):
        return False
    number = f"{area:g}"
    distance_before = re.compile(
        rf"(?:cách|gần|chỉ|khoảng|đến)[^.;,:]{{0,60}}"
        rf"(?<!\d){re.escape(number)}\s*m(?!\s*(?:2|²))",
        flags=re.IGNORECASE,
    )
    # Do not accept a later generic ``gần`` as evidence.  For example,
    # ``gác cao 2m, gần trường`` describes height, not a two-metre distance.
    return bool(distance_before.search(title))


def annotate_area_quality(
    frame: pd.DataFrame,
    *,
    original_col: str = "area_value",
    raw_col: str = "area_raw",
    title_col: str = "title_raw",
    source_col: str = "source_code",
) -> pd.DataFrame:
    """Annotate area quality while preserving uncertain statistical extremes."""
    required = {original_col, raw_col, title_col, source_col}
    missing = required.difference(frame.columns)
    if missing:
        raise KeyError(f"Missing required area columns: {sorted(missing)}")

    result = frame.copy(deep=True)
    numeric = pd.to_numeric(result[original_col], errors="coerce").astype("Float64")
    result["area_original"] = numeric

    positive = result.loc[numeric.gt(0), [source_col]].copy()
    positive["_area"] = numeric[numeric.gt(0)].astype(float)
    source_p99 = positive.groupby(source_col, dropna=False)["_area"].quantile(0.99)

    analytical: list[float | None] = []
    statuses: list[str] = []
    reasons: list[str] = []

    values = result[[source_col, title_col, raw_col]].copy()
    values["_numeric"] = numeric
    for source, title, _raw, value in values.itertuples(index=False, name=None):
        number = _finite_number(value)
        if number is None:
            analytical.append(None)
            statuses.append("MISSING")
            reasons.append("NONE")
            continue
        if number <= 0:
            analytical.append(None)
            statuses.append("INVALID_NON_POSITIVE")
            reasons.append("NON_POSITIVE_NUMERIC_AREA")
            continue
        if source == "phongtro123" and _same_number_in_distance_phrase(title, number):
            analytical.append(None)
            statuses.append("CONFIRMED_CONTAMINATION")
            reasons.append("DISTANCE_TOKEN_PARSED_AS_AREA")
            continue

        threshold = source_p99.get(source, np.nan)
        if pd.notna(threshold) and number >= float(threshold):
            analytical.append(number)
            statuses.append("SUSPICIOUS_EXTREME")
            reasons.append("AT_OR_ABOVE_SOURCE_P99_REVIEW_ONLY")
        else:
            analytical.append(number)
            statuses.append("VALID")
            reasons.append("NONE")

    result["area_analytical"] = pd.Series(
        analytical, index=result.index, dtype="Float64"
    )
    result["area_quality_status"] = statuses
    result["area_exclusion_reason"] = reasons
    return result


def _extract_explicit_district(address: object) -> str | None:
    if not isinstance(address, str):
        return None
    if _THU_DUC_CITY_PATTERN.search(address):
        return "Thành phố Thủ Đức"

    match = _HCMC_DISTRICT_PATTERN.search(address)
    if not match:
        return None
    prefix = match.group("prefix").title()
    suffix = match.group("name")
    if suffix.isdigit():
        return f"{prefix} {suffix}"
    return f"{prefix} {suffix.title()}"


def derive_location_fields(
    frame: pd.DataFrame,
    *,
    address_col: str = "full_address_text",
) -> pd.DataFrame:
    """Derive explicit location levels without expanding ambiguous mappings."""
    if address_col not in frame.columns:
        raise KeyError(f"Missing required location column: {address_col}")
    result = frame.copy(deep=True)
    result["address_clean"] = result[address_col].map(clean_address)
    result["province_analytical"] = result["address_clean"].map(
        lambda value: (
            "TPHCM"
            if isinstance(value, str)
            and re.search(
                r"\b(?:TPHCM|TP\.?\s*HCM|Hồ\s+Chí\s+Minh)\b",
                value,
                flags=re.IGNORECASE,
            )
            else None
        )
    )
    result["district_analytical"] = result["address_clean"].map(
        _extract_explicit_district
    )
    result["ward_candidates"] = result["address_clean"].map(normalize_location)
    result["ward_candidate_count"] = result["ward_candidates"].map(len)
    result["ward_analytical"] = result["ward_candidates"].map(
        lambda candidates: candidates[0] if len(candidates) == 1 else None
    )
    result["ward_mapping_status"] = result["ward_candidate_count"].map(
        lambda count: (
            "UNMAPPED" if count == 0 else "UNAMBIGUOUS" if count == 1 else "AMBIGUOUS"
        )
    )
    return result


def infer_property_type_signal(title: object) -> tuple[str | None, str]:
    """Return an explicitly inferred type signal and its confidence status."""
    if not isinstance(title, str) or not title.strip():
        return None, "UNCLASSIFIED"
    matches = [
        label for label, pattern in _PROPERTY_TYPE_PATTERNS.items() if pattern.search(title)
    ]
    if not matches:
        return None, "UNCLASSIFIED"
    if len(matches) > 1:
        return None, "AMBIGUOUS"
    return matches[0], "INFERRED"


def annotate_property_type_inference(
    frame: pd.DataFrame,
    *,
    title_col: str = "title_raw",
    source_type_col: str = "property_type_raw",
) -> pd.DataFrame:
    """Keep source type separate from title-derived analytical inference."""
    required = {title_col, source_type_col}
    missing = required.difference(frame.columns)
    if missing:
        raise KeyError(f"Missing property-type columns: {sorted(missing)}")
    result = frame.copy(deep=True)
    inferred = result[title_col].map(infer_property_type_signal)
    result["property_type_source"] = result[source_type_col]
    result["property_type_inferred"] = inferred.map(lambda pair: pair[0])
    result["property_type_inference_status"] = inferred.map(lambda pair: pair[1])
    return result


def safe_one_to_one_enrich(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: str = "rental_post_id",
) -> pd.DataFrame:
    """Left-enrich a listing snapshot while proving one-row-per-listing."""
    if on not in left.columns or on not in right.columns:
        raise KeyError(f"Join key {on!r} must exist in both frames")
    if left[on].isna().any() or left[on].duplicated().any():
        raise ValueError(f"left-side {on} must be non-null and unique")
    if right[on].isna().any() or right[on].duplicated().any():
        raise ValueError(f"right-side {on} must be non-null and unique")

    before_rows = len(left)
    before_ids = left[on].nunique()
    result = left.merge(right, how="left", on=on, sort=False, validate="one_to_one")
    if len(result) != before_rows or result[on].nunique() != before_ids:
        raise AssertionError("One-to-one enrichment changed listing cardinality")
    return result


def add_eligibility_masks(frame: pd.DataFrame) -> pd.DataFrame:
    """Create question-specific eligibility masks without dropping listings."""
    required = {
        "price_analytical",
        "price_quality_status",
        "area_analytical",
        "area_quality_status",
        "ward_analytical",
        "ward_mapping_status",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise KeyError(f"Missing eligibility columns: {sorted(missing)}")

    result = frame.copy(deep=True)
    result["price_eligible"] = (
        result["price_quality_status"].isin(
            ["VALID_ORIGINAL", "CORRECTED_COMPOSITE"]
        )
        & pd.to_numeric(result["price_analytical"], errors="coerce").gt(0)
    )
    result["area_eligible"] = (
        result["area_quality_status"].isin(["VALID", "SUSPICIOUS_EXTREME"])
        & pd.to_numeric(result["area_analytical"], errors="coerce").gt(0)
    )
    result["location_eligible"] = (
        result["ward_mapping_status"].eq("UNAMBIGUOUS")
        & result["ward_analytical"].notna()
    )
    result["price_area_eligible"] = result["price_eligible"] & result["area_eligible"]
    result["price_location_eligible"] = (
        result["price_eligible"] & result["location_eligible"]
    )
    result["area_location_eligible"] = (
        result["area_eligible"] & result["location_eligible"]
    )
    result["price_area_location_eligible"] = (
        result["price_area_eligible"] & result["location_eligible"]
    )
    result["price_per_m2_eligible"] = result["price_area_eligible"]
    return result


def add_price_per_m2(frame: pd.DataFrame) -> pd.DataFrame:
    """Create price per m² only for compatible price-and-area observations."""
    required = {
        "price_analytical",
        "area_analytical",
        "price_eligible",
        "area_eligible",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise KeyError(f"Missing price-per-m2 columns: {sorted(missing)}")
    result = frame.copy(deep=True)
    eligible = result["price_eligible"] & result["area_eligible"]
    result["price_per_m2_eligible"] = eligible
    result["price_per_m2"] = pd.Series(pd.NA, index=result.index, dtype="Float64")
    result.loc[eligible, "price_per_m2"] = (
        pd.to_numeric(result.loc[eligible, "price_analytical"], errors="coerce")
        / pd.to_numeric(result.loc[eligible, "area_analytical"], errors="coerce")
    ).astype(float)
    result["price_per_m2_reason"] = np.select(
        [~result["price_eligible"], ~result["area_eligible"]],
        ["PRICE_INELIGIBLE", "AREA_INELIGIBLE"],
        default="ELIGIBLE",
    )
    return result


def summarize_processing_impact(
    frame: pd.DataFrame,
    status_col: str,
    *,
    source_col: str = "source_code",
) -> pd.DataFrame:
    """Count processing states overall or by source with transparent percentages."""
    if status_col not in frame.columns:
        raise KeyError(f"Missing status column: {status_col}")
    group_columns: list[str] = []
    if source_col in frame.columns:
        group_columns.append(source_col)
    group_columns.append(status_col)
    summary = (
        frame.groupby(group_columns, dropna=False)
        .size()
        .rename("row_count")
        .reset_index()
    )
    summary["percentage"] = 100.0 * summary["row_count"] / len(frame) if len(frame) else 0.0
    return summary.sort_values("row_count", ascending=False, ignore_index=True)


def classify_sample_reliability(
    count: int,
    insufficient_max: int,
    low_max: int,
    usable_max: int,
) -> str:
    """Classify a group using cut points supplied by the executed EDA."""
    if not (0 <= insufficient_max < low_max < usable_max):
        raise ValueError("Reliability cut points must be strictly increasing")
    if count <= insufficient_max:
        return "INSUFFICIENT_SAMPLE"
    if count <= low_max:
        return "LOW_SAMPLE"
    if count <= usable_max:
        return "USABLE"
    return "HIGH_CONFIDENCE"


def summarize_numeric(values: Iterable[object]) -> pd.Series:
    """Return robust descriptive statistics used consistently by the notebook."""
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    present = numeric.dropna()
    quantiles = present.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    return pd.Series(
        {
            "count": int(present.size),
            "missing": int(numeric.isna().sum()),
            "zero": int(present.eq(0).sum()),
            "negative": int(present.lt(0).sum()),
            "min": present.min() if not present.empty else np.nan,
            "P01": quantiles.get(0.01, np.nan),
            "P05": quantiles.get(0.05, np.nan),
            "P25": quantiles.get(0.25, np.nan),
            "median": quantiles.get(0.5, np.nan),
            "mean": present.mean() if not present.empty else np.nan,
            "P75": quantiles.get(0.75, np.nan),
            "P95": quantiles.get(0.95, np.nan),
            "P99": quantiles.get(0.99, np.nan),
            "max": present.max() if not present.empty else np.nan,
            "IQR": quantiles.get(0.75, np.nan) - quantiles.get(0.25, np.nan),
        }
    )
