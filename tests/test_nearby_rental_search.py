"""Unit tests for the nearby rental search and spatial validation helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from notebooks.utils.nearby_rental_search import (
    EARTH_RADIUS_KM,
    assign_distance_band,
    audit_location_coverage,
    build_search_funnel,
    classify_coordinate_search_status,
    create_reference_location_contract,
    derive_display_price,
    evaluate_product_readiness,
    execute_nearby_rental_search,
    filter_rental_compatible,
    format_filter_range,
    haversine_distance_km,
    is_valid_coordinate,
    summarize_radius_market,
)


def test_is_valid_coordinate():
    # Valid coordinates
    assert is_valid_coordinate(10.7725, 106.6578) is True
    assert is_valid_coordinate("10.7725", "106.6578") is True
    assert is_valid_coordinate(-89.9, 179.9) is True

    # Invalid latitude
    assert is_valid_coordinate(91.0, 106.0) is False
    assert is_valid_coordinate(-90.1, 106.0) is False

    # Invalid longitude
    assert is_valid_coordinate(10.0, 181.0) is False
    assert is_valid_coordinate(10.0, -180.1) is False

    # Null / non-numeric
    assert is_valid_coordinate(None, 106.0) is False
    assert is_valid_coordinate(10.0, None) is False
    assert is_valid_coordinate(np.nan, 106.0) is False
    assert is_valid_coordinate("abc", 106.0) is False

    # (0, 0) explicitly rejected as placeholder default
    assert is_valid_coordinate(0.0, 0.0) is False
    assert is_valid_coordinate(0, 0) is False


def test_haversine_distance_km():
    # Same point gives 0
    dist_zero = haversine_distance_km(10.7725, 106.6578, 10.7725, 106.6578)
    assert np.isclose(dist_zero, 0.0, atol=1e-6)

    # Known pair: Landmark 81 (10.7950, 106.7218) to Ben Thanh Market (10.7720, 106.6983)
    # Expected distance is ~3.62 km
    dist_known = haversine_distance_km(10.7950, 106.7218, 10.7720, 106.6983)
    assert 3.5 <= dist_known <= 3.8

    # Vectorized test
    lats = [10.7725, 10.7950]
    lons = [106.6578, 106.7218]
    vec_dists = haversine_distance_km(lats, lons, 10.7725, 106.6578)
    assert len(vec_dists) == 2
    assert np.isclose(vec_dists[0], 0.0, atol=1e-6)
    assert vec_dists[1] > 3.0


def test_assign_distance_band():
    # Exact boundary checks
    assert assign_distance_band(0.0) == "<= 1 km"
    assert assign_distance_band(1.0) == "<= 1 km"
    assert assign_distance_band(1.0001) == "1–3 km"
    assert assign_distance_band(3.0) == "1–3 km"
    assert assign_distance_band(3.0001) == "3–5 km"
    assert assign_distance_band(5.0) == "3–5 km"
    assert assign_distance_band(5.0001) == "5–10 km"
    assert assign_distance_band(10.0) == "5–10 km"
    assert assign_distance_band(10.0001) == "> 10 km"

    # Missing / null distance returns None
    assert assign_distance_band(None) is None
    assert assign_distance_band(np.nan) is None

    # Series vectorized test
    s = pd.Series([0.5, 2.0, 4.0, 7.5, 15.0, np.nan])
    bands = assign_distance_band(s)
    expected = ["<= 1 km", "1–3 km", "3–5 km", "5–10 km", "> 10 km", pd.NA]
    assert bands.tolist() == expected


def test_filter_rental_compatible():
    sample = pd.DataFrame([
        {"rental_post_id": 1, "listing_intent": "RENT", "rental_scope": "ROOM"},
        {"rental_post_id": 2, "listing_intent": "SALE", "rental_scope": "HOUSE"},
        {"rental_post_id": 3, "listing_intent": "TRANSFER", "rental_scope": "ROOM"},
        {"rental_post_id": 4, "listing_intent": "RENT", "rental_scope": "WHOLE_BUILDING"},
        {"rental_post_id": 5, "listing_intent": "RENT", "rental_scope": "MULTI_UNIT_BUSINESS"},
        {"rental_post_id": 6, "listing_intent": "UNKNOWN", "rental_scope": "UNKNOWN"},
    ])
    compat = filter_rental_compatible(sample)
    assert set(compat["rental_post_id"]) == {1, 6}


def test_derive_display_price_policies():
    sample = pd.DataFrame([
        {"rental_post_id": 1, "price_model_value": 3500000.0, "price_amount_clean": 3500000.0, "price_target_trust_status": "TRUSTED_EXISTING"},
        {"rental_post_id": 2, "price_model_value": np.nan, "price_amount_clean": 4000000.0, "price_target_trust_status": "PARSER_DISAGREEMENT_REVIEW"},
        {"rental_post_id": 3, "price_model_value": 2800000.0, "price_amount_clean": 2800000000.0, "price_target_trust_status": "TRUSTED_REPARSED"},
        {"rental_post_id": 4, "price_model_value": np.nan, "price_amount_clean": 9900000000.0, "price_target_trust_status": "SUSPECT_UNIT_SCALE"},
    ])

    # 1. TRUSTED_ONLY policy (default)
    derived_trusted = derive_display_price(sample, price_display_policy="TRUSTED_ONLY")
    assert derived_trusted.loc[0, "display_price"] == 3500000.0
    assert derived_trusted.loc[0, "price_display_status"] == "TRUSTED"

    # Review listing is excluded from numeric display price
    assert pd.isna(derived_trusted.loc[1, "display_price"])
    assert derived_trusted.loc[1, "price_display_status"] == "REVIEW_EXCLUDED"

    assert derived_trusted.loc[2, "display_price"] == 2800000.0
    assert derived_trusted.loc[2, "price_display_status"] == "TRUSTED"

    assert pd.isna(derived_trusted.loc[3, "display_price"])
    assert derived_trusted.loc[3, "price_display_status"] == "SUSPECT_UNIT_SCALE"

    # 2. ALLOW_REVIEW_WITH_WARNING policy
    derived_review = derive_display_price(sample, price_display_policy="ALLOW_REVIEW_WITH_WARNING")
    assert derived_review.loc[1, "display_price"] == 4000000.0
    assert derived_review.loc[1, "price_display_status"] == "REVIEW_WARNING"
    assert derived_review.loc[1, "price_display_source"] == "UNCONFIRMED_CLEAN_AMOUNT"


def test_reference_location_contract():
    # Public interface verification
    assert callable(create_reference_location_contract)

    # Coords + Ward/District -> USER_SUPPLIED_UNVERIFIED
    ref1 = create_reference_location_contract(
        "Bách Khoa", 10.7725, 106.6578, ward="Phường Diên Hồng", district="Quận 10"
    )
    assert ref1["reference_admin_verification_status"] == "USER_SUPPLIED_UNVERIFIED"
    assert ref1["is_exact_distance_capable"] is True

    # Coords only -> COORDINATE_ONLY
    ref2 = create_reference_location_contract("Point X", 10.7725, 106.6578)
    assert ref2["reference_admin_verification_status"] == "COORDINATE_ONLY"

    # Admin only -> ADMIN_ONLY
    ref3 = create_reference_location_contract("District Only", None, None, district="Quận 10")
    assert ref3["reference_admin_verification_status"] == "ADMIN_ONLY"
    assert ref3["is_exact_distance_capable"] is False

    # Invalid -> INVALID
    ref4 = create_reference_location_contract("Empty", None, None)
    assert ref4["reference_admin_verification_status"] == "INVALID"


def test_format_filter_range():
    assert format_filter_range(None, None) == "None - Unlimited"
    assert format_filter_range(3000000.0, None, "VNĐ") == "3,000,000 - Unlimited VNĐ"
    assert format_filter_range(None, 10000000.0, "VNĐ") == "None - 10,000,000 VNĐ"
    assert format_filter_range(15.0, 50.0, "m²") == "15 - 50 m²"


def test_search_location_taxonomy_separation():
    # Setup mock listings
    # Ref location: (10.7725, 106.6578), Ward: "Phường 14", District: "Quận 10"
    listings = pd.DataFrame([
        # 1. Trusted coordinate nearby (< 1km) -> EXACT_DISTANCE_CAPABLE
        {
            "rental_post_id": 101,
            "title_clean": "Phòng trọ gần Bách Khoa",
            "source_code": "phongtro123",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7730,
            "map_longitude": 106.6580,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường 14",
            "district_text_extracted": "Quận 10",
            "price_model_value": 3500000.0,
            "price_amount_clean": 3500000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 20.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
        # 2. Trusted coordinate far away (> 3km) -> EXACT_DISTANCE_CAPABLE (capable != in radius)
        {
            "rental_post_id": 102,
            "title_clean": "Phòng trọ Thủ Đức",
            "source_code": "mogi",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.8500,
            "map_longitude": 106.7500,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường Linh Trung",
            "district_text_extracted": "Thủ Đức",
            "price_model_value": 2500000.0,
            "price_amount_clean": 2500000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 18.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
        # 3. Untrusted coordinate, matching ward -> SAME_WARD
        {
            "rental_post_id": 103,
            "title_clean": "Phòng trọ Lý Thường Kiệt P14",
            "source_code": "nhatot",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": np.nan,
            "map_longitude": np.nan,
            "has_trusted_coordinate": False,
            "coordinate_pair_valid": False,
            "ward_current": "Phường 14",
            "district_text_extracted": "Quận 10",
            "price_model_value": 3000000.0,
            "price_amount_clean": 3000000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 25.0,
            "latest_observed_at": pd.Timestamp("2026-09-26"),
        },
        # 4. Untrusted coordinate, different ward but matching district -> SAME_DISTRICT
        {
            "rental_post_id": 104,
            "title_clean": "Phòng trọ Phường 11 Quận 10",
            "source_code": "phongtro123",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7700,
            "map_longitude": 106.6600,
            "has_trusted_coordinate": False,
            "coordinate_trust_reason": "SHARED_POINT_CONFLICTING_ADDRESSES",
            "coordinate_pair_valid": True,
            "ward_current": "Phường 11",
            "district_text_extracted": "Quận 10",
            "price_model_value": 4000000.0,
            "price_amount_clean": 4000000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 22.0,
            "latest_observed_at": pd.Timestamp("2026-09-24"),
        },
        # 5. Untrusted coordinate, other ward & district -> RESOLVED_OUTSIDE_REFERENCE_AREA (NOT unresolved!)
        {
            "rental_post_id": 105,
            "title_clean": "Phòng trọ Bình Thạnh",
            "source_code": "nhatot",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": np.nan,
            "map_longitude": np.nan,
            "has_trusted_coordinate": False,
            "coordinate_pair_valid": False,
            "ward_current": "Phường 25",
            "district_text_extracted": "Quận Bình Thạnh",
            "price_model_value": 3200000.0,
            "price_amount_clean": 3200000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 20.0,
            "latest_observed_at": pd.Timestamp("2026-09-20"),
        },
        # 6. Truly unresolved location (no coords, no ward, no district) -> LOCATION_UNRESOLVED
        {
            "rental_post_id": 106,
            "title_clean": "Phòng trọ không rõ địa chỉ",
            "source_code": "nhatot",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": np.nan,
            "map_longitude": np.nan,
            "has_trusted_coordinate": False,
            "coordinate_pair_valid": False,
            "ward_current": None,
            "district_text_extracted": None,
            "price_model_value": 2500000.0,
            "price_amount_clean": 2500000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 18.0,
            "latest_observed_at": pd.Timestamp("2026-09-20"),
        },
        # 7. Incompatible intent (SALE) -> completely excluded
        {
            "rental_post_id": 107,
            "title_clean": "Bán nhà gần Bách Khoa",
            "source_code": "cafeland",
            "listing_intent": "SALE",
            "rental_scope": "HOUSE",
            "map_latitude": 10.7726,
            "map_longitude": 106.6579,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường 14",
            "district_text_extracted": "Quận 10",
            "price_model_value": np.nan,
            "price_amount_clean": 10000000000.0,
            "price_target_trust_status": "SUSPECT_UNIT_SCALE",
            "area_value_clean": 80.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
    ])

    exact, same_ward, same_dist, full = execute_nearby_rental_search(
        listings,
        reference_latitude=10.7725,
        reference_longitude=106.6578,
        reference_ward="Phường 14",
        reference_district="Quận 10",
        radius_km=3.0,
    )

    # 1. Tier 1 Exact distance:
    # Post 101 is trusted and within 3km (< 0.1 km)
    assert len(exact) == 1
    assert exact.iloc[0]["rental_post_id"] == 101
    assert pd.notna(exact.iloc[0]["distance_km"])
    assert exact.iloc[0]["distance_km"] < 1.0
    assert exact.iloc[0]["distance_band"] == "<= 1 km"
    assert exact.iloc[0]["location_match_type"] == "EXACT_DISTANCE_CAPABLE"

    # Post 102 is capable but outside 3km, so not in exact results
    assert 102 not in exact["rental_post_id"].values
    p102 = full.loc[full["rental_post_id"] == 102].iloc[0]
    assert p102["location_match_type"] == "EXACT_DISTANCE_CAPABLE"
    assert p102["distance_km"] > 3.0

    # Post 107 (SALE) is excluded completely from rental search
    assert 107 not in full["rental_post_id"].values

    # 2. Tier 2 Same Ward fallback:
    # Post 103 is in same ward, distance_km MUST be strictly NULL
    assert len(same_ward) == 1
    assert same_ward.iloc[0]["rental_post_id"] == 103
    assert pd.isna(same_ward.iloc[0]["distance_km"])
    assert pd.isna(same_ward.iloc[0]["distance_band"])
    assert same_ward.iloc[0]["location_match_type"] == "SAME_WARD"

    # 3. Tier 3 Same District fallback:
    # Post 104 is in same district, distance_km MUST be strictly NULL
    assert len(same_dist) == 1
    assert same_dist.iloc[0]["rental_post_id"] == 104
    assert pd.isna(same_dist.iloc[0]["distance_km"])
    assert pd.isna(same_dist.iloc[0]["distance_band"])
    assert same_dist.iloc[0]["location_match_type"] == "SAME_DISTRICT"

    # 4. Post 105 is in another district -> RESOLVED_OUTSIDE_REFERENCE_AREA (NOT UNRESOLVED!)
    p105 = full.loc[full["rental_post_id"] == 105].iloc[0]
    assert p105["location_match_type"] == "RESOLVED_OUTSIDE_REFERENCE_AREA"
    assert p105["search_tier"] == "TIER_4_RESOLVED_OUTSIDE"
    assert pd.isna(p105["distance_km"])

    # 5. Post 106 has NO location evidence -> LOCATION_UNRESOLVED
    p106 = full.loc[full["rental_post_id"] == 106].iloc[0]
    assert p106["location_match_type"] == "LOCATION_UNRESOLVED"
    assert p106["search_tier"] == "TIER_5_LOCATION_UNRESOLVED"
    assert pd.isna(p106["distance_km"])


def test_coordinate_consistency_and_ranking_priority():
    # Setup listings around Q10 reference (10.7725, 106.6578)
    # Post 201: Matches Q10 -> TRUSTED_CONSISTENT (dist ~0.3 km)
    # Post 202: District text is Quận 1 (mismatch like 69388) -> TRUSTED_BUT_ADMIN_MISMATCH (dist ~0.1 km, closer!)
    # Post 203: District text is None -> TRUSTED_ADMIN_UNVERIFIED (dist ~0.2 km)
    listings = pd.DataFrame([
        {
            "rental_post_id": 201,
            "title_clean": "Phòng Q10 chính chủ",
            "source_code": "phongtro123",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7750,
            "map_longitude": 106.6580,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường 14",
            "district_text_extracted": "Quận 10",
            "price_model_value": 3500000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 20.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
        {
            "rental_post_id": 202,
            "title_clean": "Cho thuê phòng Lê Thánh Tôn Q1",
            "source_code": "mogi",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7730,
            "map_longitude": 106.6580,  # Extremely close (0.06 km), but text says Q1!
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường Bến Thành",
            "district_text_extracted": "Quận 1",
            "price_model_value": 3500000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 25.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
        {
            "rental_post_id": 203,
            "title_clean": "Phòng không ghi quận",
            "source_code": "mogi",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7740,
            "map_longitude": 106.6580,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": None,
            "district_text_extracted": None,
            "price_model_value": 3500000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 22.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
    ])

    exact, _, _, full = execute_nearby_rental_search(
        listings,
        reference_latitude=10.7725,
        reference_longitude=106.6578,
        reference_ward="Phường 14",
        reference_district="Quận 10",
        radius_km=3.0,
    )

    # Verify status assignment
    status_map = dict(zip(full["rental_post_id"], full["coordinate_search_status"]))
    assert status_map[201] == "TRUSTED_CONSISTENT"
    assert status_map[202] == "TRUSTED_BUT_ADMIN_MISMATCH"
    assert status_map[203] == "TRUSTED_ADMIN_UNVERIFIED"

    # Deterministic Ranking check:
    # 201 (TRUSTED_CONSISTENT) MUST rank before 203 (TRUSTED_ADMIN_UNVERIFIED),
    # which MUST rank before 202 (TRUSTED_BUT_ADMIN_MISMATCH), even though 202 is closest in distance!
    ranked_ids = exact["rental_post_id"].tolist()
    assert ranked_ids == [201, 203, 202]


def test_search_filters_with_optional_none():
    listings = pd.DataFrame([
        {
            "rental_post_id": 1,
            "title_clean": "Phòng 1",
            "source_code": "phongtro123",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7726,
            "map_longitude": 106.6579,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường 14",
            "district_text_extracted": "Quận 10",
            "price_model_value": 3000000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 20.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
        {
            "rental_post_id": 2,
            "title_clean": "Phòng 2 - Đắt",
            "source_code": "phongtro123",
            "listing_intent": "RENT",
            "rental_scope": "ROOM",
            "map_latitude": 10.7726,
            "map_longitude": 106.6579,
            "has_trusted_coordinate": True,
            "coordinate_pair_valid": True,
            "ward_current": "Phường 14",
            "district_text_extracted": "Quận 10",
            "price_model_value": 8000000.0,
            "price_target_trust_status": "TRUSTED_EXISTING",
            "area_value_clean": 40.0,
            "latest_observed_at": pd.Timestamp("2026-09-25"),
        },
    ])

    # Filter with MAX_PRICE=None, MIN_PRICE=None -> must not crash and returns all matches
    exact, _, _, _ = execute_nearby_rental_search(
        listings,
        reference_latitude=10.7725,
        reference_longitude=106.6578,
        radius_km=3.0,
        min_price=None,
        max_price=None,
        min_area=None,
        max_area=None,
    )
    assert len(exact) == 2


def test_evaluate_product_readiness():
    audit_low = pd.DataFrame([
        {"Metric": "Trusted coordinate pairs (exact-distance capable)", "Percent": 1.72},
        {"Metric": "Administrative ward resolved (ward_current)", "Percent": 83.74},
    ])
    res_low = evaluate_product_readiness(audit_low)
    assert res_low["verdict"] == "ADMIN_FALLBACK_READY"
    assert "administrative ward coverage is substantial" in res_low["interpretation"]

    audit_high = pd.DataFrame([
        {"Metric": "Trusted coordinate pairs (exact-distance capable)", "Percent": 25.0},
        {"Metric": "Administrative ward resolved (ward_current)", "Percent": 90.0},
    ])
    res_high = evaluate_product_readiness(audit_high)
    assert res_high["verdict"] == "EXACT_RADIUS_READY"


@pytest.mark.parametrize(
    ("ward", "district", "expected"),
    [
        # Phường Tân Bình was formed from wards 13–15 of Quận Tân Bình, not Quận 10.
        ("Phường Tân Bình", "Quận 10", "WARD_NOT_IN_DISTRICT"),
        ("Phường Diên Hồng", "Quận 10", "CONSISTENT"),
        ("Phường Bến Thành", "Quận 1", "CONSISTENT"),
        ("Phường Không Tồn Tại", "Quận 10", "UNKNOWN_WARD"),
        (None, "Quận 10", "NOT_APPLICABLE"),
    ],
)
def test_reference_contract_checks_ward_belongs_to_district(ward, district, expected):
    contract = create_reference_location_contract("Ref", 10.7725, 106.6578, ward=ward, district=district)

    assert contract["reference_admin_consistency"] == expected
