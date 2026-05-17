<?php if ( ! defined( 'ABSPATH' ) ) exit;
global $wpdb;
$s          = BCM_Settings::get();
$lang       = $s['admin_lang'] ?? 'es';
$isES       = ( $lang === 'es' );
$categories = $s['categories'];
?>
<div class="bcm-wrap">
    <div class="bcm-header">
        <h1>🍪 <?php echo esc_html( $isES ? 'Gestor de cookies' : 'Cookie Manager' ); ?></h1>
        <div>
            <button id="bcm-seed-cookies" class="bcm-btn bcm-btn-outline"
                title="<?php echo esc_attr( $isES ? 'Importar biblioteca de cookies conocidas (Google, Infolinks, WordPress, etc.)' : 'Import known cookies library (Google, Infolinks, WordPress, etc.)' ); ?>">
                📚 <?php echo esc_html( $isES ? 'Importar biblioteca' : 'Import Library' ); ?>
            </button>
            <button id="bcm-run-scan" class="bcm-btn bcm-btn-outline">🔍 <?php echo esc_html( $isES ? 'Escanear ahora' : 'Scan Now' ); ?></button>
            <button id="bcm-add-cookie" class="bcm-btn bcm-btn-primary">+ <?php echo esc_html( $isES ? 'Agregar cookie' : 'Add Cookie' ); ?></button>
        </div>
    </div>

    <div id="bcm-scan-bar" style="display:none;" class="bcm-scan-bar">
        <span class="bcm-spinner"></span> <?php echo esc_html( $isES ? 'Escaneando el sitio en busca de cookies...' : 'Scanning your site for cookies...' ); ?>
        <span id="bcm-scan-progress"></span>
    </div>

    <div class="bcm-two-col bcm-cookies-layout">
        <div class="bcm-card bcm-cat-sidebar">
            <h4><?php echo esc_html( $isES ? 'Categorías' : 'Categories' ); ?></h4>
            <ul class="bcm-cat-list">
                <li class="bcm-cat-item active" data-cat="all">
                    <?php echo esc_html( $isES ? 'Todas las cookies' : 'All Cookies' ); ?> <span class="bcm-count" id="count-all"></span>
                </li>
                <?php foreach ( $categories as $key => $cat ) : ?>
                <li class="bcm-cat-item" data-cat="<?php echo esc_attr( $key ); ?>">
                    <?php echo esc_html( $cat['label'] ); ?> <span class="bcm-count" id="count-<?php echo esc_attr( $key ); ?>"></span>
                </li>
                <?php endforeach; ?>
            </ul>
        </div>

        <div class="bcm-card bcm-cookie-table-wrap">
            <div id="bcm-cookie-details">
                <h4 id="bcm-cat-title"><?php echo esc_html( $isES ? 'Todas las cookies' : 'All Cookies' ); ?></h4>
                <p class="bcm-cat-desc" id="bcm-cat-desc"><?php echo esc_html( $isES ? 'Todas las cookies rastreadas en tu sitio.' : 'All tracked cookies on your site.' ); ?></p>
                <table class="bcm-table" id="bcm-cookies-table">
                    <thead>
                        <tr>
                            <th><?php echo esc_html( $isES ? 'Nombre' : 'Name' ); ?></th>
                            <th><?php echo esc_html( $isES ? 'Proveedor' : 'Provider' ); ?></th>
                            <th><?php echo esc_html( $isES ? 'Categoría' : 'Category' ); ?></th>
                            <th><?php echo esc_html( $isES ? 'Caducidad' : 'Expiry' ); ?></th>
                            <th><?php echo esc_html( $isES ? 'Acciones' : 'Actions' ); ?></th>
                        </tr>
                    </thead>
                    <tbody id="bcm-cookie-tbody">
                        <tr><td colspan="5" class="bcm-loading"><?php echo esc_html( $isES ? 'Cargando...' : 'Loading...' ); ?></td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<!-- Cookie Modal -->
<div id="bcm-cookie-modal" class="bcm-modal" style="display:none;">
    <div class="bcm-modal-inner">
        <div class="bcm-modal-header">
            <h3 id="bcm-modal-title"><?php echo esc_html( $isES ? 'Agregar cookie' : 'Add Cookie' ); ?></h3>
            <button class="bcm-modal-close">✕</button>
        </div>
        <div class="bcm-modal-body">
            <input type="hidden" id="cookie-id" value="">
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Nombre de la cookie' : 'Cookie Name' ); ?></label>
                <input type="text" id="cookie-name">
            </div>
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Categoría' : 'Category' ); ?></label>
                <select id="cookie-category">
                    <?php foreach ( $categories as $key => $cat ) : ?>
                    <option value="<?php echo esc_attr( $key ); ?>"><?php echo esc_html( $cat['label'] ); ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Proveedor' : 'Provider' ); ?></label>
                <input type="text" id="cookie-provider">
            </div>
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Finalidad' : 'Purpose' ); ?></label>
                <textarea id="cookie-purpose" rows="3"></textarea>
            </div>
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Caducidad' : 'Expiry' ); ?></label>
                <input type="text" id="cookie-expiry" placeholder="<?php echo esc_attr( $isES ? 'ej. 1 año, Sesión' : 'e.g. 1 year, Session' ); ?>">
            </div>
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Dominio' : 'Domain' ); ?></label>
                <input type="text" id="cookie-domain">
            </div>
            <div class="bcm-field">
                <label><?php echo esc_html( $isES ? 'Tipo' : 'Type' ); ?></label>
                <select id="cookie-type">
                    <option value="HTTP">HTTP</option>
                    <option value="HTML">HTML (localStorage)</option>
                </select>
            </div>
        </div>
        <div class="bcm-modal-footer">
            <button class="bcm-btn bcm-btn-outline bcm-modal-close"><?php echo esc_html( $isES ? 'Cancelar' : 'Cancel' ); ?></button>
            <button id="bcm-save-cookie" class="bcm-btn bcm-btn-primary"><?php echo esc_html( $isES ? 'Guardar cookie' : 'Save Cookie' ); ?></button>
        </div>
    </div>
</div>
