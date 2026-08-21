-- 8. v_data_quality: Bảng điểm chất lượng dữ liệu
SELECT
    pl.code AS platform,
    COUNT(v.id) AS total_records,
    ROUND(COUNT(v.title_raw) * 100.0 / COUNT(v.id), 2) AS title_coverage_pct,
    ROUND(COUNT(pr.price_raw) * 100.0 / COUNT(v.id), 2) AS price_coverage_pct,
    ROUND(COUNT(dt.area_raw) * 100.0 / COUNT(v.id), 2) AS area_coverage_pct,
    ROUND(COUNT(addr.full_address_text) * 100.0 / COUNT(v.id), 2) AS location_coverage_pct,
    ROUND(COUNT(dt.description_raw) * 100.0 / COUNT(v.id), 2) AS description_coverage_pct
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts p ON v.rental_post_id = p.id
JOIN mysql_db.platforms pl ON p.platform_id = pl.id
LEFT JOIN (
    SELECT rental_post_version_id, price_raw
    FROM (
        SELECT rental_post_version_id, price_raw,
               ROW_NUMBER() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) as rn
        FROM mysql_db.post_prices
    ) sub WHERE rn = 1
) pr ON pr.rental_post_version_id = v.id
LEFT JOIN (
    SELECT rental_post_version_id, full_address_text
    FROM (
        SELECT rental_post_version_id, full_address_text,
               ROW_NUMBER() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) as rn
        FROM mysql_db.post_addresses
    ) sub WHERE rn = 1
) addr ON addr.rental_post_version_id = v.id
LEFT JOIN (
    SELECT rental_post_version_id, area_raw, description_raw
    FROM (
        SELECT rental_post_version_id, area_raw, description_raw,
               ROW_NUMBER() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) as rn
        FROM mysql_db.post_details
    ) sub WHERE rn = 1
) dt ON dt.rental_post_version_id = v.id
GROUP BY pl.code;
