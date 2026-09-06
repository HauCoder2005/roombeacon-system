from sqlalchemy import text
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory
from datetime import datetime, timezone

query = text("""
    WITH latest AS (
        SELECT id, rental_post_id,
               ROW_NUMBER() OVER (
                   PARTITION BY rental_post_id
                   ORDER BY observed_at DESC, id DESC
               ) AS rn
        FROM rental_post_versions
    )
    SELECT pl.code AS source, 
           COUNT(*) as total,
           SUM(CASE WHEN a.full_address_text IS NOT NULL AND TRIM(a.full_address_text) <> '' THEN 1 ELSE 0 END) as address_ok,
           SUM(CASE WHEN a.full_address_text IS NULL OR TRIM(a.full_address_text) = '' THEN 1 ELSE 0 END) as missing
    FROM rental_posts p
    JOIN platforms pl ON pl.id = p.platform_id
    JOIN latest l ON l.rental_post_id = p.id AND l.rn = 1
    LEFT JOIN post_addresses a ON a.rental_post_id = p.id
    GROUP BY pl.code
""")

engine = MySQLConnectionFactory.get_engine()
with engine.connect() as conn:
    rows = conn.execute(query).fetchall()

now_iso = datetime.now(timezone.utc).isoformat()
print(f"Snapshot Time: {now_iso}")
print(f"Database: roombeacon_bronze on roombeacon-mysql-bronze container")
for r in rows:
    print(f"{r.source}: {r.total} total / {r.address_ok} address / {r.missing} missing")
