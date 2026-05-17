<?php if ( ! defined( 'ABSPATH' ) ) exit;
$s    = BCM_Settings::get();
$lang = $s['admin_lang'] ?? 'es';
$isES = ( $lang === 'es' );
?>
<div class="bcm-wrap">
    <div class="bcm-header">
        <h1>⚙️ <?php echo esc_html( $isES ? 'Configuración' : 'Settings' ); ?></h1>
        <button id="bcm-save-settings" class="bcm-btn bcm-btn-primary">
            <?php echo esc_html( $isES ? 'Guardar configuración' : 'Save Settings' ); ?>
        </button>
    </div>

    <!-- ══════════════════════════════════════════
         v1.6.0 — LANGUAGE / IDIOMA
    ══════════════════════════════════════════ -->
    <div class="bcm-card" style="border-left:4px solid #e91e8c;">
        <h3>🌐 <?php echo esc_html( $isES ? 'Idioma del panel y del banner' : 'Panel & Banner Language' ); ?> <span class="bcm-badge-new">v1.6.0</span></h3>
        <p class="bcm-hint">
            <?php echo esc_html( $isES
                ? 'Selecciona el idioma de la interfaz de administración y del banner de cookies. Al cambiar el idioma se actualizan automáticamente los textos del banner si aún no los has personalizado.'
                : 'Select the language for the admin interface and the cookie banner. Changing language auto-updates banner text if you have not customised it yet.' ); ?>
        </p>
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Idioma' : 'Language' ); ?></label>
            <select id="admin_lang" onchange="this.form && this.form.submit()">
                <option value="es" <?php selected( $lang, 'es' ); ?>>🇪🇸 Español</option>
                <option value="en" <?php selected( $lang, 'en' ); ?>>🇬🇧 English</option>
            </select>
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'El cambio se aplica al guardar la configuración.'
                    : 'Change takes effect when you save settings.' ); ?>
            </span>
        </div>
    </div>

    <!-- ══════════════════════════════════════════
         v1.5.0 — LEGAL COMPLIANCE
    ══════════════════════════════════════════ -->
    <div class="bcm-card" style="border-left:4px solid #10b981;">
        <h3>🛡️ <?php echo esc_html( $isES ? 'Cumplimiento legal' : 'Legal Compliance' ); ?> <span class="bcm-badge-new">v1.5.0</span></h3>
        <p class="bcm-hint">
            <?php echo esc_html( $isES
                ? 'Ajustes requeridos por el GDPR Art. 13 (transparencia) y Art. 5.1.e (minimización de datos).'
                : 'Settings required to meet GDPR Art. 13 (transparency) and Art. 5.1.e (data minimisation) obligations.' ); ?>
        </p>

        <!-- Privacy Policy URL -->
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'URL — Política de Privacidad' : 'Privacy Policy URL' ); ?></label>
            <input type="url" id="privacy_policy_url"
                   value="<?php echo esc_attr( $s['privacy_policy_url'] ?? '' ); ?>"
                   placeholder="https://yoursite.com/privacy-policy"
                   style="width:340px">
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'Se muestra como enlace en el banner. Obligatorio bajo GDPR Art. 13 para informar quién trata los datos y con qué finalidad.'
                    : 'Shown as a link in the consent banner. Required by GDPR Art. 13 to inform users who processes their data and for what purpose.' ); ?>
            </span>
        </div>

        <!-- IP Anonymise -->
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Anonimizar IP del visitante en el registro' : 'Anonymise visitor IP in consent log' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="ip_anonymize" <?php checked( $s['ip_anonymize'] ?? true ); ?>>
                <span class="bcm-slider"></span>
            </label>
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'Reemplaza el último octeto de IPv4 (o los últimos 64 bits de IPv6) antes de guardarlo (ej. 192.168.1.xxx). Recomendado por GDPR Art. 5.1.e. Nota: puede dificultar solicitudes de borrado individuales (Art. 17) por IP.'
                    : 'When enabled, the last octet of IPv4 (or last 64 bits of IPv6) is replaced before storage (e.g. 192.168.1.xxx). Recommended under GDPR Art. 5.1.e. Note: enabling this may reduce your ability to honour individual erasure requests (Art. 17) by IP.' ); ?>
            </span>
        </div>


        <!-- FIX v2.0.5 — IP Hash (SHA-256) -->
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Hashear IP con SHA-256 (seudonimización fuerte)' : 'Hash IP with SHA-256 (strong pseudonymisation)' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="ip_hash" <?php checked( $s['ip_hash'] ?? false ); ?>>
                <span class="bcm-slider"></span>
            </label>
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'Aplica hash SHA-256 + salt a la IP antes de guardarla. El resultado es irreversible (ej. "3a7bd3e2…"). Más protector que la anonimización parcial; cumple GDPR Art. 5.1.e y recomendaciones ENISA 2019 sobre seudonimización. Las solicitudes de borrado por IP (Art. 17) siguen funcionando. Tiene precedencia sobre "Anonimizar IP" si ambas están activas.'
                    : 'Applies SHA-256 + salt hash to the IP before storing it. The result is irreversible (e.g. "3a7bd3e2…"). Stronger protection than partial anonymisation; complies with GDPR Art. 5.1.e and ENISA 2019 pseudonymisation guidelines. Erasure requests by IP (Art. 17) still work correctly. Takes precedence over "Anonymise IP" if both are enabled.' ); ?>
            </span>
        </div>

        <!-- T&C Checkbox -->
        <div class="bcm-field" style="border-top:1px solid #eee;padding-top:14px;margin-top:6px;">
            <label><?php echo esc_html( $isES ? 'Mostrar checkbox de aceptación de T&amp;C' : 'Show T&amp;C acceptance checkbox' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="show_tos_checkbox" <?php checked( $s['show_tos_checkbox'] ?? true ); ?>>
                <span class="bcm-slider"></span>
            </label>
            <span class="bcm-hint-inline">
                <?php echo wp_kses(
                    $isES
                        ? '⚠️ <strong>Requerido si tu sitio tiene compras, registro de usuarios o suscripciones.</strong> Agrega un checkbox obligatorio: "Acepto los Términos y Condiciones y la Política de Privacidad". El botón Aceptar queda bloqueado hasta que el usuario lo marca.'
                        : '⚠️ <strong>Required if your site has purchases, user registration, or subscriptions.</strong> Adds a required checkbox: "I accept the Terms and Conditions and the Privacy Policy". The Accept button is blocked until the user checks it.',
                    [ 'strong' => [] ]
                ); ?>
            </span>
        </div>

        <!-- T&C URL (visible only when checkbox is on) -->
        <div class="bcm-field" id="field-tos-url">
            <label><?php echo esc_html( $isES ? 'URL — Términos y Condiciones' : 'Terms and Conditions URL' ); ?></label>
            <input type="url" id="tos_url"
                   value="<?php echo esc_attr( $s['tos_url'] ?? '' ); ?>"
                   placeholder="https://yoursite.com/terms-and-conditions"
                   style="width:340px">
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'El texto "Términos y Condiciones" en el checkbox enlazará aquí. Déjalo vacío para mostrar el texto sin enlace.'
                    : 'The "Terms and Conditions" text in the checkbox will link here. Leave empty to show the text without a link.' ); ?>
            </span>
        </div>

        <!-- Withdrawal button -->
        <div class="bcm-field" style="border-top:1px solid #eee;padding-top:14px;margin-top:6px;">
            <label><?php echo esc_html( $isES ? 'Botón flotante para retirar consentimiento' : 'Floating consent withdrawal button' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="withdrawal_enabled" <?php checked( $s['withdrawal_enabled'] ?? true ); ?>>
                <span class="bcm-slider"></span>
            </label>
            <span class="bcm-hint-inline">
                <?php echo wp_kses(
                    $isES
                        ? 'Muestra el botón 🍪 en la esquina de la página para que los usuarios puedan cambiar sus preferencias en cualquier momento. <strong>Obligatorio bajo GDPR Art. 7(3)</strong>: retirar el consentimiento debe ser tan fácil como darlo.'
                        : 'Shows the 🍪 button in the page corner so users can change their preferences at any time. <strong>Required under GDPR Art. 7(3)</strong>: withdrawing consent must be as easy as giving it.',
                    [ 'strong' => [] ]
                ); ?>
            </span>
        </div>

        <!-- CCPA notice -->
        <div class="bcm-field" style="background:#fff8e1;border-left:3px solid #f59e0b;padding:10px 14px;border-radius:4px;margin-top:8px;">
            <strong>⚠️ <?php echo esc_html( $isES ? 'Nota sobre el alcance de CCPA' : 'CCPA scope notice' ); ?></strong>
            <p style="margin:.4em 0 0;font-size:.85em;color:#555;">
                <?php echo esc_html( $isES
                    ? 'La geo-detección aplica las reglas CCPA a todos los visitantes desde EE.UU. La CCPA aplica legalmente solo a residentes de California Y a empresas con más de $25M de ingresos anuales, o que procesen datos de 100.000+ consumidores, o que obtengan el 50%+ de sus ingresos vendiendo datos. Si tu sitio no alcanza estos umbrales, puedes desactivar la geo-detección y usar una regulación manual.'
                    : 'Geo-detection applies CCPA rules to all visitors from the United States. The CCPA legally applies only to California residents AND to businesses exceeding $25M annual revenue, or that process data from 100,000+ consumers, or derive 50%+ of revenue from selling data. If your site does not meet these thresholds, you may disable geo-detection and set a manual regulation.' ); ?>
            </p>
        </div>
    </div>

    <!-- ══════════════════════════════════════════
         GENERAL
    ══════════════════════════════════════════ -->
    <div class="bcm-card">
        <h3><?php echo esc_html( $isES ? 'General' : 'General' ); ?></h3>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Caducidad del consentimiento (días)' : 'Consent Expiry (days)' ); ?></label>
            <input type="number" id="consent_expiry" value="<?php echo esc_attr( $s['consent_expiry'] ); ?>" min="1" max="3650">
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'GDPR recomienda no superar los 12 meses (365 días). Tras ese período el usuario deberá consentir de nuevo.'
                    : 'GDPR recommends not exceeding 12 months (365 days). After that period the user will need to consent again.' ); ?>
            </span>
        </div>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Bloquear scripts hasta consentimiento' : 'Auto-block scripts until consent' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="auto_block" <?php checked( $s['auto_block'] ); ?>>
                <span class="bcm-slider"></span>
            </label>
        </div>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Activar Google Consent Mode (GCM)' : 'Enable Google Consent Mode (GCM)' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="gcm_enabled" <?php checked( $s['gcm_enabled'] ); ?>>
                <span class="bcm-slider"></span>
            </label>
            <span class="bcm-hint-inline">
                <?php echo esc_html( $isES
                    ? 'Recomendado si usas Google Analytics 4 o Google Ads. Permite que las etiquetas de Google respeten el consentimiento automáticamente.'
                    : 'Recommended if you use Google Analytics 4 or Google Ads. Lets Google tags honour consent automatically.' ); ?>
            </span>
        </div>
    </div>

    <!-- ══════════════════════════════════════════
         GEO-DETECTION
    ══════════════════════════════════════════ -->
    <div class="bcm-card">
        <h3>🌍 <?php echo esc_html( $isES ? 'Regulación y geo-detección' : 'Regulation & Geo-detection' ); ?> <span class="bcm-badge-new">v1.4.0</span></h3>
        <p class="bcm-hint">
            <?php echo esc_html( $isES
                ? 'Aplica automáticamente la regulación correcta (GDPR, CCPA, LGPD) según el país del visitante. Usa cabeceras Cloudflare si están disponibles, de lo contrario ip-api.com.'
                : 'Automatically applies the correct regulation (GDPR, CCPA, LGPD) based on the visitor\'s country. Uses Cloudflare headers if available, otherwise ip-api.com.' ); ?>
        </p>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Activar geo-detección automática' : 'Enable automatic geo-detection' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="geo_detection" <?php checked( $s['geo_detection'] ?? true ); ?>>
                <span class="bcm-slider"></span>
            </label>
        </div>

        <div class="bcm-field" id="field-geo-fallback">
            <label><?php echo esc_html( $isES ? 'Regulación de respaldo (país no detectado)' : 'Fallback regulation (when country is undetected)' ); ?></label>
            <select id="geo_fallback">
                <option value="GDPR" <?php selected( $s['geo_fallback'] ?? 'GDPR', 'GDPR' ); ?>>GDPR (opt-in)</option>
                <option value="CCPA" <?php selected( $s['geo_fallback'] ?? 'GDPR', 'CCPA' ); ?>>CCPA (opt-out)</option>
                <option value="LGPD" <?php selected( $s['geo_fallback'] ?? 'GDPR', 'LGPD' ); ?>>LGPD (opt-in)</option>
                <option value="NONE" <?php selected( $s['geo_fallback'] ?? 'GDPR', 'NONE' ); ?>><?php echo esc_html( $isES ? 'Ninguno (mostrar siempre)' : 'None (always show banner)' ); ?></option>
            </select>
        </div>

        <div class="bcm-field" id="field-regulation-manual">
            <label><?php echo esc_html( $isES ? 'Regulación manual (geo-detección desactivada)' : 'Manual regulation (geo-detection disabled)' ); ?></label>
            <select id="regulation">
                <option value="GDPR" <?php selected( $s['regulation'] ?? 'GDPR', 'GDPR' ); ?>>GDPR</option>
                <option value="CCPA" <?php selected( $s['regulation'] ?? 'GDPR', 'CCPA' ); ?>>CCPA</option>
                <option value="LGPD" <?php selected( $s['regulation'] ?? 'GDPR', 'LGPD' ); ?>>LGPD</option>
            </select>
        </div>
    </div>

    <!-- ══════════════════════════════════════════
         HEADLESS SCANNER
    ══════════════════════════════════════════ -->
    <div class="bcm-card">
        <h3>🤖 <?php echo esc_html( $isES ? 'Escáner headless' : 'Headless scanner' ); ?> <span class="bcm-badge-new">v1.4.0</span></h3>
        <p class="bcm-hint">
            <?php echo esc_html( $isES
                ? 'Se conecta a una instancia de Browserless.io para ejecutar JavaScript y detectar cookies en tiempo de ejecución. Sin token, el escáner usa solo análisis estático de HTML.'
                : 'Connects to a Browserless.io instance to execute JavaScript and detect runtime cookies. Without a token, the scanner falls back to static HTML analysis.' ); ?>
            <a href="https://www.browserless.io" target="_blank" rel="noopener"><?php echo esc_html( $isES ? 'Obtener token gratuito →' : 'Get a free token →' ); ?></a>
        </p>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Endpoint de Browserless' : 'Browserless endpoint' ); ?></label>
            <input type="url" id="browseless_endpoint"
                   value="<?php echo esc_attr( $s['browseless_endpoint'] ?? 'https://chrome.browserless.io' ); ?>"
                   placeholder="https://chrome.browserless.io" style="width:320px">
        </div>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Token API' : 'API token' ); ?></label>
            <input type="password" id="browseless_token"
                   value="<?php echo esc_attr( $s['browseless_token'] ?? '' ); ?>"
                   placeholder="<?php echo esc_attr( $isES ? 'Dejar vacío para usar solo el escáner estático' : 'Leave empty to use static scanner only' ); ?>"
                   style="width:320px" autocomplete="new-password">
        </div>
    </div>

    <!-- ══════════════════════════════════════════
         COOKIE POLICY PAGE
    ══════════════════════════════════════════ -->
    <div class="bcm-card">
        <h3>📄 <?php echo esc_html( $isES ? 'Página de política de cookies' : 'Cookie policy page' ); ?> <span class="bcm-badge-new">v1.4.0</span></h3>
        <p class="bcm-hint">
            <?php echo esc_html( $isES
                ? 'Crea automáticamente una página /politica-de-cookies con una tabla actualizada de cookies detectadas. También puedes insertar la tabla con el shortcode:'
                : 'Automatically creates a /cookie-policy page with a live table of detected cookies. You can also insert the table anywhere with the shortcode:' ); ?>
            <code>[bcm_cookie_policy]</code>
        </p>

        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Generar página /cookie-policy automáticamente' : 'Auto-generate /cookie-policy page' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="auto_policy_page" <?php checked( $s['auto_policy_page'] ?? false ); ?>>
                <span class="bcm-slider"></span>
            </label>
        </div>

        <?php
        $page_id = (int) get_option( 'bcm_policy_page_id', 0 );
        if ( $page_id && get_post_status( $page_id ) === 'publish' ) :
        ?>
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Página de política' : 'Policy page' ); ?></label>
            <a href="<?php echo esc_url( get_permalink( $page_id ) ); ?>" target="_blank" class="bcm-btn bcm-btn-outline" style="font-size:.8rem">
                <?php echo esc_html( $isES ? 'Ver página →' : 'View page →' ); ?>
            </a>
        </div>
        <?php endif; ?>
    </div>

    <!-- ══════════════════════════════════════════
         COOKIE CATEGORIES
    ══════════════════════════════════════════ -->
    <div class="bcm-card">
        <h3><?php echo esc_html( $isES ? 'Categorías de cookies' : 'Cookie Categories' ); ?></h3>
        <p class="bcm-hint"><?php echo esc_html( $isES ? 'Activa o desactiva las categorías de cookies que aparecen en el panel de preferencias.' : 'Enable or disable cookie categories shown in the preference panel.' ); ?></p>
        <table class="bcm-table">
            <thead><tr>
                <th><?php echo esc_html( $isES ? 'Categoría' : 'Category' ); ?></th>
                <th><?php echo esc_html( $isES ? 'Etiqueta' : 'Label' ); ?></th>
                <th><?php echo esc_html( $isES ? 'Activa' : 'Enabled' ); ?></th>
                <th><?php echo esc_html( $isES ? 'Bloqueada (siempre on)' : 'Locked (always on)' ); ?></th>
            </tr></thead>
            <tbody>
            <?php foreach ( $s['categories'] as $key => $cat ) : ?>
            <tr>
                <td><code><?php echo esc_html( $key ); ?></code></td>
                <td><input type="text" class="cat-label" data-cat="<?php echo esc_attr( $key ); ?>" value="<?php echo esc_attr( $cat['label'] ); ?>"></td>
                <td><input type="checkbox" class="cat-enabled" data-cat="<?php echo esc_attr( $key ); ?>" <?php checked( $cat['enabled'] ); ?>></td>
                <td><input type="checkbox" class="cat-locked"  data-cat="<?php echo esc_attr( $key ); ?>" <?php checked( $cat['locked'] );  ?>></td>
            </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <div id="bcm-save-notice" style="display:none;" class="bcm-notice bcm-notice-success">
        ✅ <?php echo esc_html( $isES ? '¡Configuración guardada correctamente!' : 'Settings saved successfully!' ); ?>
    </div>

    <!-- ══════════════════════════════════════════
         T&C ENFORCEMENT  (v1.7.0)
    ══════════════════════════════════════════ -->
    <div class="bcm-card" style="border-left:4px solid #1a73e8;">
        <h3>🔒 <?php echo esc_html( $isES ? 'Cumplimiento de Términos y Condiciones' : 'Terms & Conditions Enforcement' ); ?> <span class="bcm-badge-new">v1.7.0</span></h3>
        <p class="bcm-hint">
            <?php echo wp_kses(
                $isES
                    ? 'Obliga a los usuarios registrados a aceptar los T&amp;C antes de acceder a contenido protegido. El estado se guarda en <code>wp_usermeta</code> (<code>_tc_accepted</code>).'
                    : 'Forces registered users to accept the T&amp;C before accessing member content. State is stored in <code>wp_usermeta</code> (<code>_tc_accepted</code>).',
                [ 'code' => [] ]
            ); ?>
        </p>

        <!-- Master switch -->
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'Activar cumplimiento de T&C' : 'Enable T&C enforcement' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="tc_enforcement_enabled" <?php checked( $s['tc_enforcement_enabled'] ?? false ); ?>>
                <span class="bcm-slider"></span>
            </label>
        </div>
        <p class="bcm-hint" style="color:#888;">
            <?php echo esc_html( $isES
                ? 'Cuando está activo: los usuarios que no hayan aceptado son redirigidos a la página de aceptación. Si rechazan, la sesión se cierra y se invalidan las cookies de sesión.'
                : 'When active: users who have not accepted are redirected to the acceptance page. If they reject, the session is closed and all session cookies are invalidated.' ); ?>
        </p>

        <!-- Acceptance page -->
        <div class="bcm-field">
            <label><?php echo esc_html( $isES ? 'ID de página de aceptación' : 'Acceptance page ID' ); ?></label>
            <input type="number" id="tc_acceptance_page_id" min="0"
                   value="<?php echo esc_attr( (int)( $s['tc_acceptance_page_id'] ?? 0 ) ); ?>"
                   style="width:120px;">
        </div>
        <p class="bcm-hint">
            <?php echo wp_kses(
                $isES
                    ? 'ID de la página de WordPress que contiene el shortcode <code>[bcm_tc_acceptance]</code>. Deja en 0 para usar la URL virtual <code>/tc-acceptance/</code>.'
                    : 'WordPress page ID containing the <code>[bcm_tc_acceptance]</code> shortcode. Leave 0 to use the virtual URL <code>/tc-acceptance/</code>.',
                [ 'code' => [] ]
            ); ?>
        </p>

        <!-- Auto-purge -->
        <div class="bcm-field" style="margin-top:16px;">
            <label><?php echo esc_html( $isES ? 'Eliminar cuentas rechazadas inactivas (30 días)' : 'Auto-purge rejected inactive accounts (30 days)' ); ?></label>
            <label class="bcm-toggle">
                <input type="checkbox" id="tc_purge_rejected" <?php checked( $s['tc_purge_rejected'] ?? false ); ?>>
                <span class="bcm-slider"></span>
            </label>
        </div>
        <p class="bcm-hint" style="color:#c0392b;">
            ⚠ <?php echo wp_kses(
                $isES
                    ? '<strong>Irreversible.</strong> Un cron diario eliminará las cuentas cuyo T&C esté rechazado y no hayan tenido actividad en los últimos 30 días. Nunca elimina administradores.'
                    : '<strong>Irreversible.</strong> A daily cron will delete accounts whose T&C is rejected and have had no activity in the last 30 days. Never deletes admins.',
                [ 'strong' => [] ]
            ); ?>
        </p>

        <!-- Admin: manual reset for a specific user -->
        <div class="bcm-field" style="margin-top:20px; flex-direction:column; align-items:flex-start; gap:8px;">
            <label style="font-weight:600;"><?php echo esc_html( $isES ? 'Restablecer estado T&C de un usuario' : 'Reset T&C status for a user' ); ?></label>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <input type="number" id="bcm-tc-reset-uid" placeholder="User ID" min="1" style="width:120px;">
                <button type="button" id="bcm-tc-reset-btn" class="button button-secondary">
                    <?php echo esc_html( $isES ? 'Restablecer' : 'Reset' ); ?>
                </button>
                <span id="bcm-tc-reset-msg" style="font-size:.85em; color:#555;"></span>
            </div>
        </div>
    </div>

    <!-- ══════════════════════════════════════════════
         LOGIN / REGISTER OVERLAY  (v2.1.0)
    ══════════════════════════════════════════════ -->
    <div class="bcm-card" style="margin-top:20px;">
        <h3>🔐 <?php echo esc_html( $isES ? 'Overlay de T&C en Login/Registro' : 'T&C Overlay on Login/Register' ); ?> <span class="bcm-badge-new">v2.1.0</span></h3>
        <p style="font-size:.85rem;color:#666;margin-bottom:16px;">
            <?php echo esc_html( $isES
                ? 'El overlay aparece automáticamente en /login, /login-2, /register y /register-2. Agregá URLs extra si usás otras rutas.'
                : 'The overlay appears automatically on /login, /login-2, /register and /register-2. Add extra URLs if you use other paths.'
            ); ?>
        </p>
        <div class="bcm-field">
            <label for="ltc_urls"><?php echo esc_html( $isES ? 'URLs adicionales (una por línea o separadas por coma)' : 'Extra URLs (one per line or comma-separated)' ); ?></label>
            <textarea id="ltc_urls" rows="3" style="width:100%;font-family:monospace;font-size:.85rem;"><?php echo esc_textarea( $s['ltc_urls'] ?? '' ); ?></textarea>
            <p class="description"><?php echo esc_html( $isES ? 'Ej: https://bloomscans.com/mi-login, /otro-registro' : 'E.g.: https://bloomscans.com/my-login, /other-register' ); ?></p>
        </div>
    </div>

    <div id="bcm-save-notice-bottom" style="display:none;" class="bcm-notice bcm-notice-success">
        ✅ <?php echo esc_html( $isES ? '¡Configuración guardada correctamente!' : 'Settings saved successfully!' ); ?>
    </div>
</div>

<script>
(function($) {
    // Hook new fields into the existing bcmData.settings collect on save
    var origCollect = window._bcmCollectSettings;

    $(document).on('click', '#bcm-save-btn', function() {
        // The existing admin.js gathers settings; we patch extra keys in via filter
        // Our fields are read by ID — admin.js calls bcmCollectSettings() which we extend:
        window._bcmExtra = window._bcmExtra || {};
        window._bcmExtra.tc_enforcement_enabled = $('#tc_enforcement_enabled').is(':checked');
        window._bcmExtra.tc_acceptance_page_id  = parseInt( $('#tc_acceptance_page_id').val() ) || 0;
        window._bcmExtra.tc_purge_rejected       = $('#tc_purge_rejected').is(':checked');
        window._bcmExtra.ltc_urls                = $('#ltc_urls').val() || '';
    });

    // T&C reset button
    $('#bcm-tc-reset-btn').on('click', function() {
        var uid = parseInt( $('#bcm-tc-reset-uid').val() );
        if ( ! uid ) { $('#bcm-tc-reset-msg').text('<?php echo esc_js( $isES ? 'Introduce un ID válido.' : 'Enter a valid ID.' ); ?>'); return; }

        $.post( ajaxurl, {
            action:  'bcm_reset_tc_user',
            nonce:   (bcmData.nonces && bcmData.nonces.reset_tc_user) || '',
            user_id: uid
        }, function(res) {
            $('#bcm-tc-reset-msg').text( res.success ? (res.data.message || 'OK') : (res.data || 'Error') );
        });
    });
})(jQuery);
</script>
