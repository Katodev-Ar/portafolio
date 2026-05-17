<?php
/**
 * BUP_Profile — Perfil público de usuario.
 *
 * Ruta: /usuario/{user_login}/
 * Genera la URL de perfil y registra el rewrite rule.
 */
class BUP_Profile {

    /** Slug base de la URL de perfil */
    const SLUG = 'usuario';

    public static function init(): void {
        add_rewrite_rule(
            '^' . self::SLUG . '/([^/]+)/?$',
            'index.php?bup_user=$matches[1]',
            'top'
        );
        add_filter( 'query_vars', [ __CLASS__, 'add_query_var' ] );
        add_action( 'template_redirect', [ __CLASS__, 'maybe_render_profile' ] );
        add_action( 'template_redirect', [ __CLASS__, 'redirect_author_archive' ] );
        add_filter( 'get_comment_author_url', [ __CLASS__, 'filter_comment_author_url' ], 10, 3 );
    }

    /**
     * Filtra el enlace del autor del comentario para que apunte al perfil social.
     */
    public static function filter_comment_author_url( string $url, string $author, WP_Comment $comment ): string {
        if ( ! empty( $comment->user_id ) ) {
            $user = get_userdata( $comment->user_id );
            if ( $user ) {
                return self::get_profile_url( $user->user_login );
            }
        }
        return $url;
    }

    public static function redirect_author_archive(): void {
        if ( is_author() ) {
            $author = get_queried_object();
            if ( $author instanceof WP_User ) {
                wp_safe_redirect( self::get_profile_url( $author->user_login ), 301 );
                exit;
            }
        }
    }

    public static function add_query_var( array $vars ): array {
        $vars[] = 'bup_user';
        return $vars;
    }

    public static function maybe_render_profile(): void {
        $user_login = get_query_var( 'bup_user' );
        if ( ! $user_login ) return;

        $user = get_user_by( 'login', $user_login );
        if ( ! $user ) {
            global $wp_query;
            $wp_query->set_404();
            status_header( 404 );
            get_template_part( '404' );
            exit;
        }

        // Cargar la plantilla del perfil
        $template = BUP_DIR . 'templates/profile.php';
        if ( file_exists( $template ) ) {
            // Pasar datos al template via global
            global $bup_profile_user;
            $bup_profile_user = $user;
            include $template;
            exit;
        }
    }

    /** Devuelve la URL pública del perfil de un usuario. */
    public static function get_profile_url( string $user_login ): string {
        return home_url( '/' . self::SLUG . '/' . rawurlencode( $user_login ) . '/' );
    }

    /** Devuelve estadísticas básicas del usuario. */
    public static function get_stats( int $user_id ): array {
        global $wpdb;

        // Número de comentarios
        $comments = (int) $wpdb->get_var( $wpdb->prepare(
            "SELECT COUNT(*) FROM {$wpdb->comments}
              WHERE user_id = %d AND comment_approved = '1'",
            $user_id
        ) );

        // Número de capítulos subidos (si es scanlator o admin)
        $chapters = (int) $wpdb->get_var( $wpdb->prepare(
            "SELECT COUNT(*) FROM {$wpdb->posts}
              WHERE post_author = %d
                AND post_type   = 'post'
                AND post_status = 'publish'",
            $user_id
        ) );

        // Número de mensajes de muro recibidos
        $wall_count = BUP_DB::count_messages( $user_id );

        // Donaciones (Monedas) si es Scanlator
        $coins = 0;
        $is_scan = in_array( 'scan_group', (array) get_userdata($user_id)->roles );
        if ( $is_scan ) {
            $coins = (int) $wpdb->get_var( $wpdb->prepare(
                "SELECT SUM(amount) FROM {$wpdb->prefix}scan_donations WHERE scan_id = (
                    SELECT id FROM {$wpdb->prefix}manga_scan_groups WHERE user_id = %d LIMIT 1
                )",
                $user_id
            ) );
        }

        return [
            'comments' => $comments,
            'chapters' => $chapters,
            'wall'     => $wall_count,
            'coins'    => $coins,
        ];
    }

    /** Texto de "última vez visto" (basado en user_registered por ahora). */
    public static function get_last_seen( WP_User $user ): string {
        // WordPress no guarda last_login nativo; usamos user meta si existe
        $last = get_user_meta( $user->ID, 'bloom_last_login', true );
        if ( $last ) {
            return human_time_diff( (int) $last ) . ' atrás';
        }
        return 'Desconocido';
    }
}
