"""Build Notebook 05: RoomBeacon — Nearby Rental Search prototype."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.splitlines(True)}


cells = [
md("""# RoomBeacon — Nearby Rental Search & Spatial Discovery Prototype

This notebook implements the **product-validation and spatial retrieval layer** of RoomBeacon.

While Notebook 04 answers:
> *"Can RoomBeacon accurately estimate rental price?"*

Notebook 05 answers:
> *"Can RoomBeacon help a user find trustworthy rental listings near a location they care about?"*

### Core Architectural Invariants:
1. **Consumes Canonical Silver Parquet directly** without mutating Silver or depending on raw Bronze.
2. **Never fakes numeric distance:** True geographic distance (`distance_km`) is strictly calculated via vectorized Haversine *only* when both the reference point and the listing have validated, trusted coordinates.
3. **Rigorous 5-State Location Taxonomy:** Strictly separates capability from search results and true unresolved listings from out-of-area listings:
   - `EXACT_DISTANCE_CAPABLE`: Trusted coordinate available for geographic distance.
   - `SAME_WARD`: Untrusted coordinate, matching reference ward (distance strictly null).
   - `SAME_DISTRICT`: Untrusted coordinate, matching reference district (distance strictly null).
   - `RESOLVED_OUTSIDE_REFERENCE_AREA`: Usable administrative location in other wards/districts (not unresolved!).
   - `LOCATION_UNRESOLVED`: Truly unresolvable (no coordinate, no ward, no district).
4. **Explicit Reference Location Contract:** Distinguishes verified vs `USER_SUPPLIED_UNVERIFIED` context without fabricating reverse-geocoding network calls.
5. **Coordinate Search Quality & Deterministic Ranking:** Evaluates `coordinate_search_status` (`TRUSTED_CONSISTENT`, `TRUSTED_ADMIN_UNVERIFIED`, `TRUSTED_BUT_ADMIN_MISMATCH`, `SHARED_POINT_CONFLICT`) to prevent pin-error listings (e.g. ID 69388) from ranking equally with genuine local listings.
6. **Configurable Price Display Policy:** Defaults to `TRUSTED_ONLY` to prevent unverified prices from entering product validation."""),

md("## 1. Environment Setup & Helper Imports"),
code("""from pathlib import Path
import sys
PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'crawler').is_dir() and (p / 'analytics').is_dir())
sys.path.insert(0, str(PROJECT_ROOT))

import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import duckdb
import matplotlib.pyplot as plt
import seaborn as sns
from IPython.display import display, Markdown

from analytics.duckdb.connection import resolve_runtime_path
from roombeacon_crawler.config.get_env import env
from notebooks.utils.nearby_rental_search import (
    is_valid_coordinate,
    haversine_distance_km,
    assign_distance_band,
    filter_rental_compatible,
    derive_display_price,
    create_reference_location_contract,
    classify_coordinate_search_status,
    format_filter_range,
    audit_location_coverage,
    execute_nearby_rental_search,
    build_search_funnel,
    summarize_radius_market,
    evaluate_product_readiness,
)

pd.set_option('display.max_columns', 30)
pd.set_option('display.float_format', lambda x: f'{x:,.2f}' if abs(x) < 1000 else f'{x:,.0f}')
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
display(Markdown('**Environment and nearby search helpers initialized successfully.**'))"""),

md("""## 2. Search Configuration

Configure the reference search point, price display policy, and optional filters.

- **Mode A (Exact Coordinate):** User or client provides latitude and longitude.
- **Mode B (Administrative Context):** Optional reference ward and district for fallback retrieval when coordinates are missing or untrusted.
- **Price Display Policy:** Defaults to `TRUSTED_ONLY` (only `TRUSTED_EXISTING` and `TRUSTED_REPARSED` targets are shown).
"""),
code("""# ==============================================================================
# SEARCH CONFIGURATION (Easily configurable by user / application client)
# ==============================================================================
REFERENCE_NAME = "Đại học Bách Khoa TP.HCM (Campus Lý Thường Kiệt, Q.10)"
REFERENCE_LATITUDE = 10.7725
REFERENCE_LONGITUDE = 106.6578

# Administrative fallback configuration
REFERENCE_WARD = "Phường Tân Bình"  # Ward containing / adjacent to campus in Silver mapping
REFERENCE_DISTRICT = "Quận 10"

# Retrieval thresholds & optional filters
SEARCH_RADIUS_KM = 3.0
MAX_RESULTS = 20

# Product price display policy: "TRUSTED_ONLY" or "ALLOW_REVIEW_WITH_WARNING"
PRICE_DISPLAY_POLICY = "TRUSTED_ONLY"

# Optional rental filters (set to None to disable)
MIN_PRICE = None
MAX_PRICE = 10_000_000.0  # Optional filter: <= 10 triệu/tháng
MIN_AREA = 15.0           # Optional filter: >= 15 m²
MAX_AREA = None

config_summary = pd.DataFrame([
    {"Parameter": "Reference Location Name", "Value": REFERENCE_NAME},
    {"Parameter": "Reference Coordinates", "Value": f"({REFERENCE_LATITUDE:.4f}, {REFERENCE_LONGITUDE:.4f})"},
    {"Parameter": "Reference Ward", "Value": REFERENCE_WARD or "None"},
    {"Parameter": "Reference District", "Value": REFERENCE_DISTRICT or "None"},
    {"Parameter": "Search Radius", "Value": f"{SEARCH_RADIUS_KM:.1f} km"},
    {"Parameter": "Max Display Results", "Value": str(MAX_RESULTS)},
    {"Parameter": "Price Display Policy", "Value": PRICE_DISPLAY_POLICY},
    {"Parameter": "Price Filter (Min - Max)", "Value": format_filter_range(MIN_PRICE, MAX_PRICE, "VNĐ")},
    {"Parameter": "Area Filter (Min - Max)", "Value": format_filter_range(MIN_AREA, MAX_AREA, "m²")},
])
display(config_summary)"""),

md("## 3. Load Canonical Silver Parquet"),
code("""SILVER_PATH = resolve_runtime_path(env.processing.silver_dir) / 'rental_listings.parquet'
assert SILVER_PATH.exists(), f'Canonical Silver not found at {SILVER_PATH}'

with duckdb.connect(':memory:') as con:
    silver_df = con.execute('SELECT * FROM read_parquet(?)', [str(SILVER_PATH)]).df()

# Dynamic invariant assertions (no hardcoded row count)
assert len(silver_df) > 0, 'Canonical Silver dataset is empty'
assert 'rental_post_id' in silver_df.columns, 'rental_post_id column missing from Silver'
assert silver_df['rental_post_id'].notna().all(), 'rental_post_id contains nulls'
assert silver_df['rental_post_id'].is_unique, 'rental_post_id must be strictly unique'

# Optional dynamic metadata validation
meta_path = SILVER_PATH.parent / 'silver_metadata.json'
if meta_path.exists():
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
        if 'row_count' in meta:
            assert len(silver_df) == meta['row_count'], f"Parquet row count ({len(silver_df)}) does not match metadata ({meta['row_count']})"

display(pd.DataFrame([{
    'Silver Parquet Path': str(SILVER_PATH),
    'Total Rows': f'{len(silver_df):,}',
    'Total Columns': len(silver_df.columns),
    'Unique Listings': f'{silver_df.rental_post_id.nunique():,}',
}]))"""),

md("""## 4. Rental Search Population Eligibility & Price Policy

Filter Silver listings to the **ordinary rental-compatible population**:
- Excludes explicit `SALE` and `TRANSFER` intent.
- Excludes aggregate building operations (`WHOLE_BUILDING`, `MULTI_UNIT_BUSINESS`).
- Retains `UNKNOWN` semantics absent conflicting evidence.
- Applies `PRICE_DISPLAY_POLICY = "TRUSTED_ONLY"`: Only verified target prices (`TRUSTED_EXISTING`, `TRUSTED_REPARSED`) are exposed.
"""),
code("""rental_df = filter_rental_compatible(silver_df)
rental_df = derive_display_price(rental_df, price_display_policy=PRICE_DISPLAY_POLICY)

compat_summary = pd.DataFrame([
    {"Population Stage": "Total Canonical Silver", "Rows": len(silver_df), "Percent of Silver": 100.0},
    {"Population Stage": "Rental-compatible Search Population", "Rows": len(rental_df), "Percent of Silver": round(len(rental_df) / len(silver_df) * 100, 2)},
    {"Population Stage": "Excluded (SALE / TRANSFER / WHOLE_BUILDING)", "Rows": len(silver_df) - len(rental_df), "Percent of Silver": round((len(silver_df) - len(rental_df)) / len(silver_df) * 100, 2)},
])
display(compat_summary)

price_policy_dist = rental_df['price_display_status'].value_counts().reset_index()
price_policy_dist.columns = ['Price Display Status', 'Listing Count']
price_policy_dist['Share %'] = (price_policy_dist['Listing Count'] / len(rental_df) * 100).round(2)
display(price_policy_dist)"""),

md("""## 5. Location Quality & Coordinate Coverage Audit

Before performing spatial retrieval, we measure the empirical location quality across the rental population.
This answers the critical question:
> **"How much of RoomBeacon can actually support true radius search today?"**
"""),
code("""coverage_audit = audit_location_coverage(rental_df)
display(coverage_audit)

display(Markdown('''
> **Key Finding on Coordinate Coverage:**
> - Only **~1.72%** (2,268 listings) possess validated, trusted coordinates (`has_trusted_coordinate == True`).
> - **7.98%** (10,533 listings) have coordinates that represent **shared portal hotspots / district defaults** with conflicting street addresses. These cannot be trusted for exact distance.
> - In contrast, **83.74%** (110,481 listings) have resolved administrative wards (`ward_current`).
> - Therefore, RoomBeacon currently operates as an **administrative-location retrieval system with a high-precision radius search tier**.
'''))"""),

md("## 6. Reference Location Contract Validation"),
code("""ref_contract = create_reference_location_contract(
    name=REFERENCE_NAME,
    latitude=REFERENCE_LATITUDE,
    longitude=REFERENCE_LONGITUDE,
    ward=REFERENCE_WARD,
    district=REFERENCE_DISTRICT,
)

ref_info = pd.DataFrame([{
    'Reference Name': ref_contract['reference_name'],
    'Latitude': ref_contract['reference_latitude'],
    'Longitude': ref_contract['reference_longitude'],
    'Admin Verification Status': ref_contract['reference_admin_verification_status'],
    'Exact Distance Capable': ref_contract['is_exact_distance_capable'],
    'Fallback Ward': ref_contract['reference_ward'],
    'Fallback District': ref_contract['reference_district'],
}])
display(ref_info)

display(Markdown(f'''
> **Reference Location Verification Status:** `{ref_contract['reference_admin_verification_status']}`
> Coordinates and administrative labels are user-configured. Because offline polygon GIS boundaries are not embedded in the repository, administrative labels remain marked `USER_SUPPLIED_UNVERIFIED` rather than assuming external GIS verification.
'''))"""),

md("""## 7. Multi-Tier Nearby Rental Retrieval & Location Taxonomy

We execute the multi-tier retrieval engine:
1. **Exact Distance Capable (Tier 1):** Vectorized Haversine distance computed exclusively on trusted coordinates. Listings filtered to $\\le$ `SEARCH_RADIUS_KM` and sorted by deterministic priority:
   `TRUSTED_CONSISTENT` $\\rightarrow$ `TRUSTED_ADMIN_UNVERIFIED` $\\rightarrow$ `TRUSTED_BUT_ADMIN_MISMATCH`, then `distance_km` ascending.
2. **Same Ward Fallback (Tier 2):** Listings in the reference ward whose coordinates are untrusted/missing. Distance is strictly null.
3. **Same District Fallback (Tier 3):** Listings in the reference district outside the reference ward. Distance is strictly null.
4. **Resolved Outside Reference Area (Tier 4):** Usable administrative location in another ward/district (not unresolved!).
5. **Location Unresolved (Tier 5):** Truly unresolvable listings (no coordinates, no ward, no district).
"""),
code("""exact_results, same_ward_results, same_district_results, search_df = execute_nearby_rental_search(
    rental_df,
    reference_latitude=REFERENCE_LATITUDE,
    reference_longitude=REFERENCE_LONGITUDE,
    reference_ward=REFERENCE_WARD,
    reference_district=REFERENCE_DISTRICT,
    radius_km=SEARCH_RADIUS_KM,
    min_price=MIN_PRICE,
    max_price=MAX_PRICE,
    min_area=MIN_AREA,
    max_area=MAX_AREA,
    max_results=MAX_RESULTS,
    price_display_policy=PRICE_DISPLAY_POLICY,
)

# 1. 5-State Search Location Taxonomy Distribution
taxonomy_counts = search_df['location_match_type'].value_counts().reset_index()
taxonomy_counts.columns = ['Search Location Taxonomy State', 'Listing Count']
taxonomy_counts['Share %'] = (taxonomy_counts['Listing Count'] / len(search_df) * 100).round(2)
display(Markdown('### Search Location Taxonomy (Mutually Exclusive Partition)'))
display(taxonomy_counts)

# 2. Coordinate Search Quality Distribution
coord_quality = search_df['coordinate_search_status'].value_counts().reset_index()
coord_quality.columns = ['Coordinate Search Quality Status', 'Listing Count']
coord_quality['Share %'] = (coord_quality['Listing Count'] / len(search_df) * 100).round(2)
display(Markdown('### Overall Coordinate Search Quality Status'))
display(coord_quality)"""),

md("""## 8. Search Coverage Funnel

Conversion funnel from the total rental-compatible population down to concentric distance bands, coordinate quality, and administrative fallbacks.
"""),
code("""funnel_df = build_search_funnel(search_df, radius_km=SEARCH_RADIUS_KM)
display(funnel_df)"""),

md("## 9. Ranked Search Results Presentation"),
code("""cols_to_show = [
    'rental_post_id', 'source_code', 'title_clean', 'display_price',
    'price_display_status', 'area_value_clean', 'ward_current',
    'district_text_extracted', 'coordinate_search_status', 'distance_km',
    'distance_band', 'location_match_type', 'latest_observed_at',
]

display(Markdown(f'### Top Exact-Distance Results within {SEARCH_RADIUS_KM:.1f} km (Ranked by Coordinate Quality & Distance)'))
if len(exact_results) > 0:
    display(exact_results[cols_to_show].head(MAX_RESULTS))
else:
    display(Markdown('*No exact-distance listings matched the criteria within this radius.*'))

display(Markdown(f'### Administrative Fallback: Same Ward ({REFERENCE_WARD}) — Distance Unavailable'))
if len(same_ward_results) > 0:
    display(same_ward_results[cols_to_show].head(10))
else:
    display(Markdown('*No same-ward fallback listings available.*'))

display(Markdown(f'### Administrative Fallback: Same District ({REFERENCE_DISTRICT}) — Distance Unavailable'))
if len(same_district_results) > 0:
    display(same_district_results[cols_to_show].head(10))
else:
    display(Markdown('*No same-district fallback listings available.*'))"""),

md("""## 10. Concentric Radius Market Analysis (Trusted-Coordinate Subset Only)

Market diagnostics for exact-distance listings across 1 km, 3 km, 5 km, and 10 km bands around the reference location.

> **Important Coverage & Bias Notice:**
> - These metrics apply **strictly to the trusted-coordinate subset (~1.72% of rental listings)**.
> - They do not reflect the full 131k rental population due to **coordinate availability bias** (e.g. mogi provides exact coords while other portals frequently omit or default them).
"""),
code("""market_summary = summarize_radius_market(search_df, radii=[1.0, 3.0, 5.0, 10.0])
display(market_summary)"""),

md("## 11. Visualizations"),
code("""fig, axes = plt.subplots(2, 2, figsize=(15, 11))

# 1. Listing counts by distance band
band_counts = search_df['distance_band'].dropna().value_counts()[['<= 1 km', '1–3 km', '3–5 km', '5–10 km', '> 10 km']].dropna()
axes[0, 0].bar(band_counts.index, band_counts.values, color='#4A90E2', edgecolor='black')
axes[0, 0].set_title('Listing Count by Distance Band (Trusted Coords Only)', fontsize=12, fontweight='bold')
axes[0, 0].set_ylabel('Number of Listings')
axes[0, 0].grid(axis='y', linestyle='--', alpha=0.7)

# 2. Median rent by radius band
valid_market = market_summary.dropna(subset=['Median Rent (VNĐ)'])
axes[0, 1].plot(valid_market['Radius Band'], valid_market['Median Rent (VNĐ)'] / 1e6, marker='o', color='#E24A4A', linewidth=2.5, markersize=8)
axes[0, 1].set_title('Median Rent by Radius Band around Reference Point', fontsize=12, fontweight='bold')
axes[0, 1].set_ylabel('Median Rent (Million VNĐ)')
axes[0, 1].grid(True, linestyle='--', alpha=0.7)

# 3. Top wards around reference point within 3 km
top_wards = search_df.loc[search_df['distance_km'].le(3.0), 'ward_current'].dropna().value_counts().head(8)
axes[1, 0].barh(top_wards.index[::-1], top_wards.values[::-1], color='#50E3C2', edgecolor='black')
axes[1, 0].set_title('Top Wards within 3 km Radius', fontsize=12, fontweight='bold')
axes[1, 0].set_xlabel('Number of Listings')
axes[1, 0].grid(axis='x', linestyle='--', alpha=0.7)

# 4. Diagnostic Coordinate Scatter (Explicitly NOT a navigational map)
trusted_subset = search_df.loc[search_df['distance_km'].le(5.0)]
axes[1, 1].scatter(trusted_subset['map_longitude'], trusted_subset['map_latitude'], c=trusted_subset['distance_km'], cmap='viridis', alpha=0.6, s=30, label='Nearby Listings (<= 5 km)')
axes[1, 1].scatter(REFERENCE_LONGITUDE, REFERENCE_LATITUDE, c='red', s=120, marker='*', edgecolor='black', zorder=5, label='Reference Point')
axes[1, 1].set_title('Diagnostic Coordinate Scatter (Not a Navigational Map)', fontsize=12, fontweight='bold')
axes[1, 1].set_xlabel('Longitude')
axes[1, 1].set_ylabel('Latitude')
axes[1, 1].legend(loc='upper left')
axes[1, 1].grid(True, linestyle='--', alpha=0.5)

plt.tight_layout()
plt.show()"""),

md("""## 12. Data Quality Findings & Forensic Limitations

1. **True Coordinate Coverage Constraint:** Only **1.72%** (2,268 listings) of rental listings in Silver possess trustworthy, pinpoint coordinates.
2. **Hotspot False Pinning:** Over 10,500 listings (7.98%) share repeated coordinates with mutually conflicting street addresses (district centroids / default pins). RoomBeacon isolates these to prevent false radius matching.
3. **Mismatched Portal Metadata:** Even among trusted coordinate embeds, poster errors exist (e.g. ID `69388` describes Lê Thánh Tôn, Quận 1 but its coordinate was placed in Quận 10). The coordinate search status contract classifies these as `TRUSTED_BUT_ADMIN_MISMATCH` and deprioritizes them deterministically.
4. **Administrative Retrieval Superiority:** Ward-level coverage reaches **83.74%**, making administrative matching (Same Ward / Same District) the primary reliable discovery mechanism for users today.
"""),

md("## 13. Product Readiness & Analytical Artifacts"),
code("""readiness = evaluate_product_readiness(coverage_audit)
display(Markdown(f'''
### Current Location Retrieval Readiness: `{readiness['verdict']}`

{readiness['interpretation']}
'''))

# Persist analytical artifacts strictly to data/analysis/nearby_search/
ARTIFACT_DIR = PROJECT_ROOT / 'data' / 'analysis' / 'nearby_search'
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

coverage_audit.to_csv(ARTIFACT_DIR / 'location_quality_summary.csv', index=False)
funnel_df.to_csv(ARTIFACT_DIR / 'search_coverage_funnel.csv', index=False)
market_summary.to_csv(ARTIFACT_DIR / 'radius_market_summary.csv', index=False)
exact_results.to_csv(ARTIFACT_DIR / 'nearby_search_exact_results.csv', index=False)
same_ward_results.to_csv(ARTIFACT_DIR / 'same_ward_fallback_results.csv', index=False)
same_district_results.to_csv(ARTIFACT_DIR / 'same_district_fallback_results.csv', index=False)

metadata = {
    "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "reference_location": ref_contract,
    "price_display_policy": PRICE_DISPLAY_POLICY,
    "search_parameters": {
        "radius_km": SEARCH_RADIUS_KM,
        "max_results": MAX_RESULTS,
        "min_price": MIN_PRICE,
        "max_price": MAX_PRICE,
        "min_area": MIN_AREA,
        "max_area": MAX_AREA,
    },
    "taxonomy_counts": taxonomy_counts.set_index('Search Location Taxonomy State')['Listing Count'].to_dict(),
    "coordinate_search_quality": coord_quality.set_index('Coordinate Search Quality Status')['Listing Count'].to_dict(),
    "results_count": {
        "exact_distance_matches": len(exact_results),
        "same_ward_matches": len(same_ward_results),
        "same_district_matches": len(same_district_results),
    },
    "readiness": readiness,
}
(ARTIFACT_DIR / 'search_run_metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')

display(Markdown(f'**Saved 6 analytical artifacts and run metadata to `{ARTIFACT_DIR}`.**'))
display(Markdown('**Notebook 05 execution complete.**'))"""),
]

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "RoomBeacon (venv)",
            "language": "python",
            "name": "roombeacon-venv",
        },
        "language_info": {
            "name": "python",
            "version": "3.12.3",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

target_path = ROOT / "notebooks" / "05_roombeacon_nearby_rental_search.ipynb"
target_path.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Generated {target_path} successfully ({len(cells)} cells).")
