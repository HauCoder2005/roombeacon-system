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
        NULLIF(
            TRIM(json_extract_string(version.source_payload, '$.location_raw')),
            ''
        ) AS location_raw,
        json_extract_string(version.source_payload, '$.map_location.provider') AS map_provider,
        CASE WHEN (
            platform.code = 'cafeland'
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.latitude') AS DOUBLE) = 10.876248
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.longitude') AS DOUBLE) = 106.660338
        ) OR (
            platform.code = 'nhatrovn'
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.latitude') AS DOUBLE) = 10.6979911
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.longitude') AS DOUBLE) = 106.7168188
        ) THEN NULL ELSE
            TRY_CAST(json_extract_string(version.source_payload, '$.map_location.latitude') AS DOUBLE)
        END AS map_latitude,
        CASE WHEN (
            platform.code = 'cafeland'
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.latitude') AS DOUBLE) = 10.876248
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.longitude') AS DOUBLE) = 106.660338
        ) OR (
            platform.code = 'nhatrovn'
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.latitude') AS DOUBLE) = 10.6979911
            AND TRY_CAST(json_extract_string(version.source_payload, '$.map_location.longitude') AS DOUBLE) = 106.7168188
        ) THEN NULL ELSE
            TRY_CAST(json_extract_string(version.source_payload, '$.map_location.longitude') AS DOUBLE)
        END AS map_longitude,
        json_extract_string(version.source_payload, '$.map_location.query_raw') AS map_query_raw,
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
    rp.source_code,
    rp.rental_post_id,
    rp.source_listing_id,
    rp.title_raw,
    rp.url,
    rp.price_amount,
    rp.area_value,
    rp.full_address_text,
    rp.location_raw,
    rp.full_address_inherited,
    rp.map_provider,
    rp.map_latitude,
    rp.map_longitude,
    rp.map_query_raw,

    COALESCE(
        rp.full_address_text,
        rp.location_raw
    ) AS best_address_text,
    CASE
        WHEN rp.full_address_text IS NOT NULL THEN 'source_detail'
        WHEN rp.location_raw IS NOT NULL THEN 'source_card'
        ELSE 'none'
    END AS best_address_source,

    rp.observed_at AS latest_observed_at,
    rp.first_observed_at,
    rp.last_observed_at,
    rp.active_days
FROM ranked_posts rp
WHERE rp.row_number = 1
ORDER BY rp.last_observed_at DESC;
