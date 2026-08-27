-- Latest listing state with explicit provenance for inherited confirmed addresses.
WITH latest_price_per_version AS (
    SELECT rental_post_version_id, price_amount
    FROM (
        SELECT
            rental_post_version_id,
            price_amount,
            ROW_NUMBER() OVER (
                PARTITION BY rental_post_version_id
                ORDER BY id DESC
            ) AS row_number
        FROM mysql_db.post_prices
    ) ranked_prices
    WHERE row_number = 1
),
latest_confirmed_address_per_post AS (
    SELECT rental_post_id, rental_post_version_id, full_address_text
    FROM (
        SELECT
            rental_post_id,
            rental_post_version_id,
            full_address_text,
            ROW_NUMBER() OVER (
                PARTITION BY rental_post_id
                ORDER BY created_at DESC, id DESC
            ) AS row_number
        FROM mysql_db.post_addresses
        WHERE full_address_text IS NOT NULL
          AND TRIM(full_address_text) <> ''
    ) ranked_addresses
    WHERE row_number = 1
),
latest_detail_per_version AS (
    SELECT rental_post_version_id, area_value
    FROM (
        SELECT
            rental_post_version_id,
            area_value,
            ROW_NUMBER() OVER (
                PARTITION BY rental_post_version_id
                ORDER BY id DESC
            ) AS row_number
        FROM mysql_db.post_details
    ) ranked_details
    WHERE row_number = 1
),
ranked_posts AS (
    SELECT
        version.id AS observation_id,
        post.id AS rental_post_id,
        platform.code AS source_code,
        post.platform_post_id AS source_listing_id,
        version.url,
        version.title_raw,
        price.price_amount,
        detail.area_value,
        address.full_address_text,
        address.full_address_text AS location_raw,
        COALESCE(
            address.rental_post_version_id <> version.id,
            FALSE
        ) AS full_address_inherited,
        version.observed_at,
        post.first_observed_at,
        post.last_observed_at,
        date_diff(
            'day',
            post.first_observed_at,
            post.last_observed_at
        ) AS active_days,
        ROW_NUMBER() OVER (
            PARTITION BY post.id
            ORDER BY version.observed_at DESC, version.id DESC
        ) AS row_number
    FROM mysql_db.rental_post_versions version
    JOIN mysql_db.rental_posts post ON version.rental_post_id = post.id
    JOIN mysql_db.platforms platform ON post.platform_id = platform.id
    LEFT JOIN latest_price_per_version price
        ON price.rental_post_version_id = version.id
    LEFT JOIN latest_confirmed_address_per_post address
        ON address.rental_post_id = post.id
    LEFT JOIN latest_detail_per_version detail
        ON detail.rental_post_version_id = version.id
)
SELECT
    source_code,
    rental_post_id,
    source_listing_id,
    title_raw,
    url,
    price_amount,
    area_value,
    full_address_text,
    location_raw,
    full_address_inherited,
    observed_at AS latest_observed_at,
    first_observed_at,
    last_observed_at,
    active_days
FROM ranked_posts
WHERE row_number = 1
ORDER BY last_observed_at DESC;
