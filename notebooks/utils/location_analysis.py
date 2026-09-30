"""Location quality, radius search and local-market helpers for RoomBeacon notebooks."""

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd


EARTH_RADIUS_KM = 6371.0088
TRUSTED_COORDINATE_PROVIDERS = frozenset({'google_maps_embed'})


def audit_coordinate_trust(
    listings: pd.DataFrame,
    *,
    latitude_col: str = 'map_latitude',
    longitude_col: str = 'map_longitude',
    provider_col: str = 'map_provider',
    address_col: str = 'full_address_text',
    precision: int = 6,
) -> pd.DataFrame:
    """Return a copy with coordinate quality, hotspot and trust evidence.

    A coordinate is eligible when it is a valid non-zero pair from an explicit
    source-map provider and is not shared by conflicting detailed addresses.
    Repeated coordinates remain eligible only when every non-null detailed
    address at that rounded point is the same. This preserves legitimate
    building-level reuse while rejecting observed ward/district centroids.
    """
    result = listings.copy()
    required = {latitude_col, longitude_col, provider_col, address_col}
    missing = required - set(result.columns)
    if missing:
        raise KeyError(f'Missing coordinate audit columns: {sorted(missing)}')

    latitude = pd.to_numeric(result[latitude_col], errors='coerce')
    longitude = pd.to_numeric(result[longitude_col], errors='coerce')
    paired = latitude.notna() & longitude.notna()
    finite = pd.Series(
        np.isfinite(latitude.to_numpy(dtype=float, na_value=np.nan))
        & np.isfinite(longitude.to_numpy(dtype=float, na_value=np.nan)),
        index=result.index,
    )
    in_bounds = latitude.between(-90, 90) & longitude.between(-180, 180)
    non_zero = latitude.ne(0) & longitude.ne(0)
    valid = paired & finite & in_bounds & non_zero

    lat_key = latitude.round(precision)
    lon_key = longitude.round(precision)
    pair_frame = pd.DataFrame({'lat_key': lat_key, 'lon_key': lon_key}, index=result.index)
    pair_count = pair_frame.groupby(['lat_key', 'lon_key'], dropna=True)['lat_key'].transform('size')

    normalized_address = (
        result[address_col].astype('string').str.strip().str.lower().replace('', pd.NA)
    )
    address_frame = pair_frame.assign(address=normalized_address)
    address_count = address_frame.groupby(['lat_key', 'lon_key'], dropna=True)['address'].transform('nunique')

    provider_trusted = result[provider_col].astype('string').isin(TRUSTED_COORDINATE_PROVIDERS)
    address_consistent = pair_count.eq(1) | (normalized_address.notna() & address_count.eq(1))
    trusted = valid & provider_trusted & address_consistent

    reason = pd.Series('TRUSTED_UNIQUE_POINT', index=result.index, dtype='string')
    reason.loc[trusted & pair_count.gt(1)] = 'TRUSTED_SHARED_ADDRESS'
    reason.loc[~paired] = 'MISSING_COORDINATE_PAIR'
    reason.loc[paired & ~finite] = 'NONFINITE_COORDINATE'
    reason.loc[paired & finite & ~in_bounds] = 'OUT_OF_BOUNDS'
    reason.loc[paired & finite & in_bounds & ~non_zero] = 'ZERO_COORDINATE'
    reason.loc[valid & ~provider_trusted] = 'UNTRUSTED_PROVIDER'
    reason.loc[valid & provider_trusted & ~address_consistent] = 'SHARED_POINT_CONFLICTING_ADDRESSES'

    result['coordinate_pair_valid'] = valid
    result['coordinate_pair_listing_count'] = pair_count.fillna(0).astype('int64')
    result['coordinate_pair_address_count'] = address_count.fillna(0).astype('int64')
    result['coordinate_trust_reason'] = reason
    result['has_trusted_coordinate'] = trusted
    return result


def add_spatial_search_mode(
    listings: pd.DataFrame,
    *,
    district_col: str = 'district_text_extracted',
    ward_col: str = 'ward_current',
) -> pd.DataFrame:
    """Return a copy classified as radius eligible, admin only or unavailable."""
    if 'has_trusted_coordinate' not in listings:
        raise KeyError('has_trusted_coordinate is required')
    result = listings.copy()
    district = result.get(district_col, pd.Series(pd.NA, index=result.index, dtype='string'))
    ward = result.get(ward_col, pd.Series(pd.NA, index=result.index, dtype='string'))
    district_available = district.astype('string').str.strip().replace('', pd.NA).notna()
    ward_available = ward.astype('string').str.strip().replace('', pd.NA).notna()
    admin_available = district_available | ward_available
    result['spatial_search_mode'] = np.select(
        [result.has_trusted_coordinate, admin_available],
        ['RADIUS_ELIGIBLE', 'ADMIN_ONLY'],
        default='LOCATION_UNAVAILABLE',
    )
    return result


def validate_reference_location(reference_location: Mapping[str, object] | None) -> bool:
    """Return whether a configured reference contains a name and valid coordinates."""
    if reference_location is None:
        return False
    if not {'name', 'latitude', 'longitude'} <= set(reference_location):
        return False
    latitude = pd.to_numeric(pd.Series([reference_location['latitude']]), errors='coerce').iloc[0]
    longitude = pd.to_numeric(pd.Series([reference_location['longitude']]), errors='coerce').iloc[0]
    return bool(
        isinstance(reference_location['name'], str)
        and reference_location['name'].strip()
        and pd.notna(latitude) and pd.notna(longitude)
        and np.isfinite(latitude) and np.isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
    )


def haversine_distance_km(latitude, longitude, reference_latitude: float, reference_longitude: float):
    """Return vectorized great-circle distance from coordinates to one reference."""
    latitude = np.asarray(latitude, dtype=float)
    longitude = np.asarray(longitude, dtype=float)
    lat1 = np.radians(latitude)
    lon1 = np.radians(longitude)
    lat2 = np.radians(float(reference_latitude))
    lon2 = np.radians(float(reference_longitude))
    delta_latitude = lat1 - lat2
    delta_longitude = lon1 - lon2
    a = np.sin(delta_latitude / 2) ** 2 + np.cos(lat2) * np.cos(lat1) * np.sin(delta_longitude / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def get_listings_within_radius(
    listings: pd.DataFrame,
    reference_latitude: float,
    reference_longitude: float,
    radius_km: float,
    *,
    latitude_col: str = 'map_latitude',
    longitude_col: str = 'map_longitude',
) -> pd.DataFrame:
    """Return trusted listings within radius with distance_km, preserving one-row grain."""
    if radius_km <= 0:
        raise ValueError('radius_km must be positive')
    if 'has_trusted_coordinate' not in listings:
        raise KeyError('has_trusted_coordinate is required')
    eligible = listings.loc[listings.has_trusted_coordinate].copy()
    eligible['distance_km'] = haversine_distance_km(
        eligible[latitude_col], eligible[longitude_col], reference_latitude, reference_longitude,
    )
    result = eligible.loc[eligible.distance_km.le(radius_km)].copy()
    assert result.rental_post_id.is_unique
    return result.sort_values(['distance_km', 'rental_post_id'])


def filter_listings_by_price(
    listings_within_radius: pd.DataFrame,
    *,
    price_col: str = 'price_amount_clean_candidate',
    min_price: float | None = None,
    max_price: float | None = None,
) -> pd.DataFrame:
    """Return rows with accepted clean prices inside inclusive optional bounds."""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError('min_price cannot exceed max_price')
    if price_col not in listings_within_radius:
        raise KeyError(f'{price_col} is required')
    result = listings_within_radius.copy()
    price = pd.to_numeric(result[price_col], errors='coerce')
    keep = price.notna()
    if min_price is not None:
        keep &= price.ge(min_price)
    if max_price is not None:
        keep &= price.le(max_price)
    return result.loc[keep].copy()


def derive_local_price_bands(
    local_listings: pd.DataFrame,
    *,
    price_col: str = 'price_amount_clean_candidate',
    minimum_sample_size: int = 3,
) -> tuple[pd.Series, dict[str, float] | None]:
    """Return local tertile labels and boundaries, or unclassified labels if unsafe."""
    price = pd.to_numeric(local_listings[price_col], errors='coerce')
    labels = pd.Series(pd.NA, index=local_listings.index, dtype='string', name='local_price_band')
    valid = price.dropna()
    if len(valid) < minimum_sample_size:
        return labels, None
    lower, upper = valid.quantile([1 / 3, 2 / 3]).tolist()
    if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
        return labels, None
    labels.loc[price.le(lower)] = 'LOCAL_LOW'
    labels.loc[price.gt(lower) & price.le(upper)] = 'LOCAL_MEDIUM'
    labels.loc[price.gt(upper)] = 'LOCAL_HIGH'
    return labels, {'p33': float(lower), 'p67': float(upper), 'valid_price_count': int(len(valid))}


def summarize_local_price_by_radius(
    listings: pd.DataFrame,
    reference_location: Mapping[str, object],
    radii_km: Iterable[float],
    *,
    price_col: str = 'price_amount_clean_candidate',
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return cumulative radius price summary and long local-band counts."""
    if not validate_reference_location(reference_location):
        raise ValueError('reference_location is invalid')
    summary_rows = []
    band_rows = []
    for radius in sorted(set(float(value) for value in radii_km)):
        local = get_listings_within_radius(
            listings, float(reference_location['latitude']), float(reference_location['longitude']), radius,
        )
        price = pd.to_numeric(local[price_col], errors='coerce')
        valid = price.dropna()
        summary_rows.append({
            'radius_km': radius,
            'listing_count': len(local),
            'valid_price_count': int(price.notna().sum()),
            'missing_price_count': int(price.isna().sum()),
            'price_min': valid.min() if len(valid) else np.nan,
            'price_q1': valid.quantile(0.25) if len(valid) else np.nan,
            'price_median': valid.median() if len(valid) else np.nan,
            'price_q3': valid.quantile(0.75) if len(valid) else np.nan,
            'price_max': valid.max() if len(valid) else np.nan,
        })
        bands, boundaries = derive_local_price_bands(local, price_col=price_col)
        if boundaries:
            for band, count in bands.value_counts().items():
                band_rows.append({
                    'radius_km': radius, 'local_price_band': band, 'count': int(count),
                    'p33': boundaries['p33'], 'p67': boundaries['p67'],
                })
    return pd.DataFrame(summary_rows), pd.DataFrame(band_rows)
