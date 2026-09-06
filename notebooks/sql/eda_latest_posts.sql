-- Extended v_latest_posts for EDA analysis.
-- Includes lifecycle, location coordinates, and provenance columns
-- that the standard v_latest_posts view omits.
--
-- Source: analytics/duckdb/sql/latest_posts.sql (same CTEs, wider SELECT)

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
    SELECT rental_post_id, rental_post_version_id, full_address_text, latitude, longitude
    FROM (
        SELECT
            rental_post_id,
            rental_post_version_id,
            full_address_text,
            latitude,
            longitude,
            ROW_NUMBER() OVER (
                PARTITION BY rental_post_id
                ORDER BY
                    (latitude IS NOT NULL) DESC,
                    LENGTH(full_address_text) DESC,
                    created_at DESC,
                    id DESC
            ) AS row_number
        FROM mysql_db.post_addresses
        WHERE full_address_text IS NOT NULL
          AND TRIM(full_address_text) <> ''
    ) ranked_addresses
    WHERE row_number = 1
),

latest_contact_per_version AS (
    SELECT rental_post_version_id, contact_phone
    FROM (
        SELECT
            rental_post_version_id,
            contact_phone,
            ROW_NUMBER() OVER (
                PARTITION BY rental_post_version_id
                ORDER BY id DESC
            ) AS row_number
        FROM mysql_db.post_contacts
        WHERE contact_phone IS NOT NULL
          AND TRIM(contact_phone) <> ''
    ) ranked_contacts
    WHERE row_number = 1
),

primary_image_per_version AS (
    SELECT rental_post_version_id, image_url
    FROM (
        SELECT
            rental_post_version_id,
            image_url,
            ROW_NUMBER() OVER (
                PARTITION BY rental_post_version_id
                ORDER BY position ASC, id ASC
            ) AS row_number
        FROM mysql_db.post_images
    ) ranked_images
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
        version.id           AS observation_id,
        post.id              AS rental_post_id,
        platform.code        AS source,
        post.platform_post_id AS listing_id,
        version.url,
        version.title_raw,
        price.price_amount   AS price,
        detail.area_value    AS area,
        address.full_address_text AS address,
        address.latitude,
        address.longitude,
        contact.contact_phone,
        image.image_url,
        COALESCE(
            address.rental_post_version_id <> version.id,
            FALSE
        )                    AS full_address_inherited,
        version.observed_at,
        post.first_observed_at,
        post.last_observed_at,
        date_diff(
            'day',
            post.first_observed_at,
            post.last_observed_at
        )                    AS active_days,
        ROW_NUMBER() OVER (
            PARTITION BY post.id
            ORDER BY version.observed_at DESC, version.id DESC
        )                    AS row_number
    FROM mysql_db.rental_post_versions version
    JOIN mysql_db.rental_posts post
        ON version.rental_post_id = post.id
    JOIN mysql_db.platforms platform
        ON post.platform_id = platform.id
    LEFT JOIN latest_price_per_version price
        ON price.rental_post_version_id = version.id
    LEFT JOIN latest_confirmed_address_per_post address
        ON address.rental_post_id = post.id
    LEFT JOIN latest_detail_per_version detail
        ON detail.rental_post_version_id = version.id
    LEFT JOIN latest_contact_per_version contact
        ON contact.rental_post_version_id = version.id
    LEFT JOIN primary_image_per_version image
        ON image.rental_post_version_id = version.id
)

SELECT
    source,
    rental_post_id,
    listing_id,
    title_raw,
    url,
    price,
    area,
    address,
    latitude,
    longitude,
    contact_phone,
    image_url,
    full_address_inherited,
    observed_at,
    first_observed_at,
    last_observed_at,
    active_days
FROM ranked_posts
WHERE row_number = 1
ORDER BY last_observed_at DESC
