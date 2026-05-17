/* Bloom Cookie Manager – Admin JS */
(function($){
    'use strict';

    const { ajaxUrl, nonce, nonces, settings } = window.bcmData || {};

    // Helper: resolve per-action nonce, fall back to legacy shared nonce.
    // This ensures forward-compatibility if bcmData.nonces is ever absent.
    function n( action ) {
        return ( nonces && nonces[ action ] ) ? nonces[ action ] : nonce;
    }

    /* ────────────────────────────────
       DASHBOARD – scan
    ──────────────────────────────── */
    let currentScanId = null;
    let scanTimer = null;

    $(document).on('click', '#bcm-start-scan', function(){
        const $btn = $(this).prop('disabled', true).text('Scanning…');
        $('#bcm-scan-status').show().text('Starting scan…');

        $.post(ajaxUrl, { action:'bcm_start_scan', nonce: n('start_scan') }, function(res){
            }
        });
    });

    /* Cookie Manager scan button */
    $(document).on('click', '#bcm-run-scan', function(){
        const $bar = $('#bcm-scan-bar').show();
        $.post(ajaxUrl, { action:'bcm_start_scan', nonce: n('start_scan') }, function(res){
            }
        });
    });

    /* v1.4.2 — Importar biblioteca de cookies conocidas */
    $(document).on('click', '#bcm-seed-cookies', function(){
        const isES = (settings && settings.admin_lang === 'es') || document.documentElement.lang === 'es';
        const $btn = $(this).prop('disabled', true).text('⏳ ' + (isES ? 'Importando...' : 'Importing...'));
        $.post(ajaxUrl, { action:'bcm_seed_cookies', nonce: n('seed_cookies') }, function(res){
            if(res.success){
                const n = res.data.added;
                alert( n > 0
                    ? (isES
                        ? '✅ Se importaron ' + n + ' cookies conocidas (Google Analytics, Google Ads, Infolinks, WordPress, etc.).'
                        : '✅ Imported ' + n + ' known cookies (Google Analytics, Google Ads, Infolinks, WordPress, etc.).')
                    : (isES
                        ? 'ℹ️ Todas las cookies de la biblioteca ya estaban registradas.'
                        : 'ℹ️ All library cookies were already registered.') );
                loadCookies( currentCategory );
            }
        }).always(function(){
            const isES2 = (settings && settings.admin_lang === 'es');
            $btn.prop('disabled', false).text('📚 ' + (isES2 ? 'Importar biblioteca' : 'Import Library'));
        });
    });

    function pollScan($btn, statusSel){
        scanTimer = setInterval(function(){
            $.post(ajaxUrl, { action:'bcm_get_scan_status', nonce: n('get_scan_status'), scan_id: currentScanId }, function(res){
                if(res.success && res.data){
                    const s = res.data;
                    $(statusSel).text('Status: ' + s.status + ' | URLs: ' + s.urls_scanned + ' | Cookies: ' + s.cookies_found);
                    if(s.status === 'completed'){
                        clearInterval(scanTimer);
                        $btn.prop('disabled', false).text('🔍 Start Scan Now');
                        $(statusSel).text('✅ Scan complete! Found ' + s.cookies_found + ' cookies.');
                    }
                }
            });
        }, 2000);
    }

    function pollScanCookies($bar){
        scanTimer = setInterval(function(){
            $.post(ajaxUrl, { action:'bcm_get_scan_status', nonce: n('get_scan_status'), scan_id: currentScanId }, function(res){
                if(res.success && res.data && res.data.status === 'completed'){
                    clearInterval(scanTimer);
                    $bar.hide();
                    loadCookies( $('.bcm-cat-item.active').data('cat') );
                }
            });
        }, 2000);
    }

    /* ────────────────────────────────
       COOKIE MANAGER
    ──────────────────────────────── */
    function loadCookies(category){
        const cat = category === 'all' ? '' : category;
        $('#bcm-cookie-tbody').html('<tr><td colspan="5" class="bcm-loading">Loading…</td></tr>');

        $.post(ajaxUrl, { action:'bcm_get_cookies', nonce: n('get_cookies'), category: cat }, function(res){
            if(!res.success) return;
            const cookies = res.data;
            let html = '';

            /* update counts */
            $('#count-all').text(cookies.length);
            const catCounts = {};
            cookies.forEach(c => { catCounts[c.category] = (catCounts[c.category]||0)+1; });
            Object.entries(catCounts).forEach(([k,v]) => $('#count-'+k).text(v));

            if(!cookies.length){
                html = '<tr><td colspan="5" class="bcm-empty">No cookies found. Run a scan or add manually.</td></tr>';
            } else {
                cookies.forEach(c => {
                    html += `<tr>
                        <td><strong>${esc(c.name)}</strong></td>
                        <td>${esc(c.provider||'–')}</td>
                        <td><span class="bcm-badge bcm-badge-cat-${esc(c.category)}">${esc(c.category)}</span></td>
                        <td>${esc(c.expiry||'–')}</td>
                        <td>
                            <button class="bcm-btn bcm-btn-outline bcm-edit-cookie" data-id="${c.id}" style="padding:4px 10px;font-size:.78rem;" 
                                data-name="${esc(c.name)}" data-category="${esc(c.category)}" data-provider="${esc(c.provider)}"
                                data-purpose="${esc(c.purpose)}" data-expiry="${esc(c.expiry)}" data-domain="${esc(c.domain)}" data-type="${esc(c.cookie_type)}">Edit</button>
                            <button class="bcm-btn bcm-btn-danger bcm-delete-cookie" data-id="${c.id}" style="padding:4px 10px;font-size:.78rem;margin-left:4px">Delete</button>
                        </td>
                    </tr>`;
                });
            }
            $('#bcm-cookie-tbody').html(html);
        });
    }

    // Category tabs
    $(document).on('click', '.bcm-cat-item', function(){
        $('.bcm-cat-item').removeClass('active');
        $(this).addClass('active');
        loadCookies( $(this).data('cat') );
    });

    // Add cookie modal
    $(document).on('click', '#bcm-add-cookie', function(){
        resetModal();
        $('#bcm-modal-title').text('Add Cookie');
        $('#bcm-cookie-modal').show();
    });

    // Edit cookie
    $(document).on('click', '.bcm-edit-cookie', function(){
        const d = $(this).data();
        $('#cookie-id').val(d.id);
        $('#cookie-name').val(d.name);
        $('#cookie-category').val(d.category);
        $('#cookie-provider').val(d.provider);
        $('#cookie-purpose').val(d.purpose);
        $('#cookie-expiry').val(d.expiry);
        $('#cookie-domain').val(d.domain);
        $('#cookie-type').val(d.type);
        $('#bcm-modal-title').text('Edit Cookie');
        $('#bcm-cookie-modal').show();
    });

    // Delete cookie
    $(document).on('click', '.bcm-delete-cookie', function(){
        if(!confirm('Delete this cookie?')) return;
        const id = $(this).data('id');
        $.post(ajaxUrl, { action:'bcm_delete_cookie', nonce: n('delete_cookie'), id }, function(){
            loadCookies( $('.bcm-cat-item.active').data('cat') );
        });
    });

    // Save cookie
    $(document).on('click', '#bcm-save-cookie', function(){
        const payload = {
            action: 'bcm_save_cookie',
            nonce:  n('save_cookie'),
            id:          $('#cookie-id').val(),
            name:        $('#cookie-name').val(),
            category:    $('#cookie-category').val(),
            provider:    $('#cookie-provider').val(),
            purpose:     $('#cookie-purpose').val(),
            expiry:      $('#cookie-expiry').val(),
            domain:      $('#cookie-domain').val(),
            cookie_type: $('#cookie-type').val(),
        };
        $.post(ajaxUrl, payload, function(res){
            if(res.success){
                $('#bcm-cookie-modal').hide();
                loadCookies( $('.bcm-cat-item.active').data('cat') );
            }
        });
    });

    // Close modal
    $(document).on('click', '.bcm-modal-close', function(){ $('#bcm-cookie-modal').hide(); });
    $(document).on('click', '#bcm-cookie-modal', function(e){ if(e.target===this) $(this).hide(); });

    function resetModal(){
        $('#cookie-id,#cookie-name,#cookie-provider,#cookie-purpose,#cookie-expiry,#cookie-domain').val('');
        $('#cookie-category').val('necessary');
        $('#cookie-type').val('HTTP');
    }

    // Auto-load on cookies page
    if( $('#bcm-cookie-tbody').length ) loadCookies('all');

    /* ────────────────────────────────
       BANNER PAGE – live preview
    ──────────────────────────────── */
    function updatePreview(){
        const title   = $('#banner_title').val()   || '';
        const desc    = $('#banner_description').val() || '';
        const accept  = $('#accept_btn_text').val() || 'Aceptar';
        const reject  = $('#reject_btn_text').val() || 'Rechazar';
        const cust    = $('#customize_btn_text').val() || 'Personalizar';
        const bg      = $('#bg_color').val()        || '#1a1a2e';
        const fg      = $('#text_color').val()      || '#ffffff';
        const acceptBg= $('#btn_accept_bg').val()   || '#0066FF';
        const rejectBg= $('#btn_reject_bg').val()   || '#ffffff';
        const rejectFg= $('#btn_reject_text').val() || '#333';

        const $b = $('#bcm-preview-banner');
        $b.css({ background: bg, color: fg });
        $('#preview-title').text(title);
        $('#preview-desc').text(desc);
        $('#preview-accept').text(accept).css({ background: acceptBg, color: '#fff', border: 'none' });
        $('#preview-reject').text(reject).css({ background: rejectBg, color: rejectFg, border: '1px solid #ccc' });
        $('#preview-customize').text(cust).css({ background: 'transparent', color: fg, border: '1px solid '+fg });

        // v1.8.5 — TOS checkbox in preview
        const tosOn = $('#show_tos_checkbox').is(':checked');
        $('#preview-tos-row').toggle(tosOn);

        // v1.8.5 — Enforcement badge in preview
        const enfOn = $('#tc_enforcement_enabled').is(':checked');
        $('#bcm-preview-enforcement').toggle(enfOn);
    }

    $(document).on('input change',
        '#banner_title,#banner_description,#accept_btn_text,#reject_btn_text,' +
        '#customize_btn_text,#bg_color,#text_color,#btn_accept_bg,#btn_reject_bg,' +
        '#btn_reject_text,#show_tos_checkbox,#tc_enforcement_enabled',
        updatePreview
    );

    // v1.9.0 — initialize wp-color-picker and trigger live preview on load
    $(function(){
        if( $('#bcm-preview-banner').length ) {
            // Initialize WordPress color pickers so .val() returns the selected color
            $('input.bcm-color-picker').wpColorPicker({
                change: function(){ setTimeout(updatePreview, 50); },
                clear:  function(){ setTimeout(updatePreview, 50); }
            });
            updatePreview();
        }
    });

    /* Save banner */
    $(document).on('click', '#bcm-save-banner', function(){
        saveBannerSettings();
    });

    function collectBannerSettings(){
        return {
            // Banner base
            banner_enabled:      $('#banner_enabled').is(':checked'),
            banner_position:     $('#banner_position').val(),
            banner_title:        $('#banner_title').val(),
            banner_description:  $('#banner_description').val(),
            accept_btn_text:     $('#accept_btn_text').val(),
            reject_btn_text:     $('#reject_btn_text').val(),
            customize_btn_text:  $('#customize_btn_text').val(),
            bg_color:            $('#bg_color').val(),
            text_color:          $('#text_color').val(),
            btn_accept_bg:       $('#btn_accept_bg').val(),
            btn_reject_bg:       $('#btn_reject_bg').val(),
            btn_reject_text:     $('#btn_reject_text').val(),
            // v1.8.5 — TOS & enforcement
            show_tos_checkbox:      $('#show_tos_checkbox').is(':checked'),
            tos_url:                $('#tos_url').val(),
            privacy_policy_url:     $('#privacy_policy_url').val(),
            tc_enforcement_enabled: $('#tc_enforcement_enabled').is(':checked'),
            tc_acceptance_page_id:  parseInt( $('#tc_acceptance_page_id').val() ) || 0,
            tc_purge_rejected:      $('#tc_purge_rejected').is(':checked'),
        };
    }

    function saveBannerSettings(){
        const $btn     = $('#bcm-save-banner');
        const origText = $btn.text();
        $btn.prop('disabled', true).text('Guardando…');
        const data = collectBannerSettings();
        $.post(ajaxUrl, { action:'bcm_save_settings', nonce: n('save_settings'), settings: JSON.stringify(data) }, function(res){
            $btn.prop('disabled', false);
            if(res.success){
                $btn.text('✅ Guardado').css('background','#2e7d32');
                setTimeout(function(){ $btn.text(origText).css('background',''); }, 2200);
            } else {
                $btn.text(origText);
                alert('❌ Error al guardar. Intenta de nuevo.');
            }
        }).fail(function(){
            $btn.prop('disabled', false).text(origText);
            alert('❌ Error de conexión.');
        });
    }

    /* ────────────────────────────────
       SETTINGS PAGE
    ──────────────────────────────── */
    $(document).on('click', '#bcm-save-settings', function(){
        const cats = {};
        $('.cat-label').each(function(){
            const cat = $(this).data('cat');
            if(!cats[cat]) cats[cat]={ label:'', enabled:false, locked:false };
            cats[cat].label = $(this).val();
        });
        $('.cat-enabled').each(function(){
            const cat = $(this).data('cat');
            if(!cats[cat]) cats[cat]={ label:'', enabled:false, locked:false };
            cats[cat].enabled = $(this).is(':checked');
        });
        $('.cat-locked').each(function(){
            const cat = $(this).data('cat');
            if(!cats[cat]) cats[cat]={ label:'', enabled:false, locked:false };
            cats[cat].locked = $(this).is(':checked');
        });

        const data = {
            regulation:           $('#regulation').val(),
            consent_expiry:       parseInt($('#consent_expiry').val()),
            auto_block:           $('#auto_block').is(':checked'),
            gcm_enabled:          $('#gcm_enabled').is(':checked'),
            /* v1.4.0 */
            geo_detection:        $('#geo_detection').is(':checked'),
            geo_fallback:         $('#geo_fallback').val(),
            browseless_endpoint:  $('#browseless_endpoint').val(),
            browseless_token:     $('#browseless_token').val(),
            auto_policy_page:     $('#auto_policy_page').is(':checked'),
            /* v1.5.0 compliance */
            privacy_policy_url:   $('#privacy_policy_url').val(),
            ip_anonymize:         $('#ip_anonymize').is(':checked'),
            /* v1.5.1 T&C checkbox */
            show_tos_checkbox:    $('#show_tos_checkbox').is(':checked'),
            tos_url:              $('#tos_url').val(),
            /* v1.6.0 language + withdrawal */
            admin_lang:           $('#admin_lang').val(),
            withdrawal_enabled:   $('#withdrawal_enabled').is(':checked'),
            categories:           cats,
            /* v1.7.0 T&C enforcement */
            tc_enforcement_enabled: $('#tc_enforcement_enabled').is(':checked'),
            tc_acceptance_page_id:  parseInt($('#tc_acceptance_page_id').val()) || 0,
            tc_purge_rejected:      $('#tc_purge_rejected').is(':checked'),
            /* v2.1.0 login/register overlay */
            ltc_urls:               $('#ltc_urls').val() || '',
        };
        $.post(ajaxUrl, { action:'bcm_save_settings', nonce: n('save_settings'), settings: JSON.stringify(data) }, function(res){
            if(res.success){
                $('#bcm-save-notice').show().delay(3000).fadeOut();
            }
        });
    });

    /* ────────────────────────────────
       CONSENT LOG – v1.3.0
    ──────────────────────────────── */

    /* Exportar CSV */
    $(document).on('click', '#bcm-export-csv', function(){
        const $btn = $(this).prop('disabled', true).text('Generando…');
        $.post(ajaxUrl, { action:'bcm_export_consent_csv', nonce: n('export_csv') }, function(res){
            $btn.prop('disabled', false).text('⬇ Export CSV');
            if(res.success && res.data.url){
                window.location.href = res.data.url;
            }
        });
    });

    /* Borrar registros por IP (GDPR Art. 17) */
    $(document).on('click', '#bcm-delete-by-ip', function(){
        const ip = $('#bcm-delete-ip').val().trim();
        if(!ip){ alert('Introduce una IP válida.'); return; }
        if(!confirm('¿Eliminar todos los registros de consentimiento para la IP ' + ip + '?')) return;

        $.post(ajaxUrl, { action:'bcm_delete_consent_ip', nonce: n('delete_by_ip'), ip }, function(res){
            if(res.success){
                const n = res.data.deleted || 0;
                $('#bcm-delete-ip-result')
                    .text('✅ ' + n + ' registro(s) eliminado(s).')
                    .show().delay(4000).fadeOut();
                $('#bcm-delete-ip').val('');
            }
        });
    });

    /* ── Utility ── */
    function esc(str){ return $('<span>').text(str||'').html(); }

    /* v1.4.0: mostrar/ocultar campos según geo-detection toggle */
    function toggleGeoFields(){
        const geoOn = $('#geo_detection').is(':checked');
        $('#field-geo-fallback').toggle(geoOn);
        $('#field-regulation-manual').toggle(!geoOn);
    }
    $(document).on('change', '#geo_detection', toggleGeoFields);
    if($('#geo_detection').length) toggleGeoFields();

    /* v1.5.1: mostrar/ocultar campo URL de T&C */
    function toggleTosFields(){
        const tosOn = $('#show_tos_checkbox').is(':checked');
        $('#field-tos-url').toggle(tosOn);
    }
    $(document).on('change', '#show_tos_checkbox', toggleTosFields);
    if($('#show_tos_checkbox').length) toggleTosFields();

    /* v1.6.0: reload page on language change so PHP re-renders with new lang */
    $(document).on('change', '#admin_lang', function(){
        const lang = $(this).val();
        // save immediately then reload
        const cats = {};
        $('.cat-label').each(function(){
            const cat = $(this).data('cat');
            if(!cats[cat]) cats[cat]={ label:'', enabled:false, locked:false };
            cats[cat].label = $(this).val();
        });
        $('.cat-enabled').each(function(){
            const cat = $(this).data('cat');
            if(!cats[cat]) cats[cat]={ label:'', enabled:false, locked:false };
            cats[cat].enabled = $(this).is(':checked');
        });
        $('.cat-locked').each(function(){
            const cat = $(this).data('cat');
            if(!cats[cat]) cats[cat]={ label:'', enabled:false, locked:false };
            cats[cat].locked = $(this).is(':checked');
        });
        const data = {
            admin_lang: lang,
            regulation: $('#regulation').val(),
            consent_expiry: parseInt($('#consent_expiry').val()),
            auto_block: $('#auto_block').is(':checked'),
            gcm_enabled: $('#gcm_enabled').is(':checked'),
            geo_detection: $('#geo_detection').is(':checked'),
            geo_fallback: $('#geo_fallback').val(),
            browseless_endpoint: $('#browseless_endpoint').val(),
            browseless_token: $('#browseless_token').val(),
            auto_policy_page: $('#auto_policy_page').is(':checked'),
            privacy_policy_url: $('#privacy_policy_url').val(),
            ip_anonymize: $('#ip_anonymize').is(':checked'),
            show_tos_checkbox: $('#show_tos_checkbox').is(':checked'),
            tos_url: $('#tos_url').val(),
            withdrawal_enabled: $('#withdrawal_enabled').is(':checked'),
            categories: cats,
        };
        $.post(ajaxUrl, { action:'bcm_save_settings', nonce: n('save_settings'), settings: JSON.stringify(data) }, function(res){
            if(res.success) location.reload();
        });
    });

})(jQuery);
