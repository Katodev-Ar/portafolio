<?php
/**
 * BUP_DB — Maneja la tabla del muro de mensajes del perfil.
 */
class BUP_DB {

    const TABLE = 'bloom_user_wall';

    public static function install(): void {
        global $wpdb;
        $table   = $wpdb->prefix . self::TABLE;
        $charset = $wpdb->get_charset_collate();

        $sql = "CREATE TABLE IF NOT EXISTS {$table} (
            id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            profile_id  BIGINT UNSIGNED NOT NULL,
            author_id   BIGINT UNSIGNED NOT NULL,
            message     TEXT            NOT NULL,
            created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_profile (profile_id),
            KEY idx_author  (author_id)
        ) {$charset};";

        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        dbDelta( $sql );

        update_option( 'bup_db_version', BUP_VERSION );
    }

    /** Insertar mensaje. Devuelve ID insertado o WP_Error. */
    public static function insert_message( int $profile_id, int $author_id, string $message ) {
        global $wpdb;
        $result = $wpdb->insert(
            $wpdb->prefix . self::TABLE,
            [
                'profile_id' => $profile_id,
                'author_id'  => $author_id,
                'message'    => $message,
            ],
            [ '%d', '%d', '%s' ]
        );
        return $result ? $wpdb->insert_id : new WP_Error( 'db_error', 'No se pudo guardar el mensaje.' );
    }

    /** Obtener mensajes de un perfil (paginados). */
    public static function get_messages( int $profile_id, int $page = 1, int $per_page = 10 ): array {
        global $wpdb;
        $table  = $wpdb->prefix . self::TABLE;
        $offset = ( $page - 1 ) * $per_page;

        $rows = $wpdb->get_results( $wpdb->prepare(
            "SELECT w.*, u.display_name, u.user_login
               FROM {$table} w
               JOIN {$wpdb->users} u ON u.ID = w.author_id
              WHERE w.profile_id = %d
           ORDER BY w.created_at DESC
              LIMIT %d OFFSET %d",
            $profile_id, $per_page, $offset
        ), ARRAY_A );

        return $rows ?: [];
    }

    /** Total de mensajes de un perfil. */
    public static function count_messages( int $profile_id ): int {
        global $wpdb;
        $table = $wpdb->prefix . self::TABLE;
        return (int) $wpdb->get_var( $wpdb->prepare(
            "SELECT COUNT(*) FROM {$table} WHERE profile_id = %d",
            $profile_id
        ) );
    }
}
