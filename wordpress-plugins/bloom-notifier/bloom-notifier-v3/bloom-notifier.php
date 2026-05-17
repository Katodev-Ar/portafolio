<?php
/**
 * Plugin Name: Bloom Scans Notifier
 * Plugin URI: https://bloomscans.com/
 * Description: Publica notificaciones automáticas en Facebook y Discord cuando se sube un nuevo capítulo. Integrado con Manga Scan Groups.
 * Version: 3.0.0
 * Author: BloomScans
 * License: GPL v2 or later
 * Text Domain: bloom-notifier
 */

if (!defined('ABSPATH')) {
    exit;
}

define('BSN_VERSION', '3.0.0');
define('BSN_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('BSN_PLUGIN_URL', plugin_dir_url(__FILE__));

class Bloom_Scans_Notifier {

    private static $instance = null;

    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct() {
        add_action('admin_menu', array($this, 'add_settings_page'));
        add_action('admin_init', array($this, 'register_settings'));
        add_action('add_meta_boxes', array($this, 'add_meta_box'));
        add_action('wp_insert_post', array($this, 'on_chapter_published'), 20, 3);
        add_action('wp_ajax_bsn_send_notification', array($this, 'ajax_send_notification'));
        add_action('admin_enqueue_scripts', array($this, 'enqueue_assets'));

        // Guardar campos extra del grupo (webhook + facebook) al guardar grupo
        add_action('admin_init', array($this, 'save_group_notifier_fields'));

        // Inyectar campos en el modal de edición de grupos
        add_action('admin_footer', array($this, 'inject_notifier_fields_in_groups'));
    }

    // ─────────────────────────────────────────────
    // ASSETS
    // ─────────────────────────────────────────────

    public function enqueue_assets($hook) {
        global $post;
        if (!in_array($hook, array('post.php', 'post-new.php'))) return;
        if (!$post || $post->post_type !== 'manga') return;

        wp_enqueue_media();

        wp_add_inline_style('wp-admin', '
            #bsn-meta-box label { font-weight: 600; display: block; margin-bottom: 4px; }
            #bsn-meta-box input[type="text"], #bsn-meta-box input[type="url"] { width: 100%; margin-bottom: 6px; }
            .bsn-img-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
            .bsn-img-row img { width: 48px; height: 48px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd; display: none; }
            .bsn-img-row input[type="hidden"] { display: none; }
            .bsn-select-img { font-size: 11px !important; padding: 2px 6px !important; }
            .bsn-remove-img { font-size: 11px !important; padding: 2px 6px !important; color: #cc0000 !important; display: none; }
            #bsn_send_btn { margin-top: 8px; background: #e75480; border-color: #c03060; color: #fff; }
            #bsn_send_btn:hover { background: #c03060; border-color: #a02050; }
            #bsn_result { margin-top: 8px; font-size: 12px; padding: 6px; border-radius: 4px; }
        ');
    }

    // ─────────────────────────────────────────────
    // AJUSTES GLOBALES
    // ─────────────────────────────────────────────

    public function add_settings_page() {
        add_options_page('🌸 Bloom Notifier', '🌸 Bloom Notifier', 'manage_options', 'bloom-notifier', array($this, 'render_settings_page'));
    }

    public function register_settings() {
        register_setting('bsn_settings', 'bsn_discord_webhook');
        register_setting('bsn_settings', 'bsn_fb_page_id');
        register_setting('bsn_settings', 'bsn_fb_page_token');
        register_setting('bsn_settings', 'bsn_discord_invite');
        register_setting('bsn_settings', 'bsn_auto_notify');
    }

    public function render_settings_page() {
        ?>
        <div class="wrap">
            <h1>🌸 Bloom Scans Notifier — Configuración Global</h1>
            <p style="color:#666;">Estos valores son los predeterminados del sitio. Cada grupo puede tener sus propios webhook/tokens configurados en <strong>Grupos Scan → Editar grupo</strong>, y si están definidos tendrán prioridad sobre estos.</p>
            <form method="post" action="options.php">
                <?php settings_fields('bsn_settings'); ?>
                <table class="form-table">
                    <tr>
                        <th><label>Discord Webhook URL (global)</label></th>
                        <td><input type="text" name="bsn_discord_webhook" value="<?php echo esc_attr(get_option('bsn_discord_webhook')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th><label>Link invitación Discord</label></th>
                        <td>
                            <input type="text" name="bsn_discord_invite" value="<?php echo esc_attr(get_option('bsn_discord_invite', 'https://discord.gg/6PmTZWFZ')); ?>" class="regular-text">
                            <p class="description">Se muestra al final de la publicación de Facebook.</p>
                        </td>
                    </tr>
                    <tr>
                        <th><label>Facebook Page ID (global)</label></th>
                        <td><input type="text" name="bsn_fb_page_id" value="<?php echo esc_attr(get_option('bsn_fb_page_id')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th><label>Facebook Page Access Token (global)</label></th>
                        <td><input type="password" name="bsn_fb_page_token" value="<?php echo esc_attr(get_option('bsn_fb_page_token')); ?>" class="regular-text"></td>
                    </tr>
                    <tr>
                        <th><label>Notificación automática</label></th>
                        <td>
                            <label>
                                <input type="checkbox" name="bsn_auto_notify" value="1" <?php checked(get_option('bsn_auto_notify', 0), 1); ?>>
                                Publicar automáticamente al subir un capítulo
                            </label>
                        </td>
                    </tr>
                </table>
                <?php submit_button('Guardar configuración'); ?>
            </form>
        </div>
        <?php
    }

    // ─────────────────────────────────────────────
    // HELPERS: obtener credenciales por grupo/usuario
    // ─────────────────────────────────────────────

    /**
     * Obtiene el webhook de Discord para un usuario.
     * Si el usuario pertenece a un grupo con webhook propio, lo usa.
     * Fallback al webhook global.
     */
    private function get_discord_webhook_for_user($user_id = 0) {
        if ($user_id) {
            $group_webhook = get_user_meta($user_id, 'bsn_discord_webhook', true);
            if (!empty($group_webhook)) return $group_webhook;
        }
        return get_option('bsn_discord_webhook');
    }

    /**
     * Obtiene las credenciales de Facebook para un usuario.
     * Devuelve array ['page_id', 'token']
     */
    private function get_facebook_creds_for_user($user_id = 0) {
        if ($user_id) {
            $group_page_id = get_user_meta($user_id, 'bsn_fb_page_id', true);
            $group_token   = get_user_meta($user_id, 'bsn_fb_page_token', true);
            if (!empty($group_page_id) && !empty($group_token)) {
                return array('page_id' => $group_page_id, 'token' => $group_token);
            }
        }
        return array(
            'page_id' => get_option('bsn_fb_page_id'),
            'token'   => get_option('bsn_fb_page_token'),
        );
    }

    // ─────────────────────────────────────────────
    // PERMISOS Y CAMPOS POR GRUPO
    // ─────────────────────────────────────────────

    private function user_can_notify() {
        if (current_user_can('administrator')) return true;
        $user_id = get_current_user_id();
        return (bool) get_user_meta($user_id, 'bsn_can_notify', true);
    }

    /**
     * Guarda los campos del notifier al guardar un grupo desde admin-page.php
     */
    public function save_group_notifier_fields() {
        if (!isset($_POST['msg_action']) || $_POST['msg_action'] !== 'update_group') return;
        if (!current_user_can('administrator')) return;
        if (!isset($_POST['group_id'])) return;
        if (!isset($_POST['_wpnonce']) || !wp_verify_nonce($_POST['_wpnonce'], 'msg_admin_action')) return;

        $group_id = intval($_POST['group_id']);

        global $wpdb;
        $table   = $wpdb->prefix . 'manga_scan_groups';
        $user_id = $wpdb->get_var($wpdb->prepare("SELECT user_id FROM $table WHERE id = %d", $group_id));
        if (!$user_id) return;

        // Permiso general
        $can_notify = isset($_POST['bsn_can_notify']) ? 1 : 0;
        update_user_meta($user_id, 'bsn_can_notify', $can_notify);

        // Webhook de Discord propio
        $discord_webhook = isset($_POST['bsn_discord_webhook']) ? esc_url_raw(trim($_POST['bsn_discord_webhook'])) : '';
        update_user_meta($user_id, 'bsn_discord_webhook', $discord_webhook);

        // Credenciales de Facebook propias
        $fb_page_id = isset($_POST['bsn_fb_page_id']) ? sanitize_text_field(trim($_POST['bsn_fb_page_id'])) : '';
        $fb_token   = isset($_POST['bsn_fb_page_token']) ? sanitize_text_field(trim($_POST['bsn_fb_page_token'])) : '';
        update_user_meta($user_id, 'bsn_fb_page_id',    $fb_page_id);
        update_user_meta($user_id, 'bsn_fb_page_token', $fb_token);
    }

    /**
     * Inyecta los campos del notifier en el modal de edición de grupos
     */
    public function inject_notifier_fields_in_groups() {
        $screen = get_current_screen();
        if (!$screen || strpos($screen->id, 'manga-scan') === false) return;
        if (!current_user_can('administrator')) return;

        global $wpdb;
        $table  = $wpdb->prefix . 'manga_scan_groups';
        $groups = $wpdb->get_results("SELECT id, user_id FROM $table");

        // Construir mapa: group_id -> { can_notify, discord_webhook, fb_page_id, fb_page_token }
        $data = array();
        foreach ($groups as $g) {
            $data[$g->id] = array(
                'can_notify'       => (bool) get_user_meta($g->user_id, 'bsn_can_notify', true),
                'discord_webhook'  => (string) get_user_meta($g->user_id, 'bsn_discord_webhook', true),
                'fb_page_id'       => (string) get_user_meta($g->user_id, 'bsn_fb_page_id', true),
                // No enviamos el token al JS por seguridad — se muestra enmascarado
                'fb_has_token'     => !empty(get_user_meta($g->user_id, 'bsn_fb_page_token', true)),
            );
        }
        ?>
        <script>
        jQuery(document).ready(function($) {
            var bsnData = <?php echo wp_json_encode($data); ?>;

            var $modal    = $('#msg-edit-modal');
            var $form     = $modal.find('.msg-modal-form');
            var $footer   = $modal.find('.msg-modal-footer');

            // Inyectar sección del notifier si no existe
            if ($form.length && !$('#bsn-group-fields').length) {
                var html = '<div id="bsn-group-fields" style="border-top:1px solid #e0e4ef;margin-top:18px;padding-top:16px;">' +
                    '<h3 style="font-size:14px;font-weight:700;color:#1a1a2e;margin:0 0 12px;">🌸 Notificaciones Discord / Facebook</h3>' +

                    '<div class="msg-field" style="margin-bottom:10px;">' +
                    '<label class="msg-label" for="bsn_can_notify_check">Permitir que este grupo publique notificaciones</label>' +
                    '<label style="display:flex;align-items:center;gap:7px;cursor:pointer;">' +
                    '<input type="checkbox" name="bsn_can_notify" id="bsn_can_notify_check" value="1">' +
                    '<span style="font-size:12px;color:#666;">Habilitado</span>' +
                    '</label>' +
                    '</div>' +

                    '<div class="msg-field" style="margin-bottom:10px;">' +
                    '<label class="msg-label" for="bsn_group_discord_webhook">Discord Webhook URL (propio del grupo)</label>' +
                    '<input type="text" name="bsn_discord_webhook" id="bsn_group_discord_webhook" class="msg-input" placeholder="https://discord.com/api/webhooks/... (dejar vacío para usar el global)">' +
                    '<span class="msg-hint">Si está vacío se usará el webhook global del sitio.</span>' +
                    '</div>' +

                    '<div class="msg-field" style="margin-bottom:10px;">' +
                    '<label class="msg-label" for="bsn_group_fb_page_id">Facebook Page ID (propio del grupo)</label>' +
                    '<input type="text" name="bsn_fb_page_id" id="bsn_group_fb_page_id" class="msg-input" placeholder="Ej: 123456789 (dejar vacío para usar el global)">' +
                    '</div>' +

                    '<div class="msg-field" style="margin-bottom:4px;">' +
                    '<label class="msg-label" for="bsn_group_fb_page_token">Facebook Page Access Token (propio del grupo)</label>' +
                    '<input type="password" name="bsn_fb_page_token" id="bsn_group_fb_page_token" class="msg-input" placeholder="Dejar vacío para no cambiar / usar el global">' +
                    '<span class="msg-hint" id="bsn_fb_token_status"></span>' +
                    '</div>' +
                    '</div>';

                $footer.before(html);
            }

            // Al abrir el modal, cargar los valores del grupo
            $(document).on('click', '.msg-edit-group', function() {
                var groupId = $(this).data('group-id');
                var d = bsnData[groupId] || {};

                $('#bsn_can_notify_check').prop('checked', !!d.can_notify);
                $('#bsn_group_discord_webhook').val(d.discord_webhook || '');
                $('#bsn_group_fb_page_id').val(d.fb_page_id || '');
                $('#bsn_group_fb_page_token').val(''); // nunca pre-rellenar token
                $('#bsn_fb_token_status').text(d.fb_has_token ? '✅ Ya tiene un token guardado. Dejar vacío para mantenerlo.' : '⚠️ Sin token. Ingresar uno para activar Facebook.');
            });
        });
        </script>
        <?php
    }

    // ─────────────────────────────────────────────
    // META BOX
    // ─────────────────────────────────────────────

    public function add_meta_box() {
        if (!$this->user_can_notify()) return;
        add_meta_box('bsn_notifier', '🌸 Publicar Notificación', array($this, 'render_meta_box'), 'manga', 'side', 'default');
    }

    public function render_meta_box($post) {
        wp_nonce_field('bsn_send_nonce', 'bsn_nonce');
        $manga_url = get_permalink($post->ID);
        ?>
        <div id="bsn-meta-box">
            <p style="font-size:11px;color:#888;margin-top:0;">Completa y envía a Facebook y/o Discord.</p>

            <label>📖 Capítulo(s):</label>
            <input type="text" id="bsn_chapters_text" placeholder="Ej: 24 y 25">

            <label>🏷️ Link de tu web (auto):</label>
            <input type="text" id="bsn_main_link" value="<?php echo esc_attr($manga_url); ?>" readonly style="background:#f0f0f0;font-size:11px;">

            <label style="margin-top:6px;">🔗 Link extra 1 (opcional):</label>
            <input type="url" id="bsn_link_1" placeholder="https://...">

            <label>🔗 Link extra 2 (opcional):</label>
            <input type="url" id="bsn_link_2" placeholder="https://...">

            <label>🔗 Link extra 3 (opcional):</label>
            <input type="url" id="bsn_link_3" placeholder="https://...">

            <label style="margin-top:6px;">🖼️ Imágenes (máx 4):</label>
            <?php for ($i = 1; $i <= 4; $i++): ?>
            <div class="bsn-img-row" id="bsn_img_row_<?php echo $i; ?>">
                <img id="bsn_img_preview_<?php echo $i; ?>" src="" alt="">
                <input type="hidden" id="bsn_img_url_<?php echo $i; ?>" value="">
                <button type="button" class="button bsn-select-img" data-index="<?php echo $i; ?>">+ Imagen <?php echo $i; ?></button>
                <button type="button" class="button bsn-remove-img" data-index="<?php echo $i; ?>">✕</button>
            </div>
            <?php endfor; ?>

            <div style="margin-top:8px;">
                <label style="font-weight:normal;display:inline;"><input type="checkbox" id="bsn_send_discord" checked> 📣 Discord</label>
                &nbsp;&nbsp;
                <label style="font-weight:normal;display:inline;"><input type="checkbox" id="bsn_send_facebook" checked> 📘 Facebook</label>
            </div>

            <button type="button" id="bsn_send_btn" class="button button-primary widefat">
                🌸 Publicar Notificación
            </button>

            <div id="bsn_result"></div>
        </div>

        <script>
        jQuery(document).ready(function($) {

            $('.bsn-select-img').on('click', function() {
                var index = $(this).data('index');
                var frame = wp.media({
                    title: 'Seleccionar imagen ' + index,
                    button: { text: 'Usar esta imagen' },
                    multiple: false
                });
                frame.on('select', function() {
                    var attachment = frame.state().get('selection').first().toJSON();
                    var url = attachment.url;
                    $('#bsn_img_url_' + index).val(url);
                    $('#bsn_img_preview_' + index).attr('src', url).show();
                    $('#bsn_img_row_' + index + ' .bsn-remove-img').show();
                    $('#bsn_img_row_' + index + ' .bsn-select-img').text('✎ Cambiar');
                });
                frame.open();
            });

            $('.bsn-remove-img').on('click', function() {
                var index = $(this).data('index');
                $('#bsn_img_url_' + index).val('');
                $('#bsn_img_preview_' + index).attr('src', '').hide();
                $(this).hide();
                $('#bsn_img_row_' + index + ' .bsn-select-img').text('+ Imagen ' + index);
            });

            $('#bsn_send_btn').on('click', function() {
                var btn = $(this);
                btn.prop('disabled', true).text('Enviando...');
                $('#bsn_result').html('');

                var images = [];
                for (var i = 1; i <= 4; i++) {
                    var url = $('#bsn_img_url_' + i).val().trim();
                    if (url) images.push(url);
                }

                var extra_links = [
                    $('#bsn_link_1').val().trim(),
                    $('#bsn_link_2').val().trim(),
                    $('#bsn_link_3').val().trim()
                ].filter(Boolean);

                $.ajax({
                    url: ajaxurl,
                    method: 'POST',
                    data: {
                        action: 'bsn_send_notification',
                        nonce: $('#bsn_nonce').val(),
                        manga_id: <?php echo $post->ID; ?>,
                        chapters_text: $('#bsn_chapters_text').val(),
                        main_link: $('#bsn_main_link').val(),
                        extra_links: extra_links,
                        images: images,
                        send_discord: $('#bsn_send_discord').is(':checked') ? 1 : 0,
                        send_facebook: $('#bsn_send_facebook').is(':checked') ? 1 : 0
                    },
                    success: function(resp) {
                        var bg = resp.success ? '#eaffea' : '#ffeaea';
                        $('#bsn_result').css({'background': bg, 'padding': '6px', 'border-radius': '4px'})
                                       .html(resp.data.message);
                    },
                    error: function() {
                        $('#bsn_result').html('<span style="color:red;">❌ Error de conexión</span>');
                    },
                    complete: function() {
                        btn.prop('disabled', false).text('🌸 Publicar Notificación');
                    }
                });
            });
        });
        </script>
        <?php
    }

    // ─────────────────────────────────────────────
    // AUTO NOTIFICACIÓN
    // ─────────────────────────────────────────────

    public function on_chapter_published($post_id, $post, $update) {
        if (!get_option('bsn_auto_notify', 0)) return;
        if ($update) return;
        if ($post->post_type !== 'post') return;
        if ($post->post_status !== 'publish') return;

        $manga_id = get_post_meta($post_id, 'ero_seri', true);
        if (!$manga_id) return;

        $lock_key = 'bsn_lock_' . $post_id;
        if (get_transient($lock_key)) return;
        set_transient($lock_key, 1, 30);

        $chapter_num = get_post_meta($post_id, 'ero_chapter', true);
        $manga_title = get_the_title($manga_id);
        $manga_url   = get_permalink($manga_id);

        // Intentar obtener el user_id del autor del post
        $author_id = (int) $post->post_author;

        $images_urls = get_post_meta($post_id, '_chapter_images_urls', true);
        if (empty($images_urls)) $images_urls = get_post_meta($post_id, 'ero_chapter_images', true);
        $images = is_array($images_urls) ? array_slice(array_values($images_urls), 0, 4) : array();

        $chapters_text = 'Capítulo ' . $chapter_num;

        $this->send_to_discord($manga_title, $manga_url, $chapters_text, array(), $images, $author_id);
        $this->send_to_facebook($manga_title, $manga_url, $chapters_text, array(), $images, $author_id);
    }

    // ─────────────────────────────────────────────
    // AJAX MANUAL
    // ─────────────────────────────────────────────

    public function ajax_send_notification() {
        check_ajax_referer('bsn_send_nonce', 'nonce');
        if (!$this->user_can_notify()) {
            wp_send_json_error(array('message' => '❌ No tienes permiso para hacer esto'));
        }

        $manga_id      = intval($_POST['manga_id']);
        $chapters_text = sanitize_text_field($_POST['chapters_text']);
        $main_link     = esc_url_raw($_POST['main_link']);
        $send_discord  = intval($_POST['send_discord']);
        $send_facebook = intval($_POST['send_facebook']);
        $user_id       = get_current_user_id();

        $extra_links = array();
        if (!empty($_POST['extra_links']) && is_array($_POST['extra_links'])) {
            $extra_links = array_values(array_filter(array_map('esc_url_raw', $_POST['extra_links'])));
        }

        $images = array();
        if (!empty($_POST['images']) && is_array($_POST['images'])) {
            $images = array_values(array_slice(array_filter(array_map('esc_url_raw', $_POST['images'])), 0, 4));
        }

        $manga_title = get_the_title($manga_id);
        $results = array();

        if ($send_discord) {
            $r = $this->send_to_discord($manga_title, $main_link, $chapters_text, $extra_links, $images, $user_id);
            if ($r === true) {
                $results[] = '<span style="color:green;">✅ Discord OK</span>';
            } else {
                $results[] = '<span style="color:red;">❌ Discord falló — ' . esc_html($r) . '</span>';
            }
        }
        if ($send_facebook) {
            $r = $this->send_to_facebook($manga_title, $main_link, $chapters_text, $extra_links, $images, $user_id);
            if ($r === true) {
                $results[] = '<span style="color:green;">✅ Facebook OK</span>';
            } else {
                $results[] = '<span style="color:red;">❌ Facebook falló — ' . esc_html($r) . '</span>';
            }
        }

        wp_send_json_success(array('message' => implode(' &nbsp;|&nbsp; ', $results)));
    }

    // ─────────────────────────────────────────────
    // DISCORD
    // ─────────────────────────────────────────────

    /**
     * Envía a Discord.
     * @param int $user_id  ID del usuario/grupo que publica (para elegir webhook propio o global)
     * @return true|string  true si OK, string con el error si falla
     */
    private function send_to_discord($manga_title, $manga_url, $chapters_text, $extra_links = array(), $images = array(), $user_id = 0) {
        $webhook = $this->get_discord_webhook_for_user($user_id);
        if (empty($webhook)) {
            return 'No hay webhook de Discord configurado (ni en el grupo ni en los ajustes globales)';
        }

        // ── Construir descripción del embed ──────────────────────
        // El texto va PRIMERO, las imágenes se adjuntan DESPUÉS mediante el campo image del embed
        $desc  = ",✵°✵.｡.✰ **Actualización** ✰.｡.✵°✵, ☆\n\n";
        $desc .= "꧁✬◦°. **[" . $manga_title . "](" . $manga_url . ")** °◦✬꧂☆\n\n";
        $desc .= "📖 **" . $chapters_text . "**\n\n";
        $desc .= "🏷️ **Link:** " . $manga_url . "\n";
        if (!empty($extra_links)) {
            foreach ($extra_links as $link) {
                $desc .= $link . "\n";
            }
        }

        if (!empty($images)) {
            $valid_attachments = array();
            $temp_files        = array();
            $upload_dir        = wp_upload_dir();

            foreach (array_slice($images, 0, 4) as $i => $img_url) {
                $local_path = str_replace(
                    rtrim($upload_dir['baseurl'], '/'),
                    rtrim($upload_dir['basedir'], '/'),
                    $img_url
                );

                if (file_exists($local_path)) {
                    $valid_attachments[] = array(
                        'index'    => $i,
                        'path'     => $local_path,
                        'filename' => 'imagen_' . ($i + 1) . '.' . pathinfo($local_path, PATHINFO_EXTENSION),
                    );
                } else {
                    $tmp = download_url($img_url);
                    if (!is_wp_error($tmp)) {
                        $ext = pathinfo(parse_url($img_url, PHP_URL_PATH), PATHINFO_EXTENSION) ?: 'jpg';
                        $fn  = 'imagen_' . ($i + 1) . '.' . $ext;
                        $valid_attachments[] = array('index' => $i, 'path' => $tmp, 'filename' => $fn, 'temp' => true);
                        $temp_files[] = $tmp;
                    }
                }
            }

            if (!empty($valid_attachments)) {
                /*
                 * FIX: El texto debe aparecer ANTES de las imágenes en Discord.
                 * Se usa un embed cuya descripción contiene el texto completo.
                 * La imagen principal va en embed->image (attachment://...).
                 * Las imágenes 2-4 se envían como archivos adicionales; Discord las agrupa
                 * automáticamente debajo del embed al ser parte del mismo mensaje.
                 *
                 * Orden en Discord: contenido (mention) → embed con texto + imagen 1 → imágenes 2-4 abajo.
                 */
                $embed = array(
                    'color'       => 0x5B9BD5,
                    'description' => $desc,
                    'image'       => array('url' => 'attachment://' . $valid_attachments[0]['filename']),
                    'footer'      => array('text' => '•.☆✬ Disfrutenlo ✬☆.•⨳•.¤⊹٭'),
                );

                $boundary = '----DiscordBoundary' . uniqid();
                $body     = '';

                $payload_json = wp_json_encode(array(
                    'content'     => '@everyone @¡¡Nueva Actualización!!',
                    'embeds'      => array($embed),
                    'attachments' => array_map(function($att) {
                        return array('id' => $att['index'], 'filename' => $att['filename']);
                    }, $valid_attachments),
                ));

                // payload_json PRIMERO
                $body .= "--{$boundary}\r\n";
                $body .= "Content-Disposition: form-data; name=\"payload_json\"\r\n";
                $body .= "Content-Type: application/json\r\n\r\n";
                $body .= $payload_json . "\r\n";

                // Archivos DESPUÉS del payload
                foreach ($valid_attachments as $att) {
                    $file_data = file_get_contents($att['path']);
                    $mime      = mime_content_type($att['path']) ?: 'image/jpeg';
                    $body .= "--{$boundary}\r\n";
                    $body .= "Content-Disposition: form-data; name=\"files[{$att['index']}]\"; filename=\"{$att['filename']}\"\r\n";
                    $body .= "Content-Type: {$mime}\r\n\r\n";
                    $body .= $file_data . "\r\n";
                }
                $body .= "--{$boundary}--\r\n";

                $response = wp_remote_post($webhook, array(
                    'headers' => array('Content-Type' => 'multipart/form-data; boundary=' . $boundary),
                    'body'    => $body,
                    'timeout' => 30,
                ));

                foreach ($temp_files as $tmp) { @unlink($tmp); }

                if (is_wp_error($response)) {
                    $msg = 'WP_Error: ' . $response->get_error_message();
                    error_log('[Bloom Notifier] Discord ' . $msg);
                    return $msg;
                }
                $code = wp_remote_retrieve_response_code($response);
                if ($code >= 300) {
                    $api_body = wp_remote_retrieve_body($response);
                    $msg      = 'HTTP ' . $code . ' — ' . $api_body;
                    error_log('[Bloom Notifier] Discord ' . $msg);
                    return $msg;
                }
                return true;
            }
        }

        // Sin imágenes — JSON simple
        $payload  = array(
            'content' => '@everyone @¡¡Nueva Actualización!!',
            'embeds'  => array(array(
                'color'       => 0x5B9BD5,
                'description' => $desc,
                'footer'      => array('text' => '•.☆✬ Disfrutenlo ✬☆.•⨳•.¤⊹٭'),
            )),
        );

        $response = wp_remote_post($webhook, array(
            'headers' => array('Content-Type' => 'application/json'),
            'body'    => wp_json_encode($payload),
            'timeout' => 15,
        ));

        if (is_wp_error($response)) {
            $msg = 'WP_Error: ' . $response->get_error_message();
            error_log('[Bloom Notifier] Discord ' . $msg);
            return $msg;
        }
        $code = wp_remote_retrieve_response_code($response);
        if ($code >= 300) {
            $api_body = wp_remote_retrieve_body($response);
            $msg      = 'HTTP ' . $code . ' — ' . $api_body;
            error_log('[Bloom Notifier] Discord ' . $msg);
            return $msg;
        }
        return true;
    }

    // ─────────────────────────────────────────────
    // FACEBOOK
    // ─────────────────────────────────────────────

    /**
     * Envía a Facebook.
     * @param int $user_id  ID del usuario/grupo que publica
     * @return true|string  true si OK, string con el error si falla
     */
    private function send_to_facebook($manga_title, $manga_url, $chapters_text, $extra_links = array(), $images = array(), $user_id = 0) {
        $creds   = $this->get_facebook_creds_for_user($user_id);
        $page_id = $creds['page_id'];
        $token   = $creds['token'];

        // ── Diagnóstico de configuración ─────────────────────────
        if (empty($page_id) && empty($token)) {
            return 'Falta el Page ID y el Access Token de Facebook. Configúralos en Ajustes → 🌸 Bloom Notifier o en el apartado del grupo.';
        }
        if (empty($page_id)) {
            return 'Falta el Facebook Page ID. Configúralo en Ajustes → 🌸 Bloom Notifier o en el apartado del grupo.';
        }
        if (empty($token)) {
            return 'Falta el Facebook Page Access Token. Configúralo en Ajustes → 🌸 Bloom Notifier o en el apartado del grupo.';
        }

        $discord_invite = get_option('bsn_discord_invite', 'https://discord.gg/6PmTZWFZ');

        $message  = ",✵°✵.｡.✰ Actualización ✰.｡.✵°✵, ☆\n\n";
        $message .= "꧁✬◦°. " . $manga_title . " °◦✬꧂☆\n\n";
        $message .= "📖 " . $chapters_text . "\n\n";
        $message .= "🏷️ Link: " . $manga_url . "\n";

        if (!empty($extra_links)) {
            foreach ($extra_links as $link) {
                $message .= $link . "\n";
            }
        }

        $message .= "\n(Notificamos primero en nuestro discord, ¡únanse! 😊😊)\n";
        $message .= "Link del discord: " . $discord_invite . "\n\n";
        $message .= "@seguidores";

        $fb_api_base = 'https://graph.facebook.com/v19.0';

        if (!empty($images)) {
            $media_ids = array();

            foreach ($images as $img_url) {
                $photo_response = wp_remote_post(
                    "{$fb_api_base}/{$page_id}/photos",
                    array(
                        'body'    => array('url' => $img_url, 'published' => 'false', 'access_token' => $token),
                        'timeout' => 20,
                    )
                );

                if (is_wp_error($photo_response)) {
                    // No es fatal, seguimos con las que sí suban
                    error_log('[Bloom Notifier] Facebook foto WP_Error: ' . $photo_response->get_error_message() . ' — URL: ' . $img_url);
                    continue;
                }

                $photo_code = wp_remote_retrieve_response_code($photo_response);
                $photo_body = wp_remote_retrieve_body($photo_response);
                $photo_data = json_decode($photo_body, true);

                if (!empty($photo_data['id'])) {
                    $media_ids[] = array('media_fbid' => $photo_data['id']);
                } else {
                    // La API de Facebook devolvió un error al subir la foto — logueamos el detalle
                    $fb_error = isset($photo_data['error']['message']) ? $photo_data['error']['message'] : $photo_body;
                    error_log('[Bloom Notifier] Facebook foto HTTP ' . $photo_code . ': ' . $fb_error . ' — URL: ' . $img_url);
                }
            }

            $body = array('message' => $message, 'access_token' => $token);
            foreach ($media_ids as $i => $media) {
                $body['attached_media[' . $i . ']'] = wp_json_encode($media);
            }

            $response = wp_remote_post("{$fb_api_base}/{$page_id}/feed", array('body' => $body, 'timeout' => 20));

        } else {
            $response = wp_remote_post(
                "{$fb_api_base}/{$page_id}/feed",
                array('body' => array('message' => $message, 'link' => $manga_url, 'access_token' => $token), 'timeout' => 20)
            );
        }

        if (is_wp_error($response)) {
            $msg = 'Error de red (WP_Error): ' . $response->get_error_message();
            error_log('[Bloom Notifier] Facebook ' . $msg);
            return $msg;
        }

        $code     = wp_remote_retrieve_response_code($response);
        $raw_body = wp_remote_retrieve_body($response);
        $fb_data  = json_decode($raw_body, true);

        if ($code !== 200 || isset($fb_data['error'])) {
            // ── Mensaje de error detallado con causas comunes ─────
            $fb_msg  = isset($fb_data['error']['message']) ? $fb_data['error']['message'] : $raw_body;
            $fb_type = isset($fb_data['error']['type'])    ? $fb_data['error']['type']    : '';
            $fb_code = isset($fb_data['error']['code'])    ? (int)$fb_data['error']['code'] : 0;

            $hint = $this->facebook_error_hint($fb_code, $fb_type, $fb_msg);
            $full_msg = 'HTTP ' . $code . ' — ' . $fb_msg . ($hint ? ' (' . $hint . ')' : '');

            error_log('[Bloom Notifier] Facebook ' . $full_msg);
            return $full_msg;
        }

        return true;
    }

    /**
     * Devuelve una sugerencia de solución basada en el código/tipo de error de Facebook.
     */
    private function facebook_error_hint($code, $type, $message) {
        // Errores de token / autenticación
        if (in_array($code, array(190, 102, 467, 463, 460))) {
            if (strpos($message, 'expired') !== false || strpos($message, 'expiró') !== false) {
                return 'El token ha expirado. Genera un nuevo Page Access Token en Meta for Developers → Graph API Explorer';
            }
            if (strpos($message, 'invalid') !== false || strpos($message, 'inválido') !== false) {
                return 'El token es inválido. Verifica que copiaste el Page Access Token completo y que es de la página correcta';
            }
            return 'Token inválido o expirado. Ve a Meta for Developers y genera uno nuevo con permisos pages_manage_posts y pages_read_engagement';
        }
        // Permisos insuficientes
        if (in_array($code, array(200, 10, 3, 299))) {
            return 'El token no tiene los permisos necesarios. Asegúrate de que tenga pages_manage_posts y pages_read_engagement. Si es una app nueva, puede necesitar revisión de Meta';
        }
        // Page ID incorrecto
        if ($code === 100) {
            if (strpos($message, 'OAuthException') !== false || strpos($message, 'does not exist') !== false) {
                return 'El Page ID no existe o el token no pertenece a esa página. Verifica el ID numérico de la página (no el nombre)';
            }
            return 'Parámetro inválido. Revisa que el Page ID sea correcto (solo números)';
        }
        // Rate limit
        if (in_array($code, array(4, 17, 32, 613))) {
            return 'Límite de publicaciones alcanzado. Espera unos minutos antes de volver a intentarlo';
        }
        // Contenido / spam
        if ($code === 368) {
            return 'La publicación fue bloqueada por Facebook (posible contenido spam o restricción de cuenta). Revisa el estado de tu página en Meta Business Suite';
        }
        // Error genérico de red
        if (empty($code)) {
            return 'No se recibió respuesta de Facebook. Verifica que el servidor tenga salida a internet';
        }
        return '';
    }
}

function bsn_init() {
    return Bloom_Scans_Notifier::get_instance();
}
add_action('plugins_loaded', 'bsn_init');
