<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Admin {

    public function __construct() {
        add_action( 'admin_menu',            [ $this, 'register_menu' ] );
        add_action( 'admin_enqueue_scripts', [ $this, 'enqueue_assets' ] );
        add_action( 'wp_ajax_bcm_save_settings',   [ $this, 'ajax_save_settings' ] );
        add_action( 'wp_ajax_bcm_start_scan',      [ $this, 'ajax_start_scan' ] );
        add_action( 'wp_ajax_bcm_get_scan_status', [ $this, 'ajax_scan_status' ] );
        add_action( 'wp_ajax_bcm_save_cookie',     [ $this, 'ajax_save_cookie' ] );
        add_action( 'wp_ajax_bcm_delete_cookie',   [ $this, 'ajax_delete_cookie' ] );
        add_action( 'wp_ajax_bcm_get_cookies',     [ $this, 'ajax_get_cookies' ] );
        add_action( 'wp_ajax_bcm_seed_cookies',    [ $this, 'ajax_seed_cookies' ] );  // v1.4.2
        /* v1.3.0 */
        add_action( 'wp_ajax_bcm_export_consent_csv', [ $this, 'ajax_export_csv' ] );
        add_action( 'wp_ajax_bcm_delete_consent_ip',  [ $this, 'ajax_delete_by_ip' ] );
        add_action( 'admin_init',                     [ $this, 'handle_csv_download' ] );
    }

    /* ── Menu ── */
    public function register_menu(): void {
        add_menu_page(
            __( 'Cookie Manager', 'bloom-cookie-manager' ),
            __( 'Cookie Manager', 'bloom-cookie-manager' ),
            'manage_options',
            'bcm-dashboard',
            [ $this, 'page_dashboard' ],
            'dashicons-privacy',
            80
        );

        $pages = [
            'bcm-banner'       => __( 'Cookie Banner', 'bloom-cookie-manager' ),
            'bcm-cookies'      => __( 'Cookie Manager', 'bloom-cookie-manager' ),
            'bcm-consent-log'  => __( 'Consent Log', 'bloom-cookie-manager' ),
            'bcm-settings'     => __( 'Settings', 'bloom-cookie-manager' ),
        ];

        foreach ( $pages as $slug => $label ) {
            add_submenu_page( 'bcm-dashboard', $label, $label, 'manage_options', $slug, [ $this, 'render_page' ] );
        }
    }

    /* ── Assets ── */
    public function enqueue_assets( string $hook ): void {
        if ( strpos( $hook, 'bcm-' ) === false && $hook !== 'toplevel_page_bcm-dashboard' ) return;

        wp_enqueue_style(  'bcm-admin', BCM_PLUGIN_URL . 'admin/css/admin.css', [], BCM_VERSION );
        wp_enqueue_style(  'wp-color-picker' );
        wp_enqueue_script( 'bcm-admin', BCM_PLUGIN_URL . 'admin/js/admin.js', [ 'jquery', 'wp-color-picker' ], BCM_VERSION, true );
        wp_localize_script( 'bcm-admin', 'bcmData', [
            'ajaxUrl'  => admin_url( 'admin-ajax.php' ),
            // Legacy single nonce kept for back-compat with any external integrations;
            // per-action nonces below are the enforced values server-side.
            'nonce'    => wp_create_nonce( 'bcm_nonce' ),
            'nonces'   => [
                'save_settings'    => wp_create_nonce( 'bcm_save_settings' ),
                'start_scan'       => wp_create_nonce( 'bcm_start_scan' ),
                'get_scan_status'  => wp_create_nonce( 'bcm_get_scan_status' ),
                'save_cookie'      => wp_create_nonce( 'bcm_save_cookie' ),
                'delete_cookie'    => wp_create_nonce( 'bcm_delete_cookie' ),
                'get_cookies'      => wp_create_nonce( 'bcm_get_cookies' ),
                'seed_cookies'     => wp_create_nonce( 'bcm_seed_cookies' ),
                'export_csv'       => wp_create_nonce( 'bcm_export_consent_csv' ),
                'delete_by_ip'     => wp_create_nonce( 'bcm_delete_consent_ip' ),
                'reset_tc_user'    => wp_create_nonce( 'bcm_reset_tc_user' ),
            ],
            'settings' => BCM_Settings::get(),
        ] );
    }

    /* ── Page routing ── */
    public function render_page(): void {
        $page = isset( $_GET['page'] ) ? sanitize_key( $_GET['page'] ) : 'bcm-dashboard';
        switch ( $page ) {
            case 'bcm-banner':      include BCM_PLUGIN_DIR . 'admin/views/banner.php';      break;
            case 'bcm-cookies':     include BCM_PLUGIN_DIR . 'admin/views/cookies.php';     break;
            case 'bcm-consent-log': include BCM_PLUGIN_DIR . 'admin/views/consent-log.php'; break;
            case 'bcm-settings':    include BCM_PLUGIN_DIR . 'admin/views/settings.php';    break;
        }
    }

    public function page_dashboard(): void {
        include BCM_PLUGIN_DIR . 'admin/views/dashboard.php';
    }

    /* ── AJAX handlers ── */
    public function ajax_save_settings(): void {
        if ( ! check_ajax_referer( 'bcm_save_settings', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( 'Unauthorized', 403 );
            wp_die();
        }

        // Decode JSON from POST, then recursively sanitize every value.
        // Never trust decoded JSON as safe — arrays may contain arbitrary user input.
        $raw  = isset( $_POST['settings'] ) ? json_decode( wp_unslash( $_POST['settings'] ), true ) : null;
        $data = is_array( $raw ) ? self::sanitize_recursive( $raw ) : [];

        BCM_Settings::save( $data );
        wp_send_json_success( [ 'message' => __( 'Settings saved.', 'bloom-cookie-manager' ) ] );
    }

    /**
     * Recursively sanitizes every value in an array decoded from user-supplied JSON.
     *
     * Rules applied per value type:
     *   - string  → sanitize_text_field()
     *   - int     → intval()
     *   - float   → floatval()
     *   - bool    → (bool) cast — pass-through
     *   - array   → recurse
     *   - other   → cast to string, then sanitize_text_field()
     *
     * Array keys are run through sanitize_key() to prevent injection via key names.
     *
     * @param  array $data  Unsanitized array from json_decode().
     * @return array        Fully sanitized array safe for further processing.
     */
    private static function sanitize_recursive( array $data ): array {
        $clean = [];
        foreach ( $data as $key => $value ) {
            $safe_key = sanitize_key( $key );
            if ( is_array( $value ) ) {
                $clean[ $safe_key ] = self::sanitize_recursive( $value );
            } elseif ( is_bool( $value ) ) {
                $clean[ $safe_key ] = $value;
            } elseif ( is_int( $value ) ) {
                $clean[ $safe_key ] = intval( $value );
            } elseif ( is_float( $value ) ) {
                $clean[ $safe_key ] = floatval( $value );
            } else {
                $clean[ $safe_key ] = sanitize_text_field( (string) $value );
            }
        }
        return $clean;
    }

    public function ajax_start_scan(): void {
        if ( ! check_ajax_referer( 'bcm_start_scan', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }

        $scan_id = BCM_Scanner::start_scan();
        wp_send_json_success( [ 'scan_id' => $scan_id ] );
    }

    public function ajax_scan_status(): void {
        if ( ! check_ajax_referer( 'bcm_get_scan_status', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }
        global $wpdb;

        $scan_id = (int) ( wp_unslash( $_POST['scan_id'] ?? 0 ) );
        $row     = $wpdb->get_row( $wpdb->prepare(
            "SELECT * FROM {$wpdb->prefix}bcm_scan_history WHERE id = %d", $scan_id
        ), ARRAY_A );

        wp_send_json_success( $row );
    }

    public function ajax_save_cookie(): void {
        if ( ! check_ajax_referer( 'bcm_save_cookie', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }
        global $wpdb;

        $id      = (int) ( wp_unslash( $_POST['id'] ?? 0 ) );
        $payload = [
            'name'        => sanitize_text_field( wp_unslash( $_POST['name']        ?? '' ) ),
            'category'    => sanitize_text_field( wp_unslash( $_POST['category']    ?? 'necessary' ) ),
            'provider'    => sanitize_text_field( wp_unslash( $_POST['provider']    ?? '' ) ),
            'purpose'     => sanitize_textarea_field( wp_unslash( $_POST['purpose'] ?? '' ) ),
            'expiry'      => sanitize_text_field( wp_unslash( $_POST['expiry']      ?? '' ) ),
            'cookie_type' => sanitize_text_field( wp_unslash( $_POST['cookie_type'] ?? 'HTTP' ) ),
            'domain'      => sanitize_text_field( wp_unslash( $_POST['domain']      ?? '' ) ),
        ];

        // Constrain category to known values to prevent arbitrary DB insertion
        $allowed_cats = [ 'necessary', 'functional', 'analytics', 'performance', 'advertisement' ];
        if ( ! in_array( $payload['category'], $allowed_cats, true ) ) {
            $payload['category'] = 'necessary';
        }

        if ( $id ) {
            $wpdb->update( $wpdb->prefix . 'bcm_cookies', $payload, [ 'id' => $id ] );
        } else {
            $wpdb->insert( $wpdb->prefix . 'bcm_cookies', $payload );
        }
        wp_send_json_success();
    }

    public function ajax_delete_cookie(): void {
        if ( ! check_ajax_referer( 'bcm_delete_cookie', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }
        global $wpdb;

        $id = (int) wp_unslash( $_POST['id'] ?? 0 );
        $wpdb->delete( $wpdb->prefix . 'bcm_cookies', [ 'id' => $id ], [ '%d' ] );
        wp_send_json_success();
    }

    public function ajax_get_cookies(): void {
        if ( ! check_ajax_referer( 'bcm_get_cookies', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }
        global $wpdb;

        $category = sanitize_text_field( wp_unslash( $_POST['category'] ?? '' ) );
        $where    = $category ? $wpdb->prepare( 'WHERE category = %s', $category ) : '';
        $results  = $wpdb->get_results( "SELECT * FROM {$wpdb->prefix}bcm_cookies $where ORDER BY category, name", ARRAY_A ); // phpcs:ignore WordPress.DB.PreparedSQL.InterpolatedNotPrepared -- $where is either empty or prepared above
        wp_send_json_success( $results );
    }

    /* ── v1.4.2: Importar biblioteca de cookies conocidas ── */
    public function ajax_seed_cookies(): void {
        if ( ! check_ajax_referer( 'bcm_seed_cookies', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }
        $added = BCM_Scanner::seed_known_cookies();
        wp_send_json_success( [ 'added' => $added ] );
    }

    /* ── v1.3.0: Exportar CSV de consentimientos ── */
    public function handle_csv_download(): void {
        if ( ! isset( $_GET['bcm_export_csv'] ) ) return;
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_die( esc_html__( 'You do not have permission to perform this action.', 'bloom-cookie-manager' ) );
        }
        check_admin_referer( 'bcm_export_csv' );
        BCM_Consent_Log::export_csv();
    }

    public function ajax_export_csv(): void {
        if ( ! check_ajax_referer( 'bcm_export_consent_csv', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }
        $url = wp_nonce_url(
            admin_url( 'admin.php?bcm_export_csv=1' ),
            'bcm_export_csv'
        );
        wp_send_json_success( [ 'url' => $url ] );
    }

    /* ── v1.3.0: Eliminar registros por IP (GDPR Art. 17) ── */
    public function ajax_delete_by_ip(): void {
        if ( ! check_ajax_referer( 'bcm_delete_consent_ip', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( [ 'message' => 'Unauthorized.' ], 403 );
            wp_die();
        }

        $ip_raw = sanitize_text_field( wp_unslash( $_POST['ip'] ?? '' ) );

        // Validate this is actually an IP address before running a DELETE query
        if ( ! filter_var( $ip_raw, FILTER_VALIDATE_IP ) ) {
            wp_send_json_error( [ 'message' => 'Invalid IP address.' ] );
        }

        $deleted = BCM_Consent_Log::delete_by_ip( $ip_raw );
        wp_send_json_success( [ 'deleted' => $deleted ] );
    }
}
