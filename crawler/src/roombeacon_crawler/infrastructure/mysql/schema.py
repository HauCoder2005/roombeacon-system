import logging
from sqlalchemy import text
from roombeacon_crawler.infrastructure.mysql.connection import MySQLConnectionFactory

logger = logging.getLogger(__name__)

INIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS platforms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    base_url VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_platform_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rental_posts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    platform_id INT NOT NULL,
    platform_post_id VARCHAR(512) NOT NULL,
    url VARCHAR(500) NOT NULL,
    title_raw VARCHAR(500) NULL,
    first_observed_at DATETIME NOT NULL,
    last_observed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_platform_post (platform_id, platform_post_id),
    KEY idx_platform_last_observed (platform_id, last_observed_at),
    CONSTRAINT fk_posts_platform FOREIGN KEY (platform_id) REFERENCES platforms(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rental_post_versions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    crawl_run_id VARCHAR(100) NOT NULL,
    observed_at DATETIME NOT NULL,
    url VARCHAR(500) NOT NULL,
    title_raw VARCHAR(500) NULL,
    content_hash VARCHAR(64) NOT NULL,
    source_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_post_run (rental_post_id, crawl_run_id),
    KEY idx_observed_at (observed_at),
    KEY idx_crawl_run (crawl_run_id),
    CONSTRAINT fk_versions_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_prices (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    price_raw VARCHAR(100) NULL,
    price_amount DECIMAL(15, 2) NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'VND',
    period VARCHAR(20) NOT NULL DEFAULT 'MONTH',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_prices_version (rental_post_version_id),
    KEY idx_prices_post (rental_post_id),
    CONSTRAINT fk_prices_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_prices_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_addresses (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    province_text VARCHAR(100) NULL,
    district_text VARCHAR(100) NULL,
    ward_text VARCHAR(100) NULL,
    street_text VARCHAR(255) NULL,
    house_number_text VARCHAR(100) NULL,
    full_address_text VARCHAR(500) NULL,
    latitude DECIMAL(10, 7) NULL,
    longitude DECIMAL(10, 7) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_addresses_version (rental_post_version_id),
    KEY idx_addresses_post (rental_post_id),
    CONSTRAINT fk_addresses_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_addresses_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_details (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    area_raw VARCHAR(100) NULL,
    area_value DECIMAL(10, 2) NULL,
    description_raw TEXT NULL,
    property_type_raw VARCHAR(100) NULL,
    furnishing_raw VARCHAR(100) NULL,
    deposit_raw VARCHAR(100) NULL,
    posted_at_raw VARCHAR(100) NULL,
    seller_name_raw VARCHAR(100) NULL,
    seller_type_raw VARCHAR(50) NULL,
    seller_phone_raw VARCHAR(50) NULL,
    attributes JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_details_version (rental_post_version_id),
    KEY idx_details_post (rental_post_id),
    CONSTRAINT fk_details_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_details_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_images (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    image_url TEXT NOT NULL,
    position INT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_images_version (rental_post_version_id),
    KEY idx_images_post (rental_post_id),
    CONSTRAINT fk_images_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_images_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_amenities (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    amenity_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_amenities_version (rental_post_version_id),
    KEY idx_amenities_post (rental_post_id),
    CONSTRAINT fk_amenities_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_amenities_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_fees (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    fee_name VARCHAR(100) NOT NULL,
    fee_raw VARCHAR(100) NULL,
    fee_amount DECIMAL(15, 2) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_fees_version (rental_post_version_id),
    KEY idx_fees_post (rental_post_id),
    CONSTRAINT fk_fees_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_fees_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_contacts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    contact_name VARCHAR(100) NULL,
    contact_phone VARCHAR(50) NULL,
    contact_type VARCHAR(50) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_contacts_version (rental_post_version_id),
    KEY idx_contacts_post (rental_post_id),
    CONSTRAINT fk_contacts_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_contacts_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_attributes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    rental_post_version_id BIGINT NOT NULL,
    attribute_key VARCHAR(100) NOT NULL,
    attribute_value TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_attributes_version (rental_post_version_id),
    KEY idx_attributes_post (rental_post_id),
    CONSTRAINT fk_attributes_version FOREIGN KEY (rental_post_version_id) REFERENCES rental_post_versions(id) ON DELETE CASCADE,
    CONSTRAINT fk_attributes_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_status_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    rental_post_id BIGINT NOT NULL,
    status VARCHAR(50) NOT NULL,
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason VARCHAR(255) NULL,
    KEY idx_status_post (rental_post_id),
    CONSTRAINT fk_status_post FOREIGN KEY (rental_post_id) REFERENCES rental_posts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def ensure_mysql_schema(engine=None) -> None:
    """Tạo các bảng schema MySQL nếu chưa tồn tại (Idempotent)."""
    eng = engine or MySQLConnectionFactory.get_engine()
    with eng.connect() as conn:
        with conn.begin():
            for stmt in INIT_SCHEMA_SQL.strip().split(";"):
                stmt_clean = stmt.strip()
                if stmt_clean:
                    conn.execute(text(stmt_clean))
    logger.info("MySQL Bronze Schema đã được khởi tạo/kiểm tra thành công.")


if __name__ == "__main__":
    ensure_mysql_schema()
