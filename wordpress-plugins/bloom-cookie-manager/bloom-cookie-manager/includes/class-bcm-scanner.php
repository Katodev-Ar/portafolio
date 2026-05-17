<?php
/**
 * BCM_Scanner — v1.4.0
 *
 * Mejoras sobre v1.3.0:
 *  - Motor "headless" vía Browseless.io (API REST gratuita hasta 100 sesiones/mes).
 *    Detecta cookies que se setean en runtime tras la ejecución de JS.
 *  - Fallback automático al scanner HTML estático si la API no está configurada
 *    o falla, para garantizar que el scan siempre devuelve algo útil.
 *  - Propiedad 'detection_method' en cada cookie ('headless' | 'static' | 'known_pattern').
 *  - La URL de la API y el token se guardan en bcm_settings.
 */
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Scanner {

    /* ── Iniciar scan en background ── */
    public static function start_scan(): int {
        global $wpdb;

        $wpdb->insert(
            $wpdb->prefix . 'bcm_scan_history',
            [ 'status' => 'in_progress', 'scan_date' => current_time( 'mysql' ) ],
            [ '%s', '%s' ]
        );
        $scan_id = (int) $wpdb->insert_id;

        wp_schedule_single_event( time(), 'bcm_run_scan', [ $scan_id ] );
        spawn_cron();

        return $scan_id;
    }

    /* ── Ejecutar scan (llamado por cron) ── */
    public static function run( int $scan_id ): void {
        global $wpdb;

        $urls    = self::collect_urls();
        $found   = [];
        $scanned = 0;

        foreach ( $urls as $url ) {
            /* Intentar motor headless primero */
            $cookies = self::scan_url_headless( $url );

            /* Fallback a scanner estático si headless no está disponible o falla */
            if ( $cookies === null ) {
                $cookies = self::scan_url_static( $url );
            }

            $found   = array_merge( $found, $cookies );
            $scanned++;
        }

        /* Deduplicar por nombre y guardar */
        $unique = [];
        foreach ( $found as $c ) {
            $key = $c['name'];
            /* Preferir entradas headless sobre estáticas para el mismo nombre */
            if ( ! isset( $unique[ $key ] ) || ( $c['detection_method'] ?? '' ) === 'headless' ) {
                $unique[ $key ] = $c;
            }
        }

        foreach ( $unique as $c ) {
            $exists = $wpdb->get_var( $wpdb->prepare(
                "SELECT id FROM {$wpdb->prefix}bcm_cookies WHERE name = %s", $c['name']
            ) );
            if ( ! $exists ) {
                $wpdb->insert(
                    $wpdb->prefix . 'bcm_cookies',
                    [
                        'name'        => sanitize_text_field( $c['name'] ),
                        'category'    => sanitize_text_field( $c['category'] ),
                        'provider'    => sanitize_text_field( $c['provider']  ?? '' ),
                        'purpose'     => sanitize_textarea_field( $c['purpose']  ?? '' ),
                        'expiry'      => sanitize_text_field( $c['expiry']   ?? '' ),
                        'cookie_type' => sanitize_text_field( $c['type']     ?? 'HTTP' ),
                        'domain'      => sanitize_text_field( $c['domain']   ?? '' ),
                    ],
                    [ '%s','%s','%s','%s','%s','%s','%s' ]
                );
            }
        }

        $wpdb->update(
            $wpdb->prefix . 'bcm_scan_history',
            [
                'status'        => 'completed',
                'urls_scanned'  => $scanned,
                'cookies_found' => count( $unique ),
            ],
            [ 'id' => $scan_id ],
            [ '%s','%d','%d' ],
            [ '%d' ]
        );

        /* v1.4.0: guardar fecha para el shortcode de política */
        update_option( 'bcm_last_scan_date', current_time( 'mysql' ) );
    }

    /* ══════════════════════════════════════════════════════
     *  MOTOR HEADLESS — Browseless.io
     *
     *  Configuración en Settings > Scanner:
     *    - browseless_endpoint  (default: https://chrome.browserless.io)
     *    - browseless_token     (API key de browserless.io)
     *
     *  Si no hay token configurado → devuelve null → fallback estático.
     *  Si la llamada falla         → devuelve null → fallback estático.
     *
     *  Alternativas self-hosted gratuitas:
     *    - https://github.com/browserless/chrome (Docker)
     *    - Playwright server propio
     * ══════════════════════════════════════════════════════ */
    private static function scan_url_headless( string $url ): ?array {
        $settings = BCM_Settings::get();
        $endpoint = rtrim( $settings['browseless_endpoint'] ?? '', '/' );
        $token    = $settings['browseless_token'] ?? '';

        if ( empty( $token ) || empty( $endpoint ) ) return null;

        /* Script de puppeteer que ejecuta Browserless:
         * navega a la URL, espera 2 s para que corran los scripts
         * y devuelve todas las cookies del contexto. */
        $script = <<<'JS'
module.exports = async ({ page }) => {
    await page.goto(PAGE_URL, { waitUntil: 'networkidle2', timeout: 20000 });
    await new Promise(r => setTimeout(r, 2000));
    const cookies = await page.cookies();
    return cookies.map(c => ({
        name:   c.name,
        domain: c.domain,
        expiry: c.expires > 0
            ? Math.round((c.expires - Date.now()/1000) / 86400) + ' days'
            : 'Session',
        type:   'HTTP',
    }));
};
JS;
        $script = str_replace( 'PAGE_URL', wp_json_encode( $url ), $script );

        $api_url  = $endpoint . '/function?token=' . rawurlencode( $token );
        $response = wp_remote_post( $api_url, [
            'timeout' => 30,
            'headers' => [ 'Content-Type' => 'application/javascript' ],
            'body'    => $script,
        ]);

        if ( is_wp_error( $response ) ) return null;
        if ( wp_remote_retrieve_response_code( $response ) !== 200 ) return null;

        $body = json_decode( wp_remote_retrieve_body( $response ), true );
        if ( ! is_array( $body ) ) return null;

        /* Enriquecer cada cookie con categoría y propósito */
        // External API response must be sanitized — never trust remote JSON as safe.
        $cookies = [];
        foreach ( $body as $raw ) {
            // $raw must be an array; skip any non-array element (malformed response)
            if ( ! is_array( $raw ) ) continue;

            $name = sanitize_text_field( (string) ( $raw['name'] ?? '' ) );
            if ( empty( $name ) ) continue;

            // expiry may arrive as integer (ms) or string ("Session", "1 year") — handle both
            $raw_expiry = $raw['expiry'] ?? 'Session';
            $expiry     = is_numeric( $raw_expiry )
                ? (string) intval( $raw_expiry )
                : sanitize_text_field( (string) $raw_expiry );

            $enriched = self::enrich_cookie( $name, $raw['domain'] ?? '' );
            $cookies[] = array_merge( [
                'name'             => $name,
                'domain'           => sanitize_text_field( (string) ( $raw['domain'] ?? '' ) ),
                'expiry'           => $expiry,
                'type'             => 'HTTP',
                'detection_method' => 'headless',
            ], $enriched );
        }

        return $cookies;
    }

    /* ══════════════════════════════════════════════════════
     *  MOTOR ESTÁTICO — análisis de HTML + headers
     * ══════════════════════════════════════════════════════ */
    private static function scan_url_static( string $url ): array {
        $response = wp_remote_get( $url, [
            'timeout'    => 15,
            'user-agent' => 'BloomCookieScanner/1.4',
            'sslverify'  => false,
        ]);

        if ( is_wp_error( $response ) ) return [];

        $body    = wp_remote_retrieve_body( $response );
        $cookies = [];

        /* Patrones conocidos por fingerprint de script */
        foreach ( self::known_cookie_patterns() as $pattern => $data ) {
            if ( stripos( $body, $pattern ) !== false ) {
                $cookies[] = array_merge( $data, [ 'detection_method' => 'known_pattern' ] );
            }
        }

        /* document.cookie = ... writes en el JS inline */
        preg_match_all( '/document\.cookie\s*=\s*["\']([^"\'=]+)=/', $body, $matches );
        foreach ( $matches[1] as $name ) {
            $cookies[] = [
                'name'             => trim( $name ),
                'category'         => 'functional',
                'provider'         => parse_url( $url, PHP_URL_HOST ),
                'purpose'          => 'Cookie set by the website',
                'expiry'           => 'Session',
                'type'             => 'HTTP',
                'domain'           => parse_url( $url, PHP_URL_HOST ),
                'detection_method' => 'static',
            ];
        }

        /* Set-Cookie headers de la respuesta HTTP */
        $headers    = wp_remote_retrieve_headers( $response );
        $set_cookie = $headers['set-cookie'] ?? [];
        if ( is_string( $set_cookie ) ) $set_cookie = [ $set_cookie ];

        foreach ( (array) $set_cookie as $line ) {
            $parts  = explode( ';', $line );
            $name   = explode( '=', $parts[0] )[0];
            $expiry = 'Session';

            foreach ( $parts as $part ) {
                if ( stripos( trim( $part ), 'max-age=' ) === 0 ) {
                    $secs   = (int) explode( '=', $part )[1];
                    $expiry = round( $secs / 86400 ) . ' days';
                } elseif ( stripos( trim( $part ), 'expires=' ) === 0 ) {
                    $expiry = trim( str_ireplace( 'expires=', '', $part ) );
                }
            }

            $enriched  = self::enrich_cookie( trim( $name ), parse_url( $url, PHP_URL_HOST ) );
            $cookies[] = array_merge( [
                'name'             => trim( $name ),
                'provider'         => parse_url( $url, PHP_URL_HOST ),
                'expiry'           => $expiry,
                'type'             => 'HTTP',
                'domain'           => parse_url( $url, PHP_URL_HOST ),
                'detection_method' => 'static',
            ], $enriched );
        }

        return $cookies;
    }

    /* ── Enriquecer cookie desconocida con categoría/propósito por nombre ── */
    private static function enrich_cookie( string $name, string $domain ): array {
        $name_lower = strtolower( $name );

        /* Analytics */
        if ( preg_match( '/^_ga|^_gid|^_gat|^_utm|^_hjid|^_hjsession|^amplitude/', $name_lower ) ) {
            return [ 'category' => 'analytics', 'provider' => 'Analytics service', 'purpose' => 'Website analytics and statistics' ];
        }
        /* Advertisement */
        if ( preg_match( '/^_fbp|^_fbc|^fr$|^_ttp|^_gcl|^IDE$|^DSID$|^1P_JAR/', $name_lower ) ) {
            return [ 'category' => 'advertisement', 'provider' => 'Advertising service', 'purpose' => 'Ad targeting and conversion tracking' ];
        }
        /* Functional */
        if ( preg_match( '/^intercom|^hs-|^drift_|^__hstc|^hubspotutk/', $name_lower ) ) {
            return [ 'category' => 'functional', 'provider' => 'Live chat / CRM', 'purpose' => 'Live chat and customer support' ];
        }
        /* Session / auth */
        if ( preg_match( '/^sess|session|^wordpress_|^wp-|^PHPSESSID$|^laravel_session/', $name_lower ) ) {
            return [ 'category' => 'necessary', 'provider' => $domain, 'purpose' => 'Session management and authentication' ];
        }
        /* CSRF */
        if ( preg_match( '/csrf|xsrf|token/', $name_lower ) ) {
            return [ 'category' => 'necessary', 'provider' => $domain, 'purpose' => 'Security token to prevent CSRF attacks' ];
        }

        return [ 'category' => 'functional', 'provider' => $domain, 'purpose' => 'Set by the website' ];
    }

    /* ── Colectar URLs a escanear ── */
    private static function collect_urls(): array {
        $urls  = [ home_url( '/' ) ];
        $posts = get_posts( [
            'post_type'   => [ 'post', 'page' ],
            'numberposts' => 20,
            'post_status' => 'publish',
        ]);
        foreach ( $posts as $p ) {
            $urls[] = get_permalink( $p->ID );
        }
        return array_unique( $urls );
    }

    /* ── Fingerprints de scripts de terceros conocidos ── */
    private static function known_cookie_patterns(): array {
        $site = site_url();
        return [
            /* ── WordPress core ── */
            'wp-content' => [
                'name' => 'wordpress_logged_in', 'category' => 'necessary',
                'provider' => 'WordPress', 'purpose' => 'Autentica a los usuarios con sesión iniciada.',
                'expiry' => 'Session', 'type' => 'HTTP', 'domain' => $site,
            ],
            'wp-settings' => [
                'name' => 'wp-settings-1', 'category' => 'necessary',
                'provider' => 'WordPress', 'purpose' => 'Guarda preferencias de la interfaz de WordPress.',
                'expiry' => '1 year', 'type' => 'HTTP', 'domain' => $site,
            ],

            /* ── Google Site Kit / GA4 / GTM ── */
            'googlesitekit' => [
                'name' => '_ga', 'category' => 'analytics',
                'provider' => 'Google Analytics (Site Kit)', 'purpose' => 'Registra un ID único para generar estadísticas sobre cómo el visitante usa el sitio.',
                'expiry' => '2 years', 'type' => 'HTTP', 'domain' => $site,
            ],
            'googletagmanager.com/gtm.js' => [
                'name' => '_gid', 'category' => 'analytics',
                'provider' => 'Google Tag Manager', 'purpose' => 'Registra visitantes únicos diarios.',
                'expiry' => '1 day', 'type' => 'HTTP', 'domain' => $site,
            ],
            'googletagmanager.com/gtag' => [
                'name' => '_gat', 'category' => 'analytics',
                'provider' => 'Google Analytics', 'purpose' => 'Limita la tasa de solicitudes a Google Analytics.',
                'expiry' => '1 minute', 'type' => 'HTTP', 'domain' => $site,
            ],
            'google-analytics.com/analytics.js' => [
                'name' => '_ga', 'category' => 'analytics',
                'provider' => 'Google Analytics', 'purpose' => 'Registra un ID único para generar estadísticas de uso del sitio.',
                'expiry' => '2 years', 'type' => 'HTTP', 'domain' => $site,
            ],
            /* Search Console no setea cookies propias pero GTM sí */
            'google.com/recaptcha' => [
                'name' => '_GRECAPTCHA', 'category' => 'functional',
                'provider' => 'Google reCAPTCHA', 'purpose' => 'Distingue usuarios humanos de bots para prevenir spam.',
                'expiry' => '6 months', 'type' => 'HTTP', 'domain' => '.google.com',
            ],

            /* ── Google Ads / DoubleClick ── */
            'googleads.g.doubleclick.net' => [
                'name' => 'IDE', 'category' => 'advertisement',
                'provider' => 'Google Ads / DoubleClick', 'purpose' => 'Registra e informa sobre las acciones del usuario tras ver o hacer clic en anuncios de Google. Se utiliza para medir la eficacia de los anuncios.',
                'expiry' => '1 year', 'type' => 'HTTP', 'domain' => '.doubleclick.net',
            ],
            'pagead2.googlesyndication' => [
                'name' => 'test_cookie', 'category' => 'advertisement',
                'provider' => 'Google Ads', 'purpose' => 'Comprueba si el navegador acepta cookies.',
                'expiry' => 'Session', 'type' => 'HTTP', 'domain' => '.doubleclick.net',
            ],
            'adsbygoogle' => [
                'name' => 'NID', 'category' => 'advertisement',
                'provider' => 'Google Ads', 'purpose' => 'Registra una ID única para identificar el dispositivo y personalizar anuncios.',
                'expiry' => '6 months', 'type' => 'HTTP', 'domain' => '.google.com',
            ],

            /* ── Infolinks ── */
            'infolinks.com' => [
                'name' => 'ILP', 'category' => 'advertisement',
                'provider' => 'Infolinks', 'purpose' => 'Utilizado por Infolinks para mostrar publicidad contextual relevante para el contenido de la página.',
                'expiry' => '30 days', 'type' => 'HTTP', 'domain' => '.infolinks.com',
            ],
            'router.infolinks' => [
                'name' => 'ILP', 'category' => 'advertisement',
                'provider' => 'Infolinks', 'purpose' => 'Ruteo de anuncios Infolinks. Utilizado para seleccionar anuncios contextuales.',
                'expiry' => '30 days', 'type' => 'HTTP', 'domain' => '.infolinks.com',
            ],

            /* ── Facebook Pixel ── */
            'connect.facebook.net' => [
                'name' => '_fbp', 'category' => 'advertisement',
                'provider' => 'Facebook / Meta', 'purpose' => 'Utilizado por Facebook para rastrear visitas en sitios web con el fin de publicar anuncios relevantes.',
                'expiry' => '3 months', 'type' => 'HTTP', 'domain' => '.facebook.com',
            ],

            /* ── Hotjar ── */
            'static.hotjar.com' => [
                'name' => '_hjid', 'category' => 'analytics',
                'provider' => 'Hotjar', 'purpose' => 'Establece un ID de sesión único para generar datos estadísticos.',
                'expiry' => '1 year', 'type' => 'HTTP', 'domain' => $site,
            ],

            /* ── Hostinger ── */
            'hostinger' => [
                'name' => 'hostinger_sn', 'category' => 'necessary',
                'provider' => 'Hostinger', 'purpose' => 'Cookie de infraestructura del servidor Hostinger.',
                'expiry' => 'Session', 'type' => 'HTTP', 'domain' => $site,
            ],

            /* ── Site Kit (handle JS local) ── */
            'sitekit-gtag' => [
                'name' => '_ga', 'category' => 'analytics',
                'provider' => 'Google Site Kit', 'purpose' => 'Google Analytics vía Site Kit. Rastrea sesiones de usuario únicas.',
                'expiry' => '2 years', 'type' => 'HTTP', 'domain' => $site,
            ],

            /* ── Consent y consentimiento ── */
            'bcm_consent' => [
                'name' => 'bcm_consent', 'category' => 'necessary',
                'provider' => 'Bloom Cookie Manager', 'purpose' => 'Almacena las preferencias de consentimiento de cookies del visitante.',
                'expiry' => '1 year', 'type' => 'HTTP', 'domain' => $site,
            ],
            'cookieyes' => [
                'name' => 'cookieyes-consent', 'category' => 'necessary',
                'provider' => 'CookieYes', 'purpose' => 'Almacena el estado de consentimiento de cookies del usuario.',
                'expiry' => '1 year', 'type' => 'HTTP', 'domain' => $site,
            ],
        ];
    }

    /* ── Tabla de cookies conocidas para seed manual / importación ──
     * Basada en el inventario real del sitio bloomscans.com (v1.4.3)
     * Incluye: bloomscans.com, router.infolinks.com,
     *          googleads.g.doubleclick.net, www.google.com,
     *          Cloudflare (cfz_*), LiteSpeed, ezux_*, etc.
     */
    public static function seed_known_cookies(): int {
        global $wpdb;
        $site  = site_url();
        $host  = parse_url( $site, PHP_URL_HOST );
        $added = 0;

        $library = [
            /* WordPress */
            [ 'name'=>'wordpress_logged_in', 'category'=>'necessary', 'provider'=>'WordPress', 'purpose'=>'Autentica a los usuarios con sesión iniciada en WordPress.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'wordpress_sec', 'category'=>'necessary', 'provider'=>'WordPress', 'purpose'=>'Cookie de seguridad de WordPress para autenticación.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'wordpress_test_cookie', 'category'=>'necessary', 'provider'=>'WordPress', 'purpose'=>'Verifica que el navegador acepte cookies (comprobación interna de WordPress).', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'wp-settings-1', 'category'=>'necessary', 'provider'=>'WordPress', 'purpose'=>'Guarda preferencias personalizadas del panel de administración de WordPress.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'wp-settings-time-1', 'category'=>'necessary', 'provider'=>'WordPress', 'purpose'=>'Almacena la marca de tiempo de las últimas preferencias guardadas en WordPress.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'wp_lang', 'category'=>'functional', 'provider'=>'WordPress', 'purpose'=>'Guarda el idioma preferido del usuario en el panel de WordPress.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'bcm_consent', 'category'=>'necessary', 'provider'=>'Bloom Cookie Manager', 'purpose'=>'Almacena las preferencias de consentimiento de cookies del visitante.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            /* LiteSpeed Cache — ezux_* */
            [ 'name'=>'litespeed_tab', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Identifica la pestaña del navegador para gestionar correctamente la caché LiteSpeed.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'logglytrackingnumber', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Número de seguimiento interno para optimización de caché.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'ezux_et_765996', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Cookie interna de LiteSpeed para gestión de Edge Side Includes (ESI) y caché por usuario.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'ezux_ifep_765996', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Indica si el usuario está en modo de navegación privada para aplicar caché apropiada.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'ezux_lpl_765996', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Almacena el tiempo de última visita para calcular el TTL de caché personalizado.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'ezux_tos_765996', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Registra si el usuario aceptó los términos de servicio para adaptar la caché.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'ezds', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Cookie de diagnóstico de LiteSpeed para identificar el tipo de dispositivo del visitante.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'ezohw', 'category'=>'necessary', 'provider'=>'LiteSpeed Cache', 'purpose'=>'Almacena las dimensiones de la ventana del navegador para la optimización de imágenes.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            /* Otros — dominio propio */
            [ 'name'=>'FCCDCF', 'category'=>'necessary', 'provider'=>'IAB TCF / Consent', 'purpose'=>'Almacena el estado de consentimiento conforme al IAB Transparency & Consent Framework.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'hcdn', 'category'=>'necessary', 'provider'=>'Hostinger CDN', 'purpose'=>'Cookie de infraestructura de la CDN de Hostinger para enrutamiento de solicitudes.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'sparrow_id', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'ID de usuario generado por Cloudflare Zaraz para análisis de tráfico unificado.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            /* Google Analytics via Site Kit */
            [ 'name'=>'_ga', 'category'=>'analytics', 'provider'=>'Google Analytics (Site Kit)', 'purpose'=>'Registra un ID único para generar estadísticas sobre cómo el visitante usa el sitio.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'_ga_5H557DY8GJ', 'category'=>'analytics', 'provider'=>'Google Analytics 4', 'purpose'=>'Cookie de persistencia de sesión de GA4. Distingue sesiones de usuario individuales.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'_ga_9Q6H0QETRF', 'category'=>'analytics', 'provider'=>'Google Analytics 4', 'purpose'=>'Cookie de persistencia de sesión de GA4 vinculada a un stream de datos específico.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'_ga_SQCRB0TXZW', 'category'=>'analytics', 'provider'=>'Google Analytics 4', 'purpose'=>'Cookie de persistencia de sesión de GA4 vinculada a un stream de datos específico.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            [ 'name'=>'_gcl_au', 'category'=>'advertisement', 'provider'=>'Google Ads (Site Kit)', 'purpose'=>'Utilizado por Google Ads para almacenar y rastrear conversiones en el sitio web.', 'expiry'=>'3 months', 'cookie_type'=>'HTTP', 'domain'=>$host ],
            /* Cloudflare / cfz_* */
            [ 'name'=>'_mggpc_', 'category'=>'necessary', 'provider'=>'Cloudflare', 'purpose'=>'Cookie interna de Cloudflare para verificación de tráfico y protección DDoS.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_q_state_37pXYrro6wCZbsU7', 'category'=>'necessary', 'provider'=>'Cloudflare', 'purpose'=>'Almacena el estado de la sesión del usuario en la infraestructura de Cloudflare.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_biz_flagsA', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Almacena indicadores de comportamiento del usuario para análisis de marketing.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_biz_nA', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Contador de sesión utilizado para análisis de tráfico.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_biz_pendingA', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Almacena eventos de análisis pendientes de envío.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_biz_uid', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'ID único de usuario para seguimiento de marketing mediante Cloudflare.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_mkto_trk', 'category'=>'advertisement', 'provider'=>'Cloudflare / Marketo', 'purpose'=>'Cookie de seguimiento de Marketo para identificar al visitante en campañas de marketing.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'_uetvid', 'category'=>'advertisement', 'provider'=>'Cloudflare / Microsoft UET', 'purpose'=>'ID de seguimiento de Microsoft Universal Event Tracking para publicidad.', 'expiry'=>'13 months', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'CF_VERIFIED_DEVICE', 'category'=>'necessary', 'provider'=>'Cloudflare', 'purpose'=>'Verifica que el dispositivo ha pasado un challenge de seguridad de Cloudflare.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'cfz_adobe', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Cloudflare Zaraz gestiona el tag de Adobe Analytics de forma centralizada.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'cfz_amplitude', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Cloudflare Zaraz gestiona el tag de Amplitude para análisis de comportamiento.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'cfz_facebook-pixel', 'category'=>'advertisement', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Cloudflare Zaraz gestiona el Pixel de Facebook para seguimiento de conversiones.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'cfz_google-analytics_v4', 'category'=>'analytics', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Cloudflare Zaraz gestiona Google Analytics 4 de forma centralizada y con privacidad.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'cfz_reddit', 'category'=>'advertisement', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Cloudflare Zaraz gestiona el píxel de Reddit Ads para seguimiento de anuncios.', 'expiry'=>'Session', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'OptanonConsent', 'category'=>'necessary', 'provider'=>'OneTrust / Cloudflare', 'purpose'=>'Almacena el estado detallado del consentimiento de cookies del usuario.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'kndctr_adobe', 'category'=>'analytics', 'provider'=>'Adobe Experience Cloud', 'purpose'=>'Cookie de Adobe Experience Cloud para identificación de visitantes y personalización.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'zaraz-consent', 'category'=>'necessary', 'provider'=>'Cloudflare Zaraz', 'purpose'=>'Almacena las preferencias de consentimiento de Cloudflare Zaraz.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            [ 'name'=>'cookieyes-consent', 'category'=>'necessary', 'provider'=>'CookieYes', 'purpose'=>'Almacena el estado de consentimiento de cookies del usuario.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.cloudflare.com' ],
            /* Infolinks */
            [ 'name'=>'ANUSERCOOKIE', 'category'=>'advertisement', 'provider'=>'Infolinks', 'purpose'=>'Cookie de usuario anónimo de Infolinks para mostrar anuncios contextuales personalizados.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.infolinks.com' ],
            [ 'name'=>'QCUSERCOOKIE', 'category'=>'advertisement', 'provider'=>'Infolinks', 'purpose'=>'Cookie de calidad de usuario de Infolinks para optimizar la selección de anuncios.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.infolinks.com' ],
            [ 'name'=>'SAMUSERCOOKIE', 'category'=>'advertisement', 'provider'=>'Infolinks', 'purpose'=>'Cookie de segmento de audiencia de Infolinks para segmentar y mostrar anuncios relevantes.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.infolinks.com' ],
            /* Google Ads / DoubleClick */
            [ 'name'=>'IDE', 'category'=>'advertisement', 'provider'=>'Google Ads / DoubleClick', 'purpose'=>'Registra e informa sobre las acciones del usuario tras ver o hacer clic en anuncios de Google para medir la eficacia publicitaria.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.doubleclick.net' ],
            [ 'name'=>'DSID', 'category'=>'advertisement', 'provider'=>'Google Ads / DoubleClick', 'purpose'=>'Identifica a un usuario que ha iniciado sesión en un sitio de Google para sincronizar anuncios.', 'expiry'=>'2 weeks', 'cookie_type'=>'HTTP', 'domain'=>'.doubleclick.net' ],
            [ 'name'=>'ar_debug', 'category'=>'advertisement', 'provider'=>'Google Ads', 'purpose'=>'Cookie de depuración de Google Ads para diagnosticar problemas con el seguimiento de conversiones.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.doubleclick.net' ],
            /* Google — www.google.com */
            [ 'name'=>'NID', 'category'=>'advertisement', 'provider'=>'Google', 'purpose'=>'Registra una ID única para identificar el dispositivo del visitante y personalizar anuncios de Google.', 'expiry'=>'6 months', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'1P_JAR', 'category'=>'advertisement', 'provider'=>'Google Ads', 'purpose'=>'Recopila estadísticas del sitio y rastrea tasas de conversión de anuncios de Google.', 'expiry'=>'1 month', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'AEC', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Garantiza que las solicitudes en una sesión sean del usuario real y no de otros sitios (anti-CSRF).', 'expiry'=>'6 months', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'APISID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de sesión de API de Google para mantener la autenticación del usuario.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'HSID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de seguridad de Google que protege al usuario contra ataques de falsificación de solicitudes.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'OTZ', 'category'=>'analytics', 'provider'=>'Google', 'purpose'=>'Cookie de análisis agregado utilizada por Google para reportar estadísticas de tráfico.', 'expiry'=>'1 month', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'SAPISID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Autentica al usuario de Google para proteger información de cuenta en solicitudes de API.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'SEARCH_SAMESITE', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie SameSite de Google que previene el envío en solicitudes entre sitios.', 'expiry'=>'5 months', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'SID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de ID de sesión de Google que autentica al usuario registrado en servicios de Google.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'SIDCC', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de seguridad de Google que verifica que el titular de la cuenta tiene acceso legítimo.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'SSID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de ID de sesión segura de Google para servicios de Google Maps y otros.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-1PAPISID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de seguridad de Google para la API de primera parte con conexión HTTPS.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-1PSID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de ID de sesión segura de Google para servicios de primera parte.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-1PSIDCC', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de verificación adicional de seguridad para sesiones de primera parte de Google.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-1PSIDTS', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Marca de tiempo de la cookie de sesión segura de primera parte de Google.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-3PAPISID', 'category'=>'advertisement', 'provider'=>'Google Ads', 'purpose'=>'Cookie segura de API de terceros de Google utilizada para publicidad personalizada entre sitios.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-3PSID', 'category'=>'advertisement', 'provider'=>'Google Ads', 'purpose'=>'Cookie de ID de sesión segura de terceros de Google para publicidad y seguimiento cross-site.', 'expiry'=>'2 years', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-3PSIDCC', 'category'=>'advertisement', 'provider'=>'Google Ads', 'purpose'=>'Verificación de seguridad adicional para la cookie de sesión de terceros de Google.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-3PSIDTS', 'category'=>'advertisement', 'provider'=>'Google Ads', 'purpose'=>'Marca de tiempo de la cookie de sesión segura de terceros de Google.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-BUCKET', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de asignación de bucket de Google para experimentos A/B y distribución de tráfico.', 'expiry'=>'1 year', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
            [ 'name'=>'_Secure-ENID', 'category'=>'necessary', 'provider'=>'Google', 'purpose'=>'Cookie de ID cifrado y seguro de Google para identificación del dispositivo.', 'expiry'=>'13 months', 'cookie_type'=>'HTTP', 'domain'=>'.google.com' ],
        ];

        foreach ( $library as $c ) {
            $exists = $wpdb->get_var( $wpdb->prepare(
                "SELECT id FROM {$wpdb->prefix}bcm_cookies WHERE name = %s", $c['name']
            ) );
            if ( ! $exists ) {
                $wpdb->insert( $wpdb->prefix . 'bcm_cookies', $c,
                    [ '%s','%s','%s','%s','%s','%s','%s' ] );
                $added++;
            }
        }
        return $added;
    }
}

add_action( 'bcm_run_scan', [ 'BCM_Scanner', 'run' ] );
