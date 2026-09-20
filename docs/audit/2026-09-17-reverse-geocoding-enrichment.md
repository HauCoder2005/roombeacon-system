# RoomBeacon — Reverse Geocoding Enrichment

## I. Problem
Many rental listings contain `map_latitude` and `map_longitude` derived from source maps, but lack a structured `full_address_text`. We need to normalize these coordinates into structured addresses using a reverse geocoding service, without putting this blocking process in the crawler's critical path or overwriting source truth.

## II. Source vs Derived Address Semantics
- `location_raw`: Coarse source location.
- `address_raw`: Detailed source location.
- `full_address_text`: Confirmed source detail address.
- `map_latitude` / `map_longitude`: Extracted explicit coordinates.
- **NEW Derived Semantics**: `geocoded_address_text`, `geocoded_ward`, `geocoded_district`, `geocoded_city`, `geocode_provider`, `geocode_precision`.

Analytical field `best_address_text` computes `COALESCE(full_address_text, geocoded_address_text, location_raw)`.
Provenance is tracked via `best_address_source` (`source_detail`, `reverse_geocode`, `source_card`, `none`).

## III. Architecture
- **Crawler**: Continues to extract maps and persist only coordinates (source truth).
- **Enrichment Layer**: A decoupled `GeocodeEnrichmentJob` selects distinct missing coordinates from `v_latest_posts`.
- **Cache**: A `map_geocodes` MySQL table caches normalized `(latitude, longitude)` results.
- **DuckDB**: `v_latest_posts` employs a `LEFT JOIN` on `ROUND(latitude, 6)` against `map_geocodes` to overlay geocodes dynamically.

## IV. Provider
- **NominatimReverseGeocoder**: Uses OpenStreetMap's Nominatim HTTP API.
- Requirements: No API keys, no paid plans.
- Data Extracted: Extrapolates wards, districts, and cities from OS mapping features safely, gracefully handling null properties.

## V. Cache Strategy
- A dedicated `map_geocodes` table acts as a global caching ledger.
- Coordinates are stored and matched at 6-decimal-place precision using `ROUND(lat, 6)`.
- This ensures we do not hit rate limits calling Nominatim for identical coordinates.

## VI. Data Model
- `GeocodedLocation` (domain dataclass)
- `map_geocodes` (MySQL Table): Independent of `rental_posts` and `rental_post_versions`.
- Contains: `geocoded_address_text`, `geocoded_ward`, `geocoded_district`, `geocoded_city`, `geocode_provider`, `geocode_precision`, `geocoded_at`.

## VII. Files Changed
- `crawler/src/roombeacon_crawler/domain/models/geocoded_location.py`
- `crawler/src/roombeacon_crawler/services/reverse_geocoder.py`
- `crawler/src/roombeacon_crawler/infrastructure/mysql/repositories/geocode_repository.py`
- `crawler/src/roombeacon_crawler/jobs/enrich_geocodes.py`
- `analytics/duckdb/sql/latest_posts.sql`
- `tests/test_geocoding.py`

## VIII. RED/GREEN Evidence
TDD implemented successfully verifying:
- **Case A**: Valid HCMC coordinate extracts successfully.
- **Case C/D**: Invalid latitude/longitude bounds bypassed provider.
- **Case E**: Provider failure trapped safely without raising errors.
- **Case B**: Cache layer prevents duplicate external HTTP requests.
- **Case F/G/H**: DuckDB COALESCE dynamically assigns the correct `best_address_text` priority without overwriting truth.

## IX. Runtime Verification
Verified against live listing 3179272 (Cafeland):
- `map_latitude`: 10.8452915
- `map_longitude`: 106.7795828
- `geocoded_address_text`: 136D, 402, Khu phố 49, Phường Tăng Nhơn Phú, Thành phố Hồ Chí Minh, 71320, Việt Nam
- `best_address_text`: 25/16/1, , Tăng Nhơn Phú TP. Hồ Chí Minh
- `best_address_source`: source_detail

## X. DuckDB Exposure
DuckDB natively performs a `LEFT JOIN mysql_db.map_geocodes` rendering a completely non-destructive merge.
Fields added: `geocoded_address_text`, `geocoded_ward`, `geocoded_district`, `geocoded_city`, `geocode_provider`, `geocode_precision`, `best_address_text`, `best_address_source`.

## XI. Coverage
Tested on a bounded subset of 18,830 rows:
- Total listings: 18830
- With full_address_text: 3254
- With coordinates: 41
- With geocoded address: 41
- With best_address_text: 10516
- No location signal: 8314

## XII. Failure Behavior
Nominatim timeouts or bad IPs fail silently to `None`, preserving upstream workflows. Bounding logic bypasses out-of-range map points instantly.

## XIII. Safety
- NO `.env` secrets required.
- NO database drops, deletes, or truncates.
- NO rewrites to historical `rental_post_versions` source payloads.
- Geocoding remains strictly analytical.

## XIV. Deferred Backfill
Mass backfill has NOT been executed. The job supports a `max_records` configuration to iteratively backfill historical data safely under rate-limit constraints without multiplying DuckDB rows.

## XV. Final Verdict
REVERSE GEOCODING ENRICHMENT HEALTHY
