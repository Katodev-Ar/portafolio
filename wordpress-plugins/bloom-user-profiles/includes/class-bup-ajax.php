<?php
/**
 * BUP_Ajax — Endpoints AJAX del plugin.
 *
 *  · bloom_search_users  — Búsqueda de usuarios (pública, sin login).
 *  · bup_wall_post       — Publicar mensaje en el muro (requiere login).
 *  · bup_wall_load       — Cargar mensajes del muro (pública).
 */
class BUP_Ajax {

    /* ═══════════════════════════════════════════════
     *  Búsqueda de usuarios
     * ═══════════════════════════════════════════════ */

    public static function search_users(): void {
        $term = isset( $_GET['term'] ) ? sanitize_text_field( wp_unslash( $_GET['term'] ) ) : '';
        if ( strlen( $term ) < 2 ) {
            wp_send_json_success( [] );
        }

        global $wpdb;
        $query = new WP_User_Query( [
            'search'         => '*' . $wpdb->esc_like( $term ) . '*',
            'search_columns' => [ 'user_login', 'display_name' ],
            'number'         => 8,
            'orderby'        => 'display_name',
            'order'          => 'ASC',
        ] );

        $users = [];
        foreach ( $query->get_results() as $user ) {
            $custom_avatar = get_user_meta( $user->ID, 'msg_custom_avatar', true );
            $avatar_url    = $custom_avatar ? esc_url( $custom_avatar ) : get_avatar_url( $user->ID, [ 'size' => 48 ] );

            $role_label = self::get_role_label( $user );
            $role_color = self::get_role_color( $user );

            $users[] = [
                'id'         => $user->ID,
                'name'       => $user->display_name,
                'login'      => $user->user_login,
                'avatar'     => $avatar_url,
                'role'       => $role_label,
                'role_color' => $role_color,
                'url'        => BUP_Profile::get_profile_url( $user->user_login ),
            ];
        }

        wp_send_json_success( $users );
    }

    /* ═══════════════════════════════════════════════
     *  Muro: publicar mensaje
     * ═══════════════════════════════════════════════ */

    public static function wall_post(): void {
        if ( ! is_user_logged_in() ) {
            wp_send_json_error( [ 'message' => 'Debes iniciar sesión para dejar un mensaje.' ], 403 );
        }

        check_ajax_referer( 'bup_wall_nonce', 'nonce' );

        $profile_id = isset( $_POST['profile_id'] ) ? absint( $_POST['profile_id'] ) : 0;
        $message    = isset( $_POST['message'] )    ? sanitize_textarea_field( wp_unslash( $_POST['message'] ) ) : '';

        if ( ! $profile_id || ! get_userdata( $profile_id ) ) {
            wp_send_json_error( [ 'message' => 'Usuario no encontrado.' ], 404 );
        }

        if ( strlen( $message ) < 3 || strlen( $message ) > 500 ) {
            wp_send_json_error( [ 'message' => 'El mensaje debe tener entre 3 y 500 caracteres.' ] );
        }

        $author_id = get_current_user_id();

        // Anti-spam: max 3 mensajes en 5 minutos por mismo autor/perfil
        global $wpdb;
        $table = $wpdb->prefix . BUP_DB::TABLE;
        $recent = (int) $wpdb->get_var( $wpdb->prepare(
            "SELECT COUNT(*) FROM {$table}
              WHERE author_id = %d AND profile_id = %d
                AND created_at > DATE_SUB(NOW(), INTERVAL 5 MINUTE)",
            $author_id, $profile_id
        ) );
        if ( $recent >= 3 ) {
            wp_send_json_error( [ 'message' => 'Espera unos minutos antes de enviar más mensajes.' ] );
        }

        $id = BUP_DB::insert_message( $profile_id, $author_id, $message );
        if ( is_wp_error( $id ) ) {
            wp_send_json_error( [ 'message' => $id->get_error_message() ] );
        }

        $author    = get_userdata( $author_id );
        $avatar    = get_avatar_url( $author_id, [ 'size' => 40 ] );
        $role_label = self::get_role_label( $author );
        $role_color = self::get_role_color( $author );

        wp_send_json_success( [
            'id'           => $id,
            'author_name'  => $author->display_name,
            'author_url'   => BUP_Profile::get_profile_url( $author->user_login ),
            'avatar'       => $avatar,
            'role'         => $role_label,
            'role_color'   => $role_color,
            'message'      => esc_html( $message ),
            'created_at'   => human_time_diff( time() ) . ' atrás',
        ] );
    }

    /* ═══════════════════════════════════════════════
     *  Muro: cargar mensajes
     * ═══════════════════════════════════════════════ */

    public static function wall_load(): void {
        $profile_id = isset( $_GET['profile_id'] ) ? absint( $_GET['profile_id'] ) : 0;
        $page       = isset( $_GET['page'] )        ? max( 1, absint( $_GET['page'] ) ) : 1;

        if ( ! $profile_id ) {
            wp_send_json_error( [ 'message' => 'Perfil inválido.' ] );
        }

        $messages = BUP_DB::get_messages( $profile_id, $page );
        $total    = BUP_DB::count_messages( $profile_id );

        $formatted = [];
        foreach ( $messages as $row ) {
            $author    = get_userdata( (int) $row['author_id'] );
            $role_label = self::get_role_label( $author );
            $role_color = self::get_role_color( $author );

            $formatted[] = [
                'id'          => $row['id'],
                'author_name' => $row['display_name'],
                'author_url'  => BUP_Profile::get_profile_url( $row['user_login'] ),
                'avatar'      => get_avatar_url( (int) $row['author_id'], [ 'size' => 40 ] ),
                'role'        => $role_label,
                'role_color'  => $role_color,
                'message'     => esc_html( $row['message'] ),
                'created_at'  => human_time_diff( strtotime( $row['created_at'] ) ) . ' atrás',
            ];
        }

        wp_send_json_success( [
            'messages'  => $formatted,
            'total'     => $total,
            'page'      => $page,
            'has_more'  => ( $page * 10 ) < $total,
        ] );
    }

    /* ═══════════════════════════════════════════════
     *  Helpers de roles
     * ═══════════════════════════════════════════════ */

    public static function get_role_label( $user ): string {
        if ( ! $user instanceof WP_User ) return 'Lector';

        $caps = (array) $user->caps;
        if ( isset( $caps['administrator'] ) ) return 'Admin';
        if ( isset( $caps['editor'] ) )        return 'Editor';
        if ( isset( $caps['scan_group'] ) )    return 'Scanlator';
        if ( isset( $caps['subscriber'] ) )    return 'Lector';
        // Roles VIP específicos del sitio
        if ( in_array( 'vip', (array) $user->roles, true ) )  return 'VIP';

        $roles = (array) $user->roles;
        return ! empty( $roles ) ? ucfirst( $roles[0] ) : 'Lector';
    }

    public static function get_role_color( $user ): string {
        $label = self::get_role_label( $user );
        return match ( $label ) {
            'Admin'      => '#ff6b6b',
            'Editor'     => '#ffa94d',
            'Scanlator'  => '#00d4aa',
            'VIP'        => '#cc5de8',
            default      => '#74c0fc',
        };
    }
}
