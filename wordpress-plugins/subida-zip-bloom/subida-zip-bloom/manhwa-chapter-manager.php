<?php
/**
 * Plugin Name: Subida ZIP Bloom
 * Plugin URI: https://bloomscans.com/
 * Description: Sistema completo de gestión de capítulos para BloomScans con subida ZIP, sincronización inteligente, renombrado automático de carpetas y auto-categorización.
 * Version: 3.5.0
 * Author: BloomScans
 * License: GPL v2 or later
 * Text Domain: bloom-zip-upload
 */

if (!defined('ABSPATH')) {
    exit;
}

define('MCM_VERSION', '3.5.0');
define('MCM_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('MCM_PLUGIN_URL', plugin_dir_url(__FILE__));

class Manhwa_Chapter_Manager_V3 {

    private static $instance = null;

    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    private function __construct() {
        $this->init_hooks();
    }

    private function init_hooks() {
        add_action('add_meta_boxes', array($this, 'add_meta_box'));
        add_action('admin_enqueue_scripts', array($this, 'enqueue_assets'));

        // AJAX handlers
        add_action('wp_ajax_mcm_upload_chapters',      array($this, 'ajax_upload_chapters'));
        add_action('wp_ajax_mcm_get_chapters',         array($this, 'ajax_get_chapters'));
        add_action('wp_ajax_mcm_delete_chapter',       array($this, 'ajax_delete_chapter'));
        add_action('wp_ajax_mcm_sync_all',             array($this, 'ajax_sync_all'));
        add_action('wp_ajax_mcm_save_category_config', array($this, 'ajax_save_category_config'));
        add_action('wp_ajax_mcm_add_images',           array($this, 'ajax_add_images'));
        add_action('wp_ajax_mcm_delete_image',         array($this, 'ajax_delete_image'));
        add_action('wp_ajax_mcm_reorder_images',       array($this, 'ajax_reorder_images'));
        add_action('wp_ajax_mcm_reorder_chapters',     array($this, 'ajax_reorder_chapters'));
        add_action('wp_ajax_mcm_rename_manga_folder',  array($this, 'ajax_rename_manga_folder'));

        // FIX: Detectar cambio de título/slug del manga para renombrar la carpeta
        add_action('save_post_manga', array($this, 'on_manga_save'), 20, 3);

        // Guardar categorías al publicar/actualizar
        add_action('save_post_manga', array($this, 'save_categories_on_publish'), 10, 1);
    }

    public function add_meta_box() {
        add_meta_box(
            'mcm_manager',
            '📚 Gestión de Capítulos — BloomScans',
            array($this, 'render_meta_box'),
            'manga',
            'normal',
            'high'
        );
    }

    public function enqueue_assets($hook) {
        global $post;
        if ($hook !== 'post.php' && $hook !== 'post-new.php') return;
        if (!$post || $post->post_type !== 'manga') return;

        wp_enqueue_style('mcm-admin', MCM_PLUGIN_URL . 'assets/css/admin.css', array(), MCM_VERSION);
        wp_enqueue_script('mcm-admin', MCM_PLUGIN_URL . 'assets/js/admin.js', array('jquery', 'jquery-ui-sortable'), MCM_VERSION, true);

        wp_localize_script('mcm-admin', 'mcmData', array(
            'ajax_url' => admin_url('admin-ajax.php'),
            'nonce'    => wp_create_nonce('mcm_ajax_nonce'),
            'post_id'  => $post->ID,
        ));
    }

    public function render_meta_box($post) {
        wp_nonce_field('mcm_save', 'mcm_nonce');
        $chapters = $this->get_chapters($post->ID);
        include MCM_PLUGIN_DIR . 'templates/meta-box.php';
    }

    // =========================================================================
    // FIX: RENOMBRADO DE CARPETA CUANDO CAMBIA EL SLUG DEL MANGA
    // =========================================================================

    /**
     * Guarda el slug actual antes de que WordPress lo actualice.
     * Se llama en save_post_manga (prioridad 20, después de que WP guardó el nuevo slug).
     */
    public function on_manga_save($post_id, $post, $update) {
        if (!$update) return; // Solo en actualizaciones, no en creaciones nuevas
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
        if (!current_user_can('edit_post', $post_id)) return;

        $old_slug = get_post_meta($post_id, '_mcm_manga_slug', true);
        $new_slug = sanitize_title($post->post_title);

        // Si el slug cambió y teníamos una carpeta con el slug anterior, renombrarla
        if (!empty($old_slug) && $old_slug !== $new_slug) {
            $this->rename_manga_folder($old_slug, $new_slug, $post_id);
        }

        // Actualizar el slug guardado
        update_post_meta($post_id, '_mcm_manga_slug', $new_slug);
    }

    /**
     * Renombra la carpeta física del manga y actualiza las URLs en todos los posts de capítulos.
     */
    private function rename_manga_folder($old_slug, $new_slug, $manga_id) {
        $upload_dir = wp_upload_dir();
        $old_path   = $upload_dir['basedir'] . '/manhwas/' . $old_slug;
        $new_path   = $upload_dir['basedir'] . '/manhwas/' . $new_slug;

        if (!file_exists($old_path)) return false;
        if (file_exists($new_path)) return false; // Evitar colisiones

        // Renombrar carpeta
        if (!rename($old_path, $new_path)) return false;

        // Actualizar URLs en todos los posts de capítulos de este manga
        global $wpdb;
        $chapter_posts = $wpdb->get_col($wpdb->prepare(
            "SELECT p.ID FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm ON p.ID = pm.post_id
             WHERE pm.meta_key = 'ero_seri' AND pm.meta_value = %d",
            $manga_id
        ));

        $old_base_url = $upload_dir['baseurl'] . '/manhwas/' . $old_slug;
        $new_base_url = $upload_dir['baseurl'] . '/manhwas/' . $new_slug;

        foreach ($chapter_posts as $chapter_post_id) {
            // Actualizar post_content
            $content = get_post_field('post_content', $chapter_post_id);
            if ($content && strpos($content, $old_base_url) !== false) {
                $new_content = str_replace($old_base_url, $new_base_url, $content);
                wp_update_post(array('ID' => $chapter_post_id, 'post_content' => $new_content));
            }

            // Actualizar meta _chapter_images_urls
            $images_urls = get_post_meta($chapter_post_id, '_chapter_images_urls', true);
            if (is_array($images_urls)) {
                $images_urls = array_map(function($url) use ($old_base_url, $new_base_url) {
                    return str_replace($old_base_url, $new_base_url, $url);
                }, $images_urls);
                update_post_meta($chapter_post_id, '_chapter_images_urls', $images_urls);
            }

            // Actualizar meta ero_chapter_images
            $ero_images = get_post_meta($chapter_post_id, 'ero_chapter_images', true);
            if (is_array($ero_images)) {
                $ero_images = array_map(function($img) use ($old_base_url, $new_base_url) {
                    if (is_array($img) && isset($img['url'])) {
                        $img['url'] = str_replace($old_base_url, $new_base_url, $img['url']);
                    } elseif (is_string($img)) {
                        $img = str_replace($old_base_url, $new_base_url, $img);
                    }
                    return $img;
                }, $ero_images);
                update_post_meta($chapter_post_id, 'ero_chapter_images', $ero_images);
            }

            clean_post_cache($chapter_post_id);
        }

        // Limpiar caché del manga
        $this->clear_chapters_cache($manga_id);
        clean_post_cache($manga_id);

        return true;
    }

    /**
     * AJAX: Renombrar carpeta manualmente (botón en el panel)
     */
    public function ajax_rename_manga_folder() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id  = intval($_POST['post_id']);
        $new_slug  = sanitize_title(get_the_title($manga_id));
        $old_slug  = get_post_meta($manga_id, '_mcm_manga_slug', true);

        if (empty($old_slug)) {
            // No había slug guardado: simplemente guardar el actual
            update_post_meta($manga_id, '_mcm_manga_slug', $new_slug);
            wp_send_json_success(array('message' => 'Slug inicializado: ' . $new_slug));
        }

        if ($old_slug === $new_slug) {
            wp_send_json_success(array('message' => 'La carpeta ya tiene el nombre correcto.'));
        }

        $result = $this->rename_manga_folder($old_slug, $new_slug, $manga_id);
        if ($result) {
            update_post_meta($manga_id, '_mcm_manga_slug', $new_slug);
            wp_send_json_success(array(
                'message' => "Carpeta renombrada de '{$old_slug}' a '{$new_slug}' y URLs actualizadas en todos los capítulos."
            ));
        } else {
            wp_send_json_error(array(
                'message' => "No se pudo renombrar la carpeta. Verifica que existe '{$old_slug}' y que '{$new_slug}' no existe ya."
            ));
        }
    }

    // =========================================================================
    // CAPÍTULOS
    // =========================================================================

    public function get_chapters($manga_id, $use_cache = true) {
        $cache_key = 'mcm_chapters_' . $manga_id;
        if ($use_cache) {
            $cached = get_transient($cache_key);
            if ($cached !== false) return $cached;
        }

        $manga_slug = $this->get_manga_slug($manga_id);
        $upload_dir = wp_upload_dir();
        $base_path  = $upload_dir['basedir'] . '/manhwas/' . $manga_slug;

        $chapters = array();

        if (file_exists($base_path)) {
            $chapter_dirs = glob($base_path . '/capitulo_*', GLOB_ONLYDIR);
            foreach ($chapter_dirs as $dir) {
                $chapter_num = str_replace('capitulo_', '', basename($dir));
                $images      = glob($dir . '/*.{jpg,jpeg,png,gif,webp}', GLOB_BRACE);
                $post_id     = $this->get_chapter_post_id($manga_id, $chapter_num);

                $chapters[$chapter_num] = array(
                    'number'      => $chapter_num,
                    'path'        => $dir,
                    'image_count' => count($images),
                    'images'      => $images,
                    'post_id'     => $post_id,
                    'post_exists' => !empty($post_id),
                    'source'      => 'folder',
                );
            }
        }

        global $wpdb;
        $manual_posts = $wpdb->get_results($wpdb->prepare(
            "SELECT p.ID, pm.meta_value as chapter_num
             FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm ON p.ID = pm.post_id
             WHERE pm.meta_key = 'ero_chapter'
             AND EXISTS (
                 SELECT 1 FROM {$wpdb->postmeta} pm2
                 WHERE pm2.post_id = p.ID
                 AND pm2.meta_key = 'ero_seri'
                 AND pm2.meta_value = %d
             )",
            $manga_id
        ));

        foreach ($manual_posts as $mpost) {
            $chapter_num = $mpost->chapter_num;
            if (isset($chapters[$chapter_num])) {
                $chapters[$chapter_num]['post_id']     = $mpost->ID;
                $chapters[$chapter_num]['post_exists'] = true;
            } else {
                $chapters[$chapter_num] = array(
                    'number'      => $chapter_num,
                    'path'        => null,
                    'image_count' => 0,
                    'images'      => array(),
                    'post_id'     => $mpost->ID,
                    'post_exists' => true,
                    'source'      => 'manual',
                );
            }
        }

        $chapters = array_values($chapters);
        usort($chapters, function($a, $b) {
            return floatval($a['number']) - floatval($b['number']);
        });

        set_transient($cache_key, $chapters, 5 * MINUTE_IN_SECONDS);
        return $chapters;
    }

    private function clear_chapters_cache($manga_id) {
        delete_transient('mcm_chapters_' . $manga_id);
    }

    /**
     * Obtiene el slug actual del manga (guardado en meta o generado desde el título).
     */
    private function get_manga_slug($manga_id) {
        $slug = get_post_meta($manga_id, '_mcm_manga_slug', true);
        if (empty($slug)) {
            $slug = sanitize_title(get_the_title($manga_id));
            update_post_meta($manga_id, '_mcm_manga_slug', $slug);
        }
        return $slug;
    }

    private function get_chapter_post_id($manga_id, $chapter_num) {
        $posts = get_posts(array(
            'post_type'      => 'post',
            'meta_query'     => array(
                'relation' => 'AND',
                array('key' => 'ero_seri',    'value' => $manga_id,    'compare' => '='),
                array('key' => 'ero_chapter', 'value' => $chapter_num, 'compare' => '='),
            ),
            'posts_per_page' => 1,
            'fields'         => 'ids',
        ));
        return !empty($posts) ? $posts[0] : null;
    }

    // =========================================================================
    // FECHA RELATIVA: toma la hora real del capítulo vecino mayor y resta segundos
    // =========================================================================

    /**
     * Devuelve la fecha correcta para un capítulo nuevo, preservando las fechas reales.
     *
     * Estrategia:
     *   1. Si existe un capítulo con número MAYOR al nuevo, toma su post_date
     *      y le resta $gap_seconds. Así el nuevo queda justo "antes" del siguiente.
     *   2. Si no existe ningún capítulo mayor (es el más alto), usa current_time()
     *      — fecha real de subida, como siempre ha funcionado.
     *   3. Si es una actualización de un capítulo ya existente, conserva su fecha actual
     *      (no la modifica), a menos que se llame desde sync_all o reorder.
     *
     * @param  int    $manga_id
     * @param  string $chapter_num  Número del capítulo que se va a crear/actualizar
     * @param  int    $gap_seconds  Segundos de separación respecto al capítulo superior (default 30)
     * @return array  ['date' => ..., 'date_gmt' => ...]
     */
    private function get_chapter_date($manga_id, $chapter_num, $gap_seconds = 30) {
        global $wpdb;

        // Buscar el post del capítulo inmediatamente SUPERIOR a $chapter_num
        $next_post = $wpdb->get_row($wpdb->prepare(
            "SELECT p.post_date
             FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm_seri  ON p.ID = pm_seri.post_id
             INNER JOIN {$wpdb->postmeta} pm_chap  ON p.ID = pm_chap.post_id
             WHERE pm_seri.meta_key  = 'ero_seri'    AND pm_seri.meta_value  = %d
               AND pm_chap.meta_key = 'ero_chapter'
               AND CAST(pm_chap.meta_value AS DECIMAL(10,2)) > CAST(%s AS DECIMAL(10,2))
               AND p.post_status = 'publish'
             ORDER BY CAST(pm_chap.meta_value AS DECIMAL(10,2)) ASC
             LIMIT 1",
            $manga_id,
            (string) $chapter_num
        ));

        if ($next_post && !empty($next_post->post_date)) {
            // Restar $gap_seconds a la fecha del capítulo superior
            $ts   = strtotime($next_post->post_date) - $gap_seconds;
            $date = date('Y-m-d H:i:s', $ts);
        } else {
            // Es el capítulo más reciente (o el primero): fecha de ahora
            $date = current_time('mysql');
        }

        return array(
            'date'     => $date,
            'date_gmt' => get_gmt_from_date($date),
        );
    }

    /**
     * Versión para sync_all / reorder: recalcula TODAS las fechas de los capítulos
     * de un manga para que queden ordenadas cronológicamente preservando la fecha
     * del capítulo más reciente (el más alto) y restando $gap_seconds en cascada.
     *
     * @param  int $manga_id
     * @param  int $gap_seconds  Separación entre capítulos consecutivos
     */
    /**
     * Corrección mínima de fechas — toca solo lo estrictamente necesario.
     *
     * REGLA: los capítulos deben estar ordenados de forma que
     *   post_date(cap N) < post_date(cap N+1)   [cap mayor = más reciente]
     *
     * ALGORITMO "minimal-touch":
     *   1. Ordenar caps de MENOR a MAYOR número (array).
     *   2. Recorrer de derecha a izquierda (cap más alto primero).
     *      El cap de mayor número NUNCA se toca.
     *   3. Para cada cap[i], verificar DOS condiciones:
     *        a) ¿ ts[i] >= ts[i+1] ?  → conflicto con el de arriba (está "después")
     *        b) ¿ i > 0 && ts[i] <= ts[i-1] ? → conflicto con el de abajo (está "antes")
     *      Si hay cualquier conflicto, asignar ts[i] = ts[i+1] - gap.
     *   4. Solo escribir en BD los que realmente cambiaron.
     *
     * Resultado: serie ya correcta = 0 escrituras.
     */
    public function recalculate_all_chapter_dates($manga_id, $gap_seconds = 30) {
        global $wpdb;

        $posts = $wpdb->get_results($wpdb->prepare(
            "SELECT p.ID, pm.meta_value as chapter_num, p.post_date
             FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm ON p.ID = pm.post_id
             WHERE pm.meta_key = 'ero_chapter'
               AND EXISTS (
                   SELECT 1 FROM {$wpdb->postmeta} pm2
                   WHERE pm2.post_id = p.ID
                     AND pm2.meta_key = 'ero_seri'
                     AND pm2.meta_value = %d
               )
               AND p.post_status = 'publish'
             ORDER BY CAST(pm.meta_value AS DECIMAL(10,2)) ASC",
            $manga_id
        ));

        if (count($posts) < 2) return;

        // Snapshot inicial de timestamps
        $original = array();
        $current  = array();
        foreach ($posts as $p) {
            $ts = strtotime($p->post_date);
            $ts = ($ts && $ts > 0) ? $ts : current_time('timestamp');
            $original[] = $ts;
            $current[]  = $ts;
        }

        $n = count($posts);

        // Recorrer de derecha a izquierda: el cap más alto (último) no se toca nunca
        for ($i = $n - 2; $i >= 0; $i--) {
            $conflict_above = ($current[$i] >= $current[$i + 1]);        // >= siguiente
            $conflict_below = ($i > 0 && $current[$i] <= $current[$i - 1]); // <= anterior

            if ($conflict_above || $conflict_below) {
                $current[$i] = $current[$i + 1] - $gap_seconds;
            }
        }

        // Segunda pasada de izquierda a derecha para detectar colisiones
        // que la primera pasada pueda haber introducido hacia abajo
        for ($i = 1; $i < $n - 1; $i++) {
            if ($current[$i] >= $current[$i + 1]) {
                $current[$i] = $current[$i + 1] - $gap_seconds;
            }
        }

        // Escribir SOLO los que cambiaron
        foreach ($posts as $i => $p) {
            if ($current[$i] === $original[$i]) continue; // sin cambio, no tocar

            $new_date = date('Y-m-d H:i:s', $current[$i]);
            wp_update_post(array(
                'ID'            => $p->ID,
                'post_date'     => $new_date,
                'post_date_gmt' => get_gmt_from_date($new_date),
            ));
        }
    }
    // =========================================================================
    // FIX: AUTO-CATEGORIZACIÓN
    // =========================================================================

    /**
     * Obtiene las categorías a asignar a los capítulos.
     * Prioridad: (1) categorías guardadas en meta del manga,
     *            (2) categoría con el mismo nombre que el manga,
     *            (3) ninguna (deja sin categoría).
     */
    private function get_categories_for_manga($manga_id) {
        $saved = get_post_meta($manga_id, '_mcm_chapter_categories', true);
        if (!empty($saved) && is_array($saved)) {
            return array_filter(array_map('intval', $saved));
        }

        // Intentar encontrar categoría con el nombre del manga
        $manga_title = get_the_title($manga_id);
        $term = get_term_by('name', $manga_title, 'category');
        if ($term && !is_wp_error($term)) {
            $cats = array($term->term_id);
            update_post_meta($manga_id, '_mcm_chapter_categories', $cats);
            return $cats;
        }

        // Por slug
        $term = get_term_by('slug', sanitize_title($manga_title), 'category');
        if ($term && !is_wp_error($term)) {
            $cats = array($term->term_id);
            update_post_meta($manga_id, '_mcm_chapter_categories', $cats);
            return $cats;
        }

        return array();
    }

    // =========================================================================
    // AJAX: SUBIR CAPÍTULO
    // =========================================================================

    public function ajax_upload_chapters() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        // Aumentar límites para ZIPs grandes
        @ini_set('max_execution_time', 120);
        @ini_set('memory_limit', '512M');

        $manga_id    = intval($_POST['post_id']);
        $file_index  = intval($_POST['file_index']);
        $manga_title = get_the_title($manga_id);
        $manga_slug  = $this->get_manga_slug($manga_id);
        $upload_dir  = wp_upload_dir();
        $base_path   = $upload_dir['basedir'] . '/manhwas/' . $manga_slug;

        if (!wp_mkdir_p($base_path)) {
            wp_send_json_error(array('message' => 'Error al crear directorio base'));
        }

        $file_key = 'zip_file_' . $file_index;
        if (!isset($_FILES[$file_key]) || $_FILES[$file_key]['error'] !== UPLOAD_ERR_OK) {
            wp_send_json_error(array('message' => 'Error al recibir archivo'));
        }

        $file     = $_FILES[$file_key];
        $filename = pathinfo($file['name'], PATHINFO_FILENAME);

        preg_match('/(?:cap|capitulo|chapter)[^\d]*(\d+(?:\.\d+)?)/i', $filename, $matches);
        if (!isset($matches[1])) {
            preg_match('/(\d+(?:\.\d+)?)/', $filename, $matches);
        }
        if (!isset($matches[1]) || $matches[1] === '') {
            wp_send_json_error(array('message' => 'No se detectó número de capítulo en: ' . $file['name']));
        }

        $chapter_num  = $matches[1];
        $chapter_path = $base_path . '/capitulo_' . $chapter_num;
        $upload_ext   = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));

        $text_extensions_direct = array('txt', 'md', 'html', 'htm');

        if (in_array($upload_ext, $text_extensions_direct)) {
            $text_content = file_get_contents($file['tmp_name']);
            if ($text_content === false) {
                wp_send_json_error(array('message' => 'Error al leer el archivo: ' . $file['name']));
            }
            $text_content = $this->clean_text_content($text_content, $upload_ext);
            $post_created = $this->create_or_update_novel_chapter_post($manga_id, $chapter_num, $manga_title, $text_content);
        } elseif ($upload_ext === 'docx') {
            $text_content = $this->extract_text_from_docx($file['tmp_name']);
            if (is_wp_error($text_content)) {
                wp_send_json_error(array('message' => $text_content->get_error_message()));
            }
            $post_created = $this->create_or_update_novel_chapter_post($manga_id, $chapter_num, $manga_title, $text_content);
        } else {
            // ZIP
            $zip = new ZipArchive();
            if ($zip->open($file['tmp_name']) === true) {
                $image_extensions = array('jpg', 'jpeg', 'png', 'gif', 'webp');
                $text_extensions  = array('txt', 'md', 'html', 'htm', 'docx', 'odt', 'rtf', 'epub');
                $image_files = array();
                $text_files  = array();

                // statIndex() devuelve metadatos sin descomprimir — más rápido que getNameIndex()
                // para ZIPs con muchas entradas porque evita alocaciones de string en cada paso.
                // comp_size === 0 && name termina en '/' → directorio, saltar.
                for ($i = 0; $i < $zip->numFiles; $i++) {
                    $stat = $zip->statIndex($i);
                    if (!$stat) continue;
                    $zname = $stat['name'];
                    // Saltar directorios y archivos ocultos (Mac __MACOSX, etc.)
                    if (substr($zname, -1) === '/'
                        || strpos(basename($zname), '.') === 0
                        || strpos($zname, '__MACOSX') !== false) continue;
                    $ext = strtolower(pathinfo($zname, PATHINFO_EXTENSION));
                    if (in_array($ext, $image_extensions)) {
                        $image_files[] = array('zip_name' => $zname, 'ext' => $ext);
                    } elseif (in_array($ext, $text_extensions)) {
                        $text_files[] = array('zip_name' => $zname, 'ext' => $ext);
                    }
                }

                if (!empty($text_files) && empty($image_files)) {
                    // Novela en ZIP
                    usort($text_files, function($a, $b) {
                        return strnatcasecmp($a['zip_name'], $b['zip_name']);
                    });
                    $full_text = '';
                    foreach ($text_files as $tf) {
                        $raw = $zip->getFromName($tf['zip_name']);
                        if ($raw === false) continue;
                        if (in_array($tf['ext'], array('docx', 'odt', 'epub'))) {
                            $tmp = tempnam(sys_get_temp_dir(), 'mcm_') . '.' . $tf['ext'];
                            file_put_contents($tmp, $raw);
                            $extracted = ($tf['ext'] === 'docx')
                                ? $this->extract_text_from_docx($tmp)
                                : $this->extract_text_from_rtf_odt($tmp, $tf['ext']);
                            @unlink($tmp);
                            if (!is_wp_error($extracted)) $full_text .= $extracted . "\n\n";
                        } else {
                            $full_text .= $this->clean_text_content($raw, $tf['ext']) . "\n\n";
                        }
                    }
                    $zip->close();
                    $text_content = trim($full_text);
                    $post_created = $this->create_or_update_novel_chapter_post($manga_id, $chapter_num, $manga_title, $text_content);
                } else {
                    // Manga con imágenes
                    if (file_exists($chapter_path)) {
                        $this->delete_directory($chapter_path);
                    }
                    if (!wp_mkdir_p($chapter_path)) {
                        wp_send_json_error(array('message' => 'Error al crear directorio del capítulo'));
                    }

                    // FAST EXTRACT: recopilar imágenes del ZIP clasificadas y ordenadas,
                    // luego escribirlas directamente con nombre final __mcm_tmp_NNNN.ext.
                    // Evita colisiones entre archivos con el mismo nombre en subcarpetas distintas
                    // y es tan rápido como extractTo porque escribe cada archivo una sola vez.
                    $extracted_count = $this->extract_and_normalize($zip, $image_files, $chapter_path);
                    $zip->close();

                    $post_created = $this->create_or_update_chapter_post($manga_id, $chapter_num, $manga_title);

                    wp_update_post(array(
                        'ID'               => $manga_id,
                        'post_modified'    => current_time('mysql'),
                        'post_modified_gmt'=> current_time('mysql', 1),
                    ));

                    $this->clear_chapters_cache($manga_id);
                    clean_post_cache($manga_id);
                    if ($post_created) clean_post_cache($post_created);
                    delete_transient('madara_chapter_list_' . $manga_id);
                    delete_transient('wp_manga_chapter_' . $manga_id);

                    wp_send_json_success(array(
                        'message'        => 'Capítulo ' . $chapter_num . ' procesado',
                        'chapter_number' => $chapter_num,
                        'images'         => $extracted_count,
                        'filename'       => $file['name'],
                        'post_created'   => $post_created,
                    ));
                }
            } else {
                wp_send_json_error(array('message' => 'Error al abrir ZIP: ' . $file['name']));
            }
        }

        // Respuesta para archivos de texto
        if (isset($text_content)) {
            wp_update_post(array(
                'ID'               => $manga_id,
                'post_modified'    => current_time('mysql'),
                'post_modified_gmt'=> current_time('mysql', 1),
            ));
            $this->clear_chapters_cache($manga_id);
            clean_post_cache($manga_id);
            if (!empty($post_created)) clean_post_cache($post_created);
            delete_transient('madara_chapter_list_' . $manga_id);
            delete_transient('wp_manga_chapter_' . $manga_id);

            wp_send_json_success(array(
                'message'        => 'Capítulo ' . $chapter_num . ' (novela) procesado',
                'chapter_number' => $chapter_num,
                'images'         => 0,
                'filename'       => $file['name'],
                'post_created'   => $post_created ?? false,
            ));
        }
    }

    // =========================================================================
    // CREAR / ACTUALIZAR POST DE CAPÍTULO
    // =========================================================================

    private function create_or_update_chapter_post($manga_id, $chapter_num, $manga_title) {
        $manga_slug  = $this->get_manga_slug($manga_id);
        $upload_dir  = wp_upload_dir();
        $chapter_path = $upload_dir['basedir'] . '/manhwas/' . $manga_slug . '/capitulo_' . $chapter_num;

        if (!file_exists($chapter_path)) return false;

        $images = glob($chapter_path . '/*.{jpg,jpeg,png,gif,webp}', GLOB_BRACE);
        natsort($images);
        if (empty($images)) return false;

        $upload_basedir = wp_normalize_path($upload_dir['basedir']);
        $upload_baseurl = $upload_dir['baseurl'];

        $images_urls = array_map(function($p) use ($upload_basedir, $upload_baseurl) {
            return str_replace($upload_basedir, $upload_baseurl, wp_normalize_path($p));
        }, $images);

        $post_content = implode("\n", array_map(function($url) {
            return '<img src="' . esc_url($url) . '" alt="" class="alignnone size-full">';
        }, $images_urls));

        $existing_post_id  = $this->get_chapter_post_id($manga_id, $chapter_num);
        $saved_categories  = $this->get_categories_for_manga($manga_id);

        if ($existing_post_id) {
            // Capítulo ya existe: NO modificar la fecha — conservar la real de cuando se subió
            wp_update_post(array(
                'ID'           => $existing_post_id,
                'post_title'   => $manga_title . ' - Capítulo ' . $chapter_num,
                'post_content' => $post_content,
            ));
            $post_id = $existing_post_id;
        } else {
            $chapter_date = $this->get_chapter_date($manga_id, $chapter_num);
            $post_data = array(
                'post_title'    => $manga_title . ' - Capítulo ' . $chapter_num,
                'post_content'  => $post_content,
                'post_status'   => 'publish',
                'post_type'     => 'post',
                'post_author'   => get_current_user_id(),
                'post_date'     => $chapter_date['date'],
                'post_date_gmt' => $chapter_date['date_gmt'],
            );
            $post_id = wp_insert_post($post_data, true);
            if (is_wp_error($post_id)) return false;

            update_post_meta($post_id, 'ero_seri',    $manga_id);
            update_post_meta($post_id, 'ero_chapter', $chapter_num);
        }

        update_post_meta($post_id, '_mcm_source',           'folder');
        update_post_meta($post_id, '_chapter_images_urls',  $images_urls);
        update_post_meta($post_id, 'ero_chapter_images',    $images_urls);

        if (!empty($saved_categories)) {
            wp_set_post_terms($post_id, $saved_categories, 'category', false);
        }

        $post_obj = get_post($post_id);
        do_action('save_post',      $post_id, $post_obj, !empty($existing_post_id));
        do_action('wp_insert_post', $post_id, $post_obj, !empty($existing_post_id));

        return $post_id;
    }

    private function create_or_update_novel_chapter_post($manga_id, $chapter_num, $manga_title, $text_html) {
        $existing_post_id = $this->get_chapter_post_id($manga_id, $chapter_num);
        $saved_categories = $this->get_categories_for_manga($manga_id);

        if ($existing_post_id) {
            // Conservar fecha original
            wp_update_post(array(
                'ID'           => $existing_post_id,
                'post_title'   => $manga_title . ' - Capítulo ' . $chapter_num,
                'post_content' => $text_html,
            ));
            $post_id = $existing_post_id;
        } else {
            $post_data = array(
                'post_title'    => $manga_title . ' - Capítulo ' . $chapter_num,
                'post_content'  => $text_html,
                'post_status'   => 'publish',
                'post_type'     => 'post',
                'post_author'   => get_current_user_id(),
                'post_date'     => $chapter_date['date'],
                'post_date_gmt' => $chapter_date['date_gmt'],
            );
            $post_id = wp_insert_post($post_data, true);
            if (is_wp_error($post_id)) return false;

            update_post_meta($post_id, 'ero_seri',    $manga_id);
            update_post_meta($post_id, 'ero_chapter', $chapter_num);
        }

        update_post_meta($post_id, 'ero_chapter_mode', 'minimal');
        update_post_meta($post_id, '_mcm_source', 'text');

        if (!empty($saved_categories)) {
            wp_set_post_terms($post_id, $saved_categories, 'category', false);
        }

        $post_obj = get_post($post_id);
        do_action('save_post',      $post_id, $post_obj, !empty($existing_post_id));
        do_action('wp_insert_post', $post_id, $post_obj, !empty($existing_post_id));

        return $post_id;
    }

    // =========================================================================
    // AJAX: GET CHAPTERS
    // =========================================================================

    public function ajax_get_chapters() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        $manga_id      = intval($_POST['post_id']);
        $force_refresh = isset($_POST['force_refresh']) && $_POST['force_refresh'];
        $chapters      = $this->get_chapters($manga_id, !$force_refresh);

        ob_start();
        if (!empty($chapters)) {
            foreach ($chapters as $chapter) {
                include MCM_PLUGIN_DIR . 'templates/chapter-item.php';
            }
        }
        $html = ob_get_clean();

        wp_send_json_success(array('html' => $html, 'count' => count($chapters)));
    }

    // =========================================================================
    // AJAX: DELETE CHAPTER
    // =========================================================================

    public function ajax_delete_chapter() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id    = intval($_POST['post_id']);
        $chapter_num = $_POST['chapter_number'];
        $manga_slug  = $this->get_manga_slug($manga_id);
        $upload_dir  = wp_upload_dir();
        $chapter_path = $upload_dir['basedir'] . '/manhwas/' . $manga_slug . '/capitulo_' . $chapter_num;

        $deleted_folder = false;
        $deleted_post   = false;

        if (file_exists($chapter_path)) {
            $this->delete_directory($chapter_path);
            $deleted_folder = true;
        }

        $post_id = $this->get_chapter_post_id($manga_id, $chapter_num);
        if ($post_id) {
            wp_delete_post($post_id, true);
            $deleted_post = true;

            clean_post_cache($post_id);
            clean_post_cache($manga_id);
            delete_transient('madara_chapter_list_' . $manga_id);
            delete_transient('wp_manga_chapter_' . $manga_id);
            delete_transient('manga_chapters_' . $manga_id);
            wp_cache_delete($manga_id, 'posts');
            wp_cache_delete($post_id, 'posts');
            if (function_exists('wp_cache_flush')) wp_cache_flush();
        }

        $this->clear_chapters_cache($manga_id);

        if ($deleted_post && $deleted_folder) {
            wp_send_json_success(array('message' => 'Capítulo eliminado (carpeta y post)'));
        } elseif ($deleted_post) {
            wp_send_json_success(array('message' => 'Post eliminado (capítulo manual)'));
        } elseif ($deleted_folder) {
            wp_send_json_success(array('message' => 'Carpeta eliminada (sin post)'));
        } else {
            wp_send_json_error(array('message' => 'Capítulo no encontrado'));
        }
    }

    // =========================================================================
    // AJAX: SYNC ALL
    // =========================================================================

    public function ajax_sync_all() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        @ini_set('max_execution_time', 300);
        @ini_set('memory_limit', '512M');

        $manga_id    = intval($_POST['post_id']);
        $manga_title = get_the_title($manga_id);
        $upload_dir  = wp_upload_dir();

        global $wpdb;
        $existing_posts = $wpdb->get_results($wpdb->prepare(
            "SELECT p.ID, p.post_date, pm.meta_value as chapter_num
             FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm ON p.ID = pm.post_id
             WHERE pm.meta_key = 'ero_chapter'
             AND EXISTS (
                 SELECT 1 FROM {$wpdb->postmeta} pm2
                 WHERE pm2.post_id = p.ID
                 AND pm2.meta_key = 'ero_seri'
                 AND pm2.meta_value = %d
             )
             ORDER BY CAST(pm.meta_value AS DECIMAL(10,2)) ASC",
            $manga_id
        ));

        $existing_by_chapter = array();
        foreach ($existing_posts as $ep) {
            $existing_by_chapter[$ep->chapter_num] = $ep;
        }

        $chapters_from_folders = $this->get_chapters($manga_id, false);
        $saved_categories      = $this->get_categories_for_manga($manga_id);

        $updated_count = 0;
        $created_count = 0;

        foreach ($chapters_from_folders as $chapter) {
            $chapter_num = $chapter['number'];
            $images      = $chapter['images'];
            natsort($images);

            if (empty($images)) continue;

            $images_urls = array_map(function($p) use ($upload_dir) {
                return str_replace(
                    wp_normalize_path($upload_dir['basedir']),
                    $upload_dir['baseurl'],
                    wp_normalize_path($p)
                );
            }, $images);

            $post_content  = implode("\n", array_map(function($url) {
                return '<img src="' . esc_url($url) . '" alt="" class="alignnone size-full">';
            }, $images_urls));

            if (isset($existing_by_chapter[$chapter_num])) {
                $post_id = $existing_by_chapter[$chapter_num]->ID;
                // Preservar fecha original del capítulo existente
                wp_update_post(array(
                    'ID'            => $post_id,
                    'post_title'    => $manga_title . ' - Capítulo ' . $chapter_num,
                    'post_content'  => $post_content,
                ));
                update_post_meta($post_id, '_mcm_source',          'folder');
                update_post_meta($post_id, '_chapter_images_urls', $images_urls);
                update_post_meta($post_id, 'ero_chapter_images',   $images_urls);
                if (!empty($saved_categories)) {
                    wp_set_post_terms($post_id, $saved_categories, 'category', false);
                }
                $updated_count++;
            } else {
                // Nuevo capítulo: calcular fecha relativa al vecino superior
                $chapter_date = $this->get_chapter_date($manga_id, $chapter_num);
                $post_data = array(
                    'post_title'    => $manga_title . ' - Capítulo ' . $chapter_num,
                    'post_content'  => $post_content,
                    'post_status'   => 'publish',
                    'post_type'     => 'post',
                    'post_author'   => get_current_user_id(),
                    'post_date'     => $chapter_date['date'],
                    'post_date_gmt' => $chapter_date['date_gmt'],
                );
                $post_id = wp_insert_post($post_data, true);
                if (!is_wp_error($post_id)) {
                    update_post_meta($post_id, 'ero_seri',             $manga_id);
                    update_post_meta($post_id, 'ero_chapter',          $chapter_num);
                    update_post_meta($post_id, '_mcm_source',          'folder');
                    update_post_meta($post_id, '_chapter_images_urls', $images_urls);
                    update_post_meta($post_id, 'ero_chapter_images',   $images_urls);
                    if (!empty($saved_categories)) {
                        wp_set_post_terms($post_id, $saved_categories, 'category', false);
                    }
                    $post_obj = get_post($post_id);
                    do_action('save_post',      $post_id, $post_obj, true);
                    do_action('wp_insert_post', $post_id, $post_obj, true);
                    $created_count++;
                }
            }
        }

        // Recalcular fechas en cascada para garantizar orden correcto
        $this->recalculate_all_chapter_dates($manga_id);

        clean_post_cache($manga_id);
        $this->clear_chapters_cache($manga_id);

        wp_send_json_success(array(
            'message' => sprintf('Sincronización completa: %d actualizados, %d creados', $updated_count, $created_count),
            'updated' => $updated_count,
            'created' => $created_count,
            'total'   => count($chapters_from_folders),
        ));
    }

    // =========================================================================
    // AJAX: CATEGORÍAS
    // =========================================================================

    public function save_categories_on_publish($post_id) {
        if (!isset($_POST['mcm_nonce']) || !wp_verify_nonce($_POST['mcm_nonce'], 'mcm_save')) return;
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
        if (!current_user_can('edit_post', $post_id)) return;

        $categories = isset($_POST['mcm_categories']) ? array_map('intval', (array) $_POST['mcm_categories']) : array();
        update_post_meta($post_id, '_mcm_chapter_categories', $categories);

        // Inicializar slug si es nuevo post
        $slug = get_post_meta($post_id, '_mcm_manga_slug', true);
        if (empty($slug)) {
            update_post_meta($post_id, '_mcm_manga_slug', sanitize_title(get_the_title($post_id)));
        }
    }

    public function ajax_save_category_config() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id   = intval($_POST['post_id']);
        $categories = isset($_POST['categories']) ? array_map('intval', $_POST['categories']) : array();

        update_post_meta($manga_id, '_mcm_chapter_categories', $categories);

        wp_send_json_success(array('message' => 'Categorías guardadas', 'categories' => $categories));
    }

    // =========================================================================
    // AJAX: REORDENAR CAPÍTULOS
    // =========================================================================

    public function ajax_reorder_chapters() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id  = intval($_POST['post_id']);
        $new_order = $_POST['chapter_order'];

        if (empty($new_order) || !is_array($new_order)) {
            wp_send_json_error(array('message' => 'Orden inválido'));
        }

        // Recalcular todas las fechas en cascada preservando la del capítulo más alto
        $this->recalculate_all_chapter_dates($manga_id);

        $reordered_count = count($new_order);

        clean_post_cache($manga_id);
        $this->clear_chapters_cache($manga_id);

        wp_send_json_success(array(
            'message'   => sprintf('%d capítulos reordenados', $reordered_count),
            'reordered' => $reordered_count,
        ));
    }

    // =========================================================================
    // AJAX: IMÁGENES
    // =========================================================================

    public function ajax_add_images() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id    = intval($_POST['post_id']);
        $chapter_num = $_POST['chapter_number'];
        $manga_slug  = $this->get_manga_slug($manga_id);
        $upload_dir  = wp_upload_dir();
        $chapter_path = $upload_dir['basedir'] . '/manhwas/' . $manga_slug . '/capitulo_' . $chapter_num;

        if (!file_exists($chapter_path)) {
            wp_send_json_error(array('message' => 'Capítulo no existe'));
        }

        $uploaded = 0;
        foreach ($_FILES as $key => $file) {
            if (strpos($key, 'image') !== 0) continue;
            if ($file['error'] === UPLOAD_ERR_OK) {
                $ext      = pathinfo($file['name'], PATHINFO_EXTENSION);
                $existing = glob($chapter_path . '/*.' . $ext);
                $next_idx = count($existing);
                $new_name = str_pad($next_idx, 2, '0', STR_PAD_LEFT) . '.' . $ext;
                move_uploaded_file($file['tmp_name'], $chapter_path . '/' . $new_name);
                $uploaded++;
            }
        }

        $this->rename_images_in_order($chapter_path);
        $this->update_chapter_post($manga_id, $chapter_num);

        wp_send_json_success(array('message' => $uploaded . ' imágenes agregadas', 'count' => $uploaded));
    }

    public function ajax_delete_image() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id    = intval($_POST['post_id']);
        $chapter_num = $_POST['chapter_number'];
        $filename    = sanitize_file_name($_POST['filename']);
        $manga_slug  = $this->get_manga_slug($manga_id);
        $upload_dir  = wp_upload_dir();
        $image_path  = $upload_dir['basedir'] . '/manhwas/' . $manga_slug . '/capitulo_' . $chapter_num . '/' . $filename;

        if (!file_exists($image_path)) {
            wp_send_json_error(array('message' => 'Imagen no existe'));
        }

        unlink($image_path);
        $this->rename_images_in_order(dirname($image_path));
        $this->update_chapter_post($manga_id, $chapter_num);

        wp_send_json_success(array('message' => 'Imagen eliminada'));
    }

    public function ajax_reorder_images() {
        check_ajax_referer('mcm_ajax_nonce', 'nonce');
        if (!current_user_can('edit_posts')) {
            wp_send_json_error(array('message' => 'Permisos insuficientes'));
        }

        $manga_id    = intval($_POST['post_id']);
        $chapter_num = $_POST['chapter_number'];
        $image_order = $_POST['image_order'];
        $manga_slug  = $this->get_manga_slug($manga_id);
        $upload_dir  = wp_upload_dir();
        $chapter_path = $upload_dir['basedir'] . '/manhwas/' . $manga_slug . '/capitulo_' . $chapter_num;

        $temp_dir = $chapter_path . '_temp';
        wp_mkdir_p($temp_dir);

        foreach ($image_order as $index => $filename) {
            $old_path = $chapter_path . '/' . sanitize_file_name($filename);
            if (file_exists($old_path)) {
                $ext      = pathinfo($filename, PATHINFO_EXTENSION);
                $new_name = str_pad($index, 2, '0', STR_PAD_LEFT) . '.' . $ext;
                copy($old_path, $temp_dir . '/' . $new_name);
            }
        }

        foreach (glob($chapter_path . '/*') as $f) {
            if (is_file($f)) unlink($f);
        }
        foreach (glob($temp_dir . '/*') as $f) {
            rename($f, $chapter_path . '/' . basename($f));
        }
        rmdir($temp_dir);

        $this->update_chapter_post($manga_id, $chapter_num);

        wp_send_json_success(array('message' => 'Orden actualizado'));
    }

    // =========================================================================
    // HELPERS
    // =========================================================================

    private function rename_images_in_order($chapter_path) {
        return $this->cleanup_and_rename_fast($chapter_path);
    }

    /**
     * extract_and_normalize: extrae imágenes de un ZIP abierto directamente con nombres
     * finales (00.ext, 01.ext...), sin pasar por extractTo().
     *
     * Ventajas sobre extractTo():
     *   - Imposible colisión: dos archivos con el mismo nombre en subcarpetas distintas
     *     del ZIP nunca se sobreescriben porque se escribe con índice numérico único.
     *   - Una sola escritura por imagen (sin renombrado posterior).
     *   - Ignora archivos que no sean imágenes sin tocar el disco.
     *
     * @param ZipArchive $zip         ZIP ya abierto
     * @param array      $image_files Array de ['zip_name'=>..., 'ext'=>...] ya clasificado
     * @param string     $chapter_path Ruta destino (debe existir y estar vacía)
     * @return int Número de imágenes escritas
     */
    private function extract_and_normalize(ZipArchive $zip, array $image_files, $chapter_path) {
        if (empty($image_files)) return 0;

        // Ordenar por nombre natural (respeta 001.jpg < 002.jpg < 010.jpg)
        usort($image_files, function($a, $b) {
            return strnatcasecmp($a['zip_name'], $b['zip_name']);
        });

        $count = 0;
        foreach ($image_files as $index => $img) {
            $dest = $chapter_path . '/' . str_pad($index, 2, '0', STR_PAD_LEFT) . '.' . $img['ext'];

            // getStream() abre un stream de lectura sobre la entrada comprimida.
            // stream_copy_to_stream() copia directo ZIP→disco en chunks de 8 KB:
            // nunca carga la imagen completa en RAM, mucho más rápido en imágenes grandes.
            $src = $zip->getStream($img['zip_name']);
            if ($src === false) continue; // entrada corrupta, saltar

            $dst = fopen($dest, 'wb');
            if ($dst === false) { fclose($src); continue; }

            stream_copy_to_stream($src, $dst);
            fclose($src);
            fclose($dst);
            $count++;
        }

        return $count;
    }

    private function cleanup_and_rename_fast($chapter_path) {
        $allowed_exts = array('jpg', 'jpeg', 'png', 'gif', 'webp');
        $images = array();

        $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($chapter_path, RecursiveDirectoryIterator::SKIP_DOTS),
            RecursiveIteratorIterator::SELF_FIRST
        );

        foreach ($iterator as $file) {
            if ($file->isFile() && in_array(strtolower($file->getExtension()), $allowed_exts)) {
                $images[] = $file->getPathname();
            }
        }

        if (empty($images)) return array();

        natsort($images);
        $images        = array_values($images);
        $final_images  = array();

        foreach ($images as $index => $image_path) {
            $ext        = pathinfo($image_path, PATHINFO_EXTENSION);
            $final_name = $chapter_path . '/' . str_pad($index, 2, '0', STR_PAD_LEFT) . '.' . $ext;
            if ($image_path !== $final_name) {
                if (file_exists($final_name)) @unlink($final_name);
                rename($image_path, $final_name);
            }
            $final_images[] = $final_name;
        }

        $items = @scandir($chapter_path);
        if ($items) {
            foreach ($items as $item) {
                if ($item === '.' || $item === '..') continue;
                $path = $chapter_path . '/' . $item;
                if (is_dir($path)) {
                    $this->delete_directory($path);
                } elseif (is_file($path) && !in_array($path, $final_images)) {
                    @unlink($path);
                }
            }
        }

        return $final_images;
    }

    private function update_chapter_post($manga_id, $chapter_num) {
        $post_id     = $this->get_chapter_post_id($manga_id, $chapter_num);
        if (!$post_id) return;

        $manga_slug   = $this->get_manga_slug($manga_id);
        $upload_dir   = wp_upload_dir();
        $chapter_path = $upload_dir['basedir'] . '/manhwas/' . $manga_slug . '/capitulo_' . $chapter_num;

        $images = glob($chapter_path . '/*.{jpg,jpeg,png,gif,webp}', GLOB_BRACE);
        natsort($images);

        $images_urls   = array();
        $post_content  = '';

        foreach ($images as $image_path) {
            $url = str_replace(
                wp_normalize_path($upload_dir['basedir']),
                $upload_dir['baseurl'],
                wp_normalize_path($image_path)
            );
            $images_urls[] = $url;
            $post_content .= '<img src="' . esc_url($url) . '" alt="" class="alignnone size-full">' . "\n";
        }

        wp_update_post(array('ID' => $post_id, 'post_content' => $post_content));
        update_post_meta($post_id, 'ero_chapter_images',   $images_urls);
        update_post_meta($post_id, '_chapter_images_urls', $images_urls);

        $this->clear_chapters_cache($manga_id);
    }

    private function delete_directory($dir) {
        if (!file_exists($dir)) return true;
        $files = array_diff(scandir($dir), array('.', '..'));
        foreach ($files as $file) {
            $path = $dir . '/' . $file;
            is_dir($path) ? $this->delete_directory($path) : unlink($path);
        }
        return rmdir($dir);
    }

    // =========================================================================
    // HELPERS DE TEXTO (novelas)
    // =========================================================================

    private function clean_text_content($raw, $ext) {
        $text = str_replace(array("\r\n", "\r"), "\n", $raw);
        $text = ltrim($text, "\xEF\xBB\xBF");

        if ($ext === 'html' || $ext === 'htm') {
            if (preg_match('/<body[^>]*>(.*?)<\/body>/is', $text, $m)) $text = $m[1];
            return trim($text);
        }

        $paragraphs = preg_split('/\n{2,}/', trim($text));
        $html = '';
        foreach ($paragraphs as $p) {
            $p = trim($p);
            if ($p === '') continue;
            $html .= '<p>' . nl2br(esc_html($p)) . '</p>' . "\n";
        }
        return $html;
    }

    private function extract_text_from_docx($path) {
        if (!file_exists($path)) return new WP_Error('no_file', 'Archivo no encontrado.');
        $docx = new ZipArchive();
        if ($docx->open($path) !== true) return new WP_Error('docx_open', 'No se pudo abrir el DOCX.');
        $xml = $docx->getFromName('word/document.xml');
        $docx->close();
        if ($xml === false) return new WP_Error('docx_xml', 'Sin contenido en el DOCX.');

        $html = '';
        preg_match_all('/<w:p[ >].*?<\/w:p>/s', $xml, $paras);
        foreach ($paras[0] as $para) {
            preg_match_all('/<w:t[^>]*>(.*?)<\/w:t>/s', $para, $texts);
            $line = implode('', $texts[1]);
            $line = html_entity_decode($line, ENT_QUOTES | ENT_XML1, 'UTF-8');
            $line = trim($line);
            if ($line !== '') $html .= '<p>' . esc_html($line) . '</p>' . "\n";
        }
        return $html ?: new WP_Error('docx_empty', 'El DOCX no contiene texto legible.');
    }

    private function extract_text_from_rtf_odt($path, $ext) {
        if (!file_exists($path)) return new WP_Error('no_file', 'Archivo no encontrado.');

        if ($ext === 'odt') {
            $odt = new ZipArchive();
            if ($odt->open($path) !== true) return new WP_Error('odt_open', 'No se pudo abrir el ODT.');
            $xml = $odt->getFromName('content.xml');
            $odt->close();
            if ($xml === false) return new WP_Error('odt_xml', 'Sin contenido en ODT.');
            $text = html_entity_decode(preg_replace('/<[^>]+>/', ' ', $xml), ENT_QUOTES, 'UTF-8');
        } elseif ($ext === 'epub') {
            $epub = new ZipArchive();
            if ($epub->open($path) !== true) return new WP_Error('epub_open', 'No se pudo abrir el EPUB.');
            $text = '';
            for ($i = 0; $i < $epub->numFiles; $i++) {
                $name = $epub->getNameIndex($i);
                $e    = strtolower(pathinfo($name, PATHINFO_EXTENSION));
                if (in_array($e, array('html', 'htm', 'xhtml'))) {
                    $chunk = $epub->getFromIndex($i);
                    if (preg_match('/<body[^>]*>(.*?)<\/body>/is', $chunk, $m)) $chunk = $m[1];
                    $text .= preg_replace('/<[^>]+>/', ' ', $chunk) . "\n\n";
                }
            }
            $epub->close();
        } elseif ($ext === 'rtf') {
            $raw  = file_get_contents($path);
            $text = preg_replace('/\{[^{}]*\}/', '', $raw);
            $text = preg_replace('/\\\\[a-z]+\d* ?/', '', $text);
            $text = preg_replace('/[\\\\{}]/', '', $text);
        } else {
            return new WP_Error('unsupported', 'Formato no soportado: ' . $ext);
        }

        $text       = preg_replace('/[ \t]+/', ' ', $text);
        $paragraphs = preg_split('/\n{2,}/', trim($text));
        $html       = '';
        foreach ($paragraphs as $p) {
            $p = trim($p);
            if ($p !== '') $html .= '<p>' . esc_html($p) . '</p>' . "\n";
        }
        return $html ?: new WP_Error('empty_content', 'Sin texto legible en ' . strtoupper($ext) . '.');
    }
}

function mcm_v3_init() {
    return Manhwa_Chapter_Manager_V3::get_instance();
}
add_action('plugins_loaded', 'mcm_v3_init');

register_activation_hook(__FILE__, function() {
    $upload_dir  = wp_upload_dir();
    $manhwas_dir = $upload_dir['basedir'] . '/manhwas';
    if (!file_exists($manhwas_dir)) wp_mkdir_p($manhwas_dir);
});
