<?php
/**
 * Plantilla de Perfil Público de Usuario — BloomScans
 * Disponible en: /usuario/{user_login}/
 */

if ( ! defined( 'ABSPATH' ) ) exit;

global $bup_profile_user;
$user = $bup_profile_user;
if ( ! $user ) exit;

$user_id      = $user->ID;
$display_name = esc_html( $user->display_name );
$user_login   = esc_attr( $user->user_login );

// Avatar: Prioridad 1: msg_custom_avatar (URL externa), Prioridad 2: Gravatar
$custom_avatar = get_user_meta( $user_id, 'msg_custom_avatar', true );
$avatar_url    = $custom_avatar ? esc_url( $custom_avatar ) : get_avatar_url( $user_id, [ 'size' => 120 ] );

$bio          = esc_html( get_user_meta( $user_id, 'description', true ) );
$role_label   = BUP_Ajax::get_role_label( $user );
$role_color   = BUP_Ajax::get_role_color( $user );
$registered   = date_i18n( 'F Y', strtotime( $user->user_registered ) );
$last_seen    = BUP_Profile::get_last_seen( $user );
$stats        = BUP_Profile::get_stats( $user_id );
$banner_url   = get_user_meta( $user_id, 'bup_banner_url', true );
$is_self      = is_user_logged_in() && get_current_user_id() === $user_id;

// Fecha de registro
$registered_date = date_i18n( 'M Y', strtotime( $user->user_registered ) );

// Head del documento
get_template_part( 'header' );
?>
<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
    <meta charset="<?php bloginfo( 'charset' ); ?>">
    <title><?php echo $display_name; ?> — <?php bloginfo( 'name' ); ?></title>
    <meta name="description" content="Perfil público de <?php echo $display_name; ?> en <?php bloginfo( 'name' ); ?>">
    <meta name="robots" content="noindex,follow">
    <?php wp_head(); ?>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
</head>
<body class="bup-profile-page" <?php body_class(); ?>>
<?php wp_body_open(); ?>

<div id="bup-profile" data-user-id="<?php echo esc_attr( $user_id ); ?>">

    <!-- ══════════════════ BANNER / CABECERA ══════════════════ -->
    <div class="bup-banner" <?php if ( $banner_url ): ?>style="background-image: url('<?php echo esc_url( $banner_url ); ?>')"<?php endif; ?>>
        <div class="bup-banner-overlay"></div>
    </div>

    <div class="bup-profile-wrap">

        <!-- Avatar + info principal -->
        <div class="bup-profile-header">
            <div class="bup-avatar-wrap">
                <img src="<?php echo esc_url( $avatar_url ); ?>"
                     alt="<?php echo $display_name; ?>"
                     class="bup-avatar"
                     width="120" height="120">
                <span class="bup-online-dot" title="<?php echo esc_attr( $last_seen ); ?>"></span>
            </div>

            <div class="bup-identity">
                <h1 class="bup-display-name"><?php echo $display_name; ?></h1>
                <span class="bup-username">@<?php echo $user_login; ?></span>
                <span class="bup-role-badge" style="--role-color: <?php echo esc_attr( $role_color ); ?>">
                    <?php echo esc_html( $role_label ); ?>
                </span>
                <span class="bup-registered-date">
                    Miembro desde: <strong><?php echo esc_html( $registered_date ); ?></strong>
                </span>
            </div>

            <?php if ( ! $is_self ): ?>
            <div class="bup-header-actions">
                <button class="msg-follow-btn bup-follow-btn" data-id="<?php echo $user_id; ?>">
                    <svg viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
                    Seguir
                </button>
            </div>
            <?php endif; ?>
        </div>

        <!-- ══════════ CONTENIDO EN DOS COLUMNAS ══════════ -->
        <div class="bup-layout">

            <!-- Columna lateral -->
            <aside class="bup-sidebar">

                <!-- Sobre mí -->
                <div class="bup-card bup-bio-card">
                    <h2 class="bup-card-title">
                        <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>
                        Sobre mí
                    </h2>
                    <?php if ( $bio ): ?>
                        <p class="bup-bio-text"><?php echo nl2br( $bio ); ?></p>
                    <?php else: ?>
                        <p class="bup-bio-empty">Este usuario no ha añadido una biografía.</p>
                    <?php endif; ?>
                </div>

                <!-- Stats -->
                <div class="bup-card bup-stats-card">
                    <h2 class="bup-card-title">
                        <svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 4-4"/></svg>
                        Estadísticas
                    </h2>
                    <ul class="bup-stat-list">
                        <li class="bup-stat">
                            <span class="bup-stat-num"><?php echo number_format_i18n( $stats['comments'] ); ?></span>
                            <span class="bup-stat-label">Comentarios</span>
                        </li>
                        <?php if ( $stats['chapters'] > 0 ): ?>
                        <li class="bup-stat">
                            <span class="bup-stat-num"><?php echo number_format_i18n( $stats['chapters'] ); ?></span>
                            <span class="bup-stat-label">Capítulos subidos</span>
                        </li>
                        <?php endif; ?>
                        <?php if ( $stats['coins'] > 0 ): ?>
                        <li class="bup-stat">
                            <span class="bup-stat-num"><?php echo number_format_i18n( $stats['coins'] ); ?></span>
                            <span class="bup-stat-label">Monedas recibidas</span>
                        </li>
                        <?php endif; ?>
                        <li class="bup-stat">
                            <span class="bup-stat-num"><?php echo number_format_i18n( $stats['wall'] ); ?></span>
                            <span class="bup-stat-label">Mensajes recibidos</span>
                        </li>
                    </ul>
                </div>

                <!-- Info -->
                <div class="bup-card bup-info-card">
                    <h2 class="bup-card-title">
                        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
                        Información
                    </h2>
                    <ul class="bup-info-list">
                        <li>
                            <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                            Miembro desde <strong><?php echo $registered; ?></strong>
                        </li>
                        <li>
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            Última actividad: <strong><?php echo $last_seen; ?></strong>
                        </li>
                    </ul>
                </div>

            </aside>

            <!-- Columna principal -->
            <main class="bup-main">

                <!-- ══ MURO DE MENSAJES ══ -->
                <section class="bup-card bup-wall-card">
                    <h2 class="bup-card-title">
                        <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                        Muro de mensajes
                    </h2>

                    <?php if ( is_user_logged_in() ): ?>
                    <form id="bup-wall-form" class="bup-wall-form">
                        <div class="bup-wall-input-row">
                            <img src="<?php echo esc_url( get_avatar_url( get_current_user_id(), [ 'size' => 40 ] ) ); ?>"
                                 alt="Tú" class="bup-form-avatar" width="40" height="40">
                            <textarea id="bup-wall-msg"
                                      class="bup-wall-textarea"
                                      placeholder="Escribe un mensaje en el muro de <?php echo $display_name; ?>…"
                                      maxlength="500"
                                      rows="2"></textarea>
                        </div>
                        <div class="bup-wall-actions">
                            <span id="bup-char-count" class="bup-char-count">0 / 500</span>
                            <button type="submit" class="bup-send-btn" id="bup-wall-submit">
                                <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                                Enviar
                            </button>
                        </div>
                        <p id="bup-wall-error" class="bup-wall-error" style="display:none"></p>
                    </form>
                    <?php else: ?>
                    <p class="bup-wall-login-notice">
                        <a href="<?php echo esc_url( home_url( '/login' ) ); ?>">Inicia sesión</a>
                        para dejar un mensaje en este muro.
                    </p>
                    <?php endif; ?>

                    <!-- Mensajes del muro -->
                    <div id="bup-wall-messages" class="bup-wall-messages"></div>

                    <button id="bup-load-more" class="bup-load-more" style="display:none">
                        Cargar más mensajes
                    </button>
                </section>

            </main>

        </div><!-- .bup-layout -->
    </div><!-- .bup-profile-wrap -->
</div><!-- #bup-profile -->

<?php wp_footer(); ?>
</body>
</html>
