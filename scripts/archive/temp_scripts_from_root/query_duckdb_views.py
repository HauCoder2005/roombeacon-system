import sys
import os
from pathlib import Path
import duckdb

sys.path.insert(0, str(Path.cwd()))
from analytics.duckdb.connection import create_analytics_connection

con = create_analytics_connection()

import pandas as pd

# 1. Grain of v_latest_posts: COUNT(*) vs COUNT(DISTINCT rental_post_id)
q_latest = """
SELECT COUNT(*) as total_rows, COUNT(DISTINCT rental_post_id) as unique_posts
FROM v_latest_posts;
"""
print("--- v_latest_posts Grain ---")
print(con.execute(q_latest).df())

# 2. Total Observations
q_obs = """
SELECT COUNT(*) as total_observations, COUNT(DISTINCT rental_post_id) as unique_observed_posts
FROM v_observations;
"""
print("\n--- v_observations Grain ---")
print(con.execute(q_obs).df())

# 3. Source Inventory
q_sources = """
SELECT source_code, COUNT(DISTINCT rental_post_id) as latest_listings
FROM v_latest_posts
GROUP BY source_code
ORDER BY latest_listings DESC;
"""
print("\n--- Listing Count by Source ---")
print(con.execute(q_sources).df())

q_obs_sources = """
SELECT source_code, COUNT(observation_id) as observations
FROM v_observations
GROUP BY source_code
ORDER BY observations DESC;
"""
print("\n--- Observation Count by Source ---")
print(con.execute(q_obs_sources).df())

# 4. Check for Null/Duplicates in v_latest_posts
q_struct = """
SELECT 
    COUNT(*) FILTER(WHERE rental_post_id IS NULL) as null_ids,
    COUNT(*) - COUNT(DISTINCT source_code || '-' || source_listing_id) as dup_source_identities
FROM v_latest_posts;
"""
print("\n--- Structural Check ---")
print(con.execute(q_struct).df())

# 5. Field Inventory and Missingness
q_missing = """
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER(WHERE title_raw IS NULL OR title_raw = '') as missing_title,
    COUNT(*) FILTER(WHERE price_amount IS NULL) as missing_price,
    COUNT(*) FILTER(WHERE area_value IS NULL) as missing_area,
    COUNT(*) FILTER(WHERE address_raw IS NULL OR address_raw = '') as missing_address_raw,
    COUNT(*) FILTER(WHERE location_raw IS NULL OR location_raw = '') as missing_location_raw
FROM v_latest_posts;
"""
print("\n--- Current Missingness ---")
print(con.execute(q_missing).df())

# 6. Source Temporal Health
q_temp = """
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER(WHERE first_observed_at > latest_observed_at) as violation_1,
    COUNT(*) FILTER(WHERE first_observed_at > last_observed_at) as violation_2,
    COUNT(*) FILTER(WHERE latest_observed_at > last_observed_at) as violation_3
FROM v_latest_posts;
"""
print("\n--- Temporal Health ---")
print(con.execute(q_temp).df())

