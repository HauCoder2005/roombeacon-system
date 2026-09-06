SELECT
    v.id AS observation_id,
    pl.code AS source,
    p.id AS rental_post_id,
    p.platform_post_id AS listing_id,
    v.crawl_run_id AS run_id,
    v.url,
    v.title_raw,
    pr.price_amount AS price,
    dt.area_value AS area,
    addr.full_address_text AS address
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
    SELECT rental_post_version_id, full_address_text, latitude, longitude
    FROM (
        SELECT rental_post_version_id, full_address_text, latitude, longitude,
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
LEFT JOIN (
    SELECT rental_post_version_id, contact_phone
    FROM (
        SELECT rental_post_version_id, contact_phone,
               ROW_NUMBER() OVER (PARTITION BY rental_post_version_id ORDER BY id DESC) as rn
        FROM mysql_db.post_contacts
        WHERE contact_phone IS NOT NULL
          AND TRIM(contact_phone) <> ''
    ) sub WHERE rn = 1
) contact ON contact.rental_post_version_id = v.id
LEFT JOIN (
    SELECT rental_post_version_id, image_url
    FROM (
        SELECT rental_post_version_id, image_url,
               ROW_NUMBER() OVER (
                   PARTITION BY rental_post_version_id
                   ORDER BY position ASC, id ASC
               ) as rn
        FROM mysql_db.post_images
    ) sub WHERE rn = 1
) image ON image.rental_post_version_id = v.id
ORDER BY v.observed_at DESC, v.id DESC;
