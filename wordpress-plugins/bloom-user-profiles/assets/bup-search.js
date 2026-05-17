/**
 * bup-search.js — v1.1.0
 *
 * Intercepta los inputs de búsqueda de bloom-navbar (#nb-s y #nb-s-mob)
 * y muestra un dropdown mixto con Usuarios + Series.
 *
 * Integración con el stack real del sitio:
 *
 *  · AJAX URL: Lee window.msgAjax.ajaxurl (manga-scan-groups-v5) o
 *              ts_configs.get('general.ajaxUrl') (tema mangareader) o
 *              bupData.ajaxUrl (nuestro fallback).
 *
 *  · Búsqueda de mangas: El tema usa ajaxyLiveSearch con action=ts_live_search
 *    (o similar). Lo detectamos y usamos el mismo endpoint para no duplicar.
 *
 *  · Búsqueda de usuarios: Endpoint propio bloom_search_users.
 *
 *  · bloom-navbar crea los inputs de forma asíncrona → usamos MutationObserver.
 *
 *  · NO depende de jQuery (mismo patrón que follow-system.js de manga-scan-groups-v5).
 */

(function () {
    'use strict';

    if (typeof bupData === 'undefined') return;

    /* ── Resolver AJAX URL (orden de prioridad real del sitio) ── */
    function getAjaxUrl() {
        // 1. manga-scan-groups-v5 (más específico del proyecto)
        if (window.msgAjax && window.msgAjax.ajaxurl) return window.msgAjax.ajaxurl;
        // 2. tema mangareader (ts_configs)
        if (window.ts_configs && window.ts_configs.get) {
            const u = window.ts_configs.get('general.ajaxUrl');
            if (u) return u;
        }
        // 3. Nuestro fallback
        return bupData.ajaxUrl;
    }

    const SLUG = bupData.profileSlug || 'usuario';

    /* ── util ── */
    function debounce(fn, ms) {
        let t;
        return function (...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); };
    }

    function esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    /* ══════════════════════════════════════════════════
     *  Dropdown
     * ══════════════════════════════════════════════════ */

    function createDropdown() {
        const el = document.createElement('div');
        el.id = 'bup-search-dropdown';
        el.style.display = 'none';
        el.setAttribute('role', 'listbox');
        el.setAttribute('aria-label', 'Resultados de búsqueda');
        return el;
    }

    function showLoading(drop) {
        drop.style.display = 'block';
        drop.innerHTML = `<div class="bup-drop-loading"><span class="bup-spinner"></span>Buscando…</div>`;
    }

    function renderResults(drop, term, mangas, users) {
        if (!mangas.length && !users.length) {
            drop.innerHTML = `<div class="bup-drop-empty">Sin resultados para "<strong>${esc(term)}</strong>"</div>`;
            return;
        }

        let html = '';

        // ── Sección Usuarios ──
        if (users.length) {
            html += `<div class="bup-drop-section-title" role="presentation">Usuarios</div>`;
            users.forEach(u => {
                const roleStyle = `background:${u.role_color}22;color:${u.role_color};border:1px solid ${u.role_color}44`;
                html += `<a class="bup-drop-item" href="${esc(u.url)}" role="option">
                    <img src="${esc(u.avatar)}" alt="" class="bup-drop-item-img bup-avatar-round" width="38" height="38" loading="lazy">
                    <div class="bup-drop-item-info">
                        <span class="bup-drop-item-name">${esc(u.name)}</span>
                        <span class="bup-drop-item-sub">@${esc(u.login)}</span>
                    </div>
                    <span class="bup-drop-role" style="${roleStyle}">${esc(u.role)}</span>
                </a>`;
            });
        }

        // ── Sección Series ──
        if (mangas.length) {
            if (users.length) html += `<hr class="bup-drop-divider">`;
            html += `<div class="bup-drop-section-title" role="presentation">Series</div>`;
            mangas.forEach(m => {
                // El tema devuelve diferentes formatos según la versión de ajaxyLiveSearch
                const title  = m.title || m.post_title || '';
                const url    = m.url   || m.permalink  || '#';
                const thumb  = m.image || m.thumbnail  || (Array.isArray(m.thumbnail_url) ? m.thumbnail_url[0] : '') || '';
                const type   = m.type  || 'Manga';
                const img    = thumb
                    ? `<img src="${esc(thumb)}" alt="" class="bup-drop-item-img" width="38" height="38" loading="lazy">`
                    : `<div class="bup-drop-item-img" style="background:#1e2235;border-radius:6px;"></div>`;

                html += `<a class="bup-drop-item" href="${esc(url)}" role="option">
                    ${img}
                    <div class="bup-drop-item-info">
                        <span class="bup-drop-item-name">${esc(title)}</span>
                        <span class="bup-drop-item-sub">${esc(type)}</span>
                    </div>
                </a>`;
            });
        }

        // ── Ver todos ──
        const searchUrl = (window.ts_configs && window.ts_configs.get)
            ? ts_configs.get('general.site_url', location.origin) + '/?s=' + encodeURIComponent(term)
            : location.origin + '/?s=' + encodeURIComponent(term);

        html += `<a class="bup-drop-see-all" href="${searchUrl}">
            Ver todos los resultados
            <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
        </a>`;

        drop.innerHTML = html;
    }

    /* ══════════════════════════════════════════════════
     *  Fetch usuarios
     * ══════════════════════════════════════════════════ */

    async function fetchUsers(term) {
        try {
            const ajax = getAjaxUrl();
            const res  = await fetch(`${ajax}?action=bloom_search_users&term=${encodeURIComponent(term)}`);
            const json = await res.json();
            return json.success ? (json.data || []) : [];
        } catch {
            return [];
        }
    }

    /* ══════════════════════════════════════════════════
     *  Fetch mangas (usando el endpoint de ajaxyLiveSearch del tema)
     *
     *  El tema registra el handler en `inc/core/search.php`.
     *  La action real observada en producción es usada por ajaxyLiveSearch.
     *  Probamos el endpoint nativo del tema que usa el objeto sf_templates / jQuery.
     * ══════════════════════════════════════════════════ */

    async function fetchMangas(term) {
        try {
            const ajax = getAjaxUrl();

            // Intentar primero con ts_live_search (MangaReader theme v2)
            const fd = new FormData();
            fd.append('action', 'ts_live_search');
            fd.append('searchkey', term);

            const res  = await fetch(ajax, { method: 'POST', body: fd });
            const text = await res.text();

            // Si la respuesta es HTML (el tema puede devolver HTML directo en v1)
            if (text.trim().startsWith('<')) {
                // Parsear HTML y extraer items de búsqueda
                const parser = new DOMParser();
                const doc    = parser.parseFromString(text, 'text/html');
                const items  = Array.from(doc.querySelectorAll('.ajaxy-suggestion-row, .search-result-item, li[data-search-url]'));
                return items.slice(0, 6).map(el => ({
                    title: el.querySelector('h4, .title, strong')?.textContent.trim() || el.textContent.trim(),
                    url:   el.querySelector('a')?.href || el.dataset.searchUrl || '#',
                    image: el.querySelector('img')?.src || '',
                    type:  el.querySelector('.type, .badge')?.textContent.trim() || 'Manhwa',
                })).filter(m => m.title);
            }

            // Si es JSON
            const json = JSON.parse(text);
            if (Array.isArray(json)) return json.slice(0, 6);
            if (json && Array.isArray(json.data)) return json.data.slice(0, 6);
            return [];

        } catch {
            return [];
        }
    }

    /* ══════════════════════════════════════════════════
     *  Bind input
     * ══════════════════════════════════════════════════ */

    function bindSearch(inp) {
        if (inp.dataset.bupBound) return;
        inp.dataset.bupBound = '1';

        // El input vive dentro de .nb-pill; necesitamos un padre position:relative
        const pill    = inp.closest('.nb-pill') || inp.parentElement;
        const wrapper = pill.parentElement;
        wrapper.style.position = 'relative';

        const drop = createDropdown();
        wrapper.appendChild(drop);

        // Cerrar al hacer click fuera
        document.addEventListener('click', (e) => {
            if (!wrapper.contains(e.target)) drop.style.display = 'none';
        });

        const doSearch = debounce(async (term) => {
            if (term.length < 2) { drop.style.display = 'none'; return; }
            showLoading(drop);
            const [users, mangas] = await Promise.all([ fetchUsers(term), fetchMangas(term) ]);
            drop.style.display = 'block';
            renderResults(drop, term, mangas, users);
        }, 320);

        inp.addEventListener('input', () => doSearch(inp.value.trim()));
        inp.addEventListener('focus', () => {
            if (inp.value.trim().length >= 2) drop.style.display = 'block';
        });
        inp.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') { drop.style.display = 'none'; }
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                const first = drop.querySelector('.bup-drop-item');
                if (first) first.focus();
            }
        });

        // Navegación por teclado dentro del dropdown
        drop.addEventListener('keydown', (e) => {
            const items = Array.from(drop.querySelectorAll('.bup-drop-item, .bup-drop-see-all'));
            const idx   = items.indexOf(document.activeElement);
            if (e.key === 'ArrowDown') { e.preventDefault(); items[idx + 1]?.focus(); }
            if (e.key === 'ArrowUp')   { e.preventDefault(); idx > 0 ? items[idx - 1].focus() : inp.focus(); }
            if (e.key === 'Escape')    { drop.style.display = 'none'; inp.focus(); }
        });
    }

    /* ══════════════════════════════════════════════════
     *  Observer (bloom-navbar crea los inputs async)
     * ══════════════════════════════════════════════════ */

    function tryBind() {
        // IDs específicos de bloom-navbar
        const searchIDs = ['nb-s', 'nb-s-mob'];
        let found = false;

        searchIDs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                bindSearch(el);
                found = true;
            }
        });

        // Fallback: buscar cualquier input de búsqueda que parezca del navbar
        if (!found) {
            const inputs = document.querySelectorAll('.nb-pill input[type="text"], .centernav input[type="text"]');
            inputs.forEach(inp => {
                if (inp.placeholder && inp.placeholder.toLowerCase().includes('buscar')) {
                    bindSearch(inp);
                }
            });
        }
    }

    // Ejecución inicial
    tryBind();

    // MutationObserver para capturar los inputs que bloom-navbar inyecta tarde
    const obs = new MutationObserver((mutations) => {
        tryBind();
    });
    obs.observe(document.body, { childList: true, subtree: true });

    // Timeouts de seguridad por si el observer falla o hay delay excesivo
    [600, 1400, 3000].forEach(ms => setTimeout(tryBind, ms));

})();
