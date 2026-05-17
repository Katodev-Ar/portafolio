/**
 * bup-profile.js
 * Handles the user profile wall: loading messages, submitting new ones.
 */

(function () {
    'use strict';

    if (typeof bupData === 'undefined') return;

    const AJAX      = bupData.ajaxUrl;
    const NONCE     = bupData.wallNonce;
    const profileEl = document.getElementById('bup-profile');
    if (!profileEl) return;

    const PROFILE_ID = parseInt(profileEl.dataset.userId, 10);
    if (!PROFILE_ID) return;

    /* ── State ── */
    let page = 1;
    let loading = false;

    /* ── DOM refs ── */
    const msgContainer = document.getElementById('bup-wall-messages');
    const loadMoreBtn  = document.getElementById('bup-load-more');
    const form         = document.getElementById('bup-wall-form');
    const textarea     = document.getElementById('bup-wall-msg');
    const submitBtn    = document.getElementById('bup-wall-submit');
    const errorEl      = document.getElementById('bup-wall-error');
    const charCount    = document.getElementById('bup-char-count');

    /* ════════════════════════════
     *  Render a single message
     * ════════════════════════════ */

    function renderMessage(m, prepend = false) {
        const roleStyle = m.role_color
            ? `background:${m.role_color}22;color:${m.role_color};border:1px solid ${m.role_color}44`
            : '';

        const el = document.createElement('div');
        el.className = 'bup-wall-message';
        el.dataset.id = m.id;
        el.innerHTML = `
            <img src="${esc(m.avatar)}" alt="${esc(m.author_name)}" class="bup-msg-avatar" width="40" height="40">
            <div class="bup-msg-body">
                <div class="bup-msg-meta">
                    <a href="${esc(m.author_url)}" class="bup-msg-author">${esc(m.author_name)}</a>
                    ${m.role ? `<span class="bup-msg-role" style="${roleStyle}">${esc(m.role)}</span>` : ''}
                    <span class="bup-msg-time">${esc(m.created_at)}</span>
                </div>
                <p class="bup-msg-text">${nl2br(esc(m.message))}</p>
            </div>`;

        if (prepend) {
            msgContainer.insertBefore(el, msgContainer.firstChild);
        } else {
            msgContainer.appendChild(el);
        }
    }

    function nl2br(str) {
        return str.replace(/\n/g, '<br>');
    }

    function esc(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    /* ════════════════════════════
     *  Load messages (AJAX)
     * ════════════════════════════ */

    async function loadMessages(p = 1) {
        if (loading) return;
        loading = true;

        if (p === 1) {
            msgContainer.innerHTML = `<div class="bup-drop-loading"><span class="bup-spinner"></span>Cargando mensajes…</div>`;
        }

        try {
            const res  = await fetch(`${AJAX}?action=bup_wall_load&profile_id=${PROFILE_ID}&page=${p}`);
            const json = await res.json();

            if (!json.success) throw new Error(json.data?.message || 'Error al cargar.');

            const { messages, has_more } = json.data;

            if (p === 1) {
                msgContainer.innerHTML = '';
                if (!messages.length) {
                    msgContainer.innerHTML = `
                        <div class="bup-wall-empty">
                            <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                            Aún no hay mensajes. ¡Sé el primero en escribir!
                        </div>`;
                }
            }

            messages.forEach(m => renderMessage(m, false));
            loadMoreBtn.style.display = has_more ? 'block' : 'none';
            page = p;

        } catch (e) {
            if (p === 1) {
                msgContainer.innerHTML = `<div class="bup-wall-empty">No se pudieron cargar los mensajes.</div>`;
            }
        } finally {
            loading = false;
        }
    }

    /* ════════════════════════════
     *  Submit new message
     * ════════════════════════════ */

    if (form && textarea) {
        // Char counter
        textarea.addEventListener('input', () => {
            const len = textarea.value.length;
            charCount.textContent = `${len} / 500`;
            charCount.style.color = len > 460 ? '#ff6b6b' : '';
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = textarea.value.trim();

            if (msg.length < 3) {
                showError('El mensaje es demasiado corto (mínimo 3 caracteres).');
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = 'Enviando…';
            hideError();

            try {
                const fd = new FormData();
                fd.append('action',     'bup_wall_post');
                fd.append('nonce',      NONCE);
                fd.append('profile_id', PROFILE_ID);
                fd.append('message',    msg);

                const res  = await fetch(AJAX, { method: 'POST', body: fd });
                const json = await res.json();

                if (!json.success) throw new Error(json.data?.message || 'Error al enviar.');

                // Limpiar textarea
                textarea.value = '';
                charCount.textContent = '0 / 500';

                // Mostrar el nuevo mensaje al inicio del muro
                const empty = msgContainer.querySelector('.bup-wall-empty');
                if (empty) empty.remove();
                renderMessage(json.data, true);

                // Animación del botón
                submitBtn.innerHTML = '✓ Enviado';
                setTimeout(() => {
                    submitBtn.innerHTML = `<svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Enviar`;
                    submitBtn.disabled = false;
                }, 1500);

            } catch (err) {
                showError(err.message);
                submitBtn.innerHTML = `<svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg> Enviar`;
                submitBtn.disabled = false;
            }
        });
    }

    /* ════════════════════════════
     *  Load more
     * ════════════════════════════ */

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => loadMessages(page + 1));
    }

    /* ════════════════════════════
     *  Error helpers
     * ════════════════════════════ */

    function showError(msg) {
        if (!errorEl) return;
        errorEl.textContent = msg;
        errorEl.style.display = 'block';
    }

    function hideError() {
        if (!errorEl) return;
        errorEl.style.display = 'none';
    }

    /* ════════════════════════════
     *  Init
     * ════════════════════════════ */

    loadMessages(1);

})();
