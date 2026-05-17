<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_DB {

    public static function install() {
        global $wpdb;
        $charset = $wpdb->get_charset_collate();

        /* ── cookies table ── */
        $sql_cookies = "CREATE TABLE IF NOT EXISTS {$wpdb->prefix}bcm_cookies (
            id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
            name        VARCHAR(255) NOT NULL,
            category    VARCHAR(50)  NOT NULL DEFAULT 'necessary',
            provider    VARCHAR(255) DEFAULT '',
            purpose     TEXT,
            expiry      VARCHAR(100) DEFAULT '',
            cookie_type VARCHAR(50)  DEFAULT 'HTTP',
            domain      VARCHAR(255) DEFAULT '',
            created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        ) $charset;";

        /* ── consent logs table (v1.3.0: columna regulation) ── */
        $sql_logs = "CREATE TABLE IF NOT EXISTS {$wpdb->prefix}bcm_consent_logs (
            id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            consent_id    VARCHAR(64)  NOT NULL,
            ip_address    VARCHAR(45)  DEFAULT '',
            user_agent    TEXT,
            status        VARCHAR(20)  NOT NULL DEFAULT 'pending',
            categories    TEXT,
            regulation    VARCHAR(10)  NOT NULL DEFAULT 'GDPR',
            created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_consent_id (consent_id),
            KEY idx_created_at (created_at),
            KEY idx_ip_address (ip_address)
        ) $charset;";

        /* ── scan history table ── */
        $sql_scans = "CREATE TABLE IF NOT EXISTS {$wpdb->prefix}bcm_scan_history (
            id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
            scan_date     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status        VARCHAR(20)  NOT NULL DEFAULT 'in_progress',
            urls_scanned  INT UNSIGNED DEFAULT 0,
            cookies_found INT UNSIGNED DEFAULT 0,
            PRIMARY KEY (id)
        ) $charset;";

        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        dbDelta( $sql_cookies );
        dbDelta( $sql_logs );
        dbDelta( $sql_scans );

        /* Migración: añadir columna regulation si no existe (upgrade desde v1.0) */
        self::maybe_add_column(
            $wpdb->prefix . 'bcm_consent_logs',
            'regulation',
            "ALTER TABLE {$wpdb->prefix}bcm_consent_logs ADD COLUMN regulation VARCHAR(10) NOT NULL DEFAULT 'GDPR' AFTER categories"
        );

        /* Índice en ip_address para borrados rápidos por GDPR Art. 17 */
        self::maybe_add_index(
            $wpdb->prefix . 'bcm_consent_logs',
            'idx_ip_address',
            "ALTER TABLE {$wpdb->prefix}bcm_consent_logs ADD INDEX idx_ip_address (ip_address)"
        );

        /* Configuración por defecto */
        if ( ! get_option( 'bcm_settings' ) ) {
            update_option( 'bcm_settings', BCM_Settings::defaults() );
        }

        /* Guardar versión instalada */
        update_option( 'bcm_db_version', BCM_VERSION );
    }

    /* ── Helpers de migración ── */
    private static function maybe_add_column( string $table, string $column, string $sql ): void {
        global $wpdb;
        $exists = $wpdb->get_results( $wpdb->prepare(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            DB_NAME, $table, $column
        ) );
        if ( empty( $exists ) ) {
            $wpdb->query( $sql ); // phpcs:ignore WordPress.DB.PreparedSQL.NotPrepared
        }
    }

    private static function maybe_add_index( string $table, string $index_name, string $sql ): void {
        global $wpdb;
        $exists = $wpdb->get_results( $wpdb->prepare(
            "SELECT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s",
            DB_NAME, $table, $index_name
        ) );
        if ( empty( $exists ) ) {
            $wpdb->query( $sql ); // phpcs:ignore WordPress.DB.PreparedSQL.NotPrepared
        }
    }

    public static function deactivate() {
        // Datos conservados al desactivar — no eliminar
    }
}
