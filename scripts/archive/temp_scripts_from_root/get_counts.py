import duckdb
import os
import pandas as pd
from dotenv import load_dotenv
load_dotenv('.env')

con = duckdb.connect(database=':memory:')
con.execute("INSTALL mysql; LOAD mysql;")
host = '127.0.0.1'
port = os.getenv('BRONZE_MYSQL_HOST_PORT', 3306)
user = os.getenv('BRONZE_MYSQL_USER')
password = os.getenv('BRONZE_MYSQL_PASSWORD')
database = os.getenv('BRONZE_MYSQL_DATABASE')
con.execute(f"ATTACH 'host={host} port={port} user={user} password={password} database={database}' AS mysql_db (TYPE MYSQL, READ_ONLY);")

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

# Create fixed views
con.execute("""
CREATE OR REPLACE VIEW v_observations AS 
SELECT 
    v.id AS observation_id, pl.code AS source_code, pl."name" AS source_name, 
    p.id AS rental_post_id, p.platform_post_id AS source_listing_id, 
    v.crawl_run_id AS run_id, v.observed_at, v.url, v.title_raw, 
    pr.price_raw, pr.price_amount, dt.area_raw, dt.area_value, 
    COALESCE(addr.full_address_text, (v.source_payload ->> '$.location_raw')) AS location_raw, 
    COALESCE(addr.full_address_text, (v.source_payload ->> '$.address_raw'), (v.source_payload ->> '$.location_raw')) AS address_raw, 
    dt.posted_at_raw, dt.property_type_raw, v.content_hash
FROM mysql_db.rental_post_versions AS v 
INNER JOIN mysql_db.rental_posts AS p ON ((v.rental_post_id = p.id)) 
INNER JOIN mysql_db.platforms AS pl ON ((p.platform_id = pl.id)) 
LEFT JOIN (
    SELECT rental_post_version_id, price_raw, price_amount 
    FROM (SELECT rental_post_version_id, price_raw, price_amount, row_number() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) AS rn FROM mysql_db.post_prices) AS sub WHERE (rn = 1)
) AS pr ON ((pr.rental_post_version_id = v.id)) 
LEFT JOIN (
    SELECT rental_post_version_id, full_address_text 
    FROM (SELECT rental_post_version_id, full_address_text, row_number() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) AS rn FROM mysql_db.post_addresses) AS sub WHERE (rn = 1)
) AS addr ON ((addr.rental_post_version_id = v.id)) 
LEFT JOIN (
    SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw 
    FROM (SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw, row_number() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) AS rn FROM mysql_db.post_details) AS sub WHERE (rn = 1)
) AS dt ON ((dt.rental_post_version_id = v.id)) 
ORDER BY v.observed_at DESC, v.id DESC;
""")

con.execute("""
CREATE OR REPLACE VIEW v_latest_posts AS 
SELECT 
    v.*, 
    agg.first_observed_at, agg.latest_observed_at, agg.observations_count 
FROM v_observations AS v 
INNER JOIN (
    SELECT 
        rental_post_id, 
        min(observed_at) AS first_observed_at, 
        max(observed_at) AS latest_observed_at, 
        count(observation_id) AS observations_count 
    FROM v_observations GROUP BY rental_post_id
) AS agg ON ((v.rental_post_id = agg.rental_post_id)) 
INNER JOIN (
    SELECT rental_post_id, max(observation_id) AS latest_observation_id 
    FROM v_observations GROUP BY rental_post_id
) AS latest ON ((v.observation_id = latest.latest_observation_id));
""")

print("--- Inventory ---")
print(con.execute("SELECT COUNT(*) as total_latest, COUNT(DISTINCT rental_post_id) as unique_posts FROM v_latest_posts;").df())
print(con.execute("SELECT COUNT(*) as total_observations FROM v_observations;").df())

print("\n--- Structural Source Check ---")
print(con.execute("SELECT COUNT(*) FILTER(WHERE rental_post_id IS NULL) as null_ids, COUNT(*) - COUNT(DISTINCT source_code || '-' || source_listing_id) as dup_source_identities FROM v_latest_posts;").df())

print("\n--- Source counts ---")
print(con.execute("SELECT source_code, COUNT(DISTINCT rental_post_id) as listings FROM v_latest_posts GROUP BY source_code;").df())

print("\n--- Missingness ---")
print(con.execute("SELECT COUNT(*) as total, COUNT(*) FILTER(WHERE title_raw IS NULL OR title_raw = '') as missing_title, COUNT(*) FILTER(WHERE price_amount IS NULL) as missing_price, COUNT(*) FILTER(WHERE area_value IS NULL) as missing_area, COUNT(*) FILTER(WHERE address_raw IS NULL OR address_raw = '') as missing_address, COUNT(*) FILTER(WHERE location_raw IS NULL OR location_raw = '') as missing_location FROM v_latest_posts;").df())

print("\n--- Temporal Health ---")
print(con.execute("SELECT COUNT(*) FILTER(WHERE first_observed_at > latest_observed_at) as first_after_latest FROM v_latest_posts;").df())

