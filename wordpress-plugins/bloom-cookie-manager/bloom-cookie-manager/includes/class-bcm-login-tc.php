<?php
/**
 * BCM_Login_TC — TOS Overlay para páginas de Login/Registro (v2.1.0)
 *
 * Estrategia: inyectar el overlay via wp_footer() en las URLs de login/registro,
 * igual que el banner de cookies. Esto funciona con cualquier template PHP,
 * shortcode o plugin de login — sin importar cómo esté construida la página.
 *
 * Configuración en el admin: campo "Login/Register URLs" donde el admin
 * escribe las URLs separadas por coma (o se usan las defaults de WP).
 *
 * @package  BloomCookieManager
 * @since    2.1.0
 */

if ( ! defined( 'ABSPATH' ) ) exit;

class BCM_Login_TC {

    /** Cookie de sesión: indica que el visitante ya aceptó los T&C */
    const COOKIE = 'bcm_ltc_ok';

    public function __construct() {
        add_action( 'wp_ajax_bcm_ltc_accept',        [ $this, 'ajax_accept' ] );
        add_action( 'wp_ajax_nopriv_bcm_ltc_accept', [ $this, 'ajax_accept' ] );

        // Inyectar overlay en wp_footer() cuando estamos en una página de login/registro
        add_action( 'wp_footer', [ $this, 'maybe_inject_overlay' ], 5 );

        // Enqueue assets solo cuando se va a mostrar el overlay
        add_action( 'wp_enqueue_scripts', [ $this, 'maybe_enqueue' ], 20 );

        // Parche al banner de cookies (para usuarios logueados)
        add_action( 'wp_enqueue_scripts', [ $this, 'enqueue_banner_patch' ], 99 );

        // Shortcode legacy — por compatibilidad, ahora no hace nada si el overlay ya fue inyectado
        add_shortcode( 'bcm_login_tc', [ $this, 'shortcode_noop' ] );
    }

    /* ═══════════════════════════════════════════════════════════
     *  Detectar si la página actual es de login/registro
     * ═══════════════════════════════════════════════════════════ */

    private function is_login_register_page(): bool {
        if ( ! isset( $_SERVER['REQUEST_URI'] ) ) return false;

        $s          = class_exists( 'BCM_Settings' ) ? BCM_Settings::get() : [];
        $custom_raw = $s['ltc_urls'] ?? '';

        // URLs configuradas en el admin (separadas por coma o salto de línea)
        $urls = [];
        if ( $custom_raw ) {
            foreach ( preg_split( '/[\r\n,]+/', $custom_raw ) as $u ) {
                $u = trim( $u );
                if ( $u ) $urls[] = rtrim( parse_url( $u, PHP_URL_PATH ) ?? $u, '/' );
            }
        }

        // Defaults siempre incluidos
        $defaults = [
            rtrim( parse_url( home_url( '/login' ),      PHP_URL_PATH ) ?? '/login',      '/' ),
            rtrim( parse_url( home_url( '/login-2' ),    PHP_URL_PATH ) ?? '/login-2',    '/' ),
            rtrim( parse_url( home_url( '/register' ),   PHP_URL_PATH ) ?? '/register',   '/' ),
            rtrim( parse_url( home_url( '/register-2' ), PHP_URL_PATH ) ?? '/register-2', '/' ),
        ];

        $all       = array_unique( array_merge( $defaults, $urls ) );
        $current   = rtrim( parse_url( esc_url_raw( wp_unslash( $_SERVER['REQUEST_URI'] ) ), PHP_URL_PATH ) ?? '', '/' );

        return in_array( $current, $all, true );
    }

    private function should_show(): bool {
        // No mostrar si el usuario logueado ya aceptó
        if ( is_user_logged_in() ) {
            return get_user_meta( get_current_user_id(), '_tc_accepted', true ) !== '1';
        }
        // No mostrar si el visitante ya aceptó en esta sesión
        if ( ! empty( $_COOKIE[ self::COOKIE ] ) ) return false;

        return true;
    }

    /* ═══════════════════════════════════════════════════════════
     *  Inyección via wp_footer
     * ═══════════════════════════════════════════════════════════ */

    public function maybe_inject_overlay(): void {
        if ( ! $this->is_login_register_page() ) return;
        if ( ! $this->should_show() ) return;

        $s        = class_exists( 'BCM_Settings' ) ? BCM_Settings::get() : [];
        $is_es    = ( ( $s['admin_lang'] ?? 'es' ) === 'es' );
        $tos_url  = $s['tos_url']            ?? '';
        $priv_url = $s['privacy_policy_url'] ?? '';
        $nonce    = wp_create_nonce( 'bcm_ltc_nonce' );
        $t        = $this->strings( $is_es );

        $this->render_overlay( $t, $tos_url, $priv_url, $nonce );
    }

    public function maybe_enqueue(): void {
        if ( ! $this->is_login_register_page() ) return;
        if ( ! $this->should_show() ) return;

        $s          = class_exists( 'BCM_Settings' ) ? BCM_Settings::get() : [];
        $is_es      = ( ( $s['admin_lang'] ?? 'es' ) === 'es' );
        $t          = $this->strings( $is_es );
        $nonce      = wp_create_nonce( 'bcm_ltc_nonce' );
        $categories = class_exists( 'BCM_Settings' ) ? array_keys( array_filter(
            $s['categories'] ?? [],
            fn( $c ) => ! empty( $c['enabled'] )
        ) ) : [];

        $this->enqueue_assets( $nonce, $categories, $s, $t );
    }

    /** Shortcode legacy: ahora es un no-op porque el overlay se inyecta via footer */
    public function shortcode_noop( array $atts = [] ): string {
        return ''; // El overlay ya está en wp_footer, no hace falta renderizar nada aquí
    }

    /* ═══════════════════════════════════════════════════════════
     *  AJAX — guardar aceptación
     * ═══════════════════════════════════════════════════════════ */

    public function ajax_accept(): void {
        if ( ! check_ajax_referer( 'bcm_ltc_nonce', 'nonce', false ) ) {
            wp_send_json_error( [ 'message' => 'Nonce inválido.' ], 403 );
            wp_die();
        }
        $tos_checked = sanitize_text_field( wp_unslash( $_POST['tos_checked'] ?? '' ) );
        if ( $tos_checked !== '1' ) {
            wp_send_json_error( [ 'message' => 'Debes aceptar los Términos y Condiciones.' ], 422 );
            wp_die();
        }
        if ( is_user_logged_in() ) {
            update_user_meta( get_current_user_id(), '_tc_accepted', '1' );
        }
        wp_send_json_success( [ 'ok' => true ] );
        wp_die();
    }

    /* ═══════════════════════════════════════════════════════════
     *  Parche al banner de cookies (logged-in)
     * ═══════════════════════════════════════════════════════════ */

    public function enqueue_banner_patch(): void {
        if ( ! class_exists( 'BCM_Settings' ) ) return;
        $s = BCM_Settings::get();
        if ( empty( $s['show_tos_checkbox'] ) ) return;
        $nonce = is_user_logged_in() ? wp_create_nonce( 'bcm_tc_nonce' ) : '';
        $is_es = ( ( $s['admin_lang'] ?? 'es' ) === 'es' );
        wp_register_script( 'bcm-banner-patch', false, [], BCM_VERSION, true );
        wp_enqueue_script( 'bcm-banner-patch' );
        wp_add_inline_script( 'bcm-banner-patch', $this->banner_patch_js(
            admin_url( 'admin-ajax.php' ), $nonce, $is_es, is_user_logged_in()
        ) );
    }

    private function banner_patch_js( string $ajax_url, string $nonce, bool $is_es, bool $logged_in ): string {
        $err_tos = $is_es ? 'Debes aceptar los T\u00e9rminos y Condiciones antes de continuar.' : 'You must accept the Terms & Conditions before continuing.';
        $err_gen = $is_es ? 'Error al procesar. Intenta de nuevo.' : 'Processing error. Please try again.';
        return '(function(){
"use strict";
var ajaxUrl='.json_encode($ajax_url).';
var nonce='.json_encode($nonce).';
var errTos='.json_encode($err_tos).';
var errGen='.json_encode($err_gen).';
var isLoggedIn='.($logged_in?'true':'false').';
document.addEventListener("DOMContentLoaded",function(){
    var bA=document.getElementById("bcm-btn-accept");
    var chk=document.getElementById("bcm-tos-check");
    var err=document.getElementById("bcm-tos-error");
    if(!bA||!chk)return;
    function showErr(m){if(!err)return;err.textContent="\u26a0 "+(m||errTos);err.style.display="block";err.classList.remove("bcm-shake");void err.offsetWidth;err.classList.add("bcm-shake");chk.focus();}
    function hideErr(){if(err)err.style.display="none";}
    chk.addEventListener("change",function(){if(chk.checked)hideErr();});
    bA.addEventListener("click",function(e){
        if(e._bcmV)return;
        if(!chk.checked){e.preventDefault();e.stopImmediatePropagation();showErr();return;}
        hideErr();
        if(!isLoggedIn||!nonce)return;
        e.preventDefault();e.stopImmediatePropagation();
        bA.disabled=true;
        var fd=new FormData();fd.append("action","bcm_ltc_accept");fd.append("nonce",nonce);fd.append("tos_checked","1");
        fetch(ajaxUrl,{method:"POST",body:fd})
            .then(function(r){return r.json();})
            .then(function(d){
                bA.disabled=false;
                if(d.success){var ev=new MouseEvent("click",{bubbles:true,cancelable:true});ev._bcmV=true;bA.dispatchEvent(ev);}
                else showErr(d.data&&d.data.message?d.data.message:errGen);
            }).catch(function(){bA.disabled=false;showErr(errGen);});
    },true);
});
})();';
    }

    /* ═══════════════════════════════════════════════════════════
     *  Strings
     * ═══════════════════════════════════════════════════════════ */

    private function strings( bool $is_es ): array {
        return $is_es ? [
            'title'       => 'Términos y Condiciones',
            'intro'       => 'Para continuar necesitás aceptar nuestros Términos y Condiciones y la Política de Privacidad.',
            'tos_link'    => 'Términos y Condiciones',
            'priv_link'   => 'Política de Privacidad',
            'check_label' => 'He leído y acepto los',
            'and'         => 'y la',
            'accept_btn'  => 'Aceptar y Continuar',
            'reject_btn'  => 'Rechazar',
            'loading'     => 'Procesando…',
            'check_error' => 'Debes marcar la casilla para aceptar.',
        ] : [
            'title'       => 'Terms & Conditions',
            'intro'       => 'To continue you must accept our Terms & Conditions and Privacy Policy.',
            'tos_link'    => 'Terms & Conditions',
            'priv_link'   => 'Privacy Policy',
            'check_label' => 'I have read and accept the',
            'and'         => 'and the',
            'accept_btn'  => 'Accept & Continue',
            'reject_btn'  => 'Decline',
            'loading'     => 'Processing…',
            'check_error' => 'You must check the box to accept.',
        ];
    }

    /* ═══════════════════════════════════════════════════════════
     *  HTML del overlay
     * ═══════════════════════════════════════════════════════════ */

    private function render_overlay( array $t, string $tos_url, string $priv_url, string $nonce ): void {
        ?>
        <div id="bcm-ltc-overlay" role="dialog" aria-modal="true" aria-label="<?php echo esc_attr( $t['title'] ); ?>">
            <div class="bcm-ltc-box">
                <div class="bcm-ltc-glow"></div>
                <div class="bcm-ltc-header">
                    <svg class="bcm-ltc-icon" viewBox="0 0 24 24" fill="none">
                        <path d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <h2 class="bcm-ltc-title"><?php echo esc_html( $t['title'] ); ?></h2>
                </div>
                <p class="bcm-ltc-intro"><?php echo esc_html( $t['intro'] ); ?></p>
                <?php if ( $tos_url || $priv_url ) : ?>
                <div class="bcm-ltc-links">
                    <?php if ( $tos_url ) : ?>
                    <a href="<?php echo esc_url( $tos_url ); ?>" target="_blank" rel="noopener noreferrer" class="bcm-ltc-link">
                        <svg viewBox="0 0 20 20" fill="currentColor"><path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z"/></svg>
                        <?php echo esc_html( $t['tos_link'] ); ?>
                    </a>
                    <?php endif; ?>
                    <?php if ( $priv_url ) : ?>
                    <a href="<?php echo esc_url( $priv_url ); ?>" target="_blank" rel="noopener noreferrer" class="bcm-ltc-link">
                        <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
                        <?php echo esc_html( $t['priv_link'] ); ?>
                    </a>
                    <?php endif; ?>
                </div>
                <?php endif; ?>
                <div class="bcm-ltc-checkbox-wrap">
                    <label class="bcm-ltc-check-label">
                        <input type="checkbox" id="bcm-ltc-check" class="bcm-ltc-check">
                        <span class="bcm-ltc-checkmark"></span>
                        <span class="bcm-ltc-check-text">
                            <?php echo esc_html( $t['check_label'] ); ?>
                            <?php if ( $tos_url ) : ?><a href="<?php echo esc_url( $tos_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( $t['tos_link'] ); ?></a><?php else : echo esc_html( $t['tos_link'] ); endif; ?>
                            <?php if ( $priv_url ) : ?>
                                <?php echo ' ' . esc_html( $t['and'] ) . ' '; ?>
                                <a href="<?php echo esc_url( $priv_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( $t['priv_link'] ); ?></a>
                            <?php endif; ?>
                        </span>
                    </label>
                    <span id="bcm-ltc-check-error" class="bcm-ltc-check-error" style="display:none;">⚠ <?php echo esc_html( $t['check_error'] ); ?></span>
                </div>
                <div class="bcm-ltc-actions">
                    <button id="bcm-ltc-accept" class="bcm-ltc-btn bcm-ltc-btn--accept"
                        data-nonce="<?php echo esc_attr( $nonce ); ?>"
                        data-loading="<?php echo esc_attr( $t['loading'] ); ?>">
                        <?php echo esc_html( $t['accept_btn'] ); ?>
                    </button>
                    <button id="bcm-ltc-reject" class="bcm-ltc-btn bcm-ltc-btn--reject">
                        <?php echo esc_html( $t['reject_btn'] ); ?>
                    </button>
                </div>
                <div id="bcm-ltc-msg" class="bcm-ltc-msg" style="display:none;"></div>
            </div>
        </div>
        <?php
    }

    /* ═══════════════════════════════════════════════════════════
     *  Assets
     * ═══════════════════════════════════════════════════════════ */

    private function enqueue_assets( string $nonce, array $categories, array $s, array $t ): void {
        static $done = false;
        if ( $done ) return;
        $done = true;

        wp_register_style( 'bcm-ltc', false );
        wp_enqueue_style( 'bcm-ltc' );
        wp_add_inline_style( 'bcm-ltc', $this->css() );

        wp_register_script( 'bcm-ltc', false, [], BCM_VERSION, true );
        wp_enqueue_script( 'bcm-ltc' );

        $config = [
            'ajaxUrl'      => admin_url( 'admin-ajax.php' ),
            'nonce'        => $nonce,
            'homeUrl'      => home_url( '/' ),
            'cookieName'   => 'bcm_consent',
            'ltcCookie'    => self::COOKIE,
            'expiry'       => (int) ( $s['consent_expiry'] ?? 365 ),
            'categories'   => $categories,
            'consentNonce' => wp_create_nonce( 'bcm_consent' ),
            'isLoggedIn'   => is_user_logged_in(),
        ];
        wp_add_inline_script( 'bcm-ltc', 'var bcmLtcCfg=' . wp_json_encode( $config ) . ';', 'before' );
        wp_add_inline_script( 'bcm-ltc', $this->js() );
    }

    /* ═══════════════════════════════════════════════════════════
     *  CSS
     * ═══════════════════════════════════════════════════════════ */

    private function css(): string {
        return '
@import url("https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Inter:wght@300;400;500&display=swap");
#bcm-ltc-overlay{
    position:fixed;inset:0;
    background:rgba(0,0,0,.85);
    backdrop-filter:blur(6px);
    -webkit-backdrop-filter:blur(6px);
    z-index:2147483647;
    display:flex;align-items:center;justify-content:center;
    padding:16px;
    animation:bcm-ltc-fadein .3s ease;
}
@keyframes bcm-ltc-fadein{from{opacity:0;}to{opacity:1;}}
#bcm-ltc-overlay.bcm-ltc-hiding{
    animation:bcm-ltc-fadeout .35s ease forwards;
    pointer-events:none;
}
@keyframes bcm-ltc-fadeout{from{opacity:1;}to{opacity:0;}}
.bcm-ltc-box{
    position:relative;width:100%;max-width:480px;
    padding:36px 32px 28px;
    background:#1a1c24;
    border:1px solid rgba(255,255,255,.07);
    border-radius:14px;
    font-family:"Inter",sans-serif;color:#d4d8e0;
    overflow:hidden;
    box-shadow:0 4px 6px rgba(0,0,0,.4),0 20px 60px rgba(0,0,0,.7),inset 0 1px 0 rgba(255,255,255,.05);
    animation:bcm-ltc-slidein .3s ease;
}
@keyframes bcm-ltc-slidein{from{transform:translateY(-20px);opacity:0;}to{transform:translateY(0);opacity:1;}}
.bcm-ltc-glow{position:absolute;top:-60px;right:-60px;width:200px;height:200px;background:radial-gradient(circle,rgba(46,213,115,.15) 0%,transparent 70%);pointer-events:none;border-radius:50%;}
.bcm-ltc-box::before{content:"";display:block;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.08),transparent);margin-bottom:20px;}
.bcm-ltc-header{display:flex;align-items:center;gap:12px;margin-bottom:20px;}
.bcm-ltc-icon{width:28px;height:28px;color:#2ed573;flex-shrink:0;}
.bcm-ltc-title{margin:0;font-family:"Rajdhani",sans-serif;font-size:1.6rem;font-weight:700;letter-spacing:.03em;color:#fff;text-transform:uppercase;}
.bcm-ltc-intro{font-size:.88rem;line-height:1.6;color:#9aa0b0;margin:0 0 20px;}
.bcm-ltc-links{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:22px;}
.bcm-ltc-link{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:rgba(255,255,255,.04);color:#8ab4f8;font-size:.82rem;font-weight:500;text-decoration:none;transition:background .2s,border-color .2s;}
.bcm-ltc-link svg{width:14px;height:14px;opacity:.8;}
.bcm-ltc-link:hover{background:rgba(138,180,248,.1);border-color:rgba(138,180,248,.4);color:#adc8ff;text-decoration:none;}
.bcm-ltc-checkbox-wrap{margin-bottom:24px;}
.bcm-ltc-check-label{display:flex;align-items:flex-start;gap:12px;cursor:pointer;user-select:none;}
.bcm-ltc-check{position:absolute;opacity:0;width:0;height:0;}
.bcm-ltc-checkmark{flex-shrink:0;width:18px;height:18px;margin-top:2px;background:rgba(255,255,255,.06);border:1.5px solid rgba(255,255,255,.2);border-radius:4px;display:flex;align-items:center;justify-content:center;transition:background .2s,border-color .2s;position:relative;}
.bcm-ltc-checkmark::after{content:"";width:10px;height:6px;border-left:2px solid #fff;border-bottom:2px solid #fff;transform:rotate(-45deg) translateY(-1px);opacity:0;transition:opacity .15s;}
.bcm-ltc-check:checked~.bcm-ltc-checkmark{background:#2ed573;border-color:#2ed573;}
.bcm-ltc-check:checked~.bcm-ltc-checkmark::after{opacity:1;}
.bcm-ltc-check:focus~.bcm-ltc-checkmark{outline:2px solid rgba(46,213,115,.5);outline-offset:2px;}
.bcm-ltc-check-text{font-size:.85rem;line-height:1.5;color:#9aa0b0;}
.bcm-ltc-check-text a{color:#8ab4f8;text-decoration:none;}
.bcm-ltc-check-text a:hover{color:#adc8ff;text-decoration:underline;}
.bcm-ltc-check-error{display:block;margin-top:8px;padding:6px 10px;background:rgba(255,68,68,.1);border:1px solid rgba(255,68,68,.25);border-radius:5px;font-size:.8rem;color:#ff6b6b;}
.bcm-ltc-actions{display:flex;flex-direction:column;gap:10px;}
.bcm-ltc-btn{width:100%;padding:13px 20px;border:none;border-radius:8px;font-family:"Rajdhani",sans-serif;font-size:1rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;cursor:pointer;transition:opacity .2s,transform .15s,box-shadow .2s;}
.bcm-ltc-btn:disabled{opacity:.55;cursor:not-allowed;transform:none!important;}
.bcm-ltc-btn--accept{background:linear-gradient(135deg,#2ed573 0%,#17c058 100%);color:#0d1117;box-shadow:0 4px 15px rgba(46,213,115,.25);}
.bcm-ltc-btn--accept:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 20px rgba(46,213,115,.4);}
.bcm-ltc-btn--reject{background:transparent;border:1px solid rgba(255,255,255,.1);color:#666d7a;font-size:.85rem;}
.bcm-ltc-btn--reject:hover:not(:disabled){background:rgba(255,68,68,.08);border-color:rgba(255,68,68,.25);color:#ff6b6b;}
.bcm-ltc-msg{margin-top:14px;padding:10px 14px;background:rgba(255,68,68,.1);border:1px solid rgba(255,68,68,.25);border-radius:6px;font-size:.83rem;color:#ff6b6b;}
.bcm-ltc-msg--ok{background:rgba(46,213,115,.08);border-color:rgba(46,213,115,.2);color:#2ed573;}
@media(max-width:500px){.bcm-ltc-box{padding:24px 18px 20px;}.bcm-ltc-title{font-size:1.3rem;}}
';
    }

    /* ═══════════════════════════════════════════════════════════
     *  JavaScript
     * ═══════════════════════════════════════════════════════════ */

    private function js(): string {
        return '
(function(){
"use strict";
var cfg     = window.bcmLtcCfg || {};
var overlay = document.getElementById("bcm-ltc-overlay");
var bA      = document.getElementById("bcm-ltc-accept");
var bR      = document.getElementById("bcm-ltc-reject");
var chk     = document.getElementById("bcm-ltc-check");
var chkErr  = document.getElementById("bcm-ltc-check-error");
var msg     = document.getElementById("bcm-ltc-msg");
if (!overlay || !bA) return;

function setCookie(name, value, days) {
    var d = new Date();
    if (days) d.setTime(d.getTime() + days * 864e5);
    var exp    = days ? ";expires=" + d.toUTCString() : "";
    var secure = (location.protocol === "https:") ? ";Secure" : "";
    document.cookie = name + "=" + encodeURIComponent(value) + exp + ";path=/;SameSite=Lax" + secure;
}
function genId() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c){
        var r = Math.random()*16|0; return (c==="x"?r:(r&0x3|0x8)).toString(16);
    });
}
function saveConsentCookie() {
    if (!cfg.cookieName) return;
    var id   = genId();
    var cats = cfg.categories || [];
    var data = {consent_id:id,status:"accepted",categories:cats,regulation:"GDPR"};
    setCookie(cfg.cookieName, JSON.stringify(data), cfg.expiry || 365);
    if (cfg.consentNonce && cfg.ajaxUrl) {
        var fd = new FormData();
        fd.append("action","bcm_record_consent"); fd.append("nonce",cfg.consentNonce);
        fd.append("consent_id",id); fd.append("status","accepted");
        fd.append("categories",JSON.stringify(cats)); fd.append("regulation","GDPR");
        fetch(cfg.ajaxUrl,{method:"POST",body:fd});
    }
}
function hideAndReload() {
    overlay.classList.add("bcm-ltc-hiding");
    setTimeout(function(){ window.location.reload(); }, 380);
}
function showMsg(text, ok) {
    if (!msg) return;
    msg.textContent = text;
    msg.style.display = "block";
    msg.className = "bcm-ltc-msg" + (ok ? " bcm-ltc-msg--ok" : "");
}
function setLoading(btn, on) {
    if (on) { btn.disabled=true; btn._o=btn.textContent; btn.textContent=btn.dataset.loading||"..."; }
    else     { btn.disabled=false; if(btn._o) btn.textContent=btn._o; }
}
if (chk) chk.addEventListener("change", function(){
    if (chk.checked && chkErr) chkErr.style.display = "none";
});
bA.addEventListener("click", function(){
    if (msg) msg.style.display = "none";
    if (chk && !chk.checked) {
        if (chkErr) chkErr.style.display = "block";
        chk.focus(); return;
    }
    setLoading(bA, true); if (bR) bR.disabled = true;
    var fd = new FormData();
    fd.append("action","bcm_ltc_accept");
    fd.append("nonce", bA.dataset.nonce);
    fd.append("tos_checked","1");
    fetch(cfg.ajaxUrl,{method:"POST",body:fd})
        .then(function(r){return r.json();})
        .then(function(d){
            setLoading(bA,false); if(bR) bR.disabled=false;
            if (d.success) {
                if (!cfg.isLoggedIn) {
                    setCookie(cfg.ltcCookie, "1", null); /* sesión */
                }
                saveConsentCookie();
                var banner = document.getElementById("bcm-banner");
                if (banner) banner.style.display = "none";
                hideAndReload();
            } else {
                showMsg((d.data&&d.data.message)||"Error al procesar.");
            }
        })
        .catch(function(){ setLoading(bA,false); if(bR) bR.disabled=false; showMsg("Error de conexión."); });
});
if (bR) bR.addEventListener("click", function(){
    window.location.href = cfg.homeUrl || "/";
});
})();
';
    }
}
