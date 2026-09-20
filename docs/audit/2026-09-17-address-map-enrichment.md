# RoomBeacon — Embedded Map Location Enrichment Report

## I. Problem
Textual address coverage (e.g., "Tân Bình, Hồ Chí Minh" or specific street strings) is sometimes incomplete, noisy, or only formatted as a coarse district-level location. However, rental listing details often include an embedded geographic map (like Google Maps) that explicitly defines coordinates (Latitude/Longitude) or a structured query. Relying solely on textual address parsing leaves high-confidence geographic signals uncollected, limiting downstream location intelligence such as distance to POIs or travel-time calculations.

## II. Existing Address Semantics
- `location_raw`: Textual location generally obtained from the listing card (coarse).
- `address_raw`: Detailed textual address obtained directly from the source detail content.
- `full_address_text`: The latest confirmed/detail address exposed by analytics.

## III. Source Audit
| Source | Map Present | Pattern | Coordinates Available | Integrated |
|--------|-------------|---------|-----------------------|------------|
| Cafeland | Yes | `maps.google.com/maps?q=LAT,LON` in `urlMapIframe` | Yes | Yes |
| Chothuephongtro | No | N/A | No | No |
| Chothuenha | No | N/A | No | No |
| Phongtro123 | No | N/A | No | No |
| Nhatot | No | N/A | No | No |
| Nhatrovn | No | N/A | No | No |
| Batdongsan | No | N/A | No | No |
| Muaban | No | N/A | No | No |

## IV. Architecture
- **Detail Page Parsing**: Modifies `CafelandDetailParser` to inspect HTML for `var urlMapIframe`.
- **Shared Extractor**: `MapLocationExtractor` parses candidate map URLs into a `MapLocation` model.
- **Bronze / source_payload**: The `MapLocation` domain model is added to `ListingDetailRaw` and `RentalBronzeRecord`, automatically persisting as serialized JSON in the artifact and MySQL `source_payload`.
- **DuckDB Analytics**: `v_latest_posts` employs `json_extract_string()` to safely expose map values dynamically.

## V. Supported Map Formats
Only map URL schemes proven during the audit are supported:
1. **q coordinates/query**: `maps.google.com/maps?q=LAT,LON` or `?q=QUERY`
2. **ll coordinates**: `maps.google.com/maps?ll=LAT,LON`
3. **Path coordinates**: `google.com/maps/@LAT,LON,15z`
4. **Google Embed Encoded**: `google.com/maps/embed?...!3dLAT!4dLON` (or `!2dLON!3dLAT`)

## VI. Data Model / Provenance
Fields added to `source_payload.map_location`:
- `provider`: Explicit string identifier (e.g., `"google_maps_embed"`).
- `map_url_raw`: The unmodified embed URL discovered in the HTML.
- `latitude` / `longitude`: Finite float coordinates (`-90 <= lat <= 90`, `-180 <= lon <= 180`), strictly paired. Both or neither.
- `query_raw`: Optional place name or encoded query string if explicit coordinates are absent.

## VII. Files Changed
- `crawler/src/roombeacon_crawler/models/map_location.py`: New `MapLocation` dataclass.
- `crawler/src/roombeacon_crawler/models/listing_detail_raw.py`: Integrated `map_location`.
- `crawler/src/roombeacon_crawler/models/rental_bronze_record.py`: Integrated `map_location`.
- `crawler/src/roombeacon_crawler/mappers/bronze_mapper.py`: Transferred map metadata from detail to Bronze layer.
- `crawler/src/roombeacon_crawler/sources/map_extractor.py`: Shared coordinate extractor module.
- `crawler/src/roombeacon_crawler/sources/cafeland/parsers/detail_parser.py`: Extended to supply iframe candidates to extractor.
- `analytics/duckdb/sql/latest_posts.sql`: Patched to extract `map_provider`, `map_latitude`, `map_longitude`, `map_query_raw`.
- `tests/test_map_extractor.py`: Dedicated unit tests for extraction strategies.
- `tests/test_full_address_extraction.py`: Safely checks optional model mapping.
- `tests/test_latest_posts_address_provenance.py`: TDD test suites verifying DuckDB provenance.

## VIII. RED / GREEN Evidence
- Built robust TDD fixtures for `MapLocationExtractor` with various real-world map embed variations (`!3d`, `q=`, `ll=`, path).
- Out-of-bounds/malformed URLs successfully resulted in safe `None` returns.
- Tested `CafelandDetailParser` against fixtures embedding map URLs.
- Proven via duckdb `test_latest_posts_exposes_map_location` that DuckDB can cleanly retrieve the inserted nested map metadata.

## IX. Runtime Evidence
Bounded live scrape executed against `cafeland`:
- **URL**: `https://nhadat.cafeland.vn/cho-thue-phong-cao-cap-day-du-tien-nghi-tai-q9-2tr7-3179272.html`
- **Output MapLocation**: `MapLocation(provider='google_maps_embed', map_url_raw='https://maps.google.com/maps?q=10.8452915,106.7795828&hl=es;z=12&output=embed', latitude=10.8452915, longitude=106.7795828, query_raw=None)`

## X. Analytics Exposure
Coordinates appear in `v_latest_posts` directly via JSON paths extracted from MySQL. The rows remain strictly 1:1 with `rental_posts` without row multiplication. 
Fields exposed alongside text addresses: `map_provider`, `map_latitude`, `map_longitude`, `map_query_raw`.

## XI. Failure Behavior
Map extraction is an optional pipeline enhancement. A malformed URL or unexpected domain format cleanly fails by emitting a silent `None` capture, thereby guaranteeing that primary textual listing details are not blocked or corrupted. No crawler exceptions are raised.

## XII. Security / Safety
- `.env` secrets remain uncompromised.
- No new external API calls, Google queries, or browser automation were executed.
- No destructive DB operations or rewrites of historic events took place.

## XIII. Deferred Work
- Reverse geocoding via Google Maps API/Nominatim.
- Normalization into a canonical administrative hierarchy.
- School/company anchors.
- Distance calculations.
- Travel-time calculations.

*(All of the above are deferred as Out Of Scope).*

## XIV. Final Verdict
MAP LOCATION ENRICHMENT HEALTHY
