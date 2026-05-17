<?php
/**
 * BCM_TC_Manager — Terms & Conditions enforcement engine (v1.7.0)
 *
 * Storage  : wp_usermeta · meta_key = _tc_accepted · values: 1 = accepted, 0 = rejected / absent = not yet accepted
 * Access   : template_redirect  → redirects logged-in users who haven't accepted T&C
 * Login    : wp_login            → validates T&C at login time
 * Logout   : wp_logout           → clears session cookies on explicit rejection
 * Notices  : login_message       → shows error notice when ?error=tc_rejected is present
 * Cron     : bcm_cleanup_rejected_users → purges inactive rejected accounts after 30 days
 *
 * @package  BloomCookieManager
 * @since    1.7.0
 */

if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_TC_Manager {

    /** Meta-key used to store T&C acceptance state in wp_usermeta. */
    const META_KEY = '_tc_accepted';

    /** URL parameter used to signal T&C rejection on the login page. */
    const REJECTED_PARAM = 'tc_rejected';

    /** Cron hook name. */
    const CRON_HOOK = 'bcm_cleanup_rejected_users';

    /** How many days of inactivity before a rejected account is purged. */
    const PURGE_DAYS = 30;

    /* ──────────────────────────────────────────────────────────────
     * Bootstrap
     * ────────────────────────────────────────────────────────────── */

    public function __construct() {
        // Access-gate: runs on every front-end request
        add_action( 'template_redirect', [ $this, 'gate_access' ], 1 );

        /*
         * TWO-LAYER login interception:
         *
         * Layer 1 — `authenticate` filter (priority 100, runs BEFORE wp_set_auth_cookie).
         *   Returns a WP_Error to abort the login entirely if T&C not accepted.
         *   The cookie is never created. This is the primary defense.
         *
         * Layer 2 — `wp_login` action (runs AFTER wp_set_auth_cookie).
         *   Destroys the session token server-side and clears the cookie via headers.
         *   Acts as a safety net in case the authenticate filter is bypassed
         *   (e.g., by another plugin calling wp_set_auth_cookie directly).
         */
        add_filter( 'authenticate',      [ $this, 'block_login_if_rejected' ], 100, 1 );
        add_action( 'wp_login',          [ $this, 'check_on_login' ], 10, 2 );
        add_action( 'admin_init',         [ $this, 'gate_admin_access' ] );

        // AJAX: user explicitly accepts T&C
        add_action( 'wp_ajax_bcm_accept_tc',        [ $this, 'ajax_accept_tc' ] );
        add_action( 'wp_ajax_nopriv_bcm_accept_tc',  [ $this, 'ajax_accept_tc' ] );

        // AJAX: user explicitly rejects T&C on the acceptance page
        add_action( 'wp_ajax_bcm_reject_tc', [ $this, 'ajax_reject_tc' ] );

        // Login page notice
        add_filter( 'login_message', [ $this, 'login_notice' ] );

        // Admin: T&C settings sub-section is handled by BCM_Settings / BCM_Admin
        add_action( 'wp_ajax_bcm_reset_tc_user', [ $this, 'ajax_admin_reset_tc' ] );

        // Scheduled cleanup
        add_action( self::CRON_HOOK, [ __CLASS__, 'purge_rejected_users' ] );

        // Register/deregister cron on activation/deactivation (called from main file hooks)
        add_action( 'bcm_activated',   [ __CLASS__, 'schedule_cron' ] );
        add_action( 'bcm_deactivated', [ __CLASS__, 'unschedule_cron' ] );
    }

    /* ──────────────────────────────────────────────────────────────
     * Core helpers
     * ────────────────────────────────────────────────────────────── */

    /**
     * Returns TRUE if the given user has explicitly accepted the T&C.
     *
     * @param int $user_id
     * @return bool
     */
    public static function user_accepted( int $user_id ): bool {
        $value = get_user_meta( $user_id, self::META_KEY, true );
        return ( $value === '1' || $value === 1 );
    }

    /**
     * Saves acceptance state for a user.
     *
     * @param int  $user_id
     * @param bool $accepted  TRUE = accepted, FALSE = rejected
     */
    public static function set_acceptance( int $user_id, bool $accepted ): void {
        update_user_meta( $user_id, self::META_KEY, $accepted ? '1' : '0' );
    }

    /**
     * Returns the configured T&C acceptance page URL, or home_url() as fallback.
     *
     * Reads `tc_acceptance_page_id` from BCM settings; admins can set this in
     * Settings → Compliance.
     *
     * @return string  Absolute URL
     */
    public static function acceptance_page_url(): string {
        $page_id = (int) BCM_Settings::get( 'tc_acceptance_page_id' );
        if ( $page_id > 0 ) {
            $url = get_permalink( $page_id );
            if ( $url ) return $url;
        }
        // Fallback: create a virtual URL handled by our shortcode / template
        return home_url( '/tc-acceptance/' );
    }

    /* ──────────────────────────────────────────────────────────────
     * 1. template_redirect — access gate
     * ────────────────────────────────────────────────────────────── */

    /**
     * Runs on every front-end template load.
     * If the user is logged in but hasn't accepted T&C, redirect to acceptance page.
     * Skip the acceptance page itself (avoid infinite loop).
     */
    public function gate_access(): void {
        if ( ! is_user_logged_in() ) return;

        $s = BCM_Settings::get();

        // Feature must be enabled
        if ( empty( $s['tc_enforcement_enabled'] ) ) return;

        // Avoid redirect loop: let the acceptance page and wp-login.php through FIRST
        // (before any DB queries)
        if ( $this->is_acceptance_page() || $this->is_wp_login() ) return;

        // Allow admin users to bypass (prevent lockout)
        if ( current_user_can( 'manage_options' ) ) return;

        $user_id = get_current_user_id();

        // Already accepted — nothing to do
        if ( self::user_accepted( $user_id ) ) return;

        /*
         * User is logged in but has NOT accepted T&C (either never seen it,
         * or explicitly rejected it). In both cases: redirect to acceptance page.
         *
         * If the user rejected T&C their session should already be destroyed by
         * ajax_reject_tc(), but gate_access() acts as a hard safety net for any
         * edge case where a session survived (direct wp_set_auth_cookie() calls,
         * "Remember Me" cookie from before rejection, REST API access, etc.).
         */
        wp_safe_redirect( self::acceptance_page_url() );
        exit;
    }

    /**
     * Admin-area gate — mirrors gate_access() for wp-admin requests.
     * template_redirect does NOT fire inside wp-admin, so we need a separate
     * hook on admin_init to block non-accepting users from the dashboard.
     */
    public function gate_admin_access(): void {
        if ( ! is_user_logged_in() ) return;

        $s = BCM_Settings::get();
        if ( empty( $s['tc_enforcement_enabled'] ) ) return;

        // Allow admin users to bypass (prevent lockout)
        if ( current_user_can( 'manage_options' ) ) return;

        $user_id = get_current_user_id();
        if ( self::user_accepted( $user_id ) ) return;

        // Block wp-admin access — redirect to acceptance page.
        wp_safe_redirect( self::acceptance_page_url() );
        exit;
    }

    /**
     * Checks whether the current request is the T&C acceptance page.
     */
    private function is_acceptance_page(): bool {
        $page_id = (int) BCM_Settings::get( 'tc_acceptance_page_id' );
        if ( $page_id > 0 && is_page( $page_id ) ) return true;

        // Virtual URL fallback — sanitize REQUEST_URI before string comparison
        $request_path = trailingslashit(
            wp_parse_url( esc_url_raw( wp_unslash( $_SERVER['REQUEST_URI'] ?? '/' ) ), PHP_URL_PATH ) ?? '/'
        );
        return ( strpos( $request_path, '/tc-acceptance/' ) !== false );
    }

    /**
     * Checks whether the current request is wp-login.php.
     */
    private function is_wp_login(): bool {
        // PHP_SELF can be spoofed on some server configs — use SCRIPT_FILENAME as primary
        $script = wp_basename( sanitize_text_field( wp_unslash( $_SERVER['SCRIPT_FILENAME'] ?? '' ) ) );
        if ( $script === 'wp-login.php' ) return true;
        // Fallback for reverse-proxy setups — sanitize PHP_SELF before string comparison
        $php_self = sanitize_text_field( wp_unslash( $_SERVER['PHP_SELF'] ?? '' ) );
        return ( strpos( $php_self, 'wp-login.php' ) !== false );
    }

    /* ──────────────────────────────────────────────────────────────
     * 2a. authenticate filter — block login BEFORE cookie is created
     * ────────────────────────────────────────────────────────────── */

    /**
     * Primary login blocker — fires on the `authenticate` filter BEFORE
     * WordPress creates any auth cookie.
     *
     * If the user has previously rejected T&C (meta = '0'), login is denied
     * immediately with a WP_Error. The user sees the standard WP login error.
     * Users who have never seen T&C (meta absent) are allowed through — they
     * will be intercepted by gate_access() on the next page load.
     *
     * @param  WP_User|WP_Error|null $user  Result from prior authenticate filters.
     * @return WP_User|WP_Error|null
     */
    public function block_login_if_rejected( $user ) {
        // Only act when enforcement is enabled and we have a valid user object
        $s = BCM_Settings::get();
        if ( empty( $s['tc_enforcement_enabled'] ) ) return $user;
        if ( ! ( $user instanceof \WP_User ) ) return $user;

        // Admins are never blocked
        if ( user_can( $user->ID, 'manage_options' ) ) return $user;

        // Only block users who have EXPLICITLY rejected (meta = '0').
        // Users who have never seen T&C (meta absent / '') are allowed through
        // and will be redirected to the acceptance page by gate_access().
        $meta_value = get_user_meta( $user->ID, self::META_KEY, true );
        if ( $meta_value !== '0' && $meta_value !== 0 ) return $user;

        $lang  = BCM_Settings::get( 'admin_lang' ) ?? 'es';
        $msg   = $lang === 'es'
            ? 'Has rechazado los Términos y Condiciones. Debes aceptarlos para iniciar sesión.'
            : 'You have rejected the Terms & Conditions. You must accept them to log in.';

        return new \WP_Error( 'tc_rejected', esc_html( $msg ) );
    }

    /* ──────────────────────────────────────────────────────────────
     * 2b. wp_login — post-login safety net (cookie already created)
     * ────────────────────────────────────────────────────────────── */

    /**
     * Fires after a successful WordPress login.
     * If the user hasn't accepted T&C, log them out and send to acceptance page.
     *
     * @param string   $user_login  Username
     * @param \WP_User $user        User object
     */
    public function check_on_login( string $user_login, \WP_User $user ): void {
        $s = BCM_Settings::get();
        if ( empty( $s['tc_enforcement_enabled'] ) ) return;

        // Admins are never blocked (prevent lockout)
        if ( user_can( $user->ID, 'manage_options' ) ) return;

        if ( self::user_accepted( $user->ID ) ) return;

        /*
         * User has not accepted (or has explicitly rejected) T&C.
         *
         * This hook fires AFTER wp_set_auth_cookie() has already added the
         * Set-Cookie header to the response. We must:
         *   1. Destroy ALL server-side session tokens so the cookie is worthless
         *      on every subsequent request, even if the browser stored it.
         *   2. Send Set-Cookie headers that expire the cookies in the browser.
         *   3. Prevent any caching of this response.
         *   4. Redirect to acceptance page.
         *
         * Order matters: destroy tokens BEFORE clearing cookies so there is
         * no window where the cookie exists but the session is still valid.
         */
        $acceptance_url = self::acceptance_page_url();

        // Step 1 — invalidate ALL session tokens for this user in the DB.
        // This makes any auth cookie the browser received completely useless.
        $sessions = \WP_Session_Tokens::get_instance( $user->ID );
        $sessions->destroy_all();

        // Step 2 — send expiry headers to clear cookies from the browser.
        wp_clear_auth_cookie();

        // Step 3 — prevent browser/proxy from caching this response.
        nocache_headers();

        // Step 4 — redirect to the T&C acceptance page.
        wp_safe_redirect( $acceptance_url );
        exit;
    }

    /* ──────────────────────────────────────────────────────────────
     * 3. AJAX: accept
     * ────────────────────────────────────────────────────────────── */

    /**
     * AJAX handler: user clicks "Accept" on the acceptance page.
     * Stores acceptance and returns a redirect URL to the intended destination.
     */
    public function ajax_accept_tc(): void {
        if ( ! check_ajax_referer( 'bcm_tc_nonce', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }

        $redirect = esc_url_raw( wp_unslash( $_POST['redirect_to'] ?? '' ) );
        if ( ! $redirect || ! wp_validate_redirect( $redirect, false ) ) {
            $redirect = home_url( '/' );
        }

        // Logged-in users: save acceptance to DB
        if ( is_user_logged_in() ) {
            $user_id = get_current_user_id();
            self::set_acceptance( $user_id, true );
        }
        // Guests: no DB write needed — the JS handles the cookie client-side

        wp_send_json_success( [ 'redirect' => $redirect ] );
    }

    /* ──────────────────────────────────────────────────────────────
     * 4. AJAX: reject — invalidate session and redirect
     * ────────────────────────────────────────────────────────────── */

    /**
     * AJAX handler: user clicks "Reject" on the acceptance page.
     *
     * Sequence:
     *   1. Mark T&C as rejected (0) in wp_usermeta.
     *   2. Destroy all active session tokens for the user (WP_Session_Tokens).
     *   3. Call wp_logout() to clear cookies.
     *   4. Return the redirect URL to the client (home + ?error=tc_rejected).
     */
    public function ajax_reject_tc(): void {
        if ( ! check_ajax_referer( 'bcm_tc_nonce', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }

        if ( ! is_user_logged_in() ) {
            // User not logged in — nothing to destroy, just redirect home.
            wp_send_json_success( [
                'redirect' => add_query_arg( 'error', self::REJECTED_PARAM, home_url( '/' ) ),
            ] );
            wp_die();
        }

        $user_id = get_current_user_id();

        /*
         * Rejection sequence — ORDER IS CRITICAL:
         *
         * 1. Persist rejection state FIRST so gate_access() blocks on next load.
         * 2. Destroy all server-side session tokens (makes any stored cookie useless).
         * 3. Clear auth cookies from the browser via Set-Cookie expiry headers.
         *    We do NOT call wp_logout() here because:
         *      a) wp_logout() fires do_action('wp_logout') which may generate output
         *         and corrupt the JSON response.
         *      b) In WP >= 5.6 wp_send_json_success() calls wp_die() internally,
         *         so any code after it (including wp_logout) never executes.
         *    Calling destroy_all() + wp_clear_auth_cookie() achieves the same result
         *    without the side effects.
         * 4. Send the JSON response with the redirect target.
         */

        // Step 1 — persist rejection.
        self::set_acceptance( $user_id, false );

        // Step 2 — kill ALL active session tokens in the database.
        // This ensures the auth cookie the browser holds is immediately worthless.
        $sessions = \WP_Session_Tokens::get_instance( $user_id );
        $sessions->destroy_all();

        // Step 3 — send Set-Cookie headers that expire the cookies in the browser.
        wp_clear_auth_cookie();

        // Prevent caching of this response.
        nocache_headers();

        // Step 4 — return redirect target to the JS client.
        $redirect = add_query_arg( 'error', self::REJECTED_PARAM, home_url( '/' ) );
        wp_send_json_success( [ 'redirect' => $redirect ] );
        wp_die();
    }

    /* ──────────────────────────────────────────────────────────────
     * 5. Login page notice
     * ────────────────────────────────────────────────────────────── */

    /**
     * Appends a notice to the login form when the user arrives with ?error=tc_rejected.
     *
     * @param string $message  Existing login_message content
     * @return string
     */
    public function login_notice( string $message ): string {
        $error = isset( $_GET['error'] ) ? sanitize_key( $_GET['error'] ) : '';
        if ( $error === self::REJECTED_PARAM ) {
            $s    = BCM_Settings::get();
            $lang = $s['admin_lang'] ?? 'es';

            $notice = $lang === 'es'
                ? 'Has rechazado los Términos y Condiciones. Tu sesión ha sido cerrada. Debes aceptarlos para acceder.'
                : 'You have rejected the Terms & Conditions. Your session has been closed. You must accept them to access the site.';

            $message .= '<div id="login_error" style="border-left:4px solid #dc3232;padding:10px 12px;margin:12px 0;background:#fff8f8;">'
                . '<strong>' . esc_html( $lang === 'es' ? 'Acceso denegado:' : 'Access denied:' ) . '</strong> '
                . esc_html( $notice )
                . '</div>';
        }
        return $message;
    }

    /* ──────────────────────────────────────────────────────────────
     * 6. Admin AJAX: reset T&C state for a user
     * ────────────────────────────────────────────────────────────── */

    /**
     * Admin-only AJAX: re-set a user's T&C meta so they see the acceptance page again.
     */
    public function ajax_admin_reset_tc(): void {
        // Use the dedicated unique nonce for this action — never share nonces across handlers.
        if ( ! check_ajax_referer( 'bcm_reset_tc_user', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }
        if ( ! current_user_can( 'manage_options' ) ) {
            wp_send_json_error( 'Unauthorized', 403 );
            wp_die();
        }

        $user_id = (int) wp_unslash( $_POST['user_id'] ?? 0 );
        if ( ! $user_id || ! get_userdata( $user_id ) ) {
            wp_send_json_error( 'Invalid user.' );
        }

        delete_user_meta( $user_id, self::META_KEY );
        wp_send_json_success( [ 'message' => "T&C status reset for user #{$user_id}." ] );
    }

    /* ──────────────────────────────────────────────────────────────
     * 7. Cron: purge rejected / inactive accounts
     * ────────────────────────────────────────────────────────────── */

    /**
     * Schedule the cleanup cron when the plugin is activated.
     * Runs daily.
     */
    public static function schedule_cron(): void {
        if ( ! wp_next_scheduled( self::CRON_HOOK ) ) {
            wp_schedule_event( time(), 'daily', self::CRON_HOOK );
        }
    }

    /**
     * Remove cron when plugin is deactivated.
     */
    public static function unschedule_cron(): void {
        $timestamp = wp_next_scheduled( self::CRON_HOOK );
        if ( $timestamp ) {
            wp_unschedule_event( $timestamp, self::CRON_HOOK );
        }
    }

    /**
     * Deletes user accounts that:
     *   - Have _tc_accepted = 0 (explicitly rejected), AND
     *   - Have not logged in for PURGE_DAYS days.
     *
     * Uses user_registered + last login meta (or simply registered date when
     * no login-date plugin is active) to determine staleness.
     *
     * NOTE: This is a destructive operation. It is disabled by default.
     *       Enable via BCM Settings → Compliance → "Auto-purge rejected accounts".
     */
    public static function purge_rejected_users(): void {
        $s = BCM_Settings::get();
        if ( empty( $s['tc_purge_rejected'] ) ) return;

        // Use WordPress timezone-aware date to respect site settings
        $cutoff = gmdate( 'Y-m-d H:i:s', time() - ( self::PURGE_DAYS * DAY_IN_SECONDS ) );

        // Find users with _tc_accepted = 0 registered more than PURGE_DAYS ago
        $args = [
            'meta_key'     => self::META_KEY,
            'meta_value'   => '0',
            'date_query'   => [
                [
                    'before'    => $cutoff,
                    'inclusive' => true,
                    'column'    => 'user_registered',
                ],
            ],
            'fields'       => 'ID',
            'number'       => 200,    // Process max 200 per run to avoid timeouts
        ];

        $user_ids = get_users( $args );

        if ( empty( $user_ids ) ) return;

        require_once ABSPATH . 'wp-admin/includes/user.php';

        $purged = 0;
        foreach ( $user_ids as $uid ) {
            // Never delete admins
            if ( user_can( (int) $uid, 'manage_options' ) ) continue;

            wp_delete_user( (int) $uid );
            $purged++;
        }

        // Log to error_log for audit trail (optional)
        if ( $purged > 0 ) {
            error_log( "[BCM v1.7.0] Purged {$purged} rejected/inactive user(s) older than " . self::PURGE_DAYS . " days." );
        }
    }

    /* ──────────────────────────────────────────────────────────────
     * 8. Shortcode: [bcm_tc_acceptance]
     * Renders the T&C acceptance / rejection form.
     * ────────────────────────────────────────────────────────────── */

    /**
     * Registers the [bcm_tc_acceptance] shortcode.
     * Call this method from bcm_init().
     */
    public static function register_shortcode(): void {
        add_shortcode( 'bcm_tc_acceptance', [ __CLASS__, 'render_acceptance_form' ] );
    }

    /**
     * Outputs the T&C acceptance form HTML.
     * Handles both logged-in users (full form) and guests (redirect to login).
     *
     * @param array $atts  Shortcode attributes (unused for now)
     * @return string
     */
    public static function render_acceptance_form( array $atts = [] ): string {
        $s     = BCM_Settings::get();
        $lang  = $s['admin_lang'] ?? 'es';
        $is_es = ( $lang === 'es' );

        $tos_url     = $s['tos_url']            ?? '';
        $privacy_url = $s['privacy_policy_url'] ?? '';

        // Strings
        $title       = $is_es ? 'Términos y Condiciones'  : 'Terms & Conditions';
        $intro       = $is_es ? 'Para continuar usando el sitio debes aceptar los Términos y Condiciones.'
                              : 'To continue using the site you must accept the Terms & Conditions.';
        $tos_link    = $is_es ? 'Leer los Términos y Condiciones'  : 'Read the Terms & Conditions';
        $privacy_link= $is_es ? 'Leer la Política de Privacidad'   : 'Read the Privacy Policy';
        $accept_btn  = $is_es ? 'Aceptar y Continuar'              : 'Accept & Continue';
        $reject_btn  = $is_es ? 'Rechazar'                         : 'Decline';
        $loading     = $is_es ? 'Procesando…'                      : 'Processing…';
        $check_label = $is_es ? 'He leído y acepto los'            : 'I have read and accept the';
        $and_text    = $is_es ? 'y la'                             : 'and the';
        $check_error = $is_es ? 'Debes marcar la casilla para aceptar.' : 'You must check the box to accept.';
        $already_txt = $is_es ? '✓ Ya aceptaste los Términos y Condiciones.' : '✓ You have already accepted the Terms & Conditions.';
        $reject_msg  = $is_es ? 'Debes aceptar los Términos y Condiciones para continuar.' : 'You must accept the Terms & Conditions to continue.';

        // Detect mode
        $is_logged_in = is_user_logged_in();
        $user_id      = $is_logged_in ? get_current_user_id() : 0;
        $accepted     = $is_logged_in ? self::user_accepted( $user_id ) : false;

        // For logged-in users, use the TC nonce; for guests use a public nonce
        $nonce       = wp_create_nonce( 'bcm_tc_nonce' );
        $redirect_to = home_url( '/' );

        // Gather enabled categories for cookie consent
        $categories = array_keys( array_filter(
            $s['categories'] ?? [],
            fn( $c ) => ! empty( $c['enabled'] )
        ) );

        // Enqueue assets once
        static $assets_enqueued = false;
        if ( ! $assets_enqueued ) {
            $assets_enqueued = true;

            wp_register_style( 'bcm-tc-form', false );
            wp_enqueue_style( 'bcm-tc-form' );
            wp_add_inline_style( 'bcm-tc-form',
                '.bcm-tc-wrap{max-width:560px;margin:40px auto;padding:32px 28px;background:#fff;border:1px solid #ddd;border-radius:8px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
                .bcm-tc-title{margin-top:0;font-size:1.4em;}
                .bcm-tc-intro{color:#444;}
                .bcm-tc-notice--ok{color:#2e7d32;background:#f1f8f1;padding:10px 14px;border-left:4px solid #2e7d32;border-radius:4px;}
                .bcm-tc-check-row{display:flex;align-items:flex-start;gap:10px;margin:18px 0;}
                .bcm-tc-check-row input[type=checkbox]{margin-top:3px;flex-shrink:0;width:16px;height:16px;cursor:pointer;}
                .bcm-tc-check-row label{font-size:.92em;color:#333;cursor:pointer;line-height:1.5;}
                .bcm-tc-check-row a{color:#1a73e8;}
                .bcm-tc-check-error{display:block;margin-top:6px;color:#c62828;font-size:.85em;}
                .bcm-tc-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px;}
                .bcm-tc-btn{padding:11px 22px;border:none;border-radius:5px;cursor:pointer;font-size:.95em;font-weight:600;transition:opacity .2s;}
                .bcm-tc-btn:disabled{opacity:.6;cursor:not-allowed;}
                .bcm-tc-btn--accept{background:#1a73e8;color:#fff;}
                .bcm-tc-btn--accept:hover:not(:disabled){background:#1558b0;}
                .bcm-tc-btn--reject{background:#f5f5f5;color:#c62828;border:1px solid #e0e0e0;}
                .bcm-tc-btn--reject:hover:not(:disabled){background:#fce4e4;}
                .bcm-tc-message{padding:10px 14px;border-radius:4px;background:#fff3e0;color:#e65100;border-left:4px solid #e65100;margin-top:14px;}
                .bcm-tc-message--ok{background:#f1f8f1;color:#2e7d32;border-left-color:#2e7d32;}'
            );

            wp_register_script( 'bcm-tc-form', false, [], false, true );
            wp_enqueue_script( 'bcm-tc-form' );
            wp_add_inline_script( 'bcm-tc-form', self::tc_form_js( admin_url( 'admin-ajax.php' ) ) );
        }

        // Pass config for cookie consent sync
        wp_localize_script( 'bcm-tc-form', 'bcmTcFormConfig', [
            'ajaxUrl'      => admin_url( 'admin-ajax.php' ),
            'cookieName'   => 'bcm_consent',
            'expiry'       => (int) ( $s['consent_expiry'] ?? 365 ),
            'categories'   => $categories,
            'consentNonce' => wp_create_nonce( 'bcm_consent' ),
            'isLoggedIn'   => $is_logged_in,
            'acceptMsg'    => $is_es ? '✓ ¡T&C aceptados! El panel de preferencias ya refleja tu elección.' : '✓ T&C accepted! Your preferences panel has been updated.',
            'rejectMsg'    => $reject_msg,
        ] );

        ob_start();
        ?>
        <div id="bcm-tc-wrap" class="bcm-tc-wrap">
            <h2 class="bcm-tc-title"><?php echo esc_html( $title ); ?></h2>

            <?php if ( $accepted ) : ?>
                <p class="bcm-tc-notice bcm-tc-notice--ok"><?php echo esc_html( $already_txt ); ?></p>
            <?php else : ?>
                <p class="bcm-tc-intro"><?php echo esc_html( $intro ); ?></p>

                <?php if ( $tos_url ) : ?>
                    <p><a href="<?php echo esc_url( $tos_url ); ?>" target="_blank" rel="noopener noreferrer">
                        <?php echo esc_html( $tos_link ); ?>
                    </a></p>
                <?php endif; ?>

                <?php if ( $privacy_url ) : ?>
                    <p><a href="<?php echo esc_url( $privacy_url ); ?>" target="_blank" rel="noopener noreferrer">
                        <?php echo esc_html( $privacy_link ); ?>
                    </a></p>
                <?php endif; ?>

                <div class="bcm-tc-check-row">
                    <input type="checkbox" id="bcm-tc-chk" name="bcm_tc_accept">
                    <label for="bcm-tc-chk">
                        <?php echo esc_html( $check_label ); ?>
                        <?php if ( $tos_url ) : ?>
                            <a href="<?php echo esc_url( $tos_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( $tos_link ); ?></a>
                        <?php else : ?><?php echo esc_html( $tos_link ); ?><?php endif; ?>
                        <?php if ( $privacy_url ) : ?>
                            <?php echo ' ' . esc_html( $and_text ) . ' '; ?>
                            <a href="<?php echo esc_url( $privacy_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( $privacy_link ); ?></a>
                        <?php endif; ?>
                    </label>
                </div>
                <span id="bcm-tc-chk-error" class="bcm-tc-check-error" style="display:none;"><?php echo esc_html( $check_error ); ?></span>

                <div class="bcm-tc-actions">
                    <button id="bcm-tc-accept-btn" class="bcm-tc-btn bcm-tc-btn--accept"
                            data-nonce="<?php echo esc_attr( $nonce ); ?>"
                            data-redirect="<?php echo esc_attr( $redirect_to ); ?>"
                            data-loading="<?php echo esc_attr( $loading ); ?>">
                        <?php echo esc_html( $accept_btn ); ?>
                    </button>
                    <button id="bcm-tc-reject-btn" class="bcm-tc-btn bcm-tc-btn--reject"
                            data-nonce="<?php echo esc_attr( $nonce ); ?>"
                            data-loading="<?php echo esc_attr( $loading ); ?>">
                        <?php echo esc_html( $reject_btn ); ?>
                    </button>
                </div>

                <p id="bcm-tc-message" class="bcm-tc-message" style="display:none;"></p>
            <?php endif; ?>
        </div>
        <?php
        return ob_get_clean();
    }

    /**
     * JS inline for [bcm_tc_acceptance] — handles both logged-in and guest users.
     * On accept: saves TC in DB (if logged in) AND sets the bcm_consent cookie
     * so the "Personalizar preferencias" panel reflects the acceptance.
     */
    private static function tc_form_js( string $ajax_url ): string {
        return '(function(){
"use strict";
var ajaxUrl=' . json_encode( $ajax_url ) . ';

function setCookie(name,value,days){
    var d=new Date();d.setTime(d.getTime()+days*864e5);
    var secure=(location.protocol==="https:")? ";Secure":"";
    document.cookie=name+"="+encodeURIComponent(value)+";expires="+d.toUTCString()+";path=/;SameSite=Lax"+secure;
}
function genId(){
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g,function(c){
        var r=Math.random()*16|0;return(c==="x"?r:(r&0x3|0x8)).toString(16);
    });
}

document.addEventListener("DOMContentLoaded",function(){
    var cfg=window.bcmTcFormConfig||{};
    var acceptBtn=document.getElementById("bcm-tc-accept-btn");
    var rejectBtn=document.getElementById("bcm-tc-reject-btn");
    var chk=document.getElementById("bcm-tc-chk");
    var chkErr=document.getElementById("bcm-tc-chk-error");
    var msgEl=document.getElementById("bcm-tc-message");

    if(!acceptBtn)return;

    if(chk)chk.addEventListener("change",function(){if(chk.checked&&chkErr)chkErr.style.display="none";});

    function setLoading(b){b.disabled=true;b._orig=b.textContent;b.textContent=b.dataset.loading||"...";}
    function setDone(b){b.disabled=false;if(b._orig)b.textContent=b._orig;}
    function showMsg(t,ok){if(msgEl){msgEl.textContent=t;msgEl.style.display="block";msgEl.className="bcm-tc-message"+(ok?" bcm-tc-message--ok":"");}}

    /* Sync cookie de consentimiento con el banner de preferencias */
    function saveCookieConsent(){
        if(!cfg.cookieName)return;
        var id=genId();
        var cats=cfg.categories||[];
        var data={consent_id:id,status:"accepted",categories:cats,regulation:"GDPR"};
        setCookie(cfg.cookieName,JSON.stringify(data),cfg.expiry||365);
        /* Registrar en servidor */
        if(cfg.consentNonce){
            var fd2=new FormData();
            fd2.append("action","bcm_record_consent");
            fd2.append("nonce",cfg.consentNonce);
            fd2.append("consent_id",id);
            fd2.append("status","accepted");
            fd2.append("categories",JSON.stringify(cats));
            fd2.append("regulation","GDPR");
            fetch(cfg.ajaxUrl,{method:"POST",body:fd2});
        }
        /* Ocultar el banner de cookies si estaba visible */
        var banner=document.getElementById("bcm-banner");
        if(banner){banner.style.display="none";}
        /* Disparar evento para que el banner actualice su estado interno */
        document.dispatchEvent(new CustomEvent("bcm:consent_saved",{detail:{status:"accepted",categories:cats}}));
    }

    acceptBtn.addEventListener("click",function(){
        if(chk&&!chk.checked){if(chkErr)chkErr.style.display="block";chk.focus();return;}
        setLoading(acceptBtn);if(rejectBtn)rejectBtn.disabled=true;
        var fd=new FormData();
        fd.append("action","bcm_accept_tc");
        fd.append("nonce",acceptBtn.dataset.nonce);
        fd.append("redirect_to",acceptBtn.dataset.redirect);
        fetch(ajaxUrl,{method:"POST",body:fd})
            .then(function(r){return r.json();})
            .then(function(data){
                setDone(acceptBtn);if(rejectBtn)rejectBtn.disabled=false;
                if(data.success||(!cfg.isLoggedIn)){
                    /* Siempre setear la cookie, sea logueado o no */
                    saveCookieConsent();
                    if(cfg.isLoggedIn){
                        window.location.href=data.data&&data.data.redirect?data.data.redirect:acceptBtn.dataset.redirect;
                    } else {
                        /* Visitante: ocultar form, mostrar confirmación */
                        var wrap=document.getElementById("bcm-tc-wrap");
                        if(wrap){
                            var intro=wrap.querySelector(".bcm-tc-intro");
                            var checkRow=wrap.querySelector(".bcm-tc-check-row");
                            var actions=wrap.querySelector(".bcm-tc-actions");
                            if(intro)intro.style.display="none";
                            if(checkRow)checkRow.style.display="none";
                            if(actions)actions.style.display="none";
                            if(chkErr)chkErr.style.display="none";
                        }
                        showMsg(cfg.acceptMsg||"✓ ¡Aceptado!",true);
                    }
                } else {
                    showMsg((data.data&&data.data.message)||"Error.");
                }
            })
            .catch(function(){setDone(acceptBtn);if(rejectBtn)rejectBtn.disabled=false;showMsg("Error de conexión.");});
    });

    if(rejectBtn){
        rejectBtn.addEventListener("click",function(){
            if(!cfg.isLoggedIn){
                showMsg(cfg.rejectMsg||"Debes aceptar los T&C para continuar.",false);
                return;
            }
            setLoading(rejectBtn);acceptBtn.disabled=true;
            var fd=new FormData();
            fd.append("action","bcm_reject_tc");
            fd.append("nonce",rejectBtn.dataset.nonce);
            fetch(ajaxUrl,{method:"POST",body:fd})
                .then(function(r){return r.json();})
                .then(function(data){window.location.href=(data.success&&data.data&&data.data.redirect)?data.data.redirect:"/?error=tc_rejected";})
                .catch(function(){window.location.href="/?error=tc_rejected";});
        });
    }
});
})();';
    }
}
