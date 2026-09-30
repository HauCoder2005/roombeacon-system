import os
from dotenv import load_dotenv
import pymysql
import pandas as pd

load_dotenv('.env')

connection = pymysql.connect(
    host=os.getenv('MYSQL_HOST', '127.0.0.1'),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DATABASE'),
    port=int(os.getenv('MYSQL_PORT', 3306))
)

# 1. Total latest listings and unique rental_post_id
query1 = """
SELECT COUNT(*) as total_latest, COUNT(DISTINCT id) as unique_ids
FROM rental_posts;
"""
print("--- Listing Counts ---")
print(pd.read_sql(query1, connection))

# 2. Total observations
query2 = """
SELECT COUNT(*) as total_observations, COUNT(DISTINCT rental_post_id) as unique_observed_listings
FROM rental_post_versions;
"""
print("\n--- Observation Counts ---")
print(pd.read_sql(query2, connection))

# 3. Source counts
query3 = """
SELECT p.code as source, COUNT(DISTINCT rp.id) as listing_count, COUNT(rpv.id) as observation_count
FROM platforms p
JOIN rental_posts rp ON p.id = rp.platform_id
JOIN rental_post_versions rpv ON rp.id = rpv.rental_post_id
GROUP BY p.code;
"""
print("\n--- By Source ---")
print(pd.read_sql(query3, connection))

connection.close()
