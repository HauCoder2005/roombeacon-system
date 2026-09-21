# Address pipeline audit — 2026-09-20

## Verified live evidence

Read-only queries against the running MySQL container found 8,252 posts across nine sources, matching the supplied screenshots. Latest-version map signals:

| Source | Posts | Coordinates | Text query |
|---|---:|---:|---:|
| cafeland | 1300 | 1300 | 0 |
| chothuenha | 82 | 0 | 52 |
| chothuephongtro | 999 | 0 | 998 |
| mogi | 750 | 744 | 0 |
| muaban | 30 | 0 | 0 |
| nhatot | 141 | 0 | 0 |
| nhatrovn | 722 | 680 | 0 |
| phongtro123 | 3989 | 0 | 3985 |
| tromoi | 239 | 65 | 0 |

1,037 CafeLand posts share (10.876248, 106.660338); all 680 NhatroVN posts with coordinates share (10.6979911, 106.7168188). These are suspected template coordinates, not independently verified property positions. Quarantine these exact source/coordinate combinations from reverse geocoding; retain their original payloads. Other CafeLand coordinates are now exposed instead of excluding the entire source. Repetition alone does not prove that a coordinate is wrong.

## Implemented

- Shared Maps extractor reads lazy iframe attributes, links, and source JavaScript iframe variables. Handles HTML entities, encoded embed payloads, integer/decimal coordinate pairs, Maps query parameter variants, and simultaneous coordinates plus address labels. Rejects lookalike domains and avoids decoding literal plus signs twice.
- Consolidated duplicate map extraction in generic, PhongTro123 and CafeLand parsers.
- Generic detail address selection prefers explicit street evidence over coarse structured addresses. This is a conservative heuristic, not proof of postal accuracy.
- Geocode job queries the actual cache table instead of nonexistent columns in the latest-post view; rounds and deduplicates coordinate requests before applying the limit; resolves SQL independently of working directory; validates the limit and closes DuckDB connections.
- Geocode repository closes connections it owns, including on failure, without closing injected transaction connections.
- Optional `v_latest_posts_enriched` exposes `enriched_address_text` and `enriched_address_source`. Street text takes precedence; otherwise map text with street evidence or cached reverse geocoding can improve coarse source locations. Original address fields remain available. The view is created when analytics initializes and the geocode cache table exists; absence does not break core views.

## Validation and limits

34 focused address, map, geocode, provenance and source-parser tests passed. Corrected ChoThuePhongTro tests to use the production HtmlNode parser and address extraction entry point. Additional parser and runtime tests exposed pre-existing configuration/contract mismatches: scheduled detail budgets are 5000 where tests expect 20/40, and persistence status tests disagree with the existing no-data handling. These unrelated working-tree edits were preserved. Full-suite collection on the host is blocked by missing `airflow.exceptions` in three test modules.

No bulk recrawl, geocoding backfill, database schema change, or process restart was performed. Live verification above is read-only. Existing records need replay/recrawl to benefit from parser changes. Refresh DuckDB views to apply analytics changes. The geocode job remains an explicit batch operation; no automatic scheduler was added.

Not all map queries identify streets. Google short links/place IDs without explicit coordinates are not resolved over the network. Reverse geocoding returns the mapped location near a coordinate, not proof of the rental's house number. Full street coverage cannot be asserted for sources that withhold that information or publish a generic map.

The repository is not yet clean: numerous pre-existing modified files and scratch scripts remain. This change does not claim a complete repository cleanup or measured throughput improvement.
