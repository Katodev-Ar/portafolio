/* Bloom Cookie Manager v1.5.0 – Frontend JS
 * v1.5.0 Compliance fixes:
 *   - Checkboxes desmarcados por defecto en primera visita (GDPR Art. 7 / Cdo. 32)
 *   - Cookie de consentimiento con flag Secure en sitios HTTPS
 *   - openPreferences() refleja correctamente el estado real según status previo
 */
(function(){
    'use strict';

    function bcmInit() {

    const cfg         = window.bcmConfig || {};
    const COOKIE_NAME = 'bcm_consent';
    const expDays     = cfg.expiry    || 365;
    const regulation  = (cfg.regulation || 'GDPR').toUpperCase();

    /* Modo por regulación
     *  GDPR / LGPD : opt-in  — bloquear todo hasta consentimiento
     *  CCPA        : opt-out — cargar todo, mostrar "Do Not Sell"   */
    const isOptIn = ( regulation === 'GDPR' || regulation === 'LGPD' );
    const isCCPA  = ( regulation === 'CCPA' );

    /* ── Cookie helpers ── */
    function setCookie( name, value, days ){
        const d = new Date();
        d.setTime( d.getTime() + days * 864e5 );
        /* FIX v1.5.0: se agrega el flag Secure cuando el sitio sirve sobre HTTPS.
         * Esto evita que la cookie de consentimiento viaje por canales no cifrados. */
        const secure = ( location.protocol === 'https:' ) ? ';Secure' : '';
        document.cookie = name + '=' + encodeURIComponent( value )
            + ';expires=' + d.toUTCString() + ';path=/;SameSite=Lax' + secure;
    }
    function getCookie( name ){
        const m = document.cookie.match( '(?:^|;)\\s*' + name + '=([^;]*)' );
        return m ? decodeURIComponent( m[1] ) : null;
    }
    function genId(){
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace( /[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return ( c === 'x' ? r : ( r & 0x3 | 0x8 ) ).toString(16);
        });
    }

    /* ── Leer consentimiento guardado ── */
    function getStoredConsent(){
        const raw = getCookie( COOKIE_NAME );
        if ( !raw ) return null;
        try { return JSON.parse( raw ); } catch(e){ return null; }
    }
    function isCategoryGranted( cat ){
        const stored = getStoredConsent();
        if ( !stored ) return !isOptIn;
        if ( stored.status === 'accepted' ) return true;
        if ( stored.status === 'rejected' ) return cat === 'necessary';
        return stored.categories && stored.categories.includes( cat );
    }

    /* ══════════════════════════════════════════════════════════════
     *  BLOQUEO Y ACTIVACIÓN DINÁMICA DE SCRIPTS (v1.4.1)
     *
     *  Uso en el HTML del sitio:
     *    <script type="text/plain" data-bcm-cat="analytics"
     *            data-src="https://www.googletagmanager.com/gtm.js?id=GTM-XXXXX">
     *    </script>
     *
     *    <script type="text/plain" data-bcm-cat="analytics">
     *      // código inline
     *    </script>
     * ══════════════════════════════════════════════════════════════ */

    function activateBlockedScripts( grantedCategories ){
        document.querySelectorAll( 'script[type="text/plain"][data-bcm-cat]' ).forEach( el => {
            const cat = el.getAttribute( 'data-bcm-cat' );
            if ( !grantedCategories.includes( cat ) ) return;

            const s    = document.createElement( 'script' );
            s.type     = 'text/javascript';
            ['id','async','defer','crossorigin','integrity'].forEach( attr => {
                if ( el.hasAttribute( attr ) ) s.setAttribute( attr, el.getAttribute( attr ) );
            });
            const src = el.getAttribute( 'data-src' ) || el.getAttribute( 'src' );
            if ( src ) {
                s.src = src;
            } else {
                s.textContent = el.textContent;
            }
            el.parentNode.insertBefore( s, el.nextSibling );
            el.remove();
        });
    }

    function activateBlockedIframes( grantedCategories ){
        /* iframes con data-bcm-cat aún en el DOM */
        document.querySelectorAll( 'iframe[data-bcm-cat]' ).forEach( el => {
            const cat = el.getAttribute( 'data-bcm-cat' );
            if ( !grantedCategories.includes( cat ) ) return;
            const src = el.getAttribute( 'data-bcm-src' ) || el.getAttribute( 'data-src' );
            if ( src ){
                el.src = src;
                el.removeAttribute( 'data-bcm-src' );
                el.removeAttribute( 'data-bcm-cat' );
            }
        });
        /* Placeholders generados por blockPendingIframes() */
        document.querySelectorAll( '.bcm-blocked-placeholder[data-bcm-cat]' ).forEach( ph => {
            const cat = ph.getAttribute( 'data-bcm-cat' );
            if ( !grantedCategories.includes( cat ) ) return;
            const src = ph.getAttribute( 'data-bcm-src' );
            if ( src ){
                const iframe   = document.createElement( 'iframe' );
                iframe.src     = src;
                iframe.setAttribute( 'loading', 'lazy' );
                ph.replaceWith( iframe );
            }
        });
    }

    function blockPendingIframes(){
        if ( !isOptIn ) return;
        document.querySelectorAll( 'iframe[data-bcm-cat]' ).forEach( el => {
            const cat = el.getAttribute( 'data-bcm-cat' );
            if ( cat === 'necessary' || isCategoryGranted( cat ) ) return;
            const originalSrc = el.src || el.getAttribute( 'data-src' );
            if ( originalSrc && !el.getAttribute( 'data-bcm-src' ) ){
                el.setAttribute( 'data-bcm-src', originalSrc );
                el.removeAttribute( 'src' );
                const ph = document.createElement( 'div' );
                ph.className = 'bcm-blocked-placeholder';
                ph.setAttribute( 'data-bcm-cat', cat );
                ph.setAttribute( 'data-bcm-src', originalSrc );
                const tpl = ( cfg.strings && cfg.strings.blockedContent )
                    ? cfg.strings.blockedContent
                    : '🍪 Este contenido requiere cookies de <strong>%cat%</strong>. <a href="#" class="bcm-unblock-link" data-cat="%cat%">Aceptar para cargar</a>';
                ph.innerHTML = tpl.replace( /%cat%/g, cat );
                el.replaceWith( ph );
            }
        });
    }

    /* ── Google Consent Mode v2 ── */
    function gcmDefault(){
        if ( !cfg.gcm ) return;
        /* gtag puede no estar disponible aún — usar dataLayer push directo */
        window.dataLayer = window.dataLayer || [];
        function gtag(){ window.dataLayer.push(arguments); }
        gtag( 'consent', 'default', {
            analytics_storage:       'denied',
            ad_storage:              'denied',
            functionality_storage:   'denied',
            personalization_storage: 'denied',
            wait_for_update:         500,
        });
    }
    function updateGCM( data ){
        if ( !cfg.gcm ) return;
        if ( typeof gtag !== 'function' && typeof window.gtag !== 'function' ) return;
        const _gtag = typeof gtag === 'function' ? gtag : window.gtag;
        const cats = data.categories || [];
        _gtag( 'consent', 'update', {
            analytics_storage:       cats.includes('analytics')     ? 'granted' : 'denied',
            ad_storage:              cats.includes('advertisement')  ? 'granted' : 'denied',
            functionality_storage:   cats.includes('functional')     ? 'granted' : 'denied',
            personalization_storage: cats.includes('functional')     ? 'granted' : 'denied',
        });
    }

    /* ── Elementos del DOM ── */
    const banner    = document.getElementById( 'bcm-banner' );
    const prefPanel = document.getElementById( 'bcm-preferences' );
    const reopenBtn = document.getElementById( 'bcm-reopen' );

    if ( !banner ) return;

    gcmDefault();

    /* ── Adaptar UI según regulación ── */
    function adaptBannerToRegulation(){
        if ( isCCPA ){
            const rejectBtn = document.getElementById( 'bcm-btn-reject' );
            if ( rejectBtn ){
                rejectBtn.textContent = cfg.lang === 'es' ? 'No vender mis datos' : 'Do Not Sell My Data';
                rejectBtn.setAttribute( 'data-ccpa', '1' );
            }
            const custBtn = document.getElementById( 'bcm-btn-customize' );
            if ( custBtn ) custBtn.style.display = 'none';

            const desc = banner.querySelector( '.bcm-banner-desc' );
            if ( desc ){
                const note = document.createElement( 'small' );
                note.style.cssText = 'display:block;margin-top:6px;opacity:.75;font-size:.8em';
                note.textContent   = ( cfg.strings && cfg.strings.ccpaNote )
                    ? cfg.strings.ccpaNote
                    : 'Residents of California have the right to opt out of the sale of personal data.';
                desc.after( note );
            }
        }
    }

    function showBanner(){
        banner.style.display = '';
        banner.classList.remove( 'bcm-hidden' );
        if ( reopenBtn ) reopenBtn.style.display = 'none';
    }
    function hideBanner(){
        banner.classList.add( 'bcm-hidden' );
        setTimeout( () => { banner.style.display = 'none'; }, 380 );
        if ( reopenBtn ) reopenBtn.style.display = '';
    }

    /* ── Guardar consentimiento ── */
    function saveConsent( status, categories ){
        const id   = genId();
        const data = { consent_id: id, status, categories, regulation };

        setCookie( COOKIE_NAME, JSON.stringify( data ), expDays );
        updateGCM( data );

        /* Activar contenido bloqueado SIN recargar la página */
        if ( status === 'accepted' ){
            activateBlockedScripts( cfg.categories || [] );
            activateBlockedIframes( cfg.categories || [] );
        } else if ( status === 'custom' ){
            activateBlockedScripts( categories );
            activateBlockedIframes( categories );
        }
        /* CCPA opt-out: no activar publicidad pero dejar el resto */
        if ( isCCPA && status === 'custom' ){
            activateBlockedScripts( categories );
            activateBlockedIframes( categories );
        }

        const fd = new FormData();
        fd.append( 'action',     'bcm_record_consent' );
        fd.append( 'nonce',      cfg.nonce );
        fd.append( 'consent_id', id );
        fd.append( 'status',     status );
        fd.append( 'categories', JSON.stringify( categories ) );
        fd.append( 'regulation', regulation );
        fetch( cfg.ajaxUrl, { method: 'POST', body: fd });
    }

    /* ── v1.8.3: T&C Enforcement — conectar banner con TC Manager ── */
    const tcEnforcement = cfg.tcEnforcement === true;
    const tcAlreadyAccepted = cfg.tcAccepted === true;

    /**
     * Si el T&C enforcement está activo y el usuario aún no aceptó,
     * registrar la aceptación en el servidor vía bcm_accept_tc.
     * Se llama junto con saveConsent() cuando el usuario hace "Aceptar".
     */
    function tcAcceptIfNeeded() {
        if ( !tcEnforcement || tcAlreadyAccepted ) return;
        if ( !cfg.tcNonce ) return;
        const fd = new FormData();
        fd.append( 'action',      'bcm_accept_tc' );
        fd.append( 'nonce',       cfg.tcNonce );
        fd.append( 'redirect_to', window.location.href );
        fetch( cfg.ajaxUrl, { method: 'POST', body: fd } );
        // Mark locally so we don't send twice in same session
        cfg.tcAccepted = true;
    }

    /**
     * Si el T&C enforcement está activo, llamar bcm_reject_tc para
     * destruir la sesión del usuario y redirigirlo.
     * Retorna true si se inició el proceso de logout (el caller debe parar).
     */
    function tcRejectIfNeeded( onComplete ) {
        // FIX v1.9.0: tcNonce is now always provided for logged-in users,
        // regardless of tc_enforcement_enabled. This ensures "Rechazar todo"
        // always triggers a proper logout for authenticated users.
        if ( !cfg.tcNonce ) return false;
        const fd = new FormData();
        fd.append( 'action', 'bcm_reject_tc' );
        fd.append( 'nonce',  cfg.tcNonce );
        fetch( cfg.ajaxUrl, { method: 'POST', body: fd } )
            .then( r => r.json() )
            .then( data => {
                if ( data.success && data.data && data.data.redirect ) {
                    window.location.href = data.data.redirect;
                } else {
                    window.location.href = '/?error=tc_rejected';
                }
            } )
            .catch( () => { window.location.href = '/?error=tc_rejected'; } );
        if ( onComplete ) onComplete();
        return true;
    }

    /* ── v1.5.1: Validación del checkbox T&C ── */
    const tosRequired = cfg.showTos === true;

    function tosCheck( checkId, errorId ) {
        if ( !tosRequired ) return true;
        const chk = document.getElementById( checkId );
        const err = document.getElementById( errorId );
        if ( chk && !chk.checked ) {
            if ( err ) {
                err.style.display = 'block';
                /* Shake visual para llamar la atención */
                err.classList.remove( 'bcm-shake' );
                void err.offsetWidth; // reflow para reiniciar animación
                err.classList.add( 'bcm-shake' );
            }
            chk.focus();
            return false;
        }
        if ( err ) err.style.display = 'none';
        return true;
    }

    /* Limpiar error en cuanto el usuario marca el checkbox */
    ['bcm-tos-check', 'bcm-tos-check-pref'].forEach( id => {
        const el = document.getElementById( id );
        if ( el ) el.addEventListener( 'change', function() {
            const errId = id === 'bcm-tos-check' ? 'bcm-tos-error' : 'bcm-tos-error-pref';
            const err = document.getElementById( errId );
            if ( err ) err.style.display = 'none';
        });
    });

    /* ── Listeners — FIX v1.4.1: usar getElementById en cada bind ── */
    const btnAccept    = document.getElementById( 'bcm-btn-accept' );
    const btnReject    = document.getElementById( 'bcm-btn-reject' );
    const btnCustomize = document.getElementById( 'bcm-btn-customize' );

    if ( btnAccept ) {
        btnAccept.addEventListener( 'click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if ( !tosCheck( 'bcm-tos-check', 'bcm-tos-error' ) ) return;
            saveConsent( 'accepted', cfg.categories || [] );
            tcAcceptIfNeeded(); // v1.8.3: registrar aceptación de T&C si aplica
            hideBanner();
        });
    }

    if ( btnReject ) {
        btnReject.addEventListener( 'click', function(e){
            e.preventDefault();
            e.stopPropagation();
            if ( isCCPA ){
                const keepCats = (cfg.categories || []).filter( c => c !== 'advertisement' );
                saveConsent( 'custom', keepCats );
                hideBanner();
            } else {
                saveConsent( 'rejected', ['necessary'] );
                // v1.8.3: si T&C enforcement activo, rechazar también cierra sesión
                if ( !tcRejectIfNeeded( () => hideBanner() ) ) {
                    hideBanner();
                }
            }
        });
    }

    if ( btnCustomize ) {
        btnCustomize.addEventListener( 'click', function(e){
            e.preventDefault();
            e.stopPropagation();
            openPreferences();
        });

    }

    if ( reopenBtn ) {
        reopenBtn.addEventListener( 'click', function(e){
            e.preventDefault();
            openPreferences();
        });
    }

    function openPreferences(){
        if ( prefPanel ) prefPanel.style.display = '';
        const stored = getStoredConsent();
        document.querySelectorAll( '[name="bcm_cat"]' ).forEach( el => {
            if ( el.getAttribute( 'data-locked' ) === '1' ) return; // necessary siempre on
            if ( stored ) {
                /* Visita posterior: reflejar elección previa */
                if ( stored.status === 'accepted' ) {
                    el.checked = true;
                } else if ( stored.status === 'rejected' ) {
                    el.checked = false;
                } else {
                    /* custom: marcar solo las categorías aprobadas */
                    el.checked = stored.categories && stored.categories.includes( el.value );
                }
            } else {
                /* FIX v1.5.0 — Primera visita: desmarcadas por defecto.
                 * El consentimiento GDPR/LGPD debe ser una acción positiva del usuario
                 * (opt-in). Tener checkboxes pre-marcados invalida el consentimiento
                 * bajo GDPR Art. 7 y el considerando 32. */
                el.checked = false;
            }
        });
    }

    const prefClose   = document.querySelector( '.bcm-pref-close' );
    const prefOverlay = document.querySelector( '.bcm-pref-overlay' );
    const prefSave    = document.getElementById( 'bcm-pref-save' );
    const prefAccept  = document.getElementById( 'bcm-pref-accept' );
    const prefReject  = document.getElementById( 'bcm-pref-reject' );

    if ( prefClose )   prefClose.addEventListener(   'click', () => { if(prefPanel) prefPanel.style.display='none'; });
    if ( prefOverlay ) prefOverlay.addEventListener( 'click', () => { if(prefPanel) prefPanel.style.display='none'; });

    if ( prefSave ) prefSave.addEventListener( 'click', () => {
        // FIX v1.9.0: if TOS checkbox exists and is NOT checked, treat as rejection
        const tosChk = document.getElementById( 'bcm-tos-check-pref' );
        if ( tosRequired && tosChk && !tosChk.checked ) {
            // Show error AND trigger TC reject (logout) for logged-in users
            const err = document.getElementById( 'bcm-tos-error-pref' );
            if ( err ) {
                err.style.display = 'block';
                err.classList.remove( 'bcm-shake' );
                void err.offsetWidth;
                err.classList.add( 'bcm-shake' );
            }
            tosChk.focus();
            // If logged in, also trigger logout
            tcRejectIfNeeded( () => { if ( prefPanel ) prefPanel.style.display = 'none'; hideBanner(); } );
            return;
        }
        if ( !tosCheck( 'bcm-tos-check-pref', 'bcm-tos-error-pref' ) ) return;
        const cats = ['necessary'];
        document.querySelectorAll( '[name="bcm_cat"]:checked' ).forEach( el => cats.push( el.value ) );
        saveConsent( 'custom', cats );
        tcAcceptIfNeeded();
        if ( prefPanel ) prefPanel.style.display = 'none';
        hideBanner();
    });
    if ( prefAccept ) prefAccept.addEventListener( 'click', () => {
        // FIX v1.9.0: if TOS checkbox exists and is NOT checked, block and logout
        const tosChk = document.getElementById( 'bcm-tos-check-pref' );
        if ( tosRequired && tosChk && !tosChk.checked ) {
            const err = document.getElementById( 'bcm-tos-error-pref' );
            if ( err ) {
                err.style.display = 'block';
                err.classList.remove( 'bcm-shake' );
                void err.offsetWidth;
                err.classList.add( 'bcm-shake' );
            }
            tosChk.focus();
            tcRejectIfNeeded( () => { if ( prefPanel ) prefPanel.style.display = 'none'; hideBanner(); } );
            return;
        }
        if ( !tosCheck( 'bcm-tos-check-pref', 'bcm-tos-error-pref' ) ) return;
        saveConsent( 'accepted', cfg.categories || [] );
        tcAcceptIfNeeded();
        if ( prefPanel ) prefPanel.style.display = 'none';
        hideBanner();
    });
    if ( prefReject ) prefReject.addEventListener( 'click', () => {
        saveConsent( 'rejected', ['necessary'] );
        // v1.8.3: rechazar en preferencias también cierra sesión si T&C enforcement activo
        if ( !tcRejectIfNeeded( () => { if ( prefPanel ) prefPanel.style.display = 'none'; hideBanner(); } ) ) {
            if ( prefPanel ) prefPanel.style.display = 'none';
            hideBanner();
        }
    });

    document.addEventListener( 'click', e => {
        const link = e.target.closest( '.bcm-unblock-link' );
        if ( link ){ e.preventDefault(); openPreferences(); }
    });

    /* ── Init ── */

    // v1.8.3: Si T&C enforcement está activo y el usuario logueado no ha aceptado,
    // redirigir a la página de aceptación de T&C antes de mostrar el banner.
    // Esto es una defensa client-side complementaria al gate_access() del servidor.
    if ( tcEnforcement && !tcAlreadyAccepted && cfg.tcPageUrl ) {
        window.location.href = cfg.tcPageUrl;
        return; // No continuar inicializando el banner
    }

    const stored = getStoredConsent();
    if ( stored ){
        hideBanner();
        updateGCM( stored );
        if ( stored.status === 'accepted' ){
            activateBlockedScripts( cfg.categories || [] );
            activateBlockedIframes( cfg.categories || [] );
        } else if ( stored.status === 'custom' && stored.categories ){
            activateBlockedScripts( stored.categories );
            activateBlockedIframes( stored.categories );
        }
    } else {
        if ( isOptIn ) blockPendingIframes();
        adaptBannerToRegulation();
        showBanner();
    }

    } // end bcmInit

    /* FIX v1.4.1: garantizar que el DOM esté listo antes de vincular eventos */
    if ( document.readyState === 'loading' ) {
        document.addEventListener( 'DOMContentLoaded', bcmInit );
    } else {
        bcmInit();
    }

})();
