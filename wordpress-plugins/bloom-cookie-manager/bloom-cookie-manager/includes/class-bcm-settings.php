<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Settings {

    /**
     * String maps for banner UI — EN and ES.
     */
    public static function lang_strings( string $lang = 'es' ): array {
        $strings = [
            'es' => [
                'banner_title'       => 'Valoramos tu privacidad',
                'banner_description' => 'Usamos cookies para mejorar tu experiencia de navegación, mostrar anuncios o contenido personalizado y analizar nuestro tráfico. Al hacer clic en "Aceptar todo", aceptas el uso de cookies.',
                'accept_btn_text'    => 'Aceptar todo',
                'reject_btn_text'    => 'Rechazar todo',
                'customize_btn_text' => 'Personalizar',
                'cat_necessary'      => 'Necesarias',
                'cat_functional'     => 'Funcionales',
                'cat_analytics'      => 'Analíticas',
                'cat_performance'    => 'Rendimiento',
                'cat_advertisement'  => 'Publicidad',
                'tos_label'          => 'Acepto los',
                'tos_and'            => 'y la',
                'tos_error'          => 'Debes aceptar los Términos y Condiciones para continuar.',
                'privacy_link_text'  => 'Política de Privacidad',
                'tos_link_text'      => 'Términos y Condiciones',
                'pref_title'         => 'Personalizar preferencias',
                'pref_intro'         => 'Usamos cookies para mejorar tu experiencia. Elige qué cookies aceptas a continuación.',
                'pref_save'          => 'Guardar preferencias',
                'cookie_settings'    => 'Configuración de cookies',
                'withdraw_link'      => 'Retirar consentimiento',
                'desc_necessary'     => 'Necesarias para el funcionamiento básico del sitio. No se pueden desactivar.',
                'desc_functional'    => 'Recuerdan tus preferencias y configuración.',
                'desc_analytics'     => 'Nos ayudan a entender cómo usas el sitio.',
                'desc_performance'   => 'Mejoran los tiempos de carga y el rendimiento.',
                'desc_advertisement' => 'Se usan para mostrarte publicidad relevante.',
            ],
            'en' => [
                'banner_title'       => 'We value your privacy',
                'banner_description' => 'We use cookies to improve your browsing experience, show personalised ads or content, and analyse our traffic. By clicking "Accept all" you consent to our use of cookies.',
                'accept_btn_text'    => 'Accept all',
                'reject_btn_text'    => 'Reject all',
                'customize_btn_text' => 'Customize',
                'cat_necessary'      => 'Necessary',
                'cat_functional'     => 'Functional',
                'cat_analytics'      => 'Analytics',
                'cat_performance'    => 'Performance',
                'cat_advertisement'  => 'Advertising',
                'tos_label'          => 'I accept the',
                'tos_and'            => 'and the',
                'tos_error'          => 'You must accept the Terms and Conditions to continue.',
                'privacy_link_text'  => 'Privacy Policy',
                'tos_link_text'      => 'Terms and Conditions',
                'pref_title'         => 'Customize preferences',
                'pref_intro'         => 'We use cookies to enhance your browsing experience. Choose which cookies you consent to below.',
                'pref_save'          => 'Save preferences',
                'cookie_settings'    => 'Cookie settings',
                'withdraw_link'      => 'Withdraw consent',
                'desc_necessary'     => 'Required for basic site functionality. Cannot be disabled.',
                'desc_functional'    => 'Remember your preferences and settings.',
                'desc_analytics'     => 'Help us understand how you use our site.',
                'desc_performance'   => 'Improve loading speeds and performance.',
                'desc_advertisement' => 'Used to show you relevant advertisements.',
            ],
        ];
        return $strings[ $lang ] ?? $strings['es'];
    }

    public static function defaults(): array {
        $l = self::lang_strings('es');
        return [
            /* v1.6.0 — Admin / banner language */
            'admin_lang'        => 'es',   // 'es' | 'en'

            /* Banner */
            'banner_enabled'    => true,
            'banner_position'   => 'bottom',
            'banner_layout'     => 'banner',
            'banner_title'      => $l['banner_title'],
            'banner_description'=> $l['banner_description'],
            'accept_btn_text'   => $l['accept_btn_text'],
            'reject_btn_text'   => $l['reject_btn_text'],
            'customize_btn_text'=> $l['customize_btn_text'],
            'show_reject_btn'   => true,
            'show_customize_btn'=> true,

            /* Colors */
            'primary_color'     => '#e91e8c',
            'bg_color'          => '#111111',
            'text_color'        => '#e0e0e0',
            'btn_accept_bg'     => '#e91e8c',
            'btn_reject_bg'     => '#1e1e1e',
            'btn_reject_text'   => '#aaaaaa',

            /* Cookie lifetime */
            'consent_expiry'    => 365,

            /* Regulation */
            'regulation'        => 'GDPR',

            /* Categories */
            'categories'        => [
                'necessary'     => [ 'enabled' => true,  'locked' => true,  'label' => $l['cat_necessary']     ],
                'functional'    => [ 'enabled' => true,  'locked' => false, 'label' => $l['cat_functional']    ],
                'analytics'     => [ 'enabled' => true,  'locked' => false, 'label' => $l['cat_analytics']     ],
                'performance'   => [ 'enabled' => true,  'locked' => false, 'label' => $l['cat_performance']   ],
                'advertisement' => [ 'enabled' => true,  'locked' => false, 'label' => $l['cat_advertisement'] ],
            ],

            /* Auto-blocking */
            'auto_block'        => true,

            /* GCM */
            'gcm_enabled'       => false,

            /* v1.4.0 — Geo detection */
            'geo_detection'     => true,
            'geo_fallback'      => 'GDPR',

            /* v1.4.0 — Headless scanner */
            'browseless_endpoint' => 'https://chrome.browserless.io',
            'browseless_token'    => '',

            /* v1.4.0 — Cookie policy page */
            'auto_policy_page'  => false,

            /* v1.5.0 — Compliance */
            'privacy_policy_url' => '',
            'ip_anonymize'       => true,   // FIX v1.6.0: default ON — GDPR Art. 5.1.e
            'ip_hash'            => false,  // FIX v2.0.5: hash SHA-256 irreversible (más fuerte que anonimizar)

            /* v1.5.1 — T&C checkbox */
            'show_tos_checkbox'  => true,   // FIX v1.6.0: default ON — required for sites with purchases
            'tos_url'            => '',

            /* v1.6.0 — Withdrawal button */
            'withdrawal_enabled' => true,   // GDPR Art. 7(3) — must be as easy to withdraw as to give

            /* v1.7.0 — T&C Enforcement */
            'tc_enforcement_enabled' => false, // Master switch — enable to force T&C acceptance
            'tc_acceptance_page_id'  => 0,     // Page ID for the acceptance page ([bcm_tc_acceptance] shortcode)
            'tc_purge_rejected'      => false, // Auto-delete rejected/inactive accounts after 30 days

            /* v2.1.0 — Login/Register overlay URLs */
            'ltc_urls'               => '', // Extra URLs where the T&C overlay should appear (comma-separated)
        ];
    }

    public static function get( string $key = '' ) {
        $settings = get_option( 'bcm_settings', self::defaults() );
        $settings = array_merge( self::defaults(), $settings );
        if ( $key === '' ) return $settings;
        return $settings[ $key ] ?? null;
    }

    /**
     * Sanitizes every known settings key before persisting.
     * Called internally by save() — never store raw POST data directly.
     *
     * @param  array $data  Raw unsanitized settings payload
     * @return array        Sanitized payload
     */
    private static function sanitize( array $data ): array {
        $clean = [];

        /* ── Strings / text ── */
        $text_fields = [
            'admin_lang', 'banner_position', 'banner_layout',
            'banner_title', 'accept_btn_text', 'reject_btn_text',
            'customize_btn_text', 'regulation', 'geo_fallback',
            'browseless_endpoint', 'browseless_token',
        ];
        foreach ( $text_fields as $k ) {
            if ( array_key_exists( $k, $data ) ) {
                $clean[ $k ] = sanitize_text_field( $data[ $k ] );
            }
        }

        /* ── Textarea (allows newlines) ── */
        if ( array_key_exists( 'banner_description', $data ) ) {
            $clean['banner_description'] = sanitize_textarea_field( $data['banner_description'] );
        }

        /* ── URLs ── */
        $url_fields = [ 'privacy_policy_url', 'tos_url' ];
        foreach ( $url_fields as $k ) {
            if ( array_key_exists( $k, $data ) ) {
                $clean[ $k ] = esc_url_raw( $data[ $k ] );
            }
        }

        /* ── Hex colors ── */
        $color_fields = [ 'primary_color', 'bg_color', 'text_color', 'btn_accept_bg', 'btn_reject_bg', 'btn_reject_text' ];
        foreach ( $color_fields as $k ) {
            if ( array_key_exists( $k, $data ) ) {
                $val = sanitize_text_field( $data[ $k ] );
                // Accept only valid CSS hex colors (#rgb or #rrggbb)
                $clean[ $k ] = preg_match( '/^#[0-9a-fA-F]{3,6}$/', $val ) ? $val : '';
            }
        }

        /* ── Integers ── */
        if ( array_key_exists( 'consent_expiry', $data ) ) {
            $clean['consent_expiry'] = absint( $data['consent_expiry'] );
        }
        if ( array_key_exists( 'tc_acceptance_page_id', $data ) ) {
            $clean['tc_acceptance_page_id'] = absint( $data['tc_acceptance_page_id'] );
        }

        /* ── Booleans ── */
        $bool_fields = [
            'banner_enabled', 'show_reject_btn', 'show_customize_btn',
            'auto_block', 'gcm_enabled', 'geo_detection', 'auto_policy_page',
            'ip_anonymize', 'ip_hash', 'show_tos_checkbox', 'withdrawal_enabled',
            'tc_enforcement_enabled', 'tc_purge_rejected',
        ];
        foreach ( $bool_fields as $k ) {
            if ( array_key_exists( $k, $data ) ) {
                $clean[ $k ] = (bool) $data[ $k ];
            }
        }

        /* ── Categories array ── */
        if ( array_key_exists( 'categories', $data ) && is_array( $data['categories'] ) ) {
            $allowed_cats = [ 'necessary', 'functional', 'analytics', 'performance', 'advertisement' ];
            $clean_cats   = [];
            foreach ( $allowed_cats as $cat_key ) {
                if ( isset( $data['categories'][ $cat_key ] ) ) {
                    $cat = $data['categories'][ $cat_key ];
                    $clean_cats[ $cat_key ] = [
                        'label'   => sanitize_text_field( $cat['label']   ?? '' ),
                        'enabled' => (bool) ( $cat['enabled'] ?? false ),
                        'locked'  => (bool) ( $cat['locked']  ?? false ),
                    ];
                }
            }
            $clean['categories'] = $clean_cats;
        }

        return $clean;
    }

    public static function save( array $data ): bool {
        // Sanitize ALL incoming data before touching the database
        $data    = self::sanitize( $data );
        $current = self::get();
        $merged  = array_merge( $current, $data );

        /*
         * v1.6.0 — When admin_lang changes, auto-translate banner text defaults
         * only if the fields still contain the previous default (not customised).
         */
        if ( isset( $data['admin_lang'] ) && $data['admin_lang'] !== ( $current['admin_lang'] ?? 'es' ) ) {
            $old_l = self::lang_strings( $current['admin_lang'] ?? 'es' );
            $new_l = self::lang_strings( $data['admin_lang'] );
            $text_fields = [ 'banner_title', 'banner_description', 'accept_btn_text', 'reject_btn_text', 'customize_btn_text' ];
            foreach ( $text_fields as $field ) {
                if ( ( $current[ $field ] ?? '' ) === $old_l[ $field ] ) {
                    $merged[ $field ] = $new_l[ $field ];
                }
            }
            $cat_keys = [ 'necessary', 'functional', 'analytics', 'performance', 'advertisement' ];
            foreach ( $cat_keys as $cat ) {
                $old_label = $old_l[ 'cat_' . $cat ] ?? '';
                if ( isset( $merged['categories'][ $cat ] ) && $merged['categories'][ $cat ]['label'] === $old_label ) {
                    $merged['categories'][ $cat ]['label'] = $new_l[ 'cat_' . $cat ] ?? $old_label;
                }
            }
        }

        return update_option( 'bcm_settings', $merged );
    }
}
