-- 2. v_latest_posts: Quan sát mới nhất của từng bài đăng (Duy nhất 1 dòng mỗi rental_post_id)
WITH ranked_observations AS (
    SELECT
        v.id AS observation_id,
        p.id AS rental_post_id,
        pl.code AS source_code,
        p.platform_post_id AS source_listing_id,
        v.url,
        v.title_raw,
        pr.price_amount,
        dt.area_value,
        addr.full_address_text AS location_raw,
        v.observed_at,
        p.first_observed_at,
        p.last_observed_at,
        date_diff('day', p.first_observed_at, p.last_observed_at) AS active_days,
        ROW_NUMBER() OVER (
            PARTITION BY p.id
            ORDER BY v.observed_at DESC, v.id DESC
        ) AS rn
    FROM mysql_db.rental_post_versions v
    JOIN mysql_db.rental_posts p ON v.rental_post_id = p.id
    JOIN mysql_db.platforms pl ON p.platform_id = pl.id
    LEFT JOIN (
        SELECT rental_post_version_id, price_amount
        FROM (
            SELECT rental_post_version_id, price_amount,
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
        SELECT rental_post_version_id, area_value
        FROM (
            SELECT rental_post_version_id, area_value,
                   ROW_NUMBER() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) as rn
            FROM mysql_db.post_details
        ) sub WHERE rn = 1
    ) dt ON dt.rental_post_version_id = v.id
)
SELECT
    source_code,
    rental_post_id,
    source_listing_id,
    title_raw,
    url,
    price_amount,
    area_value,
    location_raw,
    observed_at AS latest_observed_at,
    first_observed_at,
    last_observed_at,
    active_days
FROM ranked_observations
WHERE rn = 1
ORDER BY last_observed_at DESC;
