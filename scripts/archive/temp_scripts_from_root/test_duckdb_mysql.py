import duckdb
import os
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

import sys
sys.path.insert(0, os.getcwd())
from analytics.duckdb.views import DuckDBViewManager
try:
    DuckDBViewManager.create_views(con)
except Exception as e:
    print(e)
    
# try creating v_observations directly to see the error
q = """
CREATE OR REPLACE VIEW v_observations AS SELECT v.id AS observation_id, pl.code AS source_code, pl."name" AS source_name, p.id AS rental_post_id, p.platform_post_id AS source_listing_id, v.crawl_run_id AS run_id, v.observed_at, v.url, v.title_raw, pr.price_raw, pr.price_amount, dt.area_raw, dt.area_value, COALESCE(addr.full_address_text, (v.source_payload ->> '$.location_raw')) AS location_raw, COALESCE(addr.full_address_text, (v.source_payload ->> '$.address_raw'), (v.source_payload ->> '$.location_raw')) AS address_raw, dt.posted_at_raw, dt.property_type_raw, v.content_hash, v.ingestion_origin FROM mysql_db.rental_post_versions AS v INNER JOIN mysql_db.rental_posts AS p ON ((v.rental_post_id = p.id)) INNER JOIN mysql_db.platforms AS pl ON ((p.platform_id = pl.id)) LEFT JOIN (SELECT rental_post_version_id, price_raw, price_amount FROM (SELECT rental_post_version_id, price_raw, price_amount, row_number() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) AS rn FROM mysql_db.post_prices) AS sub WHERE (rn = 1)) AS pr ON ((pr.rental_post_version_id = v.id)) LEFT JOIN (SELECT rental_post_version_id, full_address_text FROM (SELECT rental_post_version_id, full_address_text, row_number() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) AS rn FROM mysql_db.post_addresses) AS sub WHERE (rn = 1)) AS addr ON ((addr.rental_post_version_id = v.id)) LEFT JOIN (SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw FROM (SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw, row_number() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) AS rn FROM mysql_db.post_details) AS sub WHERE (rn = 1)) AS dt ON ((dt.rental_post_version_id = v.id)) ORDER BY v.observed_at DESC, v.id DESC;
"""
try:
    con.execute(q)
except Exception as e:
    print("Error creating v_observations:", e)

