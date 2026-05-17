<?php if ( ! defined( 'ABSPATH' ) ) exit;
$s    = BCM_Settings::get();
$lang = $s['admin_lang'] ?? 'es';
$isES = ( $lang === 'es' );

/* ── Helper: get all pages for the TC page selector ── */
$pages_list = get_pages( [ 'post_status' => 'publish', 'sort_column' => 'post_title' ] );
?>
<div class="bcm-wrap">
    <div class="bcm-header">
        <h1>🎨 <?php echo esc_html( $isES ? 'Banner de cookies' : 'Cookie Banner' ); ?></h1>
        <button id="bcm-save-banner" class="bcm-btn bcm-btn-primary">
            <?php echo esc_html( $isES ? 'Publicar cambios' : 'Publish Changes' ); ?>
        </button>
    </div>

    <div class="bcm-two-col">
        <!-- Settings panel -->
        <div class="bcm-card">

            <!-- SECCIÓN 1: Banner de cookies -->
            <h3><?php echo esc_html( $isES ? 'Configuración del banner' : 'Banner Settings' ); ?></h3>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Activar banner' : 'Enable Banner' ); ?></label>
                <label class="bcm-toggle">
                    <input type="checkbox" id="banner_enabled" <?php checked( $s['banner_enabled'] ); ?>>
                    <span class="bcm-slider"></span>
                </label>
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Posición' : 'Position' ); ?></label>
                <select id="banner_position">
                    <?php
                    $positions = $isES
                        ? [ 'bottom' => 'Abajo', 'top' => 'Arriba', 'popup' => 'Popup centrado' ]
                        : [ 'bottom' => 'Bottom', 'top' => 'Top', 'popup' => 'Popup Center' ];
                    foreach ( $positions as $v => $l ) : ?>
                    <option value="<?php echo esc_attr( $v ); ?>" <?php selected( $s['banner_position'], $v ); ?>><?php echo esc_html( $l ); ?></option>
                    <?php endforeach; ?>
                </select>
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Título' : 'Title' ); ?></label>
                <input type="text" id="banner_title" value="<?php echo esc_attr( $s['banner_title'] ); ?>">
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Descripción' : 'Description' ); ?></label>
                <textarea id="banner_description" rows="4"><?php echo esc_textarea( $s['banner_description'] ); ?></textarea>
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Texto botón Aceptar' : 'Accept Button Text' ); ?></label>
                <input type="text" id="accept_btn_text" value="<?php echo esc_attr( $s['accept_btn_text'] ); ?>">
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Texto botón Rechazar' : 'Reject Button Text' ); ?></label>
                <input type="text" id="reject_btn_text" value="<?php echo esc_attr( $s['reject_btn_text'] ); ?>">
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Texto botón Personalizar' : 'Customize Button Text' ); ?></label>
                <input type="text" id="customize_btn_text" value="<?php echo esc_attr( $s['customize_btn_text'] ); ?>">
            </div>

            <hr>
            <h4><?php echo esc_html( $isES ? 'Colores' : 'Colors' ); ?></h4>

            <?php
            $colors = $isES ? [
                'primary_color'   => 'Color primario',
                'bg_color'        => 'Color de fondo',
                'text_color'      => 'Color de texto',
                'btn_accept_bg'   => 'Fondo botón Aceptar',
                'btn_reject_bg'   => 'Fondo botón Rechazar',
                'btn_reject_text' => 'Texto botón Rechazar',
            ] : [
                'primary_color'   => 'Primary Color',
                'bg_color'        => 'Background Color',
                'text_color'      => 'Text Color',
                'btn_accept_bg'   => 'Accept Button BG',
                'btn_reject_bg'   => 'Reject Button BG',
                'btn_reject_text' => 'Reject Button Text',
            ];
            foreach ( $colors as $id => $label ) : ?>
            <div class="bcm-field bcm-field-color">
                <label><?php echo esc_html( $label ); ?></label>
                <input type="text" class="bcm-color-picker" id="<?php echo esc_attr( $id ); ?>" value="<?php echo esc_attr( $s[ $id ] ); ?>">
            </div>
            <?php endforeach; ?>

            <!-- SECCIÓN 2: Términos y Condiciones en el banner -->
            <hr>
            <h3 style="margin-top:8px;">📋 <?php echo esc_html( $isES ? 'Términos y Condiciones en el banner' : 'Terms & Conditions in Banner' ); ?></h3>
            <p class="bcm-hint">
                <?php echo esc_html( $isES
                    ? 'Muestra un checkbox de aceptación de T&C dentro del banner de cookies. El usuario debe marcarlo antes de poder aceptar las cookies.'
                    : 'Show a T&C acceptance checkbox inside the cookie banner. The user must check it before accepting cookies.' ); ?>
            </p>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Mostrar checkbox de T&C en el banner' : 'Show T&C checkbox in banner' ); ?></label>
                <label class="bcm-toggle">
                    <input type="checkbox" id="show_tos_checkbox" <?php checked( ! empty( $s['show_tos_checkbox'] ) ); ?>>
                    <span class="bcm-slider"></span>
                </label>
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'URL de los Términos y Condiciones' : 'Terms & Conditions URL' ); ?></label>
                <input type="url" id="tos_url" value="<?php echo esc_attr( $s['tos_url'] ?? '' ); ?>"
                       placeholder="https://tusitio.com/terminos">
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'URL de la Política de Privacidad' : 'Privacy Policy URL' ); ?></label>
                <input type="url" id="privacy_policy_url" value="<?php echo esc_attr( $s['privacy_policy_url'] ?? '' ); ?>"
                       placeholder="https://tusitio.com/privacidad">
            </div>

            <!-- SECCIÓN 3: Enforcement de T&C -->
            <hr>
            <h3 style="margin-top:8px;">🔒 <?php echo esc_html( $isES ? 'Enforcement de T&C (cierre de sesión)' : 'T&C Enforcement (session control)' ); ?></h3>
            <p class="bcm-hint">
                <?php echo esc_html( $isES
                    ? 'Cuando está activo, los usuarios registrados que no hayan aceptado los T&C son redirigidos a la página de aceptación. Si rechazan, se cierra su sesión.'
                    : 'When enabled, registered users who have not accepted T&C are redirected to the acceptance page. If they reject, their session is closed.' ); ?>
            </p>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Activar enforcement de T&C' : 'Enable T&C Enforcement' ); ?></label>
                <label class="bcm-toggle">
                    <input type="checkbox" id="tc_enforcement_enabled" <?php checked( ! empty( $s['tc_enforcement_enabled'] ) ); ?>>
                    <span class="bcm-slider"></span>
                </label>
            </div>

            <div class="bcm-field" style="align-items:flex-start;">
                <label style="padding-top:6px;"><?php echo esc_html( $isES ? 'Página de aceptación de T&C' : 'T&C Acceptance Page' ); ?></label>
                <div style="display:flex;flex-direction:column;gap:4px;flex:1;">
                    <select id="tc_acceptance_page_id" style="width:100%;">
                        <option value="0"><?php echo esc_html( $isES ? '— Seleccionar página —' : '— Select page —' ); ?></option>
                        <?php foreach ( $pages_list as $page ) : ?>
                        <option value="<?php echo esc_attr( $page->ID ); ?>"
                            <?php selected( (int) ( $s['tc_acceptance_page_id'] ?? 0 ), $page->ID ); ?>>
                            <?php echo esc_html( $page->post_title ); ?>
                        </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if ( ! empty( $s['tc_acceptance_page_id'] ) ) : ?>
                    <a href="<?php echo esc_url( get_permalink( (int) $s['tc_acceptance_page_id'] ) ); ?>"
                       target="_blank" rel="noopener" style="font-size:12px;">
                        <?php echo esc_html( $isES ? 'Ver página ↗' : 'View page ↗' ); ?>
                    </a>
                    <?php endif; ?>
                </div>
            </div>

            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Auto-purgar cuentas rechazadas (30 días)' : 'Auto-purge rejected accounts (30 days)' ); ?></label>
                <label class="bcm-toggle">
                    <input type="checkbox" id="tc_purge_rejected" <?php checked( ! empty( $s['tc_purge_rejected'] ) ); ?>>
                    <span class="bcm-slider"></span>
                </label>
            </div>

            <div style="background:rgba(0,0,0,0.04);border-left:3px solid #0066FF;padding:12px 14px;border-radius:0 6px 6px 0;margin-top:12px;font-size:13px;line-height:1.8;">
                <strong><?php echo esc_html( $isES ? 'Shortcodes disponibles:' : 'Available shortcodes:' ); ?></strong><br>
                <code>[bcm_tc_acceptance]</code> — <?php echo esc_html( $isES ? 'Formulario estándar de aceptación/rechazo.' : 'Standard accept/reject form.' ); ?><br>
                <span style="display:block;font-size:11px;color:#555;margin:2px 0 8px 8px;">
                    <?php echo esc_html( $isES
                        ? '⚠ Solo visible para usuarios con sesión iniciada. Los visitantes anónimos ven un aviso de "inicia sesión". Puede colocarse en la misma página que el texto de T&C.'
                        : '⚠ Only visible to logged-in users. Anonymous visitors see a "please log in" notice. Can be placed on the same page as your T&C text.' ); ?>
                </span>
                <code>[bcm_login_tc]</code> — <?php echo esc_html( $isES ? 'Formulario con estética dark/gaming para usuarios registrados.' : 'Dark/gaming styled form for logged-in users.' ); ?><br>
                <span style="display:block;font-size:11px;color:#555;margin:2px 0 0 8px;">
                    <?php echo esc_html( $isES
                        ? '⚠ También requiere sesión iniciada. Los visitantes anónimos ven un mensaje de aviso.'
                        : '⚠ Also requires login. Anonymous visitors see a notice message.' ); ?>
                </span>
            </div>

        </div><!-- /.bcm-card -->

        <!-- Live Preview -->
        <div>
            <div class="bcm-card">
                <h3><?php echo esc_html( $isES ? 'Vista previa en tiempo real' : 'Live Preview' ); ?></h3>
                <p class="bcm-hint"><?php echo esc_html( $isES ? 'Se actualiza mientras escribes.' : 'Updates as you type.' ); ?></p>
            </div>
            <div id="bcm-preview-wrapper">
                <div id="bcm-preview-banner" class="bcm-preview-banner">
                    <strong id="preview-title"></strong>
                    <p id="preview-desc"></p>
                    <div id="preview-tos-row" style="display:none;padding:6px 0;margin:4px 0;border-top:1px solid rgba(255,255,255,0.15);">
                        <label style="display:flex;align-items:center;gap:6px;font-size:11px;opacity:.85;cursor:default;">
                            <input type="checkbox" disabled style="margin:0;">
                            <span><?php echo esc_html( $isES ? 'Acepto los Términos y Condiciones' : 'I accept the Terms & Conditions' ); ?></span>
                        </label>
                    </div>
                    <div class="bcm-preview-btns">
                        <button id="preview-customize" class="bcm-preview-btn bcm-btn-outline-sm"></button>
                        <button id="preview-reject"    class="bcm-preview-btn bcm-btn-reject-sm"></button>
                        <button id="preview-accept"    class="bcm-preview-btn bcm-btn-accept-sm"></button>
                    </div>
                </div>
            </div>

            <div id="bcm-preview-enforcement" style="display:none;margin-top:12px;">
                <div class="bcm-card" style="border-left:3px solid #ff6b35;padding:12px 16px;">
                    <p style="margin:0;font-size:13px;line-height:1.6;">
                        🔒 <strong><?php echo esc_html( $isES ? 'Enforcement activo' : 'Enforcement active' ); ?></strong><br>
                        <span style="opacity:.7;font-size:12px;">
                            <?php echo esc_html( $isES
                                ? 'Los usuarios sin T&C aceptado serán redirigidos a la página de aceptación al iniciar sesión.'
                                : 'Users without T&C accepted will be redirected to the acceptance page on login.' ); ?>
                        </span>
                    </p>
                </div>
            </div>
        </div>
    </div>
</div>
