-- One row per Bronze observation (rental_post_versions row) for the
-- Historical Curated Observations layer. Child rows use the same
-- latest-child-ID rule as v_latest_posts. Raw payloads and seller/contact
-- fields are intentionally not exported.
WITH price_per_version AS (
    SELECT rental_post_version_id, price_raw, price_amount, currency, period
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY rental_post_version_id ORDER BY id DESC
        ) AS child_rank
        FROM post_prices
    ) ranked
    WHERE child_rank = 1
),
detail_per_version AS (
    SELECT rental_post_version_id, area_raw, area_value, posted_at_raw, property_type_raw
    FROM (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY rental_post_version_id ORDER BY id DESC
        ) AS child_rank
        FROM post_details
    ) ranked
    WHERE child_rank = 1
)
SELECT
    version.id AS observation_id,
    version.rental_post_id,
    platform.code AS source_code,
    post.platform_post_id AS source_listing_id,
    version.crawl_run_id,
    version.observed_at,
    version.content_hash,
    version.ingestion_origin,
    price.price_raw,
    CAST(price.price_amount AS DOUBLE) AS price_amount,
    price.currency,
    price.period,
    detail.area_raw,
    CAST(detail.area_value AS DOUBLE) AS area_value,
    NULLIF(TRIM(detail.posted_at_raw), '') AS posted_at_raw,
    NULLIF(TRIM(detail.property_type_raw), '') AS property_type_raw
FROM rental_post_versions version
JOIN rental_posts post ON post.id = version.rental_post_id
JOIN platforms platform ON platform.id = post.platform_id
LEFT JOIN price_per_version price ON price.rental_post_version_id = version.id
LEFT JOIN detail_per_version detail ON detail.rental_post_version_id = version.id
ORDER BY version.id
