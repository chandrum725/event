-- MySQL schema for the PyMySQL access layer in db.py.
-- The configured database is created and selected by db.ensure_schema().

CREATE TABLE IF NOT EXISTS admins (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(80) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_admins_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS media (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(160) NOT NULL,
    category VARCHAR(32) NOT NULL,
    kind VARCHAR(16) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    poster_name VARCHAR(255) NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL DEFAULT 0,
    is_private TINYINT(1) NOT NULL DEFAULT 1,
    admin_id BIGINT UNSIGNED NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_media_visibility_created (is_private, created_at),
    KEY idx_media_category (category),
    KEY idx_media_kind (kind),
    KEY idx_media_admin (admin_id),
    CONSTRAINT chk_media_kind CHECK (kind IN ('image', 'video')),
    CONSTRAINT fk_media_admin FOREIGN KEY (admin_id) REFERENCES admins (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
