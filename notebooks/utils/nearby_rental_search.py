"""Nearby rental search and spatial validation helpers for RoomBeacon.

This module owns the core spatial retrieval logic, coordinate validation,
Haversine distance calculation, distance band assignment, administrative
fallback matching, coordinate-to-admin consistency auditing, search ranking,
price display policy enforcement, and market summarization.
"""

from __future__ import annotations
import re
import unicodedata

from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np
import pandas as pd

EARTH_RADIUS_KM: float = 6371.0088

# Known adjacent district boundaries in Ho Chi Minh City
# Used strictly for conservative coordinate-to-admin consistency checking without GIS boundary polygons
HCM_ADJACENT_DISTRICTS: dict[str, set[str]] = {
    "Quận 1": {"Quận 1", "Quận 3", "Quận 4", "Quận 5", "Quận 10", "Quận Bình Thạnh", "Quận Phú Nhuận", "Thành phố Thủ Đức"},
    "Quận 3": {"Quận 3", "Quận 1", "Quận 10", "Quận Phú Nhuận", "Quận Tân Bình"},
    "Quận 4": {"Quận 4", "Quận 1", "Quận 7", "Quận 8"},
    "Quận 5": {"Quận 5", "Quận 1", "Quận 6", "Quận 8", "Quận 10", "Quận 11"},
    "Quận 6": {"Quận 6", "Quận 5", "Quận 8", "Quận 11", "Quận Tân Phú", "Quận Bình Tân"},
    "Quận 7": {"Quận 7", "Quận 4", "Quận 8", "Huyện Nhà Bè", "Thành phố Thủ Đức", "Huyện Bình Chánh"},
    "Quận 8": {"Quận 8", "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận Bình Tân", "Huyện Bình Chánh"},
    "Quận 10": {"Quận 10", "Quận 3", "Quận 5", "Quận 11", "Quận Tân Bình"},
    "Quận 11": {"Quận 11", "Quận 5", "Quận 6", "Quận 10", "Quận Tân Bình", "Quận Tân Phú"},
    "Quận 12": {"Quận 12", "Quận Gò Vấp", "Quận Tân Bình", "Quận Tân Phú", "Quận Bình Tân", "Thành phố Thủ Đức", "Huyện Hóc Môn", "Huyện Củ Chi"},
    "Quận Bình Thạnh": {"Quận Bình Thạnh", "Quận 1", "Quận Phú Nhuận", "Quận Gò Vấp", "Thành phố Thủ Đức"},
    "Quận Gò Vấp": {"Quận Gò Vấp", "Quận 12", "Quận Bình Thạnh", "Quận Phú Nhuận", "Quận Tân Bình"},
    "Quận Phú Nhuận": {"Quận Phú Nhuận", "Quận 1", "Quận 3", "Quận Bình Thạnh", "Quận Gò Vấp", "Quận Tân Bình"},
    "Quận Tân Bình": {"Quận Tân Bình", "Quận 3", "Quận 10", "Quận 11", "Quận 12", "Quận Gò Vấp", "Quận Phú Nhuận", "Quận Tân Phú"},
    "Quận Tân Phú": {"Quận Tân Phú", "Quận 6", "Quận 11", "Quận 12", "Quận Tân Bình", "Quận Bình Tân"},
    "Quận Bình Tân": {"Quận Bình Tân", "Quận 6", "Quận 8", "Quận 12", "Quận Tân Phú", "Huyện Bình Chánh", "Huyện Hóc Môn"},
    "Thành phố Thủ Đức": {"Thành phố Thủ Đức", "Quận 1", "Quận 4", "Quận 7", "Quận Bình Thạnh", "Quận 12"},
}

__all__ = [
    "EARTH_RADIUS_KM",
    "HCM_ADJACENT_DISTRICTS",
    "is_valid_coordinate",
    "haversine_distance_km",
    "assign_distance_band",
    "filter_rental_compatible",
    "derive_display_price",
    "create_reference_location_contract",
    "classify_coordinate_search_status",
    "format_filter_range",
    "audit_location_coverage",
    "execute_nearby_rental_search",
    "build_search_funnel",
    "summarize_radius_market",
    "evaluate_product_readiness",
]


def is_valid_coordinate(latitude: Any, longitude: Any) -> bool:
    """Validate whether latitude and longitude form a valid, non-zero geographic coordinate pair.

    Requirements:
    - Not null / NaN
    - Numeric and finite
    - -90 <= latitude <= 90
    - -180 <= longitude <= 180
    - (0, 0) is explicitly rejected as a default/null coordinate pair
    """
    if latitude is None or longitude is None:
        return False
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (ValueError, TypeError):
        return False

    if not (np.isfinite(lat) and np.isfinite(lon)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    return True


def haversine_distance_km(
    latitude: Any,
    longitude: Any,
    reference_latitude: float,
    reference_longitude: float,
) -> np.ndarray | float:
    """Return great-circle distance in kilometers using the standard Haversine formula.

    Supports both scalar and vectorized numpy/pandas inputs.
    Earth radius is taken as 6371.0088 km.
    """
    lat1 = np.radians(np.asarray(latitude, dtype=float))
    lon1 = np.radians(np.asarray(longitude, dtype=float))
    lat2 = np.radians(float(reference_latitude))
    lon2 = np.radians(float(reference_longitude))

    delta_lat = lat1 - lat2
    delta_lon = lon1 - lon2

    a = np.sin(delta_lat / 2.0) ** 2 + np.cos(lat2) * np.cos(lat1) * np.sin(delta_lon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return EARTH_RADIUS_KM * c


def assign_distance_band(distance_km: pd.Series | float | None) -> pd.Series | str | None:
    """Assign distance bands without double counting:

    - <= 1 km   : [0.0, 1.0]
    - 1–3 km    : (1.0, 3.0]
    - 3–5 km    : (3.0, 5.0]
    - 5–10 km   : (5.0, 10.0]
    - > 10 km   : (10.0, inf)

    Returns None / pd.NA for missing or administrative fallback listings.
    """
    if isinstance(distance_km, pd.Series):
        conds = [
            distance_km.notna() & (distance_km >= 0.0) & (distance_km <= 1.0),
            distance_km.notna() & (distance_km > 1.0) & (distance_km <= 3.0),
            distance_km.notna() & (distance_km > 3.0) & (distance_km <= 5.0),
            distance_km.notna() & (distance_km > 5.0) & (distance_km <= 10.0),
            distance_km.notna() & (distance_km > 10.0),
        ]
        choices = ["<= 1 km", "1–3 km", "3–5 km", "5–10 km", "> 10 km"]
        return pd.Series(np.select(conds, choices, default=pd.NA), index=distance_km.index, dtype="string")
    elif distance_km is not None and pd.notna(distance_km):
        d = float(distance_km)
        if 0.0 <= d <= 1.0:
            return "<= 1 km"
        elif 1.0 < d <= 3.0:
            return "1–3 km"
        elif 3.0 < d <= 5.0:
            return "3–5 km"
        elif 5.0 < d <= 10.0:
            return "5–10 km"
        elif d > 10.0:
            return "> 10 km"
    return None


def filter_rental_compatible(listings: pd.DataFrame) -> pd.DataFrame:
    """Filter to ordinary rental-compatible listings using canonical Silver fields.

    Excludes explicit SALE, TRANSFER, and aggregate building scopes (WHOLE_BUILDING, MULTI_UNIT_BUSINESS).
    UNKNOWN intent and scope are retained absent conflicting evidence.
    """
    intent = listings["listing_intent"].astype("string") if "listing_intent" in listings else pd.Series("RENT", index=listings.index)
    scope = listings["rental_scope"].astype("string") if "rental_scope" in listings else pd.Series("ROOM", index=listings.index)

    incompatible_intent = intent.isin(["SALE", "TRANSFER"])
    incompatible_scope = scope.isin(["WHOLE_BUILDING", "MULTI_UNIT_BUSINESS"])

    eligible = ~(incompatible_intent | incompatible_scope)
    return listings.loc[eligible].copy()


def derive_display_price(
    df: pd.DataFrame,
    price_display_policy: str = "TRUSTED_ONLY",
) -> pd.DataFrame:
    """Derive user-facing rental display price and trust metadata according to price display policy.

    Policies:
    - "TRUSTED_ONLY" (default): Only prices verified by the canonical target trust contract
      (TRUSTED_EXISTING or TRUSTED_REPARSED) are displayed as numeric values.
      PARSER_DISAGREEMENT_REVIEW and untrusted listings have display_price = np.nan.
    - "ALLOW_REVIEW_WITH_WARNING": Allows PARSER_DISAGREEMENT_REVIEW prices to be displayed
      with an explicit price_display_status = "REVIEW_WARNING".
    """
    if price_display_policy not in {"TRUSTED_ONLY", "ALLOW_REVIEW_WITH_WARNING"}:
        raise ValueError(f"Invalid price_display_policy: {price_display_policy}. Must be 'TRUSTED_ONLY' or 'ALLOW_REVIEW_WITH_WARNING'.")

    result = df.copy()
    model_val = pd.to_numeric(result.get("price_model_value", pd.Series(np.nan, index=result.index)), errors="coerce")
    clean_val = pd.to_numeric(result.get("price_amount_clean", pd.Series(np.nan, index=result.index)), errors="coerce")
    trust_status = result.get("price_target_trust_status", pd.Series("UNASSESSED", index=result.index)).astype("string")

    is_trusted = trust_status.isin(["TRUSTED_EXISTING", "TRUSTED_REPARSED"]) & model_val.notna() & model_val.gt(0)
    is_review = trust_status.eq("PARSER_DISAGREEMENT_REVIEW") & clean_val.notna() & clean_val.gt(0)

    display_price = pd.Series(np.nan, index=result.index, dtype="float64")
    display_status = pd.Series("MISSING", index=result.index, dtype="string")
    display_source = pd.Series("MISSING_PRICE", index=result.index, dtype="string")

    # 1. Trusted target values
    display_price.loc[is_trusted] = model_val.loc[is_trusted]
    display_status.loc[is_trusted] = "TRUSTED"
    display_source.loc[is_trusted] = "TRUSTED_TARGET_MODEL_VALUE"

    # 2. Review values handling based on policy
    if price_display_policy == "ALLOW_REVIEW_WITH_WARNING":
        display_price.loc[is_review] = clean_val.loc[is_review]
        display_status.loc[is_review] = "REVIEW_WARNING"
        display_source.loc[is_review] = "UNCONFIRMED_CLEAN_AMOUNT"
    else:  # TRUSTED_ONLY
        display_status.loc[is_review] = "REVIEW_EXCLUDED"
        display_source.loc[is_review] = "REVIEW_PRICE_EXCLUDED_IN_TRUSTED_ONLY"

    # 3. Non-trusted / suspect unit scale
    suspect = trust_status.eq("SUSPECT_UNIT_SCALE")
    display_status.loc[suspect] = "SUSPECT_UNIT_SCALE"
    display_source.loc[suspect] = "SUSPECT_UNIT_SCALE"

    result["display_price"] = display_price
    result["price_display_status"] = display_status
    result["price_display_source"] = display_source
    result["price_display_policy"] = price_display_policy
    if "price_target_trust_status" not in result:
        result["price_target_trust_status"] = trust_status

    return result


_DISTRICT_IN_KEY = re.compile(r"\b((?:quan|huyen|thi xa|thanh pho)\s+.+)$")


def _ascii_key(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(c for c in decomposed if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")
    return " ".join(plain.lower().split())


def reference_ward_district_consistency(ward: str | None, district: str | None) -> str:
    """Check a user-supplied current ward against its district via the internal ward mapping.

    Returns CONSISTENT, WARD_NOT_IN_DISTRICT, UNKNOWN_WARD, UNVERIFIABLE (the mapping
    records no district for that ward) or NOT_APPLICABLE (ward or district missing).
    """
    if not ward or not district:
        return "NOT_APPLICABLE"
    from roombeacon_processing.ward_mapping import WARD_MAPPING

    sources = [key for key, wards in WARD_MAPPING.items() if ward in wards]
    if not sources:
        return "UNKNOWN_WARD"
    districts = {match.group(1) for key in sources if (match := _DISTRICT_IN_KEY.search(key))}
    if not districts:
        return "UNVERIFIABLE"
    return "CONSISTENT" if _ascii_key(district) in districts else "WARD_NOT_IN_DISTRICT"


def create_reference_location_contract(
    name: str,
    latitude: float | None,
    longitude: float | None,
    ward: str | None = None,
    district: str | None = None,
) -> dict[str, Any]:
    """Create explicit reference location contract with normalization and verification status.

    Statuses:
    - USER_SUPPLIED_UNVERIFIED: Coordinates and administrative labels are both supplied,
      but offline polygon GIS boundaries do not exist in the project to prove lat/lon belongs to ward.
    - COORDINATE_ONLY: Valid coordinates provided without administrative context.
    - ADMIN_ONLY: Administrative ward/district provided without valid coordinates.
    - INVALID: Neither valid coordinates nor administrative labels are usable.
    """
    has_coord = is_valid_coordinate(latitude, longitude)
    norm_ward = str(ward).strip() if ward is not None and str(ward).strip() else None
    norm_dist = str(district).strip() if district is not None and str(district).strip() else None

    if has_coord and (norm_ward or norm_dist):
        verification_status = "USER_SUPPLIED_UNVERIFIED"
    elif has_coord:
        verification_status = "COORDINATE_ONLY"
    elif norm_ward or norm_dist:
        verification_status = "ADMIN_ONLY"
    else:
        verification_status = "INVALID"

    return {
        "reference_name": str(name).strip(),
        "reference_latitude": float(latitude) if has_coord else None,
        "reference_longitude": float(longitude) if has_coord else None,
        "reference_ward": norm_ward,
        "reference_district": norm_dist,
        "reference_admin_verification_status": verification_status,
        "reference_admin_consistency": reference_ward_district_consistency(norm_ward, norm_dist),
        "is_exact_distance_capable": has_coord,
    }


def classify_coordinate_search_status(
    listings: pd.DataFrame,
    reference_district: str | None = None,
    reference_ward: str | None = None,
) -> pd.Series:
    """Classify coordinate search status reflecting validity, provider trust, and textual consistency.

    Statuses:
    - TRUSTED_CONSISTENT: Trusted coordinates and administrative text matches reference area.
    - TRUSTED_ADMIN_UNVERIFIED: Trusted coordinates, but administrative text is missing or adjacent without polygon proof.
    - TRUSTED_BUT_ADMIN_MISMATCH: Trusted coordinates, but textual district explicitly contradicts the reference area.
    - SHARED_POINT_CONFLICT: Multiple conflicting addresses pinned to the exact same rounded coordinate.
    - INVALID: Coordinates are out of bounds, non-finite, zero, or from untrusted provider.
    - MISSING: Latitude or longitude is null/empty.
    """
    has_lat = listings["map_latitude"].notna() if "map_latitude" in listings else pd.Series(False, index=listings.index)
    has_lon = listings["map_longitude"].notna() if "map_longitude" in listings else pd.Series(False, index=listings.index)
    paired = has_lat & has_lon

    valid_pair = listings["coordinate_pair_valid"].fillna(False) if "coordinate_pair_valid" in listings else paired
    trusted_coord = listings["has_trusted_coordinate"].fillna(False) if "has_trusted_coordinate" in listings else pd.Series(False, index=listings.index)
    trust_reason = listings.get("coordinate_trust_reason", pd.Series("MISSING_COORDINATE_PAIR", index=listings.index)).astype("string")

    dist_col = listings.get("district_text_extracted", pd.Series(pd.NA, index=listings.index)).astype("string").str.strip()
    ward_col = listings.get("ward_current", pd.Series(pd.NA, index=listings.index)).astype("string").str.strip()

    status = pd.Series("MISSING", index=listings.index, dtype="string")
    status.loc[paired & ~valid_pair] = "INVALID"
    status.loc[valid_pair & ~trusted_coord] = "INVALID"
    status.loc[trust_reason.eq("SHARED_POINT_CONFLICTING_ADDRESSES")] = "SHARED_POINT_CONFLICT"

    if trusted_coord.any():
        trusted_idx = listings.index[trusted_coord]
        ref_d = str(reference_district).strip() if reference_district is not None else ""
        ref_w = str(reference_ward).strip() if reference_ward is not None else ""
        adjacent = HCM_ADJACENT_DISTRICTS.get(ref_d, {ref_d}) if ref_d else set()

        for idx in trusted_idx:
            ld = dist_col.loc[idx] if pd.notna(dist_col.loc[idx]) else ""
            lw = ward_col.loc[idx] if pd.notna(ward_col.loc[idx]) else ""
            if not ld and not lw:
                status.loc[idx] = "TRUSTED_ADMIN_UNVERIFIED"
            elif (ref_d and ld == ref_d) or (ref_w and lw == ref_w):
                status.loc[idx] = "TRUSTED_CONSISTENT"
            elif ref_d and ld in adjacent:
                status.loc[idx] = "TRUSTED_ADMIN_UNVERIFIED"
            elif ref_d and ld:
                status.loc[idx] = "TRUSTED_BUT_ADMIN_MISMATCH"
            else:
                status.loc[idx] = "TRUSTED_ADMIN_UNVERIFIED"

    return status


def format_filter_range(min_val: float | None, max_val: float | None, unit: str = "") -> str:
    """Format numeric filter bounds safely without raising format exceptions when bounds are None."""
    min_str = f"{min_val:,.0f}" if min_val is not None else "None"
    max_str = f"{max_val:,.0f}" if max_val is not None else "Unlimited"
    return f"{min_str} - {max_str} {unit}".strip()


def audit_location_coverage(listings: pd.DataFrame) -> pd.DataFrame:
    """Produce comprehensive location and coordinate coverage statistics.

    Measures total rows, valid coordinates, trusted coordinates, suspicious hotspots,
    and administrative resolutions (ward/district).
    """
    total = len(listings)
    if total == 0:
        return pd.DataFrame()

    has_lat = listings["map_latitude"].notna() if "map_latitude" in listings else pd.Series(False, index=listings.index)
    has_lon = listings["map_longitude"].notna() if "map_longitude" in listings else pd.Series(False, index=listings.index)
    paired = has_lat & has_lon

    valid_pair = listings["coordinate_pair_valid"].fillna(False) if "coordinate_pair_valid" in listings else paired
    trusted_coord = listings["has_trusted_coordinate"].fillna(False) if "has_trusted_coordinate" in listings else pd.Series(False, index=listings.index)

    trust_reason = listings.get("coordinate_trust_reason", pd.Series("MISSING_COORDINATE_PAIR", index=listings.index))
    hotspot_conflict = trust_reason.eq("SHARED_POINT_CONFLICTING_ADDRESSES")

    ward = listings["ward_current"].astype("string").str.strip() if "ward_current" in listings else pd.Series("", index=listings.index)
    has_ward = ward.notna() & ward.ne("")

    dist = listings["district_text_extracted"].astype("string").str.strip() if "district_text_extracted" in listings else pd.Series("", index=listings.index)
    has_dist = dist.notna() & dist.ne("")

    unresolved = ~trusted_coord & ~has_ward & ~has_dist

    metrics = [
        {"Metric": "Total rental-compatible listings", "Count": total, "Percent": 100.0},
        {"Metric": "Coordinate fields present (lat & lon)", "Count": int(paired.sum()), "Percent": round(paired.sum() / total * 100, 2)},
        {"Metric": "Valid coordinate pairs (-90..90, -180..180, non-zero)", "Count": int(valid_pair.sum()), "Percent": round(valid_pair.sum() / total * 100, 2)},
        {"Metric": "Trusted coordinate pairs (exact-distance capable)", "Count": int(trusted_coord.sum()), "Percent": round(trusted_coord.sum() / total * 100, 2)},
        {"Metric": "Suspicious shared/default coordinates (conflicting addresses)", "Count": int(hotspot_conflict.sum()), "Percent": round(hotspot_conflict.sum() / total * 100, 2)},
        {"Metric": "Missing coordinate pairs", "Count": int((~paired).sum()), "Percent": round((~paired).sum() / total * 100, 2)},
        {"Metric": "Administrative ward resolved (ward_current)", "Count": int(has_ward.sum()), "Percent": round(has_ward.sum() / total * 100, 2)},
        {"Metric": "Administrative district resolved", "Count": int(has_dist.sum()), "Percent": round(has_dist.sum() / total * 100, 2)},
        {"Metric": "Unresolved location (no trusted coord, no ward, no district)", "Count": int(unresolved.sum()), "Percent": round(unresolved.sum() / total * 100, 2)},
    ]
    return pd.DataFrame(metrics)


def execute_nearby_rental_search(
    listings: pd.DataFrame,
    *,
    reference_latitude: float,
    reference_longitude: float,
    reference_ward: str | None = None,
    reference_district: str | None = None,
    radius_km: float = 3.0,
    min_price: float | None = None,
    max_price: float | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    max_results: int = 20,
    price_display_policy: str = "TRUSTED_ONLY",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Execute nearby rental retrieval according to the multi-tier confidence contract.

    Taxonomy States:
    - EXACT_DISTANCE_CAPABLE: Listings with trusted coordinates eligible for exact distance calculation.
    - SAME_WARD: Untrusted coordinates, but listing ward matches reference ward. distance_km is strictly None.
    - SAME_DISTRICT: Untrusted coordinates, different ward, but district matches reference district. distance_km is strictly None.
    - RESOLVED_OUTSIDE_REFERENCE_AREA: Untrusted coordinates, resolved administrative location outside reference area. distance_km is strictly None.
    - LOCATION_UNRESOLVED: Untrusted coordinates and neither ward nor district could be resolved.

    Returns:
        (exact_results, same_ward_results, same_district_results, full_prepared_df)
    """
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    if not is_valid_coordinate(reference_latitude, reference_longitude):
        raise ValueError(f"Invalid reference coordinate pair: ({reference_latitude}, {reference_longitude})")

    prepared = filter_rental_compatible(listings)
    prepared = derive_display_price(prepared, price_display_policy=price_display_policy)

    trusted_coord = prepared["has_trusted_coordinate"].fillna(False) if "has_trusted_coordinate" in prepared else pd.Series(False, index=prepared.index)

    # 1. Exact distance calculation ONLY for trusted coordinates
    distance_km = pd.Series(np.nan, index=prepared.index, dtype="float64")
    if trusted_coord.any():
        trusted_idx = prepared.index[trusted_coord]
        lats = prepared.loc[trusted_idx, "map_latitude"]
        lons = prepared.loc[trusted_idx, "map_longitude"]
        distance_km.loc[trusted_idx] = haversine_distance_km(lats, lons, reference_latitude, reference_longitude)

    prepared["distance_km"] = distance_km
    prepared["distance_band"] = assign_distance_band(distance_km)

    # 2. Location match taxonomy & search tier assignment
    ward_col = prepared["ward_current"].astype("string").str.strip().fillna("") if "ward_current" in prepared else pd.Series("", index=prepared.index)
    dist_col = prepared["district_text_extracted"].astype("string").str.strip().fillna("") if "district_text_extracted" in prepared else pd.Series("", index=prepared.index)

    ref_w = str(reference_ward).strip() if reference_ward is not None and str(reference_ward).strip() else ""
    ref_d = str(reference_district).strip() if reference_district is not None and str(reference_district).strip() else ""

    has_ward = ward_col.ne("")
    has_dist = dist_col.ne("")

    is_exact_capable = trusted_coord
    is_same_ward = (~trusted_coord) & (ref_w != "") & ward_col.eq(ref_w)
    is_same_district = (~trusted_coord) & (~is_same_ward) & (ref_d != "") & dist_col.eq(ref_d)
    is_unresolved = (~trusted_coord) & (~has_ward) & (~has_dist)
    is_outside = (~trusted_coord) & (~is_same_ward) & (~is_same_district) & (has_ward | has_dist)

    location_match_type = pd.Series("LOCATION_UNRESOLVED", index=prepared.index, dtype="string")
    location_match_type.loc[is_exact_capable] = "EXACT_DISTANCE_CAPABLE"
    location_match_type.loc[is_same_ward] = "SAME_WARD"
    location_match_type.loc[is_same_district] = "SAME_DISTRICT"
    location_match_type.loc[is_outside] = "RESOLVED_OUTSIDE_REFERENCE_AREA"
    location_match_type.loc[is_unresolved] = "LOCATION_UNRESOLVED"

    search_tier = pd.Series("TIER_5_LOCATION_UNRESOLVED", index=prepared.index, dtype="string")
    search_tier.loc[is_exact_capable] = "TIER_1_EXACT_DISTANCE"
    search_tier.loc[is_same_ward] = "TIER_2_SAME_WARD"
    search_tier.loc[is_same_district] = "TIER_3_SAME_DISTRICT"
    search_tier.loc[is_outside] = "TIER_4_RESOLVED_OUTSIDE"
    search_tier.loc[is_unresolved] = "TIER_5_LOCATION_UNRESOLVED"

    prepared["location_match_type"] = location_match_type
    prepared["search_tier"] = search_tier

    # 3. Coordinate Search Quality classification
    prepared["coordinate_search_status"] = classify_coordinate_search_status(
        prepared,
        reference_district=ref_d,
        reference_ward=ref_w,
    )

    # 4. Optional price & area filtering
    keep_mask = pd.Series(True, index=prepared.index)
    price = pd.to_numeric(prepared["display_price"], errors="coerce")
    area = pd.to_numeric(prepared.get("area_value_clean", pd.Series(np.nan, index=prepared.index)), errors="coerce")

    if min_price is not None:
        keep_mask &= price.notna() & price.ge(min_price)
    if max_price is not None:
        keep_mask &= price.notna() & price.le(max_price)
    if min_area is not None:
        keep_mask &= area.notna() & area.ge(min_area)
    if max_area is not None:
        keep_mask &= area.notna() & area.le(max_area)

    filtered = prepared.loc[keep_mask].copy()

    # 5. Result separation & deterministic ranking
    # TIER 1: Exact distance <= radius_km
    exact_candidates = filtered.loc[
        filtered["location_match_type"].eq("EXACT_DISTANCE_CAPABLE") & filtered["distance_km"].le(radius_km)
    ].copy()

    # Priority rank:
    # 1. coordinate_search_status: TRUSTED_CONSISTENT (0) -> TRUSTED_ADMIN_UNVERIFIED (1) -> TRUSTED_BUT_ADMIN_MISMATCH (2)
    # 2. distance_km ASC
    # 3. price trust priority: TRUSTED (0) -> other (1)
    # 4. display_price ASC
    # 5. latest_observed_at DESC
    exact_candidates["_coord_rank"] = exact_candidates["coordinate_search_status"].map({
        "TRUSTED_CONSISTENT": 0,
        "TRUSTED_ADMIN_UNVERIFIED": 1,
        "TRUSTED_BUT_ADMIN_MISMATCH": 2,
    }).fillna(1)
    exact_candidates["_trust_rank"] = exact_candidates["price_display_status"].eq("TRUSTED").map({True: 0, False: 1})

    exact_sorted = exact_candidates.sort_values(
        by=["_coord_rank", "distance_km", "_trust_rank", "display_price", "latest_observed_at"],
        ascending=[True, True, True, True, False],
        na_position="last",
    ).drop(columns=["_coord_rank", "_trust_rank"])
    exact_results = exact_sorted.head(max_results)

    # TIER 2: Same Ward fallback
    same_ward_candidates = filtered.loc[filtered["location_match_type"].eq("SAME_WARD")].copy()
    same_ward_candidates["_trust_rank"] = same_ward_candidates["price_display_status"].eq("TRUSTED").map({True: 0, False: 1})
    same_ward_sorted = same_ward_candidates.sort_values(
        by=["_trust_rank", "latest_observed_at", "display_price"],
        ascending=[True, False, True],
        na_position="last",
    ).drop(columns=["_trust_rank"])
    same_ward_results = same_ward_sorted.head(max_results)

    # TIER 3: Same District fallback
    same_dist_candidates = filtered.loc[filtered["location_match_type"].eq("SAME_DISTRICT")].copy()
    same_dist_candidates["_trust_rank"] = same_dist_candidates["price_display_status"].eq("TRUSTED").map({True: 0, False: 1})
    same_dist_sorted = same_dist_candidates.sort_values(
        by=["_trust_rank", "latest_observed_at", "display_price"],
        ascending=[True, False, True],
        na_position="last",
    ).drop(columns=["_trust_rank"])
    same_district_results = same_dist_sorted.head(max_results)

    return exact_results, same_ward_results, same_district_results, prepared


def build_search_funnel(
    prepared: pd.DataFrame,
    radius_km: float = 3.0,
) -> pd.DataFrame:
    """Build the search coverage funnel table from the prepared search population.

    Strictly separates:
    1. Overall rental population
    2. Search location taxonomy (5 mutually exclusive states)
    3. Radius distance reach (among exact-distance capable subset)
    4. Coordinate search quality within search radius
    """
    total_compat = len(prepared)
    exact_capable = int(prepared["location_match_type"].eq("EXACT_DISTANCE_CAPABLE").sum())
    same_ward = int(prepared["location_match_type"].eq("SAME_WARD").sum())
    same_dist = int(prepared["location_match_type"].eq("SAME_DISTRICT").sum())
    resolved_outside = int(prepared["location_match_type"].eq("RESOLVED_OUTSIDE_REFERENCE_AREA").sum())
    unresolved = int(prepared["location_match_type"].eq("LOCATION_UNRESOLVED").sum())

    exact_df = prepared.loc[prepared["location_match_type"].eq("EXACT_DISTANCE_CAPABLE") & prepared["distance_km"].notna()]
    dist = exact_df["distance_km"]

    w10 = int((dist <= 10.0).sum())
    w5 = int((dist <= 5.0).sum())
    w3 = int((dist <= 3.0).sum())
    w1 = int((dist <= 1.0).sum())

    within_r = exact_df.loc[dist <= radius_km]
    coord_consistent = int(within_r["coordinate_search_status"].eq("TRUSTED_CONSISTENT").sum())
    coord_unverified = int(within_r["coordinate_search_status"].eq("TRUSTED_ADMIN_UNVERIFIED").sum())
    coord_mismatch = int(within_r["coordinate_search_status"].eq("TRUSTED_BUT_ADMIN_MISMATCH").sum())

    funnel_data = [
        {"Category": "Total Population", "Stage": "1. Rental-compatible listings", "Count": total_compat, "Share % (Total)": 100.0, "Share % (Exact)": round(total_compat / total_compat * 100, 2)},
        {"Category": "Search Taxonomy (Mutually Exclusive)", "Stage": "  ├── Exact-distance capable (trusted coords)", "Count": exact_capable, "Share % (Total)": round(exact_capable / total_compat * 100, 2), "Share % (Exact)": 100.0},
        {"Category": "Search Taxonomy (Mutually Exclusive)", "Stage": "  ├── Fallback: Same Ward matches", "Count": same_ward, "Share % (Total)": round(same_ward / total_compat * 100, 2), "Share % (Exact)": 0.0},
        {"Category": "Search Taxonomy (Mutually Exclusive)", "Stage": "  ├── Fallback: Same District matches", "Count": same_dist, "Share % (Total)": round(same_dist / total_compat * 100, 2), "Share % (Exact)": 0.0},
        {"Category": "Search Taxonomy (Mutually Exclusive)", "Stage": "  ├── Resolved outside reference area", "Count": resolved_outside, "Share % (Total)": round(resolved_outside / total_compat * 100, 2), "Share % (Exact)": 0.0},
        {"Category": "Search Taxonomy (Mutually Exclusive)", "Stage": "  └── Location unresolved (no coords, no admin)", "Count": unresolved, "Share % (Total)": round(unresolved / total_compat * 100, 2), "Share % (Exact)": 0.0},
        {"Category": "Exact Radius Reach", "Stage": "2. Exact distance <= 10 km", "Count": w10, "Share % (Total)": round(w10 / total_compat * 100, 2), "Share % (Exact)": round(w10 / exact_capable * 100, 2) if exact_capable else 0.0},
        {"Category": "Exact Radius Reach", "Stage": "3. Exact distance <= 5 km", "Count": w5, "Share % (Total)": round(w5 / total_compat * 100, 2), "Share % (Exact)": round(w5 / exact_capable * 100, 2) if exact_capable else 0.0},
        {"Category": "Exact Radius Reach", "Stage": f"4. Exact distance <= {radius_km:g} km", "Count": w3, "Share % (Total)": round(w3 / total_compat * 100, 2), "Share % (Exact)": round(w3 / exact_capable * 100, 2) if exact_capable else 0.0},
        {"Category": "Exact Radius Reach", "Stage": "5. Exact distance <= 1 km", "Count": w1, "Share % (Total)": round(w1 / total_compat * 100, 2), "Share % (Exact)": round(w1 / exact_capable * 100, 2) if exact_capable else 0.0},
        {"Category": "Coordinate Quality in Radius", "Stage": f"  ├── Consistent with reference area (<= {radius_km:g} km)", "Count": coord_consistent, "Share % (Total)": round(coord_consistent / total_compat * 100, 2), "Share % (Exact)": round(coord_consistent / w3 * 100, 2) if w3 else 0.0},
        {"Category": "Coordinate Quality in Radius", "Stage": f"  ├── Unverified / adjacent admin (<= {radius_km:g} km)", "Count": coord_unverified, "Share % (Total)": round(coord_unverified / total_compat * 100, 2), "Share % (Exact)": round(coord_unverified / w3 * 100, 2) if w3 else 0.0},
        {"Category": "Coordinate Quality in Radius", "Stage": f"  └── Admin mismatch (e.g. claimed Q1/Bình Thạnh)", "Count": coord_mismatch, "Share % (Total)": round(coord_mismatch / total_compat * 100, 2), "Share % (Exact)": round(coord_mismatch / w3 * 100, 2) if w3 else 0.0},
    ]
    return pd.DataFrame(funnel_data)


def summarize_radius_market(
    prepared: pd.DataFrame,
    radii: Iterable[float] = (1.0, 3.0, 5.0, 10.0),
) -> pd.DataFrame:
    """Calculate localized rental price and area diagnostics across concentric radius bands.

    Note: Applies STRICTLY to the trusted-coordinate subset (~1.72% of rental listings).
    """
    exact_df = prepared.loc[prepared["location_match_type"].eq("EXACT_DISTANCE_CAPABLE") & prepared["distance_km"].notna()].copy()
    total_compat = len(prepared)
    rows = []

    for r in sorted(set(float(x) for x in radii)):
        subset = exact_df.loc[exact_df["distance_km"].le(r)]
        prices = pd.to_numeric(subset["display_price"], errors="coerce").dropna()
        areas = pd.to_numeric(subset["area_value_clean"], errors="coerce").dropna()

        # Analytical price per area (for product analysis only, never ML feature)
        valid_ppa = (subset["display_price"] > 0) & (subset["area_value_clean"] > 0)
        ppa = (subset.loc[valid_ppa, "display_price"] / subset.loc[valid_ppa, "area_value_clean"]).dropna()

        top_sources = ", ".join(subset["source_code"].value_counts().head(2).index.tolist()) if len(subset) else "None"
        top_wards = ", ".join(subset["ward_current"].dropna().value_counts().head(2).index.tolist()) if len(subset) else "None"

        rows.append({
            "Radius Band": f"<= {r:g} km",
            "Listing Count (Trusted-Subset Only)": len(subset),
            "Share of Total Rental (%)": round(len(subset) / total_compat * 100, 2) if total_compat else 0.0,
            "Median Rent (VNĐ)": float(prices.median()) if len(prices) else np.nan,
            "P25 Rent (VNĐ)": float(prices.quantile(0.25)) if len(prices) else np.nan,
            "P75 Rent (VNĐ)": float(prices.quantile(0.75)) if len(prices) else np.nan,
            "Median Area (m²)": float(areas.median()) if len(areas) else np.nan,
            "Analytical Median Rent/m² (VNĐ)": float(ppa.median()) if len(ppa) else np.nan,
            "Top Sources": top_sources,
            "Top Wards": top_wards,
        })
    return pd.DataFrame(rows)


def evaluate_product_readiness(
    audit_summary: pd.DataFrame,
    exact_share_threshold: float = 15.0,
    admin_share_threshold: float = 50.0,
) -> dict[str, Any]:
    """Evaluate product readiness according to actual runtime coordinate coverage."""
    metrics_map = dict(zip(audit_summary["Metric"], audit_summary["Percent"]))
    trusted_pct = metrics_map.get("Trusted coordinate pairs (exact-distance capable)", 0.0)
    ward_pct = metrics_map.get("Administrative ward resolved (ward_current)", 0.0)

    if trusted_pct >= exact_share_threshold:
        verdict = "EXACT_RADIUS_READY"
        interpretation = (
            f"RoomBeacon has adequate trusted coordinate coverage ({trusted_pct:.1f}%) "
            "to support radius-based geographic retrieval as a primary feature."
        )
    elif ward_pct >= admin_share_threshold:
        verdict = "ADMIN_FALLBACK_READY"
        interpretation = (
            f"RoomBeacon trusted coordinate coverage is currently limited ({trusted_pct:.1f}%), "
            f"while administrative ward coverage is substantial ({ward_pct:.1f}%). "
            "The platform reliably supports administrative location discovery (Same-Ward / Same-District), "
            "with exact radius retrieval operating as a high-precision but low-coverage prototype tier."
        )
    else:
        verdict = "LIMITED_LOCATION_COVERAGE"
        interpretation = (
            f"Both trusted coordinate coverage ({trusted_pct:.1f}%) and administrative coverage "
            f"({ward_pct:.1f}%) are insufficient for reliable location-based discovery."
        )

    return {
        "verdict": verdict,
        "trusted_coordinate_percent": trusted_pct,
        "administrative_ward_percent": ward_pct,
        "interpretation": interpretation,
    }
