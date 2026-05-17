<?php
if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Consent_Log {

    /* ── Registrar consentimiento ── */
    public static function record( string $consent_id, string $status, array $categories, string $regulation = 'GDPR' ): void {
        global $wpdb;

        $ip = self::get_ip();

        /*
         * FIX v2.0.5 — Tratamiento de IP como dato personal (GDPR Art. 5.1.e).
         *
         * Se evalúan dos opciones excluyentes en este orden de precedencia:
         *
         *  1. ip_hash (nuevo) — aplica hash SHA-256 a la IP completa antes de
         *     guardarla. El resultado es un string de 64 chars hexadecimales,
         *     irreversible. Permite aún cumplir el Art. 17 (supresión) porque
         *     delete_by_ip() hashea el parámetro entrante antes de comparar.
         *     Cumple con GDPR y con la guía de seudonimización de la AEPD
         *     (ENISA Pseudonymisation Techniques, 2019).
         *
         *  2. ip_anonymize — trunca el último octeto en IPv4 / últimos 64 bits
         *     en IPv6 (comportamiento pre-v2.0.5). Sigue disponible para quienes
         *     prefieran la IP parcial legible en el log de auditoría.
         *
         *  Si ninguna opción está activa la IP se guarda en claro. En ese caso
         *  el administrador asume la responsabilidad sobre la base legal del
         *  tratamiento (Art. 6 GDPR) y debe reflejarlo en su Registro de
         *  Actividades de Tratamiento (Art. 30 GDPR).
         */
        if ( BCM_Settings::get( 'ip_hash' ) ) {
            $ip = self::hash_ip( $ip );
        } elseif ( BCM_Settings::get( 'ip_anonymize' ) ) {
            $ip = self::anonymize_ip( $ip );
        }

        $wpdb->insert(
            $wpdb->prefix . 'bcm_consent_logs',
            [
                'consent_id'  => sanitize_text_field( $consent_id ),
                'ip_address'  => sanitize_text_field( $ip ),
                'user_agent'  => isset( $_SERVER['HTTP_USER_AGENT'] )
                    ? sanitize_text_field( wp_unslash( $_SERVER['HTTP_USER_AGENT'] ) ) : '',
                'status'      => sanitize_text_field( $status ),
                'categories'  => wp_json_encode( $categories ),
                'regulation'  => sanitize_text_field( strtoupper( $regulation ) ),
                'created_at'  => current_time( 'mysql' ),
            ],
            [ '%s','%s','%s','%s','%s','%s','%s' ]
        );
    }

    /* ── Obtener registros recientes ── */
    public static function get_recent( int $limit = 50 ): array {
        global $wpdb;
        return $wpdb->get_results( $wpdb->prepare(
            "SELECT * FROM {$wpdb->prefix}bcm_consent_logs ORDER BY created_at DESC LIMIT %d",
            $limit
        ), ARRAY_A );
    }

    /* ── Estadísticas ── */
    public static function get_stats(): array {
        global $wpdb;
        $total    = (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$wpdb->prefix}bcm_consent_logs" );
        $accepted = (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$wpdb->prefix}bcm_consent_logs WHERE status = 'accepted'" );
        $rejected = (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$wpdb->prefix}bcm_consent_logs WHERE status = 'rejected'" );
        $custom   = (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$wpdb->prefix}bcm_consent_logs WHERE status = 'custom'" );

        return [
            'total'    => $total,
            'accepted' => $accepted,
            'rejected' => $rejected,
            'custom'   => $custom,
            'rate'     => $total > 0 ? round( ( $accepted / $total ) * 100, 1 ) : 0,
        ];
    }

    /* ── v1.3.0: Exportar a CSV (GDPR Art. 17 / auditoría) ── */
    public static function export_csv(): void {
        global $wpdb;

        $logs = $wpdb->get_results(
            "SELECT * FROM {$wpdb->prefix}bcm_consent_logs ORDER BY created_at DESC",
            ARRAY_A
        );

        $filename = 'consent-log-' . gmdate( 'Y-m-d' ) . '.csv';

        header( 'Content-Type: text/csv; charset=UTF-8' );
        header( 'Content-Disposition: attachment; filename="' . $filename . '"' );
        header( 'Pragma: no-cache' );
        header( 'Expires: 0' );

        $out = fopen( 'php://output', 'w' );
        fprintf( $out, chr(0xEF).chr(0xBB).chr(0xBF) ); // BOM UTF-8

        fputcsv( $out, [ 'ID', 'Consent ID', 'IP Address', 'User Agent', 'Status', 'Categories', 'Regulation', 'Date (UTC)' ] );

        foreach ( $logs as $row ) {
            fputcsv( $out, [
                $row['id'],
                $row['consent_id'],
                $row['ip_address'],
                $row['user_agent'],
                $row['status'],
                $row['categories'],
                $row['regulation'] ?? 'GDPR',
                $row['created_at'],
            ]);
        }

        fclose( $out );
        exit;
    }

    /* ── v1.3.0: Eliminar registros por IP (GDPR Art. 17 — derecho de supresión) ──
     *
     * FIX v2.0.5: si ip_hash está activo los registros se guardaron hasheados,
     * por lo que hay que transformar el parámetro entrante con el mismo algoritmo
     * antes de buscar. De lo contrario ningún registro coincidiría y la solicitud
     * de borrado del interesado quedaría sin efecto, incumpliendo el Art. 17 GDPR.
     */
    public static function delete_by_ip( string $ip ): int {
        global $wpdb;

        $search_value = BCM_Settings::get( 'ip_hash' )
            ? self::hash_ip( sanitize_text_field( $ip ) )
            : sanitize_text_field( $ip );

        return (int) $wpdb->delete(
            $wpdb->prefix . 'bcm_consent_logs',
            [ 'ip_address' => $search_value ],
            [ '%s' ]
        );
    }

    /* ── Obtener IP real del visitante ── */
    private static function get_ip(): string {
        $keys = [ 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR' ];
        foreach ( $keys as $k ) {
            if ( ! empty( $_SERVER[ $k ] ) ) {
                $ip = sanitize_text_field( wp_unslash( $_SERVER[ $k ] ) );
                return trim( explode( ',', $ip )[0] );
            }
        }
        return '';
    }

    /**
     * FIX v2.0.5 — Seudonimiza la IP mediante hash SHA-256.
     *
     * El resultado es irreversible (one-way) y tiene longitud fija (64 hex chars),
     * lo que lo convierte en un seudónimo conforme al Considerando 26 del GDPR y a
     * las recomendaciones del ENISA sobre técnicas de seudonimización (2019).
     *
     * Se añade un salt estático derivado del secret de WordPress para evitar
     * ataques de rainbow-table sobre el espacio limitado de direcciones IPv4
     * (~4 mil millones de valores posibles sin salt serían pre-computables).
     */
    private static function hash_ip( string $ip ): string {
        if ( empty( $ip ) ) return '';
        $salt = defined( 'LOGGED_IN_KEY' ) ? LOGGED_IN_KEY : wp_salt( 'logged_in' );
        return hash( 'sha256', $salt . $ip );
    }

    /**
     * FIX v1.5.0 — Anonimiza una dirección IP para cumplir con el principio de
     * minimización de datos del GDPR (Art. 5.1.e) y recomendaciones de la AEPD.
     *
     * IPv4: sustituye el último octeto por "0"  → "192.168.1.xxx"
     * IPv6: sustituye los últimos 8 grupos por "::"  → "2001:db8::"
     */
    private static function anonymize_ip( string $ip ): string {
        if ( empty( $ip ) ) return '';

        /* IPv4 */
        if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 ) ) {
            $parts    = explode( '.', $ip );
            $parts[3] = 'xxx';
            return implode( '.', $parts );
        }

        /* IPv6 */
        if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6 ) ) {
            /* Expandir la dirección completa y borrar la segunda mitad */
            $full = inet_ntop( inet_pton( $ip ) );
            if ( $full ) {
                $groups    = explode( ':', $full );
                $groups[4] = $groups[5] = $groups[6] = $groups[7] = '0000';
                return implode( ':', array_slice( $groups, 0, 4 ) ) . '::';
            }
        }

        return '';
    }
}
