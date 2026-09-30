"""Deterministic boundaries for location-first analytical helpers."""

import numpy as np
import pandas as pd
import pytest

from notebooks.utils.location_analysis import (
    add_spatial_search_mode,
    audit_coordinate_trust,
    derive_local_price_bands,
    filter_listings_by_price,
    get_listings_within_radius,
    haversine_distance_km,
    summarize_local_price_by_radius,
    validate_reference_location,
)


def location_frame():
    """Return unique, shared-address, conflicting-centroid and missing fixtures."""
    return pd.DataFrame({
        'rental_post_id': [1, 2, 3, 4, 5, 6],
        'source_code': ['a'] * 6,
        'map_latitude': [10.0, 10.01, 10.01, 10.02, 10.02, None],
        'map_longitude': [106.0, 106.01, 106.01, 106.02, 106.02, None],
        'map_provider': ['google_maps_embed'] * 5 + [None],
        'full_address_text': ['A', 'B', 'B', 'C', 'D', None],
        'district_text_extracted': ['D1', 'D1', 'D1', 'D2', 'D3', 'D4'],
        'ward_current': [None] * 6,
        'price_amount_clean_candidate': [1, 2, 3, 4, 5, None],
    })


def test_coordinate_trust_rejects_conflicting_shared_point():
    audited = audit_coordinate_trust(location_frame())
    assert audited.has_trusted_coordinate.tolist() == [True, True, True, False, False, False]
    assert audited.loc[3, 'coordinate_trust_reason'] == 'SHARED_POINT_CONFLICTING_ADDRESSES'
    assert audited.loc[5, 'coordinate_trust_reason'] == 'MISSING_COORDINATE_PAIR'


def test_spatial_modes_keep_admin_fallback():
    audited = audit_coordinate_trust(location_frame())
    result = add_spatial_search_mode(audited)
    assert result.spatial_search_mode.tolist() == [
        'RADIUS_ELIGIBLE', 'RADIUS_ELIGIBLE', 'RADIUS_ELIGIBLE',
        'ADMIN_ONLY', 'ADMIN_ONLY', 'ADMIN_ONLY',
    ]


def test_haversine_and_radius_filter_preserve_one_row_grain():
    assert haversine_distance_km([0], [0], 0, 0)[0] == pytest.approx(0)
    assert haversine_distance_km([0], [1], 0, 0)[0] == pytest.approx(111.195, rel=1e-3)
    audited = audit_coordinate_trust(location_frame())
    local = get_listings_within_radius(audited, 10.0, 106.0, 2)
    assert local.rental_post_id.tolist() == [1, 2, 3]
    assert local.rental_post_id.is_unique


def test_price_filter_uses_existing_clean_candidate_only():
    audited = audit_coordinate_trust(location_frame())
    local = get_listings_within_radius(audited, 10.0, 106.0, 2)
    result = filter_listings_by_price(local, min_price=2, max_price=3)
    assert result.rental_post_id.tolist() == [2, 3]
    with pytest.raises(ValueError):
        filter_listings_by_price(local, min_price=4, max_price=3)


def test_local_bands_are_derived_locally_and_fail_closed_on_ties():
    data = pd.DataFrame({'price_amount_clean_candidate': [1, 2, 3, 4, 5, 6]})
    labels, boundaries = derive_local_price_bands(data)
    assert labels.value_counts().to_dict() == {'LOCAL_LOW': 2, 'LOCAL_MEDIUM': 2, 'LOCAL_HIGH': 2}
    assert boundaries == {'p33': pytest.approx(2.6666666667), 'p67': pytest.approx(4.3333333333), 'valid_price_count': 6}
    tied = pd.DataFrame({'price_amount_clean_candidate': [2, 2, 2, 2]})
    labels, boundaries = derive_local_price_bands(tied)
    assert labels.isna().all() and boundaries is None


def test_radius_summary_is_cumulative_and_reference_validation_is_strict():
    audited = audit_coordinate_trust(location_frame())
    reference = {'name': 'fixture', 'latitude': 10.0, 'longitude': 106.0}
    summary, bands = summarize_local_price_by_radius(audited, reference, [1, 2])
    assert summary.listing_count.tolist() == [1, 3]
    assert summary.valid_price_count.tolist() == [1, 3]
    assert bands.radius_km.unique().tolist() == [2]
    assert validate_reference_location(reference)
    assert not validate_reference_location(None)
    assert not validate_reference_location({'name': 'bad', 'latitude': 91, 'longitude': 0})
