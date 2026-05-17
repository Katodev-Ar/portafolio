<?php
/**
 * Plugin Name: Gemini Manga Summary
 * Description: Genera un resumen automático de ~500 palabras por capítulo usando Gemini Vision, y lo muestra debajo de los comentarios de cada capítulo.
 * Version: 1.0.0
 * Author: Tu equipo
 * Text Domain: gemini-manga-summary
 */

if ( ! defined( 'ABSPATH' ) ) exit;

// ─────────────────────────────────────────────
// CONSTANTES
// ─────────────────────────────────────────────
define( 'GMS_VERSION',    '1.0.0' );
define( 'GMS_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'GMS_OPTION',     'gms_settings' );

// Meta key donde se guarda el resumen generado
define( 'GMS_META_SUMMARY',   '_gms_chapter_summary' );
// Meta key para saber si ya se procesó (evitar duplicados)
define( 'GMS_META_PROCESSED', '_gms_processed' );

// ─────────────────────────────────────────────
// 1. ADMIN: PÁGINA DE AJUSTES
// ─────────────────────────────────────────────
add_action( 'admin_menu', 'gms_admin_menu' );
function gms_admin_menu() {
    add_options_page(
        'Gemini Manga Summary',
        'Gemini Summary',
        'manage_options',
        'gemini-manga-summary',
        'gms_settings_page'
    );
}

add_action( 'admin_init', 'gms_register_settings' );
function gms_register_settings() {
    register_setting( 'gms_settings_group', GMS_OPTION, 'gms_sanitize_settings' );
}

function gms_sanitize_settings( $input ) {
    $clean = [];
    $clean['api_key']       = sanitize_text_field( $input['api_key'] ?? '' );
    $clean['gemini_model']  = sanitize_text_field( $input['gemini_model'] ?? 'gemini-1.5-flash' );
    $clean['prompt_text']   = sanitize_textarea_field( $input['prompt_text'] ?? '' );
    $clean['chapter_post_type'] = sanitize_text_field( $input['chapter_post_type'] ?? 'wp-manga-chapter' );
    return $clean;
}

function gms_get_settings() {
    $defaults = [
        'api_key'            => '',
        'gemini_model'       => 'gemini-1.5-flash',
        'chapter_post_type'  => 'wp-manga-chapter',
        'prompt_text'        => 'Eres un experto en manga y anime. Analiza todas las páginas de este capítulo de manga y redacta un resumen detallado en español de exactamente 500 palabras. Describe los eventos principales, las acciones de los personajes, los diálogos importantes y el avance de la trama. Usa un tono narrativo y atractivo para los lectores del sitio.',
    ];
    return wp_parse_args( get_option( GMS_OPTION, [] ), $defaults );
}

function gms_settings_page() {
    $settings = gms_get_settings();
    $saved    = isset( $_GET['settings-updated'] ) ? true : false;
    ?>
    <div class="wrap">
        <h1>⚙️ Gemini Manga Summary</h1>
        <?php if ( $saved ): ?>
            <div class="notice notice-success is-dismissible"><p>✅ Configuración guardada.</p></div>
        <?php endif; ?>

        <form method="post" action="options.php">
            <?php settings_fields( 'gms_settings_group' ); ?>
            <table class="form-table">
                <tr>
                    <th scope="row"><label for="api_key">🔑 Google Gemini API Key</label></th>
                    <td>
                        <input type="password" id="api_key" name="<?= GMS_OPTION ?>[api_key]"
                               value="<?= esc_attr( $settings['api_key'] ) ?>"
                               class="regular-text" autocomplete="new-password" />
                        <p class="description">Obtén tu API Key en <a href="https://aistudio.google.com/app/apikey" target="_blank">Google AI Studio</a>.</p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="gemini_model">🤖 Modelo Gemini</label></th>
                    <td>
                        <select id="gemini_model" name="<?= GMS_OPTION ?>[gemini_model]">
                            <?php
                            $models = [
                                'gemini-1.5-flash'       => 'gemini-1.5-flash (Rápido y económico) ✅ Recomendado',
                                'gemini-1.5-pro'         => 'gemini-1.5-pro (Más preciso, más caro)',
                                'gemini-2.0-flash-exp'   => 'gemini-2.0-flash-exp (Experimental)',
                            ];
                            foreach ( $models as $val => $label ):
                                $selected = selected( $settings['gemini_model'], $val, false );
                            ?>
                                <option value="<?= esc_attr( $val ) ?>" <?= $selected ?>><?= esc_html( $label ) ?></option>
                            <?php endforeach; ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="chapter_post_type">📄 Post Type de Capítulos</label></th>
                    <td>
                        <input type="text" id="chapter_post_type" name="<?= GMS_OPTION ?>[chapter_post_type]"
                               value="<?= esc_attr( $settings['chapter_post_type'] ) ?>"
                               class="regular-text" />
                        <p class="description">El post_type usado para los capítulos. Por defecto: <code>wp-manga-chapter</code>. También puede ser <code>post</code> si usas otro plugin.</p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="prompt_text">💬 Prompt para Gemini</label></th>
                    <td>
                        <textarea id="prompt_text" name="<?= GMS_OPTION ?>[prompt_text]"
                                  rows="6" class="large-text"><?= esc_textarea( $settings['prompt_text'] ) ?></textarea>
                        <p class="description">Instrucción que se envía a Gemini junto con las imágenes del capítulo.</p>
                    </td>
                </tr>
            </table>
            <?php submit_button( 'Guardar configuración' ); ?>
        </form>

        <hr>
        <h2>🔄 Regenerar resumen manualmente</h2>
        <p>Puedes regenerar el resumen de un capítulo específico ingresando su ID de WordPress:</p>
        <form method="post" action="">
            <?php wp_nonce_field( 'gms_manual_generate', 'gms_nonce' ); ?>
            <input type="hidden" name="gms_action" value="manual_generate" />
            <input type="number" name="gms_post_id" placeholder="ID del capítulo" min="1" style="width:150px" />
            <?php submit_button( '⚡ Generar ahora', 'secondary', 'gms_submit', false ); ?>
        </form>

        <?php
        // Procesar generación manual
        if (
            isset( $_POST['gms_action'] ) &&
            $_POST['gms_action'] === 'manual_generate' &&
            wp_verify_nonce( $_POST['gms_nonce'] ?? '', 'gms_manual_generate' )
        ) {
            $pid = intval( $_POST['gms_post_id'] ?? 0 );
            if ( $pid > 0 ) {
                $result = gms_process_chapter( $pid, true );
                if ( is_wp_error( $result ) ) {
                    echo '<div class="notice notice-error"><p>❌ Error: ' . esc_html( $result->get_error_message() ) . '</p></div>';
                } else {
                    echo '<div class="notice notice-success"><p>✅ Resumen generado para el post ID ' . $pid . '.</p></div>';
                    echo '<blockquote style="background:#f9f9f9;padding:15px;border-left:4px solid #0073aa">' . nl2br( esc_html( $result ) ) . '</blockquote>';
                }
            }
        }
        ?>
    </div>
    <?php
}

// ─────────────────────────────────────────────
// 2. HOOK: GENERAR RESUMEN AL PUBLICAR CAPÍTULO
// ─────────────────────────────────────────────
add_action( 'transition_post_status', 'gms_on_chapter_publish', 10, 3 );
function gms_on_chapter_publish( $new_status, $old_status, $post ) {
    // Solo cuando un post pasa a "publish" por primera vez
    if ( $new_status !== 'publish' ) return;
    if ( $old_status === 'publish' ) return; // ya estaba publicado, no re-generar

    $settings = gms_get_settings();
    if ( $post->post_type !== $settings['chapter_post_type'] ) return;

    // Evitar doble procesamiento
    if ( get_post_meta( $post->ID, GMS_META_PROCESSED, true ) ) return;

    // Lanzar la generación de forma asíncrona (via WP Cron de 1 segundo)
    // para no bloquear la respuesta del admin.
    wp_schedule_single_event( time() + 2, 'gms_async_generate', [ $post->ID ] );
}

add_action( 'gms_async_generate', 'gms_process_chapter' );

// ─────────────────────────────────────────────
// 3. LÓGICA PRINCIPAL: OBTENER IMÁGENES → GEMINI → GUARDAR
// ─────────────────────────────────────────────
/**
 * @param int  $post_id   ID del capítulo en WordPress
 * @param bool $force     Si true, regenera aunque ya exista resumen
 * @return string|WP_Error  El resumen generado, o WP_Error en caso de fallo
 */
function gms_process_chapter( $post_id, $force = false ) {
    $settings = gms_get_settings();

    if ( empty( $settings['api_key'] ) ) {
        return new WP_Error( 'no_api_key', 'Configura la API Key de Gemini en Ajustes → Gemini Summary.' );
    }

    if ( ! $force && get_post_meta( $post_id, GMS_META_PROCESSED, true ) ) {
        return get_post_meta( $post_id, GMS_META_SUMMARY, true );
    }

    // ── Obtener imágenes del capítulo ──────────────────────────────────────
    $images = gms_get_chapter_images( $post_id );

    if ( empty( $images ) ) {
        return new WP_Error( 'no_images', 'No se encontraron imágenes para el capítulo ID ' . $post_id );
    }

    // ── Obtener contexto del capítulo ─────────────────────────────────────
    $context = gms_get_chapter_context( $post_id );

    // ── Construir el payload para Gemini ──────────────────────────────────
    $parts = [];

    // Texto del prompt con contexto al inicio
    $parts[] = [
        'text' => gms_build_prompt( $settings['prompt_text'], $context )
    ];

    // Agregar cada imagen como inline_data (base64)
    $added = 0;
    foreach ( $images as $image_path_or_url ) {
        $image_data = gms_image_to_base64( $image_path_or_url );
        if ( is_wp_error( $image_data ) ) continue;

        $parts[] = [
            'inline_data' => [
                'mime_type' => $image_data['mime'],
                'data'      => $image_data['base64'],
            ]
        ];
        $added++;

        // Gemini 1.5 Flash soporta hasta ~300 imágenes, pero para manga
        // limitamos a 60 páginas para evitar timeouts y costos excesivos.
        if ( $added >= 60 ) break;
    }

    if ( $added === 0 ) {
        return new WP_Error( 'images_unreadable', 'No se pudieron leer las imágenes del capítulo.' );
    }

    // ── Llamada a la API de Gemini ─────────────────────────────────────────
    $endpoint = sprintf(
        'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s',
        $settings['gemini_model'],
        $settings['api_key']
    );

    $body = wp_json_encode( [
        'contents' => [
            [
                'parts' => $parts
            ]
        ],
        'generationConfig' => [
            'temperature'     => 0.7,
            'maxOutputTokens' => 1024,
        ]
    ] );

    $response = wp_remote_post( $endpoint, [
        'method'  => 'POST',
        'timeout' => 120, // segundos — las imágenes son pesadas
        'headers' => [ 'Content-Type' => 'application/json' ],
        'body'    => $body,
    ] );

    if ( is_wp_error( $response ) ) {
        return $response;
    }

    $http_code = wp_remote_retrieve_response_code( $response );
    $raw_body  = wp_remote_retrieve_body( $response );
    $decoded   = json_decode( $raw_body, true );

    if ( $http_code !== 200 ) {
        $error_msg = $decoded['error']['message'] ?? $raw_body;
        return new WP_Error( 'gemini_api_error', 'Gemini API error ' . $http_code . ': ' . $error_msg );
    }

    $summary = $decoded['candidates'][0]['content']['parts'][0]['text'] ?? '';

    if ( empty( $summary ) ) {
        return new WP_Error( 'empty_response', 'Gemini devolvió una respuesta vacía.' );
    }

    $summary = trim( $summary );

    // ── Guardar resultado ────────────────────────────────────────────────
    update_post_meta( $post_id, GMS_META_SUMMARY,   $summary );
    update_post_meta( $post_id, GMS_META_PROCESSED, current_time( 'mysql' ) );

    return $summary;
}

// ─────────────────────────────────────────────
// 4. OBTENER IMÁGENES DEL CAPÍTULO
//    Compatible con el tema MangaReader + tu plugin de uploads
// ─────────────────────────────────────────────
function gms_get_chapter_images( $post_id ) {
    $images = [];

    // ── Método A: Meta 'ero_chapter_images' (usado en single-chapter-mcm.php)
    $ero_images = get_post_meta( $post_id, 'ero_chapter_images', true );
    if ( ! empty( $ero_images ) && is_array( $ero_images ) ) {
        // Ordenar por índice
        usort( $ero_images, fn( $a, $b ) => ( $a['index'] ?? 0 ) <=> ( $b['index'] ?? 0 ) );
        foreach ( $ero_images as $img ) {
            $url = $img['url'] ?? $img['src'] ?? '';
            if ( $url ) $images[] = $url;
        }
        if ( ! empty( $images ) ) return $images;
    }

    // ── Método B: Imágenes adjuntas al post (attachments)
    $attachments = get_attached_media( 'image', $post_id );
    if ( ! empty( $attachments ) ) {
        foreach ( $attachments as $att ) {
            $images[] = wp_get_attachment_url( $att->ID );
        }
        if ( ! empty( $images ) ) return $images;
    }

    // ── Método C: Carpeta de capitulos del plugin manga-uploads-organizer
    //    Estructura: /wp-content/uploads/capitulos/cap-{post_id}/
    $upload_dir  = wp_upload_dir();
    $chapter_dir = $upload_dir['basedir'] . '/capitulos/cap-' . $post_id;
    $chapter_url = $upload_dir['baseurl'] . '/capitulos/cap-' . $post_id;

    if ( is_dir( $chapter_dir ) ) {
        $exts  = [ 'jpg', 'jpeg', 'png', 'webp', 'gif' ];
        $files = [];
        foreach ( $exts as $ext ) {
            $found = glob( $chapter_dir . '/*.' . $ext );
            if ( $found ) $files = array_merge( $files, $found );
        }
        // Ordenar por nombre de archivo (natural sort)
        natsort( $files );
        foreach ( $files as $filepath ) {
            $filename = basename( $filepath );
            $images[] = $chapter_url . '/' . $filename;
        }
        if ( ! empty( $images ) ) return $images;
    }

    // ── Método D: Meta genérica 'chapter_images' o '_images'
    foreach ( [ 'chapter_images', '_images', 'ts_reader_img' ] as $meta_key ) {
        $meta = get_post_meta( $post_id, $meta_key, true );
        if ( ! empty( $meta ) ) {
            if ( is_array( $meta ) ) {
                foreach ( $meta as $img ) {
                    $url = is_array( $img ) ? ( $img['url'] ?? '' ) : $img;
                    if ( $url ) $images[] = $url;
                }
                if ( ! empty( $images ) ) return $images;
            }
        }
    }

    return $images;
}

// ─────────────────────────────────────────────
// 5. CONVERTIR IMAGEN A BASE64 PARA LA API
// ─────────────────────────────────────────────
function gms_image_to_base64( $url_or_path ) {
    // Si es una ruta local directa
    if ( file_exists( $url_or_path ) ) {
        $filepath = $url_or_path;
    } else {
        // Intentar convertir URL a ruta local
        $upload_dir = wp_upload_dir();
        $filepath   = str_replace( $upload_dir['baseurl'], $upload_dir['basedir'], $url_or_path );
    }

    if ( file_exists( $filepath ) ) {
        $raw  = file_get_contents( $filepath );
        $mime = wp_check_filetype( $filepath )['type'] ?: 'image/jpeg';
    } else {
        // Descargar la imagen de forma remota
        $response = wp_remote_get( $url_or_path, [ 'timeout' => 30 ] );
        if ( is_wp_error( $response ) ) return $response;

        $raw  = wp_remote_retrieve_body( $response );
        $ct   = wp_remote_retrieve_header( $response, 'content-type' );
        $mime = strtok( $ct ?: 'image/jpeg', ';' );
    }

    if ( empty( $raw ) ) {
        return new WP_Error( 'empty_image', 'Imagen vacía: ' . $url_or_path );
    }

    return [
        'base64' => base64_encode( $raw ),
        'mime'   => $mime,
    ];
}

// ─────────────────────────────────────────────
// 6. MOSTRAR EL RESUMEN DEBAJO DE LOS COMENTARIOS
// ─────────────────────────────────────────────
add_action( 'wp_enqueue_scripts', 'gms_enqueue_styles' );
function gms_enqueue_styles() {
    wp_add_inline_style( 'wp-block-library', gms_inline_css() );
}

function gms_inline_css() {
    return '
    .gms-summary-box {
        margin: 40px auto;
        max-width: 860px;
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 28px 32px;
        color: #e0e0e0;
        font-family: inherit;
        box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    }
    .gms-summary-box h3 {
        margin: 0 0 16px 0;
        font-size: 1.1rem;
        color: #e94560;
        text-transform: uppercase;
        letter-spacing: 1px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .gms-summary-box h3::before {
        content: "📖";
    }
    .gms-summary-box .gms-summary-text {
        line-height: 1.8;
        font-size: 0.97rem;
        color: #ccc;
    }
    .gms-summary-box .gms-footer {
        margin-top: 16px;
        font-size: 0.78rem;
        color: #555;
        text-align: right;
    }
    ';
}

/**
 * Inyectar el resumen después del bloque de comentarios.
 * Se usa el filtro comments_template para agregar el resumen
 * justo debajo de la sección de comentarios.
 */
add_filter( 'comments_template', 'gms_wrap_comments_template' );
function gms_wrap_comments_template( $template ) {
    $settings = gms_get_settings();
    if ( ! is_singular( $settings['chapter_post_type'] ) ) {
        return $template;
    }
    // Devolver nuestro wrapper en lugar del template original
    // Guardamos la ruta para incluirla dentro del wrapper
    global $gms_original_comments_template;
    $gms_original_comments_template = $template;
    return GMS_PLUGIN_DIR . 'comments-wrapper.php';
}

// ─────────────────────────────────────────────
// 7. SHORTCODE [gms_summary] — uso manual en entradas
// ─────────────────────────────────────────────
add_shortcode( 'gms_summary', 'gms_shortcode' );
function gms_shortcode( $atts ) {
    $atts = shortcode_atts( [ 'id' => get_the_ID() ], $atts );
    return gms_render_summary_box( intval( $atts['id'] ) );
}

function gms_render_summary_box( $post_id ) {
    $summary = get_post_meta( $post_id, GMS_META_SUMMARY, true );
    if ( empty( $summary ) ) return '';

    $processed = get_post_meta( $post_id, GMS_META_PROCESSED, true );
    ob_start();
    ?>
    <div class="gms-summary-box">
        <h3>Resumen del Capítulo</h3>
        <div class="gms-summary-text"><?= nl2br( esc_html( $summary ) ) ?></div>
        <div class="gms-footer">✨ Generado por IA el <?= esc_html( $processed ) ?></div>
    </div>
    <?php
    return ob_get_clean();
}

// ─────────────────────────────────────────────
// 8. COLUMNA EN LISTA DE POSTS DEL ADMIN
// ─────────────────────────────────────────────
// ─────────────────────────────────────────────
// 9. OBTENER CONTEXTO DEL CAPÍTULO
// ─────────────────────────────────────────────
function gms_get_chapter_context( $post_id ) {
    $ctx = [];

    // ── Nombre del capítulo (título de la entrada) ─────────────────────
    $ctx['chapter_title'] = get_the_title( $post_id );

    // ── Número de capítulo (meta ero_chapter del tema MangaReader) ──────
    $ctx['chapter_number'] = get_post_meta( $post_id, 'ero_chapter', true );

    // ── Nombre del manga desde el post padre (meta ero_seri) ─────────
    $manga_id = get_post_meta( $post_id, 'ero_seri', true );
    if ( $manga_id ) {
        $ctx['manga_title'] = get_the_title( $manga_id );
        $ctx['manga_id']    = $manga_id;
    }

    // ── Fallback: nombre del manga desde el título de la entrada ────────
    // Ej: "One Piece - Capítulo 1100" → extraer "One Piece"
    if ( empty( $ctx['manga_title'] ) && ! empty( $ctx['chapter_title'] ) ) {
        // Patrones comunes: "Titulo - Cap X", "Titulo Cap X", "Titulo #X"
        $title_clean = preg_replace( '/[\s\-–—]+cap[íi]tulo[\s\d\.]+$/i', '', $ctx['chapter_title'] );
        $title_clean = preg_replace( '/[\s\-–—]+cap[\s\d\.]+$/i', '', $title_clean );
        $title_clean = preg_replace( '/[\s\-–—]+ch(apter)?[\s\d\.]+$/i', '', $title_clean );
        $title_clean = preg_replace( '/[\s\-–—]+#[\d\.]+$/i', '', $title_clean );
        if ( $title_clean !== $ctx['chapter_title'] ) {
            $ctx['manga_title'] = trim( $title_clean );
        }
    }

    // ── Nombre del manga desde el post padre de WordPress ───────────────
    if ( empty( $ctx['manga_title'] ) ) {
        $parent_id = wp_get_post_parent_id( $post_id );
        if ( $parent_id ) {
            $ctx['manga_title'] = get_the_title( $parent_id );
            $ctx['manga_id']    = $parent_id;
        }
    }

    // ── Géneros / categorías del manga ──────────────────────────────────
    $genres = [];

    // Taxonomía 'manga_genres' (MangaReader / Madara)
    foreach ( [ 'manga_genres', 'genre', 'genres' ] as $tax ) {
        $terms = get_the_terms( $manga_id ?: $post_id, $tax );
        if ( $terms && ! is_wp_error( $terms ) ) {
            $genres = wp_list_pluck( $terms, 'name' );
            break;
        }
    }

    // Categorías estándar de WordPress como fallback
    if ( empty( $genres ) ) {
        $cats = get_the_category( $manga_id ?: $post_id );
        if ( $cats ) {
            $genres = wp_list_pluck( $cats, 'name' );
        }
    }

    $ctx['genres'] = $genres;

    // ── Nombre del manga desde la categoría si aún no lo tenemos ────────
    // Muchos sitios crean una categoría con el mismo nombre del manga
    if ( empty( $ctx['manga_title'] ) && ! empty( $genres ) ) {
        // Heurística: la primera categoría que no sea genérica suele ser el nombre del manga
        $generic = [ 'manga', 'manhwa', 'manhua', 'comic', 'capítulo', 'capitulo', 'chapter', 'uncategorized' ];
        foreach ( $genres as $genre ) {
            if ( ! in_array( strtolower( $genre ), $generic, true ) ) {
                $ctx['manga_title'] = $genre;
                break;
            }
        }
    }

    return $ctx;
}

// ─────────────────────────────────────────────
// 10. CONSTRUIR EL PROMPT CON CONTEXTO
// ─────────────────────────────────────────────
function gms_build_prompt( $base_prompt, $context ) {
    $lines = [];

    // Bloque de contexto
    $lines[] = '=== CONTEXTO DEL CAPÍTULO ===';

    if ( ! empty( $context['manga_title'] ) ) {
        $lines[] = 'Manga: ' . $context['manga_title'];
    }

    if ( ! empty( $context['chapter_number'] ) ) {
        $lines[] = 'Número de capítulo: ' . $context['chapter_number'];
    } elseif ( ! empty( $context['chapter_title'] ) ) {
        $lines[] = 'Título del capítulo: ' . $context['chapter_title'];
    }

    if ( ! empty( $context['genres'] ) ) {
        $lines[] = 'Géneros: ' . implode( ', ', $context['genres'] );
    }

    $lines[] = '=== FIN DEL CONTEXTO ===';
    $lines[] = '';
    $lines[] = $base_prompt;

    // Añadir instrucción final de contextualización
    if ( ! empty( $context['manga_title'] ) ) {
        $lines[] = '';
        $lines[] = 'Recuerda mencionar el nombre del manga (' . $context['manga_title'] . ') y el número de capítulo en el resumen para dar contexto al lector.';
    }

    return implode( "\n", $lines );
}

add_filter( 'manage_posts_columns', 'gms_add_column', 10, 1 );
function gms_add_column( $columns ) {
    $settings = gms_get_settings();
    if ( get_current_screen()->post_type !== $settings['chapter_post_type'] ) return $columns;
    $columns['gms_status'] = '🤖 Resumen IA';
    return $columns;
}

add_action( 'manage_posts_custom_column', 'gms_column_content', 10, 2 );
function gms_column_content( $column, $post_id ) {
    if ( $column !== 'gms_status' ) return;
    $processed = get_post_meta( $post_id, GMS_META_PROCESSED, true );
    if ( $processed ) {
        echo '<span style="color:green">✅ ' . esc_html( $processed ) . '</span>';
    } else {
        echo '<span style="color:#aaa">— Pendiente</span>';
    }
}
