<?php
/**
 * Meta Box principal del plugin Subida ZIP Bloom v3.5.3
 */
$saved_categories = get_post_meta($post->ID, '_mcm_chapter_categories', true);
if (empty($saved_categories)) $saved_categories = array();
$all_categories = get_categories(array('hide_empty' => false));
$current_slug   = get_post_meta($post->ID, '_mcm_manga_slug', true);
$title_slug     = sanitize_title($post->post_title);
$slug_mismatch  = (!empty($current_slug) && $current_slug !== $title_slug);
?>
<div class="mcm-manager-v3">

    <?php if ($slug_mismatch): ?>
    <div class="mcm-notice mcm-notice-warning">
        <span class="dashicons dashicons-warning"></span>
        <div>
            <strong>¡El título del manga cambió!</strong>
            La carpeta aún se llama <code><?php echo esc_html($current_slug); ?></code>
            pero el título actual genera el slug <code><?php echo esc_html($title_slug); ?></code>.
            Los capítulos tendrán URLs rotas hasta que sincronices.
        </div>
        <button type="button" class="button button-primary" id="rename-manga-folder">
            <span class="dashicons dashicons-update"></span>
            Sincronizar carpeta
        </button>
    </div>
    <?php endif; ?>

    <!-- CATEGORÍAS -->
    <div class="mcm-collapsible-section">
        <h3 class="mcm-section-toggle" data-target="cat-section">
            <span class="dashicons dashicons-arrow-right-alt2"></span>
            <span class="dashicons dashicons-category"></span>
            Categorías de capítulos
            <?php if (!empty($saved_categories)): ?>
                <span class="mcm-badge mcm-badge-success"><?php echo count($saved_categories); ?> seleccionada(s)</span>
            <?php else: ?>
                <span class="mcm-badge mcm-badge-warning">Sin categoría</span>
            <?php endif; ?>
        </h3>
        <div class="mcm-section-content" id="cat-section" style="display:none;">
            <?php if (empty($all_categories)): ?>
                <div class="mcm-notice mcm-notice-info">
                    <span class="dashicons dashicons-info"></span>
                    <div>No hay categorías todavía. <strong>Publica el manga primero</strong>, luego vuelve aquí a seleccionar la categoría. Los capítulos que subas después se asignarán solos.</div>
                </div>
            <?php else: ?>
                <p class="description">Las categorías marcadas se asignan automáticamente a cada capítulo que subas.</p>
                <div class="mcm-category-list">
                    <?php foreach ($all_categories as $cat): ?>
                        <label>
                            <input type="checkbox" name="mcm_categories[]" value="<?php echo $cat->term_id; ?>" <?php checked(in_array($cat->term_id, $saved_categories)); ?>>
                            <?php echo esc_html($cat->name); ?>
                            <small>(<?php echo $cat->count; ?>)</small>
                        </label>
                    <?php endforeach; ?>
                </div>
                <button type="button" class="button" id="save-categories">
                    <span class="dashicons dashicons-saved"></span> Confirmar selección
                </button>
                <p class="description mcm-auto-save-hint">✅ También se guarda al marcar/desmarcar.</p>
            <?php endif; ?>
            <div class="mcm-message-cat mcm-message"></div>
        </div>
    </div>

    <!-- SUBIDA UNIFICADA -->
    <div class="mcm-collapsible-section">
        <h3 class="mcm-section-toggle" data-target="upload-section">
            <span class="dashicons dashicons-arrow-right-alt2"></span>
            <span class="dashicons dashicons-upload"></span>
            Subir capítulos
        </h3>
        <div class="mcm-section-content" id="upload-section" style="display:none;">
            <p class="description">
                Selecciona uno o varios archivos. Cada nombre debe incluir el número de capítulo
                (<em>cap05.zip</em>, <em>capitulo_12.zip</em>, <em>chapter3.zip</em>…).<br>
                📦 <strong>Manga:</strong> ZIP con imágenes &nbsp;|&nbsp;
                📖 <strong>Novela:</strong> ZIP con texto o archivo directo .txt .docx .html .md<br>
                <strong>Límite:</strong> 500 MB por lote.
            </p>

            <div class="mcm-upload-area" id="drop-zone">
                <span class="dashicons dashicons-cloud-upload mcm-upload-icon"></span>
                <p>Arrastra archivos aquí o haz clic para seleccionar</p>
                <p class="mcm-upload-hint">Un archivo o varios a la vez</p>
                <input type="file" id="upload-files" accept=".zip,.txt,.docx,.doc,.md,.html,.htm" multiple>
            </div>

            <div class="mcm-selected-files-list" id="files-preview" style="display:none;"></div>

            <div class="mcm-upload-controls">
                <button type="button" class="button button-primary mcm-btn-upload" id="upload-btn">
                    <span class="dashicons dashicons-upload"></span>
                    Subir
                </button>
                <button type="button" class="button mcm-btn-clear" id="clear-files" style="display:none;">
                    <span class="dashicons dashicons-no-alt"></span>
                    Limpiar
                </button>
            </div>

            <div class="mcm-progress-container" style="display:none;">
                <div class="mcm-progress-bar"><div class="mcm-progress-fill"></div></div>
                <div class="mcm-progress-info">
                    <span class="mcm-progress-text">Preparando...</span>
                    <span class="mcm-progress-percentage">0%</span>
                </div>
                <div class="mcm-progress-details"></div>
            </div>

            <div class="mcm-message mcm-message-upload"></div>
        </div>
    </div>

    <!-- GESTIÓN DE CAPÍTULOS -->
    <div class="mcm-collapsible-section">
        <h3 class="mcm-section-toggle" data-target="chapter-management">
            <span class="dashicons dashicons-arrow-right-alt2"></span>
            <span class="dashicons dashicons-list-view"></span>
            Gestión de Capítulos
            <span class="mcm-badge mcm-badge-info mcm-chapter-count"><?php echo count($chapters); ?></span>
        </h3>
        <div class="mcm-section-content" id="chapter-management" style="display:none;">
            <div class="mcm-section-header">
                <div class="mcm-actions">
                    <button type="button" class="button" id="refresh-chapters">
                        <span class="dashicons dashicons-update"></span> Actualizar lista
                    </button>
                    <button type="button" class="button button-primary" id="sync-all">
                        <span class="dashicons dashicons-update-alt"></span> Sincronizar Todo
                    </button>
                </div>
            </div>
            <p class="description">
                <strong>Sincronizar Todo:</strong> Actualiza posts existentes, crea los que falten y corrige fechas.
            </p>
            <div id="chapters-list" class="mcm-chapters-list">
                <?php if (empty($chapters)): ?>
                    <div class="mcm-empty">
                        <span class="dashicons dashicons-book-alt"></span>
                        <p>No hay capítulos. Sube tu primer capítulo arriba.</p>
                    </div>
                <?php else: ?>
                    <?php foreach ($chapters as $chapter): ?>
                        <?php include MCM_PLUGIN_DIR . 'templates/chapter-item.php'; ?>
                    <?php endforeach; ?>
                <?php endif; ?>
            </div>
            <div class="mcm-message mcm-message-chapters"></div>
        </div>
    </div>

</div>

<!-- Modal imagen completa -->
<div class="mcm-image-modal" style="display:none;">
    <div class="mcm-modal-overlay"></div>
    <div class="mcm-modal-content">
        <button type="button" class="mcm-modal-close"><span class="dashicons dashicons-no-alt"></span></button>
        <img src="" alt="Vista completa" class="mcm-full-image">
    </div>
</div>
