<?php
/**
 * BCM_Cookie_Policy — v1.4.0
 *
 * Genera la tabla de política de cookies a partir de las cookies
 * detectadas por el scanner, agrupadas por categoría.
 *
 * Uso:  [bcm_cookie_policy]
 *       [bcm_cookie_policy category="analytics"]
 *       [bcm_cookie_policy show_empty="yes"]
 *       [bcm_cookie_policy lang="en"]    (fuerza idioma: es|en|pt)
 *
 * También expone una página de política auto-generada si el admin
 * activa "Auto-generate policy page" en Settings.
 */
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Cookie_Policy {

    public function __construct() {
        add_shortcode( 'bcm_cookie_policy', [ $this, 'render_shortcode' ] );
        add_action( 'init', [ $this, 'maybe_create_policy_page' ] );
        add_filter( 'the_content', [ $this, 'append_last_updated' ] );
    }

    /* ══════════════════════════════════════════════════════
     *  SHORTCODE
     * ══════════════════════════════════════════════════════ */
    public function render_shortcode( array $atts ): string {
        $atts = shortcode_atts( [
            'category'   => '',       // filtrar por categoría
            'show_empty' => 'no',     // mostrar categorías sin cookies
            'lang'       => '',       // forzar idioma
        ], $atts, 'bcm_cookie_policy' );

        global $wpdb;

        $where = '';
        if ( ! empty( $atts['category'] ) ) {
            $where = $wpdb->prepare( 'WHERE category = %s', sanitize_text_field( $atts['category'] ) );
        }

        $cookies = $wpdb->get_results(
            "SELECT * FROM {$wpdb->prefix}bcm_cookies {$where} ORDER BY category, name",
            ARRAY_A
        );

        /* Strings i18n */
        $lang   = $this->resolve_lang( $atts['lang'] );
        $labels = $this->get_labels( $lang );

        /* Agrupar por categoría */
        $grouped = [];
        foreach ( $cookies as $c ) {
            $grouped[ $c['category'] ][] = $c;
        }

        /* Categorías en orden canónico */
        $order = [ 'necessary', 'functional', 'analytics', 'performance', 'advertisement' ];
        uksort( $grouped, fn( $a, $b ) =>
            array_search( $a, $order, true ) <=> array_search( $b, $order, true )
        );

        ob_start();
        wp_enqueue_style( 'bcm-policy', BCM_PLUGIN_URL . 'public/css/cookie-policy.css', [], BCM_VERSION );

        echo '<div class="bcm-cookie-policy">';

        foreach ( $order as $cat ) {
            if ( ! isset( $grouped[ $cat ] ) ) {
                if ( $atts['show_empty'] !== 'yes' ) continue;
                $grouped[ $cat ] = [];
            }

            $cat_label = $labels['categories'][ $cat ] ?? ucfirst( $cat );
            $cat_desc  = $labels['descriptions'][ $cat ] ?? '';

            echo '<div class="bcm-policy-section">';
            echo '<h3 class="bcm-policy-heading">' . esc_html( $cat_label ) . '</h3>';
            if ( $cat_desc ) {
                echo '<p class="bcm-policy-desc">' . esc_html( $cat_desc ) . '</p>';
            }

            if ( empty( $grouped[ $cat ] ) ) {
                echo '<p class="bcm-policy-empty">' . esc_html( $labels['no_cookies'] ) . '</p>';
            } else {
                echo '<div class="bcm-policy-table-wrap">';
                echo '<table class="bcm-policy-table">';
                echo '<thead><tr>';
                echo '<th>' . esc_html( $labels['col_name'] ) . '</th>';
                echo '<th>' . esc_html( $labels['col_provider'] ) . '</th>';
                echo '<th>' . esc_html( $labels['col_purpose'] ) . '</th>';
                echo '<th>' . esc_html( $labels['col_expiry'] ) . '</th>';
                echo '<th>' . esc_html( $labels['col_type'] ) . '</th>';
                echo '</tr></thead><tbody>';

                foreach ( $grouped[ $cat ] as $c ) {
                    echo '<tr>';
                    echo '<td><code>' . esc_html( $c['name'] ) . '</code></td>';
                    echo '<td>' . esc_html( $c['provider'] ?: '—' ) . '</td>';
                    echo '<td>' . esc_html( $c['purpose']  ?: '—' ) . '</td>';
                    echo '<td>' . esc_html( $c['expiry']   ?: '—' ) . '</td>';
                    echo '<td><span class="bcm-policy-type">' . esc_html( $c['cookie_type'] ?: 'HTTP' ) . '</span></td>';
                    echo '</tr>';
                }

                echo '</tbody></table></div>';
            }

            echo '</div>';
        }

        /* Nota de última actualización */
        $last_scan = get_option( 'bcm_last_scan_date', '' );
        if ( $last_scan ) {
            echo '<p class="bcm-policy-updated">'
                . esc_html( $labels['last_updated'] ) . ' '
                . esc_html( date_i18n( get_option( 'date_format' ), strtotime( $last_scan ) ) )
                . '</p>';
        }

        echo '</div>';

        return ob_get_clean();
    }

    /* ══════════════════════════════════════════════════════
     *  AUTO-CREAR PÁGINA DE POLÍTICA
     * ══════════════════════════════════════════════════════ */
    public function maybe_create_policy_page(): void {
        $s = BCM_Settings::get();
        if ( empty( $s['auto_policy_page'] ) ) return;

        $page_id = (int) get_option( 'bcm_policy_page_id', 0 );

        /* Si ya existe y está publicada, no hacer nada */
        if ( $page_id && get_post_status( $page_id ) === 'publish' ) return;

        $lang   = $this->resolve_lang('');
        $labels = $this->get_labels( $lang );

        $page_id = wp_insert_post( [
            'post_title'   => $labels['policy_page_title'],
            'post_name'    => 'cookie-policy',
            'post_content' => '<!-- wp:shortcode -->[bcm_cookie_policy]<!-- /wp:shortcode -->',
            'post_status'  => 'publish',
            'post_type'    => 'page',
            'post_author'  => 1,
        ]);

        if ( ! is_wp_error( $page_id ) ) {
            update_option( 'bcm_policy_page_id', $page_id );
        }
    }

    /* Añadir "Última actualización" al contenido de la página de política */
    public function append_last_updated( string $content ): string {
        $page_id = (int) get_option( 'bcm_policy_page_id', 0 );
        if ( ! $page_id || ! is_page( $page_id ) ) return $content;
        return $content; // ya se incluye dentro del shortcode
    }

    /* ══════════════════════════════════════════════════════
     *  I18N
     * ══════════════════════════════════════════════════════ */
    private function resolve_lang( string $forced ): string {
        if ( ! empty( $forced ) ) return strtolower( $forced );
        $locale = get_locale();
        if ( str_starts_with( $locale, 'es' ) ) return 'es';
        if ( str_starts_with( $locale, 'pt' ) ) return 'pt';
        return 'en';
    }

    private function get_labels( string $lang ): array {
        $strings = [
            'es' => [
                'col_name'     => 'Cookie',
                'col_provider' => 'Proveedor',
                'col_purpose'  => 'Propósito',
                'col_expiry'   => 'Duración',
                'col_type'     => 'Tipo',
                'no_cookies'   => 'No se han detectado cookies en esta categoría.',
                'last_updated' => 'Última actualización:',
                'policy_page_title' => 'Política de Cookies',
                'categories'   => [
                    'necessary'     => 'Cookies necesarias',
                    'functional'    => 'Cookies funcionales',
                    'analytics'     => 'Cookies analíticas',
                    'performance'   => 'Cookies de rendimiento',
                    'advertisement' => 'Cookies publicitarias',
                ],
                'descriptions' => [
                    'necessary'     => 'Son imprescindibles para el funcionamiento del sitio y no pueden desactivarse.',
                    'functional'    => 'Permiten recordar tus preferencias y configuración.',
                    'analytics'     => 'Nos ayudan a entender cómo usas el sitio para mejorarlo.',
                    'performance'   => 'Mejoran la velocidad de carga y el rendimiento.',
                    'advertisement' => 'Se usan para mostrarte anuncios relevantes.',
                ],
            ],
            'pt' => [
                'col_name'     => 'Cookie',
                'col_provider' => 'Fornecedor',
                'col_purpose'  => 'Finalidade',
                'col_expiry'   => 'Duração',
                'col_type'     => 'Tipo',
                'no_cookies'   => 'Nenhum cookie detectado nesta categoria.',
                'last_updated' => 'Última atualização:',
                'policy_page_title' => 'Política de Cookies',
                'categories'   => [
                    'necessary'     => 'Cookies necessários',
                    'functional'    => 'Cookies funcionais',
                    'analytics'     => 'Cookies analíticos',
                    'performance'   => 'Cookies de desempenho',
                    'advertisement' => 'Cookies de publicidade',
                ],
                'descriptions' => [
                    'necessary'     => 'Essenciais para o funcionamento do site e não podem ser desativados.',
                    'functional'    => 'Permitem lembrar suas preferências.',
                    'analytics'     => 'Ajudam-nos a entender como você usa o site.',
                    'performance'   => 'Melhoram a velocidade e desempenho.',
                    'advertisement' => 'Usados para exibir anúncios relevantes.',
                ],
            ],
            'en' => [
                'col_name'     => 'Cookie',
                'col_provider' => 'Provider',
                'col_purpose'  => 'Purpose',
                'col_expiry'   => 'Expiry',
                'col_type'     => 'Type',
                'no_cookies'   => 'No cookies detected in this category.',
                'last_updated' => 'Last updated:',
                'policy_page_title' => 'Cookie Policy',
                'categories'   => [
                    'necessary'     => 'Necessary cookies',
                    'functional'    => 'Functional cookies',
                    'analytics'     => 'Analytics cookies',
                    'performance'   => 'Performance cookies',
                    'advertisement' => 'Advertisement cookies',
                ],
                'descriptions' => [
                    'necessary'     => 'Required for basic site functionality and cannot be disabled.',
                    'functional'    => 'Enable personalisation and remembering your preferences.',
                    'analytics'     => 'Help us understand how you use our site.',
                    'performance'   => 'Improve loading speed and site performance.',
                    'advertisement' => 'Used to show you relevant advertisements.',
                ],
            ],
        ];

        return $strings[ $lang ] ?? $strings['en'];
    }
}
