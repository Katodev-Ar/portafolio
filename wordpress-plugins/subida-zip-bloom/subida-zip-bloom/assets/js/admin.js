jQuery(document).ready(function ($) {

    const ALLOWED_EXTS = ['zip', 'txt', 'md', 'html', 'htm', 'docx', 'doc', 'odt', 'rtf', 'epub'];

    function getExt(f)       { return f.split('.').pop().toLowerCase(); }
    function isAllowed(f)    { return ALLOWED_EXTS.includes(getExt(f)); }
    function fmtSize(bytes)  { return (bytes / 1048576).toFixed(1) + ' MB'; }
    function chapterLabel(ch) {
        return ch.images === 0 ? `✅ Cap. ${ch.number}: novela` : `✅ Cap. ${ch.number}: ${ch.images} imgs`;
    }
    function extractChapterNum(filename) {
        const base = filename.replace(/\.[^.]+$/, '');
        let m = base.match(/(?:cap|capitulo|chapter)[^\d]*(\d+(?:\.\d+)?)/i);
        if (m) return parseFloat(m[1]);
        m = base.match(/(\d+(?:\.\d+)?)/);
        return m ? parseFloat(m[1]) : 0;
    }

    // ── Toggle colapsables ────────────────────────────────────────────────────
    $(document).on('click', '.mcm-section-toggle', function () {
        $('#' + $(this).data('target')).slideToggle(220);
        $(this).find('.dashicons-arrow-right-alt2').toggleClass('mcm-rotated');
    });

    // ── Drag & drop ───────────────────────────────────────────────────────────
    $('#drop-zone').on('dragover dragenter', function (e) {
        e.preventDefault(); $(this).addClass('dragover');
    }).on('dragleave drop', function (e) {
        e.preventDefault(); $(this).removeClass('dragover');
    });

    // ── Selección de archivos ─────────────────────────────────────────────────
    let selectedFiles = [];

    $('#upload-files').on('change', function () { handleFiles(this.files); });

    function handleFiles(fileList) {
        if (!fileList || !fileList.length) return;
        const raw = Array.from(fileList);
        const bad = raw.filter(f => !isAllowed(f.name));
        if (bad.length) {
            showMsg('.mcm-message-upload', '❌ Formatos no soportados: ' + bad.map(f => f.name).join(', '), 'error');
            return;
        }
        const totalSize = raw.reduce((a, f) => a + f.size, 0);
        if (totalSize > 500 * 1024 * 1024) {
            showMsg('.mcm-message-upload', `❌ Supera 500 MB (${fmtSize(totalSize)})`, 'error');
            return;
        }
        // Ordenar de menor a mayor capítulo antes de mostrar/subir
        selectedFiles = raw.sort((a, b) => extractChapterNum(a.name) - extractChapterNum(b.name));
        renderPreview();
    }

    function renderPreview() {
        if (!selectedFiles.length) { $('#files-preview, #clear-files').hide(); return; }
        const n = selectedFiles.length;
        let html = `<strong>📦 ${n} archivo${n > 1 ? 's' : ''} en cola:</strong><br>`;
        selectedFiles.forEach((f, i) => {
            const num = extractChapterNum(f.name);
            html += `<span class="mcm-file-chip">${i + 1}. ${num > 0 ? 'Cap. ' + num + ' — ' : ''}${f.name} <small>${fmtSize(f.size)}</small></span>`;
        });
        $('#files-preview').html(html).show();
        $('#clear-files').show();
    }

    $('#clear-files').on('click', function () {
        selectedFiles = [];
        $('#upload-files').val('');
        $('#files-preview').hide();
        $(this).hide();
    });

    // ── SUBIDA UNIFICADA ──────────────────────────────────────────────────────
    $('#upload-btn').on('click', function () {
        if (!selectedFiles.length) {
            showMsg('.mcm-message-upload', '❌ Selecciona al menos un archivo', 'error');
            return;
        }

        const $btn = $(this), orig = $btn.html();
        const total = selectedFiles.length;
        let cur = 0;
        const done = [], errs = [];

        $btn.prop('disabled', true).html('<span class="dashicons dashicons-update mcm-spin"></span> Subiendo…');
        $('#clear-files').prop('disabled', true);
        $('.mcm-progress-container').show();
        $('.mcm-progress-fill').css('width', '0%');
        $('.mcm-progress-percentage').text('0%');
        $('.mcm-progress-text').text('Preparando…');
        $('.mcm-progress-details').html('');

        function finish() {
            $('.mcm-progress-fill').css('width', '100%');
            $('.mcm-progress-percentage').text('100%');
            $('.mcm-progress-text').text(errs.length ? `Listo (${errs.length} error(es))` : '¡Completado!');
            $('.mcm-progress-details').html(
                `<strong>${done.length}/${total} procesados</strong><br>${done.map(chapterLabel).join('<br>')}` +
                (errs.length ? '<br><br><strong>⚠️ Errores:</strong><br>' + errs.join('<br>') : '')
            );
            showMsg('.mcm-message-upload', done.length ? `✅ ${done.length} capítulo(s) subido(s).` : '❌ No se subió ninguno.', done.length ? 'success' : 'error');
            $btn.prop('disabled', false).html(orig);
            $('#clear-files').prop('disabled', false);
            selectedFiles = []; $('#upload-files').val(''); $('#files-preview, #clear-files').hide();
            setTimeout(refreshChapters, 800);
        }

        function uploadNext() {
            if (cur >= total) { finish(); return; }
            const f = selectedFiles[cur];
            const pct = Math.round((cur / total) * 100);
            $('.mcm-progress-fill').css('width', pct + '%');
            $('.mcm-progress-percentage').text(pct + '%');
            $('.mcm-progress-text').text(`(${cur + 1}/${total}) ${f.name}`);

            const fd = new FormData();
            fd.append('action',         'mcm_upload_chapters');
            fd.append('nonce',          mcmData.nonce);
            fd.append('post_id',        mcmData.post_id);
            fd.append('file_index',     cur);
            fd.append('zip_file_' + cur, f);

            $.ajax({
                url: mcmData.ajax_url, type: 'POST', data: fd,
                processData: false, contentType: false, timeout: 180000,
                success: function (r) {
                    if (r.success) {
                        done.push({ number: r.data.chapter_number, images: r.data.images });
                        $('.mcm-progress-details').html(done.map(chapterLabel).join('<br>'));
                    } else {
                        errs.push(`❌ ${f.name}: ${r.data.message}`);
                    }
                    cur++; uploadNext();
                },
                error: function (_, status) {
                    errs.push(`❌ ${f.name}: ${status === 'timeout' ? 'Timeout — ZIP muy grande' : 'Error de conexión'}`);
                    cur++; uploadNext();
                }
            });
        }

        uploadNext();
    });

    // ── Categorías ────────────────────────────────────────────────────────────
    function autoSaveCategories() {
        $.post(mcmData.ajax_url, {
            action: 'mcm_save_category_config', nonce: mcmData.nonce, post_id: mcmData.post_id,
            categories: $('input[name="mcm_categories[]"]:checked').map(function () { return $(this).val(); }).get()
        });
    }
    $(document).on('change', 'input[name="mcm_categories[]"]', autoSaveCategories);

    $('#save-categories').on('click', function () {
        const $btn = $(this), orig = $btn.html();
        $btn.prop('disabled', true).html('<span class="dashicons dashicons-update"></span> Guardando…');
        const cats = $('input[name="mcm_categories[]"]:checked').map(function () { return $(this).val(); }).get();
        $.post(mcmData.ajax_url, { action: 'mcm_save_category_config', nonce: mcmData.nonce, post_id: mcmData.post_id, categories: cats },
            function (r) {
                showMsg('.mcm-message-cat', r.success ? '✅ Categorías guardadas.' : '❌ ' + r.data.message, r.success ? 'success' : 'error');
                $btn.prop('disabled', false).html(orig);
            }
        ).fail(function () { showMsg('.mcm-message-cat', '❌ Error', 'error'); $btn.prop('disabled', false).html(orig); });
    });

    // ── Renombrar carpeta ─────────────────────────────────────────────────────
    $('#rename-manga-folder').on('click', function () {
        const $btn = $(this), orig = $btn.html();
        $btn.prop('disabled', true).html('<span class="dashicons dashicons-update"></span> Sincronizando…');
        $.post(mcmData.ajax_url, { action: 'mcm_rename_manga_folder', nonce: mcmData.nonce, post_id: mcmData.post_id },
            function (r) {
                if (r.success) { $btn.closest('.mcm-notice').fadeOut(300, function () { $(this).remove(); }); showMsg('.mcm-message-chapters', '✅ ' + r.data.message, 'success'); }
                else { $btn.prop('disabled', false).html(orig); alert('❌ ' + r.data.message); }
            }
        ).fail(function () { $btn.prop('disabled', false).html(orig); });
    });

    // ── Actualizar lista ──────────────────────────────────────────────────────
    $('#refresh-chapters').on('click', refreshChapters);
    function refreshChapters() {
        const $btn = $('#refresh-chapters'), orig = $btn.html();
        $btn.prop('disabled', true).html('<span class="dashicons dashicons-update"></span>');
        $.post(mcmData.ajax_url, { action: 'mcm_get_chapters', nonce: mcmData.nonce, post_id: mcmData.post_id, force_refresh: true },
            function (r) {
                if (r.success) { $('#chapters-list').html(r.data.html); $('.mcm-chapter-count').text(r.data.count); initChapterActions(); }
                $btn.prop('disabled', false).html(orig);
            }
        ).fail(function () { $btn.prop('disabled', false).html(orig); });
    }

    // ── Sincronizar todo ──────────────────────────────────────────────────────
    $('#sync-all').on('click', function () {
        if (!confirm('Actualiza todos los posts y corrige fechas.\n¿Continuar?')) return;
        const $btn = $(this), orig = $btn.html();
        $btn.prop('disabled', true).html('<span class="dashicons dashicons-update-alt"></span> Sincronizando…');
        $.post(mcmData.ajax_url, { action: 'mcm_sync_all', nonce: mcmData.nonce, post_id: mcmData.post_id },
            function (r) {
                showMsg('.mcm-message-chapters', r.success ? '✅ ' + r.data.message : '❌ ' + r.data.message, r.success ? 'success' : 'error');
                if (r.success) refreshChapters();
                $btn.prop('disabled', false).html(orig);
            }
        ).fail(function () { showMsg('.mcm-message-chapters', '❌ Error de conexión', 'error'); $btn.prop('disabled', false).html(orig); });
    });

    // ── Eliminar capítulo ─────────────────────────────────────────────────────
    $(document).on('click', '.mcm-delete-chapter', function () {
        const ch = $(this).data('chapter');
        if (!confirm(`¿Eliminar capítulo ${ch}?\nSe borrará carpeta, imágenes y post.`)) return;
        $.post(mcmData.ajax_url, { action: 'mcm_delete_chapter', nonce: mcmData.nonce, post_id: mcmData.post_id, chapter_number: ch },
            function (r) {
                showMsg('.mcm-message-chapters', r.success ? '✅ ' + r.data.message : '❌ ' + r.data.message, r.success ? 'success' : 'error');
                if (r.success) refreshChapters();
            }
        );
    });

    // ── Imágenes ──────────────────────────────────────────────────────────────
    $(document).on('click', '.mcm-toggle-images', function () {
        $(this).closest('.mcm-chapter-item').find('.mcm-chapter-images').slideToggle(180);
    });
    $(document).on('click', '.mcm-add-images', function () {
        const ch = $(this).data('chapter');
        $('<input type="file" multiple accept="image/*" style="display:none">').appendTo('body').on('change', function () {
            if (!this.files.length) { $(this).remove(); return; }
            const fd = new FormData();
            fd.append('action', 'mcm_add_images'); fd.append('nonce', mcmData.nonce);
            fd.append('post_id', mcmData.post_id); fd.append('chapter_number', ch);
            Array.from(this.files).forEach((f, i) => fd.append('image_' + i, f));
            $.ajax({ url: mcmData.ajax_url, type: 'POST', data: fd, processData: false, contentType: false,
                success: function (r) { showMsg('.mcm-message-chapters', r.success ? '✅ ' + r.data.message : '❌ ' + r.data.message, r.success ? 'success' : 'error'); if (r.success) refreshChapters(); }
            });
            $(this).remove();
        }).trigger('click');
    });
    $(document).on('click', '.mcm-delete-image', function () {
        if (!confirm('¿Eliminar imagen?')) return;
        $.post(mcmData.ajax_url, { action: 'mcm_delete_image', nonce: mcmData.nonce, post_id: mcmData.post_id, chapter_number: $(this).data('chapter'), filename: $(this).data('filename') },
            function (r) { showMsg('.mcm-message-chapters', r.success ? '✅ Eliminada' : '❌ ' + r.data.message, r.success ? 'success' : 'error'); if (r.success) refreshChapters(); }
        );
    });

    // ── Sortables ─────────────────────────────────────────────────────────────
    function initSortable() {
        $('.sortable-images').sortable({
            items: '.mcm-image-item', handle: '.mcm-image-drag', cursor: 'move', placeholder: 'ui-sortable-placeholder',
            update: function () {
                const ch = $(this).closest('.mcm-chapter-item').data('chapter');
                const order = $(this).find('.mcm-image-item').map(function () { return $(this).data('filename'); }).get();
                $.post(mcmData.ajax_url, { action: 'mcm_reorder_images', nonce: mcmData.nonce, post_id: mcmData.post_id, chapter_number: ch, image_order: order },
                    function (r) { showMsg('.mcm-message-chapters', r.success ? '✅ Orden actualizado' : '❌ ' + r.data.message, r.success ? 'success' : 'error'); if (r.success) refreshChapters(); }
                );
            }
        });
    }
    function initChapterSortable() {
        $('.mcm-chapters-list').sortable({
            items: '.mcm-chapter-item', handle: '.mcm-drag-handle', cursor: 'move', placeholder: 'ui-sortable-placeholder', axis: 'y',
            update: function () {
                const order = $('.mcm-chapter-item').map(function () { return $(this).data('chapter'); }).get();
                $.post(mcmData.ajax_url, { action: 'mcm_reorder_chapters', nonce: mcmData.nonce, post_id: mcmData.post_id, chapter_order: order },
                    function (r) { showMsg('.mcm-message-chapters', r.success ? '✅ ' + r.data.message : '❌ ' + r.data.message, r.success ? 'success' : 'error'); if (r.success) setTimeout(refreshChapters, 600); }
                );
            }
        });
    }

    // ── Modal ─────────────────────────────────────────────────────────────────
    $(document).on('click', '.mcm-view-full-image, .mcm-image-thumbnail', function () {
        $('.mcm-full-image').attr('src', $(this).data('url') || $(this).attr('src'));
        $('.mcm-image-modal').fadeIn(150);
    });
    $(document).on('click', '.mcm-modal-close, .mcm-modal-overlay', function () { $('.mcm-image-modal').fadeOut(150); });
    $(document).on('keyup', function (e) { if (e.key === 'Escape') $('.mcm-image-modal').fadeOut(150); });

    function initChapterActions() { initSortable(); initChapterSortable(); }

    function showMsg(sel, msg, type) {
        $(sel).removeClass('success error').addClass(type + ' show').html(msg);
        setTimeout(() => $(sel).removeClass('show'), 5500);
    }

    initChapterActions();
});
