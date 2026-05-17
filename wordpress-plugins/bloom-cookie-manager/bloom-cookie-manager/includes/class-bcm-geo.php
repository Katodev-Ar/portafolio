<?php
/**
 * BCM_Geo — v1.4.0
 *
 * Detecta la regulación aplicable al visitante según su país de origen.
 * Prioridad de fuentes (de mayor a menor confiabilidad):
 *   1. Header CF-IPCountry  (Cloudflare — sin llamada externa)
 *   2. Header X-Forwarded-For + ip-api.com  (fallback)
 *   3. 'GDPR' como valor por defecto seguro
 *
 * El resultado se cachea en una transient por IP (TTL 24 h) para evitar
 * llamadas repetidas a la API externa.
 */
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Geo {

    /* Países sujetos a GDPR (EEA + UK + CH) */
    private static array $GDPR_COUNTRIES = [
        'AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU',
        'IE','IT','LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES',
        'SE','IS','LI','NO',  // EEA no-UE
        'GB',                 // UK (UK GDPR post-Brexit)
        'CH',                 // Suiza (nDSG equivalente)
    ];

    /* Países sujetos a LGPD */
    private static array $LGPD_COUNTRIES = [ 'BR' ];

    /* Estados CCPA — California es el único estado con opt-out,
     * pero detectamos por país (US) y dejamos que el admin refine si quiere */
    private static array $CCPA_COUNTRIES = [ 'US' ];

    /**
     * Devuelve la regulación para el visitante actual: 'GDPR' | 'LGPD' | 'CCPA' | 'NONE'.
     * 'NONE' significa que no existe obligación específica detectada; el banner
     * puede mostrarse igual según la configuración global del admin.
     *
     * NOTA CCPA (Fix v1.5.0):
     * La CCPA aplica estrictamente a empresas que operan en California y superan
     * ciertos umbrales (>$25M ingresos anuales, o >100K registros de consumidores,
     * o >50% de ingresos por venta de datos). Detectar el país como 'US' es una
     * aproximación conservadora y segura; si el sitio no supera esos umbrales,
     * se puede desactivar la geo-detección y configurar la regulación manualmente.
     */
    public static function detect(): string {
        $ip      = self::get_visitor_ip();
        $country = self::get_country( $ip );

        if ( in_array( $country, self::$GDPR_COUNTRIES, true ) ) return 'GDPR';
        if ( in_array( $country, self::$LGPD_COUNTRIES, true ) ) return 'LGPD';
        if ( in_array( $country, self::$CCPA_COUNTRIES, true ) ) return 'CCPA';

        return 'NONE';
    }

    /**
     * Devuelve el código ISO-3166-1 alpha-2 del país del visitante.
     * Cachea en transient 24 h para evitar llamadas repetidas.
     */
    public static function get_country( string $ip ): string {
        if ( empty( $ip ) || $ip === '127.0.0.1' || $ip === '::1' ) {
            return '';
        }

        /* 1. Cloudflare: header CF-IPCountry */
        if ( ! empty( $_SERVER['HTTP_CF_IPCOUNTRY'] ) ) {
            $cc = strtoupper( sanitize_text_field( wp_unslash( $_SERVER['HTTP_CF_IPCOUNTRY'] ) ) );
            if ( preg_match( '/^[A-Z]{2}$/', $cc ) ) return $cc;
        }

        /* 2. Caché de transient */
        $cache_key = 'bcm_geo_' . md5( $ip );
        $cached    = get_transient( $cache_key );
        if ( $cached !== false ) return (string) $cached;

        /* 3. Llamada a ip-api.com (gratuita, sin API key, 45 req/min) */
        $country = self::lookup_via_ipapi( $ip );

        set_transient( $cache_key, $country, DAY_IN_SECONDS );
        return $country;
    }

    /* ── ipapi.co (HTTPS gratuito, sin API key) ── */
    private static function lookup_via_ipapi( string $ip ): string {
        /*
         * FIX v1.5.0 — Se reemplaza ip-api.com (HTTP únicamente en plan gratuito)
         * por ipapi.co que soporta HTTPS sin coste. La IP del visitante es un dato
         * personal bajo GDPR Art. 4(1); transmitirla sin cifrado no es aceptable.
         * ipapi.co: 1.000 req/día gratis, responde en texto plano el código ISO-3166.
         */
        $url      = 'https://ipapi.co/' . rawurlencode( $ip ) . '/country/';
        $response = wp_remote_get( $url, [
            'timeout'   => 3,
            'sslverify' => true,
            'headers'   => [ 'Accept' => 'text/plain', 'User-Agent' => 'BloomCookieManager/' . BCM_VERSION ],
        ]);

        if ( is_wp_error( $response ) ) return '';

        $code = strtoupper( trim( wp_remote_retrieve_body( $response ) ) );
        /* La respuesta es el código de 2 letras (ej. "ES") o un JSON de error */
        if ( preg_match( '/^[A-Z]{2}$/', $code ) ) {
            return sanitize_text_field( $code );
        }
        return '';
    }

    /* ── IP del visitante (igual que BCM_Consent_Log) ── */
    public static function get_visitor_ip(): string {
        $keys = [ 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR' ];
        foreach ( $keys as $k ) {
            if ( ! empty( $_SERVER[ $k ] ) ) {
                $ip = sanitize_text_field( wp_unslash( $_SERVER[ $k ] ) );
                return trim( explode( ',', $ip )[0] );
            }
        }
        return '';
    }
}
