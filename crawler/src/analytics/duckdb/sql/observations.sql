-- 1. v_observations: Toàn bộ bản ghi quan sát Bronze (1 dòng duy nhất cho mỗi rental_post_versions)
SELECT
    v.id AS observation_id,
    pl.code AS source_code,
    pl.name AS source_name,
    p.id AS rental_post_id,
    p.platform_post_id AS source_listing_id,
    v.crawl_run_id AS run_id,
    v.observed_at,
    v.url,
    v.title_raw,
    pr.price_raw,
    pr.price_amount,
    dt.area_raw,
    dt.area_value,
    addr.full_address_text AS location_raw,
    addr.full_address_text AS address_raw,
    dt.posted_at_raw,
    dt.property_type_raw,
    v.content_hash
FROM mysql_db.rental_post_versions v
JOIN mysql_db.rental_posts p ON v.rental_post_id = p.id
JOIN mysql_db.platforms pl ON p.platform_id = pl.id
LEFT JOIN (
    -- Lấy 1 bản ghi giá đại diện theo version để tránh nhân dòng
    SELECT rental_post_version_id, price_raw, price_amount
    FROM (
        SELECT rental_post_version_id, price_raw, price_amount,
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
    SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw
    FROM (
        SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw,
               ROW_NUMBER() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) as rn
        FROM mysql_db.post_details
    ) sub WHERE rn = 1
) dt ON dt.rental_post_version_id = v.id
ORDER BY v.observed_at DESC, v.id DESC;
