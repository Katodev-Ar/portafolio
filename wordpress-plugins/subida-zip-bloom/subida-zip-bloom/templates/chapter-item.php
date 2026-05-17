<div class="mcm-chapter-item" data-chapter="<?php echo esc_attr($chapter['number']); ?>">
    <div class="mcm-chapter-header">
        <div class="mcm-drag-handle" title="Arrastra para reordenar">
            <span class="dashicons dashicons-menu"></span>
        </div>
        <div class="mcm-chapter-info">
            <h4>
                Capítulo <?php echo esc_html($chapter['number']); ?>
                <?php if ($chapter['post_exists']): ?>
                    <span class="mcm-badge mcm-badge-success">✓ Post creado</span>
                <?php else: ?>
                    <span class="mcm-badge mcm-badge-warning">⚠ Sin post</span>
                <?php endif; ?>
                <?php if ($chapter['source'] == 'manual'): ?>
                    <span class="mcm-badge mcm-badge-info">📝 Manual</span>
                <?php endif; ?>
            </h4>
            <span class="mcm-meta">
                <?php if ($chapter['source'] == 'folder'): ?>
                    <?php echo $chapter['image_count']; ?> imágenes
                <?php else: ?>
                    Creado manualmente (sin carpeta)
                <?php endif; ?>
                <?php if ($chapter['post_exists']): ?>
                    | <a href="<?php echo get_edit_post_link($chapter['post_id']); ?>" target="_blank">Editar post</a>
                    | <a href="<?php echo get_permalink($chapter['post_id']); ?>" target="_blank">Ver en sitio</a>
                <?php endif; ?>
            </span>
        </div>
        <div class="mcm-chapter-actions">
            <?php if ($chapter['source'] == 'folder' && !empty($chapter['images'])): ?>
                <button type="button" class="button mcm-toggle-images" title="Ver imágenes">
                    <span class="dashicons dashicons-visibility"></span>
                </button>
                <button type="button" class="button mcm-add-images" 
                        data-chapter="<?php echo esc_attr($chapter['number']); ?>"
                        title="Agregar imágenes">
                    <span class="dashicons dashicons-plus-alt"></span>
                </button>
            <?php endif; ?>
            <button type="button" class="button button-link-delete mcm-delete-chapter" 
                    data-chapter="<?php echo esc_attr($chapter['number']); ?>"
                    title="Eliminar capítulo">
                <span class="dashicons dashicons-trash"></span>
            </button>
        </div>
    </div>
    
    <?php if ($chapter['source'] == 'folder' && !empty($chapter['images'])): ?>
    <div class="mcm-chapter-images" style="display: none;">
        <div class="mcm-images-grid sortable-images">
            <?php 
            $images = $chapter['images'];
            natsort($images);
            foreach ($images as $index => $image_path): 
                $image_url = str_replace(
                    wp_normalize_path(wp_upload_dir()['basedir']),
                    wp_upload_dir()['baseurl'],
                    wp_normalize_path($image_path)
                );
            ?>
                <div class="mcm-image-item" data-filename="<?php echo basename($image_path); ?>">
                    <div class="mcm-image-drag">
                        <span class="dashicons dashicons-move"></span>
                    </div>
                    <img src="<?php echo esc_url($image_url); ?>" 
                         alt="Página <?php echo $index + 1; ?>"
                         class="mcm-image-thumbnail"
                         loading="lazy">
                    <span class="mcm-image-number"><?php echo str_pad($index, 2, '0', STR_PAD_LEFT); ?></span>
                    <button type="button" class="mcm-view-full-image" 
                            data-url="<?php echo esc_url($image_url); ?>"
                            title="Ver imagen completa">
                        <span class="dashicons dashicons-search"></span>
                    </button>
                    <button type="button" class="mcm-delete-image" 
                            data-chapter="<?php echo esc_attr($chapter['number']); ?>"
                            data-filename="<?php echo basename($image_path); ?>"
                            title="Eliminar imagen">
                        <span class="dashicons dashicons-no-alt"></span>
                    </button>
                </div>
            <?php endforeach; ?>
        </div>
    </div>
    <?php endif; ?>
</div>
