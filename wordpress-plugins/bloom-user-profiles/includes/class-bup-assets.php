<?php
/**
 * BUP_Assets — Encola CSS y JS del plugin.
 *
 * Integraciones clave encontradas analizando el sitio real:
 *
 *  1. manga-scan-groups-v5 ya localiza `window.msgAjax` con ajaxurl + nonce.
 *     Nuestro JS puede leer `window.msgAjax.ajaxurl` directamente.
 *
 *  2. El tema usa `ts_configs.get('general.ajaxUrl')` (localizado via jquery-js-after).
 *     Nuestro bup-search.js ya lee ese objeto para las queries de mangas.
 *
 *  3. bloom-navbar monta los inputs de búsqueda de forma asíncrona con JS.
 *     Nuestro bup-search.js usa MutationObserver para detectarlos.
 *
 *  4. No hay dependencia de jQuery en nuestros scripts — usamos fetch() nativo,
 *     igual que lo hace manga-scan-groups-v5 en su sistema de follows.
 */
class BUP_Assets {

    public static function enqueue(): void {
        $is_profile = (bool) get_query_var( 'bup_user' );

        // Detectar reader (mismo criterio que bloom-navbar) para no cargar en capítulos
        $is_reader = is_singular( 'post' );
        if ( $is_reader ) return;

        // ── CSS base (siempre, fuera del reader) ──
        wp_enqueue_style(
            'bup-styles',
            BUP_URL . 'assets/bup.css',
            [ 'manga-scan-groups-css' ],   // dep: estilos del plugin de grupos ya cargado
            BUP_VERSION
        );

        // ── JS del buscador (siempre fuera del reader) ──
        wp_enqueue_script(
            'bup-search',
            BUP_URL . 'assets/bup-search.js',
            [],          // sin jQuery — usa fetch() nativo
            BUP_VERSION,
            true         // footer
        );

        // Localizar datos para bup-search.js
        // Usamos window.msgAjax si ya está disponible (manga-scan-groups-v5);
        // como fallback pasamos el ajaxUrl directo.
        wp_localize_script( 'bup-search', 'bupData', [
            'ajaxUrl'     => admin_url( 'admin-ajax.php' ),
            'siteUrl'     => home_url(),
            'isLoggedIn'  => is_user_logged_in() ? '1' : '',
            'wallNonce'   => $is_profile ? wp_create_nonce( 'bup_wall_nonce' ) : '',
            'profileSlug' => BUP_Profile::SLUG,
            // Pasamos el nonce de manga-scan-groups si está disponible
            // (no requerido para búsqueda pero sí para acciones futuras)
        ] );

        // ── JS del perfil (solo en la página de perfil) ──
        if ( $is_profile ) {
            wp_enqueue_script(
                'bup-profile',
                BUP_URL . 'assets/bup-profile.js',
                [ 'bup-search' ],
                BUP_VERSION,
                true
            );
        }
    }
}
