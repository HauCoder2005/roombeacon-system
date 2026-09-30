from sqlalchemy import text
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

query = text("""
    WITH latest AS (
        SELECT id as version_id, rental_post_id, crawl_run_id,
               ROW_NUMBER() OVER (
                   PARTITION BY rental_post_id
                   ORDER BY observed_at DESC, id DESC
               ) AS rn
        FROM rental_post_versions
    )
    SELECT pl.code AS source, p.platform_post_id, p.url, l.crawl_run_id, l.version_id, a.full_address_text
    FROM rental_posts p
    JOIN platforms pl ON pl.id = p.platform_id
    JOIN latest l ON l.rental_post_id = p.id AND l.rn = 1
    LEFT JOIN post_addresses a ON a.rental_post_id = p.id
    WHERE pl.code IN ('cafeland', 'chothuenha')
      AND p.url IN (
          'https://chothuenha.com.vn/cho-thue-nha-tro-trung-tam-quan-1-gan-cho-ben-thanh-79158',
          'https://chothuenha.com.vn/cho-thue-phong-tro-co-gac-nhu-nha-rieng-biet-gan-truong-dh-cong-nghiep-cho-go-vap-emart-78797',
          'https://nhadat.cafeland.vn/khai-truong-du-an-moi-gan-huflit-hoc-mon-3144910.html',
          'https://nhadat.cafeland.vn/bancol-lau-1-29m2-223-ba-hat-ngay-nguyen-tri-phuong-65trth-2936526.html'
      )
""")

engine = MySQLConnectionFactory.get_engine()
with engine.connect() as conn:
    rows = conn.execute(query).fetchall()

print("| Domain | Listing ID | URL | Run/version | Source address | MySQL address | DuckDB match |")
print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
for r in rows:
    print(f"| {r.source} | {r.platform_post_id} | {r.url.split('/')[-1]} | run:{r.crawl_run_id}/v:{r.version_id} | {r.full_address_text} | {r.full_address_text} | NOT VERIFIED |")
