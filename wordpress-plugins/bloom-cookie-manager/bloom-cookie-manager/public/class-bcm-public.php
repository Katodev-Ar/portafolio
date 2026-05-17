<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Public {

    public function __construct() {
        add_action( 'wp_enqueue_scripts',            [ $this, 'enqueue' ] );
        add_action( 'wp_footer',                     [ $this, 'render_banner' ], 100 );
        add_action( 'wp_ajax_nopriv_bcm_record_consent', [ $this, 'ajax_record_consent' ] );
        add_action( 'wp_ajax_bcm_record_consent',        [ $this, 'ajax_record_consent' ] );

        if ( BCM_Settings::get( 'auto_block' ) ) {
            add_filter( 'script_loader_tag', [ $this, 'maybe_block_script_tag' ], 10, 3 );
        }
    }

    /* ── Enqueue ── */
    public function enqueue(): void {
        $s = BCM_Settings::get();
        if ( ! $s['banner_enabled'] ) return;

        wp_enqueue_style(  'bcm-public', BCM_PLUGIN_URL . 'public/css/banner.css', [], BCM_VERSION );
        wp_enqueue_script( 'bcm-public', BCM_PLUGIN_URL . 'public/js/banner.js',   [], BCM_VERSION, true );

        /* v1.4.0: Resolución de regulación por geo-detección */
        $regulation = $this->resolve_regulation( $s );

        $lang    = $s['admin_lang'] ?? 'es';
        $l       = BCM_Settings::lang_strings( $lang );

        // T&C enforcement — only relevant for logged-in users
        $tc_enforcement_on = ! empty( $s['tc_enforcement_enabled'] );
        $tc_enabled        = $tc_enforcement_on && is_user_logged_in();
        $tc_accepted       = $tc_enabled ? BCM_TC_Manager::user_accepted( get_current_user_id() ) : true;
        $tc_page_url       = $tc_enabled ? BCM_TC_Manager::acceptance_page_url() : '';
        // FIX v1.9.0: always provide tcNonce for logged-in users so that
        // "Rechazar todo" can trigger bcm_reject_tc (logout) regardless of
        // whether tc_enforcement_enabled is on. Without this, the JS guard
        // `if (!cfg.tcNonce) return false` prevents logout from ever firing.
        $tc_nonce = is_user_logged_in() ? wp_create_nonce( 'bcm_tc_nonce' ) : '';

        wp_localize_script( 'bcm-public', 'bcmConfig', [
            'ajaxUrl'          => admin_url( 'admin-ajax.php' ),
            'nonce'            => wp_create_nonce( 'bcm_consent' ),
            'expiry'           => (int)  $s['consent_expiry'],
            'autoBlock'        => (bool) $s['auto_block'],
            'categories'       => array_keys( array_filter( $s['categories'], fn($c) => $c['enabled'] ) ),
            'gcm'              => (bool) $s['gcm_enabled'],
            'regulation'       => $regulation,
            'privacyPolicyUrl' => esc_url( $s['privacy_policy_url'] ?? '' ),
            'showTos'          => (bool) ( $s['show_tos_checkbox'] ?? true ),
            'withdrawal'       => (bool) ( $s['withdrawal_enabled'] ?? true ),
            'lang'             => $lang,
            // T&C enforcement state for logged-in users
            'tcEnforcement'    => $tc_enabled,
            'tcAccepted'       => $tc_accepted,
            'tcNonce'          => $tc_nonce,
            'tcPageUrl'        => esc_url( $tc_page_url ),
            'strings'          => [
                'ccpaNote'           => $lang === 'es'
                    ? 'Los residentes de California tienen derecho a rechazar la venta de sus datos personales.'
                    : 'Residents of California have the right to opt out of the sale of personal data.',
                'blockedContent'     => $lang === 'es'
                    ? 'Este contenido requiere cookies de <strong>%cat%</strong>. <a href="#" class="bcm-unblock-link" data-cat="%cat%">Aceptar para cargar</a>'
                    : 'This content requires <strong>%cat%</strong> cookies. <a href="#" class="bcm-unblock-link" data-cat="%cat%">Accept to load</a>',
                'withdrawLink'       => esc_html( $l['withdraw_link'] ?? ( $lang === 'es' ? 'Retirar consentimiento' : 'Withdraw consent' ) ),
                'tcRequiredError'    => $lang === 'es'
                    ? 'Debes aceptar los Términos y Condiciones para continuar.'
                    : 'You must accept the Terms & Conditions to continue.',
            ],
        ] );
    }

    /**
     * v1.4.0 — Resolver regulación aplicable al visitante.
     *
     * Si geo_detection está activa, detecta por IP.
     * Si la detección devuelve 'NONE' (país sin regulación específica),
     * usa el valor de geo_fallback del admin.
     * Si geo_detection está desactivada, usa el valor manual del admin.
     */
    private function resolve_regulation( array $s ): string {
        if ( ! empty( $s['geo_detection'] ) ) {
            $detected = BCM_Geo::detect();
            if ( $detected !== 'NONE' ) return $detected;
            return $s['geo_fallback'] ?? 'GDPR';
        }
        return $s['regulation'] ?? 'GDPR';
    }

    /* ── Render banner ── */
    public function render_banner(): void {
        $s = BCM_Settings::get();
        if ( ! $s['banner_enabled'] ) return;
        $cats = array_filter( $s['categories'], fn($c) => $c['enabled'] );
        include BCM_PLUGIN_DIR . 'public/views/banner.php';
    }

    /* ── v1.3.0+: auto-block de scripts registrados por WordPress ── */
    public function maybe_block_script_tag( string $tag, string $handle, string $src ): string {
        global $wp_scripts;

        $category = '';

        if ( isset( $wp_scripts->registered[ $handle ] ) ) {
            $category = $wp_scripts->registered[ $handle ]->extra['bcm_category'] ?? '';
        }

        /* FIX v1.4.1: detectar por handle primero si no había categoría asignada */
        if ( $category === '' ) {
            $category = $this->detect_script_category_by_handle( $handle );
        }

        $category = (string) apply_filters( 'bcm_script_category', $category, $handle, $src );

        if ( $category === '' ) {
            $category = $this->detect_script_category_by_url( $src );
        }

        if ( $category === '' || $category === 'necessary' ) return $tag;

        $tag = str_replace( " type='text/javascript'", '', $tag );
        $tag = str_replace( ' type="text/javascript"', '', $tag );
        $tag = str_replace( " src='", " type='text/plain' data-bcm-cat='" . esc_attr( $category ) . "' data-src='", $tag );
        $tag = str_replace( ' src="', ' type="text/plain" data-bcm-cat="' . esc_attr( $category ) . '" data-src="', $tag );

        return $tag;
    }

    private function detect_script_category_by_url( string $src ): string {
        $patterns = [
            /* Analytics — Google */
            'google-analytics.com'              => 'analytics',
            'googletagmanager.com'              => 'analytics',
            'googlesitekit'                     => 'analytics',   // Site Kit by Google (local handle)
            'sitekit'                           => 'analytics',   // Site Kit asset slug
            'googleapis.com/analytics'          => 'analytics',
            'analytics.google.com'              => 'analytics',
            /* Analytics — otros */
            'static.hotjar.com'                 => 'analytics',
            'cdn.segment.com'                   => 'analytics',
            'js.hs-scripts.com'                 => 'analytics',
            'cdn.amplitude.com'                 => 'analytics',
            'browser.sentry-cdn.com'            => 'analytics',
            'clarity.ms'                        => 'analytics',   // Microsoft Clarity
            'cdn.plausible.io'                  => 'analytics',
            'matomo'                            => 'analytics',
            'piwik'                             => 'analytics',
            /* Advertisement */
            'connect.facebook.net'              => 'advertisement',
            'ads.google.com'                    => 'advertisement',
            'static.ads-twitter.com'            => 'advertisement',
            'snap.licdn.com'                    => 'advertisement',
            'platform.twitter.com/widgets'      => 'advertisement',
            'pagead2.googlesyndication.com'     => 'advertisement',
            'adsbygoogle'                       => 'advertisement',
            'doubleclick.net'                   => 'advertisement',
            'infolinks'                         => 'advertisement',  // Infolinks (detectado en el sitio)
            /* Functional */
            'widget.intercom.io'                => 'functional',
            'js.stripe.com'                     => 'functional',
            'maps.googleapis.com'               => 'functional',
            'recaptcha'                         => 'functional',
            /* Performance */
            'cloudflare'                        => 'performance',
        ];

        foreach ( $patterns as $pattern => $cat ) {
            if ( stripos( $src, $pattern ) !== false ) return $cat;
        }
        return '';
    }

    /**
     * FIX v1.4.1 — Detectar categoría también por handle de WordPress.
     * Site Kit registra sus scripts con handles que contienen 'googlesitekit'.
     */
    private function detect_script_category_by_handle( string $handle ): string {
        $handle_patterns = [
            'googlesitekit'  => 'analytics',
            'google-site-kit'=> 'analytics',
            'gtag'           => 'analytics',
            'google-tag'     => 'analytics',
            'google_tag'     => 'analytics',
            'infolinks'      => 'advertisement',
            'adsbygoogle'    => 'advertisement',
            'facebook-pixel' => 'advertisement',
        ];
        foreach ( $handle_patterns as $pattern => $cat ) {
            if ( stripos( $handle, $pattern ) !== false ) return $cat;
        }
        return '';
    }

    /* ── AJAX: registrar consentimiento ── */
    public function ajax_record_consent(): void {
        if ( ! check_ajax_referer( 'bcm_consent', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Invalid nonce.' ], 403 );
            wp_die();
        }

        // ── Rate limiting ────────────────────────────────────────────────────
        // Allow max 5 consent submissions per IP per 60 seconds.
        // Uses a transient keyed by a hashed IP to avoid storing raw IPs in
        // option names, and to prevent cache-key enumeration.
        $raw_ip      = sanitize_text_field( wp_unslash(
            $_SERVER['HTTP_CF_CONNECTING_IP']
            ?? $_SERVER['HTTP_X_FORWARDED_FOR']
            ?? $_SERVER['REMOTE_ADDR']
            ?? ''
        ) );
        $ip          = trim( explode( ',', $raw_ip )[0] );
        $rate_key    = 'bcm_rl_' . substr( md5( $ip . wp_salt( 'nonce' ) ), 0, 24 );
        $rate_limit  = 5;   // max submissions
        $rate_window = 60;  // seconds

        $hits = (int) get_transient( $rate_key );
        if ( $hits >= $rate_limit ) {
            wp_send_json_error( [ 'message' => 'Too many requests. Please wait before submitting again.' ], 429 );
            wp_die();
        }
        // Increment counter; set TTL only on first hit so the window is fixed
        if ( $hits === 0 ) {
            set_transient( $rate_key, 1, $rate_window );
        } else {
            // Preserve original TTL — get_transient returns the value so we just overwrite the count.
            // We must re-set with the remaining TTL; use a second transient to track expiry time.
            $expiry_key = $rate_key . '_exp';
            $expires_at = (int) get_transient( $expiry_key );
            $remaining  = $expires_at > time() ? $expires_at - time() : $rate_window;
            set_transient( $rate_key, $hits + 1, $remaining );
        }
        set_transient( $rate_key . '_exp', time() + $rate_window, $rate_window );

        // ── consent_id — validate UUID v4 format ────────────────────────────
        // The client supplies its own consent_id. We accept it only if it
        // matches the RFC 4122 UUID v4 pattern; otherwise we generate a fresh one
        // server-side. This prevents arbitrary strings from being stored in the DB.
        $raw_consent_id = sanitize_text_field( wp_unslash( $_POST['consent_id'] ?? '' ) );
        $uuid_v4_regex  = '/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i';
        $consent_id     = ( $raw_consent_id !== '' && preg_match( $uuid_v4_regex, $raw_consent_id ) )
            ? strtolower( $raw_consent_id )
            : wp_generate_uuid4();

        // ── status — whitelist ───────────────────────────────────────────────
        // Only the three known consent states are accepted. Any other value is
        // rejected with a 400 rather than silently stored in the database.
        $allowed_statuses = [ 'accepted', 'rejected', 'custom' ];
        $raw_status       = sanitize_text_field( wp_unslash( $_POST['status'] ?? 'accepted' ) );
        if ( ! in_array( $raw_status, $allowed_statuses, true ) ) {
            wp_send_json_error( [ 'message' => 'Invalid consent status.' ], 400 );
            wp_die();
        }
        $status = $raw_status;

        // ── regulation — whitelist ───────────────────────────────────────────
        // Constrain to the four regulations the plugin understands. Anything
        // else is rejected rather than persisted with an unknown value.
        $allowed_regulations = [ 'GDPR', 'CCPA', 'LGPD', 'NONE' ];
        $raw_regulation      = strtoupper( sanitize_text_field( wp_unslash( $_POST['regulation'] ?? 'GDPR' ) ) );
        if ( ! in_array( $raw_regulation, $allowed_regulations, true ) ) {
            wp_send_json_error( [ 'message' => 'Invalid regulation value.' ], 400 );
            wp_die();
        }
        $regulation = $raw_regulation;

        // ── categories — decode JSON, sanitize, whitelist ───────────────────
        // json_decode output must never be trusted as safe — sanitize before use.
        $allowed_cats = [ 'necessary', 'functional', 'analytics', 'performance', 'advertisement' ];
        $raw_decoded  = isset( $_POST['categories'] )
            ? json_decode( wp_unslash( $_POST['categories'] ), true )
            : null;
        // Ensure we have a flat list of strings; reject any non-array / nested payloads.
        $raw_cats = ( is_array( $raw_decoded ) && ! empty( $raw_decoded ) )
            ? array_filter( $raw_decoded, 'is_string' )
            : [];
        // Sanitize each element as a key-style string, then whitelist against known slugs.
        $categories = array_values(
            array_filter(
                array_map(
                    static function ( $cat ) {
                        return sanitize_key( (string) $cat );
                    },
                    $raw_cats
                ),
                static fn( string $cat ) => in_array( $cat, $allowed_cats, true )
            )
        );

        BCM_Consent_Log::record( $consent_id, $status, $categories, $regulation );
        wp_send_json_success();
    }
}
