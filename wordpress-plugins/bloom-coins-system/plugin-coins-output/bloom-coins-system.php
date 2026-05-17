<?php
/**
 * Plugin Name: Bloom Coins System
 * Plugin URI:  https://bloomscans.com
 * Description: Sistema de monedas para Bloom Scans. Dashboard con gráficos, gestión de wallet, capítulos premium con ícono 🪙 y bloqueo de acceso.
 * Version:     1.2.0
 * Author:      Bloom Scans
 * Author URI:  https://bloomscans.com
 * License:     GPL v2 or later
 * Text Domain: bloom-coins
 */

if ( ! defined( 'ABSPATH' ) ) exit;

// ── Constantes ───────────────────────────────────────────────────────────────
define( 'BCS_VERSION',    '1.2.0' );
define( 'BCS_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'BCS_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

// ── Cargar dependencias de inmediato (antes de cualquier hook) ───────────────
require_once BCS_PLUGIN_DIR . 'includes/coins-system.php';
require_once BCS_PLUGIN_DIR . 'includes/coins-user-menu.php';

// ── Activación ───────────────────────────────────────────────────────────────
register_activation_hook( __FILE__, function() {
    MSG_Coins_System::get_instance()->create_coins_tables();
    flush_rewrite_rules();
} );
register_deactivation_hook( __FILE__, 'flush_rewrite_rules' );

// ── Inicializar clases al arrancar WordPress ─────────────────────────────────
add_action( 'plugins_loaded', function() {
    MSG_Coins_System::get_instance();
    MSG_Coins_User_Menu_Integration::get_instance();
}, 5 );

// ════════════════════════════════════════════════════════════════════════════
// ASSETS FRONTEND
// ════════════════════════════════════════════════════════════════════════════
add_action( 'wp_enqueue_scripts', function() {
    if ( file_exists( BCS_PLUGIN_DIR . 'assets/css/coins-system.css' ) ) {
        wp_enqueue_style( 'bcs-coins', BCS_PLUGIN_URL . 'assets/css/coins-system.css', [], BCS_VERSION );
    }
    if ( file_exists( BCS_PLUGIN_DIR . 'assets/js/coins-system.js' ) ) {
        wp_enqueue_script( 'bcs-coins', BCS_PLUGIN_URL . 'assets/js/coins-system.js', ['jquery'], BCS_VERSION, true );
        wp_localize_script( 'bcs-coins', 'msgCoins', [
            'ajax_url'    => admin_url( 'admin-ajax.php' ),
            'nonce'       => wp_create_nonce( 'msg_coins_nonce' ),
            'user_balance'=> is_user_logged_in()
                ? (int) MSG_Coins_System::get_instance()->get_user_balance( get_current_user_id() )
                : 0,
        ] );
    }
} );

// Fallback CSS inline para badges si el CSS externo no cargó
add_action( 'wp_footer', function() {
    if ( wp_style_is( 'bcs-coins', 'done' ) ) return;
    echo '<style>
.msg-coin-badge{display:inline-flex;align-items:center;font-size:.8em;vertical-align:middle;margin-left:5px;cursor:help;}
.msg-coin-timer{display:inline-flex;align-items:center;font-size:.7em;vertical-align:middle;margin-left:3px;background:rgba(0,212,170,.15);color:#00d4aa;border-radius:4px;padding:1px 5px;}
.bcs-chapter-locked .chapternum::after{content:" 🪙";font-size:.85em;}
</style>' . "\n";
}, 5 );

// ════════════════════════════════════════════════════════════════════════════
// BADGE EN LISTA DE CAPÍTULOS (inyección JS en frontend)
// Agrega clase CSS a los <li> de capítulos bloqueados para mostrar el 🪙
// ════════════════════════════════════════════════════════════════════════════
add_action( 'wp_footer', function() {
    if ( ! is_singular( ['post', 'page', 'wp-manga'] ) && ! is_tax() ) return;

    // Obtener IDs de capítulos bloqueados del manga actual
    global $post, $wpdb;
    $manga_id = is_singular() ? get_the_ID() : 0;
    if ( ! $manga_id ) return;

    // Buscar capítulos bloqueados asociados a este manga
    $locked_chapters = $wpdb->get_results( $wpdb->prepare(
        "SELECT p.ID, p.post_title, pm_price.meta_value AS price, pm_free.meta_value AS free_after
         FROM {$wpdb->posts} p
         INNER JOIN {$wpdb->postmeta} pm_lock ON pm_lock.post_id = p.ID AND pm_lock.meta_key = '_msg_chapter_locked' AND pm_lock.meta_value = '1'
         LEFT JOIN {$wpdb->postmeta} pm_price ON pm_price.post_id = p.ID AND pm_price.meta_key = '_msg_coin_price'
         LEFT JOIN {$wpdb->postmeta} pm_free  ON pm_free.post_id  = p.ID AND pm_free.meta_key  = '_msg_free_after_days'
         LEFT JOIN {$wpdb->postmeta} pm_seri  ON pm_seri.post_id  = p.ID AND pm_seri.meta_key  = 'ero_seri'
         WHERE pm_seri.meta_value = %d AND p.post_status = 'publish'",
        $manga_id
    ) );

    if ( empty( $locked_chapters ) ) return;

    $cs      = MSG_Coins_System::get_instance();
    $user_id = get_current_user_id();

    $locked_map = [];
    foreach ( $locked_chapters as $ch ) {
        // Si ya lo compró o se liberó por tiempo, no mostramos icono
        if ( $user_id && $cs->user_has_purchased( $user_id, $ch->ID ) ) continue;
        if ( $cs->chapter_is_free_by_time( $ch->ID ) ) continue;
        $price = $ch->price ?: 100;
        $locked_map[ $ch->ID ] = $price;
    }

    if ( empty( $locked_map ) ) return;

    $json = json_encode( $locked_map );
    ?>
    <style>
    .bcs-locked-row .chapternum { position: relative; }
    .bcs-coin-chip {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        background: linear-gradient(135deg, rgba(0,212,170,.18), rgba(0,168,150,.12));
        border: 1px solid rgba(0,212,170,.4);
        color: #00d4aa;
        font-size: 11px;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 20px;
        margin-left: 6px;
        vertical-align: middle;
        white-space: nowrap;
        letter-spacing: .3px;
    }
    </style>
    <script>
    (function() {
        var locked = <?php echo $json; ?>;
        var lockedIds = Object.keys(locked);
        if (!lockedIds.length) return;

        /* Inserta el chip en el elemento correcto del <li> */
        function insertChip(li, price) {
            if (li.querySelector('.bcs-coin-chip')) return; // ya marcado
            li.classList.add('bcs-locked-row');
            var target = li.querySelector('.chapternum, .chapter-number, .num-chap, .chapter-link');
            if (!target) target = li.querySelector('a');
            if (!target) return;
            target.insertAdjacentHTML('beforeend',
                '<span class="bcs-coin-chip">🪙 ' + price + '</span>'
            );
        }

        /* Extrae el post ID desde una URL usando múltiples patrones */
        function extractId(href) {
            if (!href) return null;
            // ?p=12345  o  &p=12345
            var m = href.match(/[?&]p=(\d+)/);
            if (m) return m[1];
            // /12345/ (4+ dígitos entre slashes — typical permalink con ID)
            m = href.match(/\/(\d{4,})(?:\/|$)/);
            if (m) return m[1];
            // URL contiene el ID como último segmento: /capitulo-1/12345
            m = href.match(/\/(\d+)\/?(?:\?|$|#)/);
            if (m) return m[1];
            return null;
        }

        function markLocked() {
            // Todos los selectores posibles del tema Ero-Reader / Mangareader / WP-Manga
            var items = document.querySelectorAll([
                '#chapterlist li',
                '.eplister li',
                '.bxcl li',
                'ul.clstyle li',
                '.version-chap li',
                'li.wp-manga-chapter',
                '.chapter-list li',
                '.chapterlist li',
                '.listing-chapters_wrap li',
                'ul.main li'
            ].join(', '));

            items.forEach(function(li) {
                /* ── Estrategia 1: data-attributes en el <li> ── */
                var chId = li.getAttribute('data-id') ||
                           li.getAttribute('data-chapter-id') ||
                           li.getAttribute('data-post-id') ||
                           li.getAttribute('data-post');

                if (chId && locked[chId] !== undefined) {
                    insertChip(li, locked[chId]);
                    return;
                }

                /* ── Estrategia 2: extraer ID de la URL del enlace ── */
                var a = li.querySelector('a[href]');
                var href = a ? (a.getAttribute('href') || '') : '';

                if (!chId && href) {
                    chId = extractId(href);
                    if (chId && locked[chId] !== undefined) {
                        insertChip(li, locked[chId]);
                        return;
                    }
                }

                /* ── Estrategia 3: búsqueda exhaustiva por substring en href ── */
                if (href) {
                    for (var i = 0; i < lockedIds.length; i++) {
                        var id = lockedIds[i];
                        if (href.indexOf('/' + id + '/') !== -1 ||
                            href.indexOf('p=' + id) !== -1 ||
                            href.indexOf('/' + id + '?') !== -1 ||
                            href.endsWith('/' + id)) {
                            insertChip(li, locked[id]);
                            return;
                        }
                    }
                }

                /* ── Estrategia 4: buscar en TODOS los <a> del <li> ── */
                var allLinks = li.querySelectorAll('a[href]');
                allLinks.forEach(function(lnk) {
                    var h = lnk.getAttribute('href') || '';
                    var eid = extractId(h);
                    if (eid && locked[eid] !== undefined) {
                        insertChip(li, locked[eid]);
                    }
                });
            });
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', markLocked);
        } else {
            markLocked();
        }
        // Re-run después de carga AJAX del tema
        setTimeout(markLocked, 600);
        setTimeout(markLocked, 1600);
        setTimeout(markLocked, 3500);

        // Observar cambios dinámicos (AJAX pagination de capítulos)
        var observer = new MutationObserver(function(mutations) {
            var hasNew = mutations.some(function(m) { return m.addedNodes.length > 0; });
            if (hasNew) setTimeout(markLocked, 150);
        });
        var chapterContainer = document.querySelector('#chapterlist, .eplister, .listing-chapters_wrap, .chapter-list');
        if (chapterContainer) {
            observer.observe(chapterContainer, { childList: true, subtree: true });
        }
    })();
    </script>
    <?php
}, 20 );

// ════════════════════════════════════════════════════════════════════════════
// AJAX ENDPOINTS
// ════════════════════════════════════════════════════════════════════════════

// Balance del usuario
add_action( 'wp_ajax_get_user_balance', function() {
    if ( ! is_user_logged_in() ) wp_send_json_error( ['message' => 'Not logged in'] );
    wp_send_json_success( ['balance' => (int) MSG_Coins_System::get_instance()->get_user_balance( get_current_user_id() )] );
} );

// Compra simulada (demo)
add_action( 'wp_ajax_simulate_coin_purchase', function() {
    if ( ! is_user_logged_in() ) wp_send_json_error( ['message' => 'Debes iniciar sesión'] );
    $user_id = get_current_user_id();
    $coins   = absint( $_POST['coins'] ?? 0 );
    $price   = floatval( $_POST['price'] ?? 0 );
    if ( ! wp_verify_nonce( $_POST['nonce'] ?? '', 'simulate_purchase_' . $user_id ) )
        wp_send_json_error( ['message' => 'Sesión inválida'] );
    $valid = [100 => 1, 1000 => 10, 2000 => 20];
    if ( ! isset( $valid[$coins] ) || $valid[$coins] != $price )
        wp_send_json_error( ['message' => 'Paquete inválido'] );
    $cs = MSG_Coins_System::get_instance();
    $cs->add_coins( $user_id, $coins, $price, 'DEMO_' . time() . '_' . $user_id,
        "Compra demo — {$coins} monedas por \${$price} USD" );
    wp_send_json_success( ['message' => "¡+{$coins} monedas agregadas!", 'new_balance' => $cs->get_user_balance( $user_id )] );
} );

// Gestión admin: agregar/quitar monedas
add_action( 'wp_ajax_bcs_admin_add_coins', function() {
    check_ajax_referer( 'bcs_admin_add_coins', 'bcs_nonce' );
    if ( ! current_user_can( 'manage_options' ) ) wp_send_json_error( ['message' => 'Sin permisos'] );

    $user_id = absint( $_POST['user_id'] ?? 0 );
    $amount  = intval( $_POST['coins_amount'] ?? 0 );
    $reason  = sanitize_text_field( $_POST['reason'] ?? '' );
    if ( ! $user_id || $amount === 0 ) wp_send_json_error( ['message' => 'Datos inválidos'] );

    $user = get_user_by( 'id', $user_id );
    if ( ! $user ) wp_send_json_error( ['message' => 'Usuario no encontrado'] );

    $cs = MSG_Coins_System::get_instance();
    global $wpdb;

    if ( $amount > 0 ) {
        $cs->add_coins( $user_id, $amount, 0, 'ADMIN_ADD', $reason );
        $action = 'agregadas'; $sign = '+';
    } else {
        $wpdb->query( $wpdb->prepare(
            "UPDATE {$wpdb->prefix}user_wallet SET coins_balance = coins_balance + %d WHERE user_id = %d",
            $amount, $user_id
        ) );
        $wpdb->insert( $wpdb->prefix . 'coin_transactions', [
            'user_id' => $user_id, 'transaction_type' => 'admin_deduct',
            'coins_amount' => $amount, 'payment_status' => 'completed', 'description' => $reason,
        ] );
        $action = 'quitadas'; $sign = '';
    }

    if ( class_exists( 'MSG_Notifications' ) ) {
        $msg = $sign . abs($amount) . " monedas {$action}" . ( $reason ? " — {$reason}" : '' );
        MSG_Notifications::create_notification( $user_id, 'coins_added', $msg, '' );
    }

    wp_send_json_success( [
        'message' => abs($amount) . " monedas {$action} a {$user->display_name}. Saldo: "
                   . number_format( $cs->get_user_balance( $user_id ) ) . ' 🪙',
    ] );
} );

// Dashboard stats AJAX
add_action( 'wp_ajax_bcs_dashboard_stats', function() {
    if ( ! current_user_can( 'manage_options' ) ) wp_send_json_error();
    global $wpdb;

    $period = sanitize_text_field( $_POST['period'] ?? '30d' );
    $days   = $period === '7d' ? 7 : ( $period === '90d' ? 90 : 30 );
    $since  = date( 'Y-m-d', strtotime( "-{$days} days" ) );

    $tx  = $wpdb->prefix . 'coin_transactions';
    $cp  = $wpdb->prefix . 'chapter_purchases';
    $uw  = $wpdb->prefix . 'user_wallet';

    // KPIs globales
    $kpis = $wpdb->get_row(
        "SELECT
            (SELECT COALESCE(SUM(coins_balance),0) FROM $uw) AS total_circulating,
            (SELECT COUNT(*) FROM $uw WHERE coins_balance > 0) AS active_wallets,
            (SELECT COALESCE(SUM(coins_spent),0) FROM $cp WHERE purchase_date >= '$since') AS coins_spent_period,
            (SELECT COUNT(*) FROM $cp WHERE purchase_date >= '$since') AS unlocks_period,
            (SELECT COUNT(DISTINCT user_id) FROM $cp WHERE purchase_date >= '$since') AS buyers_period"
    );

    // Actividad diaria (monedas gastadas por día)
    $daily = $wpdb->get_results(
        "SELECT DATE(purchase_date) AS day, SUM(coins_spent) AS coins, COUNT(*) AS unlocks
         FROM $cp
         WHERE purchase_date >= '$since'
         GROUP BY DATE(purchase_date)
         ORDER BY day ASC"
    );

    // Top 5 mangas por monedas
    $top_manga = $wpdb->get_results(
        "SELECT cp.manga_id, p.post_title AS title, cp.scan_group_name AS scan,
                SUM(cp.coins_spent) AS coins, COUNT(*) AS unlocks
         FROM $cp cp
         LEFT JOIN {$wpdb->posts} p ON p.ID = cp.manga_id
         WHERE cp.purchase_date >= '$since'
         GROUP BY cp.manga_id ORDER BY coins DESC LIMIT 5"
    );

    // Top 5 usuarios compradores
    $top_users = $wpdb->get_results(
        "SELECT cp.user_id, u.display_name, SUM(cp.coins_spent) AS coins, COUNT(*) AS unlocks
         FROM $cp cp
         LEFT JOIN {$wpdb->users} u ON u.ID = cp.user_id
         WHERE cp.purchase_date >= '$since'
         GROUP BY cp.user_id ORDER BY coins DESC LIMIT 5"
    );

    // Últimos movimientos (transacciones)
    $movements = $wpdb->get_results(
        "SELECT t.id, t.user_id, u.display_name, t.transaction_type,
                t.coins_amount, t.payment_amount, t.description, t.created_at
         FROM $tx t
         LEFT JOIN {$wpdb->users} u ON u.ID = t.user_id
         ORDER BY t.created_at DESC LIMIT 50"
    );

    // Ingresos por scan group
    $by_scan = $wpdb->get_results(
        "SELECT scan_group_name, SUM(coins_spent) AS coins, COUNT(*) AS unlocks,
                COUNT(DISTINCT manga_id) AS mangas
         FROM $cp
         WHERE purchase_date >= '$since' AND scan_group_id IS NOT NULL
         GROUP BY scan_group_id ORDER BY coins DESC"
    );

    // Distribución de tipos de transacción
    $tx_types = $wpdb->get_results(
        "SELECT transaction_type, COUNT(*) AS count, SUM(ABS(coins_amount)) AS total
         FROM $tx WHERE created_at >= '$since'
         GROUP BY transaction_type ORDER BY total DESC"
    );

    wp_send_json_success( compact( 'kpis', 'daily', 'top_manga', 'top_users', 'movements', 'by_scan', 'tx_types', 'days' ) );
} );

// ════════════════════════════════════════════════════════════════════════════
// ADMIN MENU
// ════════════════════════════════════════════════════════════════════════════
add_action( 'admin_menu', function() {
    global $menu;
    $parent     = 'manga-scan-groups';
    $has_parent = false;
    foreach ( (array) $menu as $item ) {
        if ( isset($item[2]) && $item[2] === $parent ) { $has_parent = true; break; }
    }
    if ( $has_parent ) {
        add_submenu_page( $parent, 'Monedas', '🪙 Monedas', 'manage_options', 'bcs-coins', 'bcs_render_page' );
    } else {
        add_menu_page( 'Bloom Coins', '🪙 Bloom Coins', 'manage_options', 'bcs-coins', 'bcs_render_page', 'dashicons-money-alt', 56 );
    }
}, 99 );

add_action( 'admin_enqueue_scripts', function( $hook ) {
    if ( strpos( $hook, 'bcs-coins' ) === false ) return;
    // Chart.js desde CDN
    wp_enqueue_script( 'chartjs', 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js', [], '4.4.0', true );
} );

// ════════════════════════════════════════════════════════════════════════════
// ADMIN PAGE
// ════════════════════════════════════════════════════════════════════════════
function bcs_render_page() {
    if ( ! current_user_can( 'manage_options' ) ) wp_die( 'Sin permisos.' );

    $cs    = MSG_Coins_System::get_instance();
    $users = get_users( ['orderby' => 'registered', 'order' => 'DESC'] );
    global $wpdb;
    $stats = $wpdb->get_row(
        "SELECT COUNT(*) AS total_users, COALESCE(SUM(coins_balance),0) AS total_coins,
                COALESCE(AVG(coins_balance),0) AS avg_balance
         FROM {$wpdb->prefix}user_wallet"
    );
    ?>
    <div class="wrap bcs-admin-wrap">
        <h1 class="bcs-title">🪙 Bloom Coins System <span>v<?php echo BCS_VERSION; ?></span></h1>

        <nav class="bcs-tabs">
            <button class="bcs-tab active" data-tab="dashboard">📊 Dashboard</button>
            <button class="bcs-tab" data-tab="movimientos">📋 Movimientos</button>
            <button class="bcs-tab" data-tab="reporte">🎴 Por Manga</button>
            <button class="bcs-tab" data-tab="gestion">⚙️ Gestión</button>
        </nav>

        <!-- ── DASHBOARD ──────────────────────────────────────────────── -->
        <div id="bcs-tab-dashboard" class="bcs-panel">
            <div class="bcs-period-bar">
                <span>Período:</span>
                <button class="bcs-pbtn active" data-days="7d">7 días</button>
                <button class="bcs-pbtn" data-days="30d">30 días</button>
                <button class="bcs-pbtn" data-days="90d">90 días</button>
                <span id="bcs-loading" style="display:none; color:#999; margin-left:10px;">⏳ Cargando...</span>
            </div>

            <!-- KPI Cards -->
            <div class="bcs-kpi-grid" id="bcs-kpis">
                <div class="bcs-kpi-card"><div class="bcs-kpi-icon">🪙</div><div class="bcs-kpi-val" id="k-circulating">—</div><div class="bcs-kpi-lbl">En circulación</div></div>
                <div class="bcs-kpi-card"><div class="bcs-kpi-icon">👛</div><div class="bcs-kpi-val" id="k-wallets">—</div><div class="bcs-kpi-lbl">Wallets activas</div></div>
                <div class="bcs-kpi-card accent"><div class="bcs-kpi-icon">🔓</div><div class="bcs-kpi-val" id="k-unlocks">—</div><div class="bcs-kpi-lbl">Desbloques (período)</div></div>
                <div class="bcs-kpi-card accent"><div class="bcs-kpi-icon">💸</div><div class="bcs-kpi-val" id="k-spent">—</div><div class="bcs-kpi-lbl">Monedas gastadas</div></div>
                <div class="bcs-kpi-card"><div class="bcs-kpi-icon">👥</div><div class="bcs-kpi-val" id="k-buyers">—</div><div class="bcs-kpi-lbl">Compradores únicos</div></div>
            </div>

            <!-- Charts -->
            <div class="bcs-charts-grid">
                <div class="bcs-card">
                    <h3>📈 Actividad diaria (monedas gastadas)</h3>
                    <canvas id="chart-daily" height="120"></canvas>
                </div>
                <div class="bcs-card">
                    <h3>🍕 Tipos de transacción</h3>
                    <canvas id="chart-types" height="160"></canvas>
                </div>
            </div>

            <!-- Top Tables -->
            <div class="bcs-two-col">
                <div class="bcs-card">
                    <h3>🏆 Top 5 Mangas (período)</h3>
                    <div id="tbl-top-manga"></div>
                </div>
                <div class="bcs-card">
                    <h3>🧑‍💻 Top 5 Compradores (período)</h3>
                    <div id="tbl-top-users"></div>
                </div>
            </div>

            <!-- Scan Groups -->
            <div class="bcs-card" style="margin-top:20px;">
                <h3>👥 Por Grupo de Scan (período)</h3>
                <div id="tbl-by-scan"></div>
            </div>
        </div>

        <!-- ── MOVIMIENTOS ────────────────────────────────────────────── -->
        <div id="bcs-tab-movimientos" class="bcs-panel" style="display:none;">
            <div class="bcs-card">
                <h3>📋 Últimos 50 movimientos</h3>
                <div style="display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap;">
                    <input type="text" id="bcs-mv-search" placeholder="Buscar usuario, tipo…" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;min-width:200px;">
                    <select id="bcs-mv-type" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;">
                        <option value="">— Todos los tipos —</option>
                        <option value="purchase">purchase (recarga)</option>
                        <option value="chapter_unlock">chapter_unlock (desbloqueo)</option>
                        <option value="admin_add">admin_add</option>
                        <option value="admin_deduct">admin_deduct</option>
                    </select>
                    <button class="button" id="bcs-mv-refresh">🔄 Actualizar</button>
                </div>
                <div id="bcs-movements-table" style="overflow-x:auto;"></div>
            </div>
        </div>

        <!-- ── REPORTE POR MANGA ──────────────────────────────────────── -->
        <div id="bcs-tab-reporte" class="bcs-panel" style="display:none;">
            <div class="bcs-card">
                <h3>🎴 Monedas generadas por Manga y Scan</h3>
                <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
                    <button class="bcs-pbtn active" data-days="all" onclick="bcsLoadReport('all')">Todo</button>
                    <button class="bcs-pbtn" data-days="30d" onclick="bcsLoadReport('30d')">30 días</button>
                    <button class="bcs-pbtn" data-days="7d" onclick="bcsLoadReport('7d')">7 días</button>
                </div>
                <div id="bcs-report-totals" style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px;"></div>
                <h4 style="margin-bottom:6px;">Por Manga</h4>
                <div id="bcs-report-manga" style="overflow-x:auto;"></div>
                <h4 style="margin:20px 0 6px;">Por Grupo de Scan</h4>
                <div id="bcs-report-scan" style="overflow-x:auto;"></div>
            </div>
        </div>

        <!-- ── GESTIÓN ────────────────────────────────────────────────── -->
        <div id="bcs-tab-gestion" class="bcs-panel" style="display:none;">
            <div class="bcs-two-col">
                <div class="bcs-card">
                    <h3>⚙️ Agregar / Quitar Monedas</h3>
                    <form id="bcs-coins-form">
                        <div class="bcs-field">
                            <label>Usuario</label>
                            <select name="user_id" id="bcs-user" required>
                                <option value="">— Selecciona —</option>
                                <?php foreach ($users as $u) :
                                    $bal = $cs->get_user_balance($u->ID); ?>
                                <option value="<?php echo $u->ID; ?>">
                                    <?php echo esc_html($u->display_name); ?> (<?php echo esc_html($u->user_email); ?>) — <?php echo number_format($bal); ?> 🪙
                                </option>
                                <?php endforeach; ?>
                            </select>
                        </div>
                        <div class="bcs-field">
                            <label>Cantidad <small>(+ agregar / − quitar)</small></label>
                            <input type="number" name="coins_amount" id="bcs-amount" required placeholder="Ej: 500 o -100">
                        </div>
                        <div class="bcs-field">
                            <label>Motivo</label>
                            <input type="text" name="reason" id="bcs-reason" required placeholder="Ej: Bono especial, corrección…">
                        </div>
                        <?php wp_nonce_field('bcs_admin_add_coins', 'bcs_nonce'); ?>
                        <button type="submit" class="bcs-btn-primary">💰 Procesar</button>
                    </form>
                    <div id="bcs-result"></div>
                </div>

                <div class="bcs-card">
                    <h3>📊 Estadísticas globales</h3>
                    <table class="bcs-stats-table">
                        <tr><th>Wallets con saldo</th><td><?php echo number_format($stats->total_users); ?></td></tr>
                        <tr><th>Total en circulación</th><td>🪙 <?php echo number_format($stats->total_coins); ?></td></tr>
                        <tr><th>Promedio por wallet</th><td>🪙 <?php echo number_format($stats->avg_balance, 1); ?></td></tr>
                    </table>

                    <?php
                    // Top wallets
                    $top_wallets = $wpdb->get_results(
                        "SELECT w.user_id, u.display_name, w.coins_balance
                         FROM {$wpdb->prefix}user_wallet w
                         LEFT JOIN {$wpdb->users} u ON u.ID = w.user_id
                         ORDER BY w.coins_balance DESC LIMIT 5"
                    );
                    if ($top_wallets) : ?>
                    <h4 style="margin:18px 0 8px;">💰 Top wallets</h4>
                    <table class="bcs-table">
                        <thead><tr><th>Usuario</th><th>Saldo</th></tr></thead>
                        <tbody>
                        <?php foreach ($top_wallets as $i => $w) : ?>
                        <tr>
                            <td><?php echo ['🥇','🥈','🥉','4.','5.'][$i]; ?> <?php echo esc_html($w->display_name ?: '—'); ?></td>
                            <td class="bcs-coins-val">🪙 <?php echo number_format($w->coins_balance); ?></td>
                        </tr>
                        <?php endforeach; ?>
                        </tbody>
                    </table>
                    <?php endif; ?>
                </div>
            </div>
        </div>
    </div><!-- .wrap -->

    <style>
    /* ── Admin Styles ─────────────────────────────────────────────── */
    .bcs-admin-wrap { max-width: 1400px; }
    .bcs-title { display:flex; align-items:center; gap:10px; margin-bottom:16px; }
    .bcs-title span { font-size:13px; font-weight:400; color:#999; }

    .bcs-tabs { display:flex; gap:0; margin-bottom:0; border-bottom:2px solid #e0e0e0; }
    .bcs-tab { background:none; border:none; border-bottom:3px solid transparent; margin-bottom:-2px;
        padding:10px 18px; font-size:13px; font-weight:600; cursor:pointer; color:#555; transition:.2s; }
    .bcs-tab:hover { color:#1d2327; }
    .bcs-tab.active { color:#1d2327; border-bottom-color:#00d4aa; }

    .bcs-panel { padding-top:20px; }
    .bcs-card { background:#fff; border:1px solid #e0e0e0; border-radius:10px; padding:20px; margin-bottom:20px; }
    .bcs-card h3 { margin:0 0 14px; font-size:14px; font-weight:700; }

    .bcs-period-bar { display:flex; align-items:center; gap:8px; margin-bottom:18px; flex-wrap:wrap; }
    .bcs-period-bar span { font-weight:600; font-size:13px; }
    .bcs-pbtn { padding:5px 14px; border:1px solid #ddd; border-radius:20px; background:#fff;
        font-size:12px; font-weight:600; cursor:pointer; transition:.2s; }
    .bcs-pbtn:hover, .bcs-pbtn.active { background:#1d2327; color:#fff; border-color:#1d2327; }

    .bcs-kpi-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:14px; margin-bottom:20px; }
    .bcs-kpi-card { background:#fff; border:1px solid #e0e0e0; border-radius:10px; padding:16px; text-align:center; }
    .bcs-kpi-card.accent { border-color:#00d4aa; background:rgba(0,212,170,.04); }
    .bcs-kpi-icon { font-size:26px; margin-bottom:6px; }
    .bcs-kpi-val { font-size:22px; font-weight:800; color:#1d2327; margin-bottom:4px; }
    .bcs-kpi-lbl { font-size:11px; color:#888; font-weight:600; text-transform:uppercase; letter-spacing:.5px; }

    .bcs-charts-grid { display:grid; grid-template-columns:2fr 1fr; gap:16px; margin-bottom:20px; }
    @media (max-width:900px) { .bcs-charts-grid { grid-template-columns:1fr; } }

    .bcs-two-col { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    @media (max-width:900px) { .bcs-two-col { grid-template-columns:1fr; } }

    /* Tables */
    .bcs-table { width:100%; border-collapse:collapse; font-size:13px; }
    .bcs-table th, .bcs-table td { padding:8px 10px; border-bottom:1px solid #f0f0f0; text-align:left; }
    .bcs-table thead th { background:#f8f8f8; font-weight:700; border-bottom:2px solid #e0e0e0; }
    .bcs-table tbody tr:hover td { background:#fafafa; }
    .bcs-coins-val { font-weight:700; color:#00a896; }

    .bcs-stats-table { width:100%; border-collapse:collapse; font-size:13px; margin-bottom:8px; }
    .bcs-stats-table th, .bcs-stats-table td { padding:8px 10px; border-bottom:1px solid #f0f0f0; }
    .bcs-stats-table th { text-align:left; color:#555; font-weight:600; }
    .bcs-stats-table td { font-weight:700; text-align:right; }

    /* Form */
    .bcs-field { margin-bottom:14px; }
    .bcs-field label { display:block; font-size:13px; font-weight:600; margin-bottom:5px; }
    .bcs-field input, .bcs-field select { width:100%; max-width:460px; padding:8px 10px;
        border:1px solid #ddd; border-radius:6px; font-size:13px; }
    .bcs-btn-primary { background:#1d2327; color:#fff; border:none; padding:10px 22px;
        border-radius:8px; font-size:14px; font-weight:700; cursor:pointer; margin-top:6px; }
    .bcs-btn-primary:hover { background:#00a896; }

    /* Result box */
    #bcs-result.ok  { margin-top:12px; padding:10px 14px; background:#d4edda; border:1px solid #c3e6cb; border-radius:6px; color:#155724; }
    #bcs-result.err { margin-top:12px; padding:10px 14px; background:#f8d7da; border:1px solid #f5c6cb; border-radius:6px; color:#721c24; }

    /* Movements */
    .bcs-mv-type-purchase    { color:#155724; background:#d4edda; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
    .bcs-mv-type-chapter_unlock { color:#004085; background:#cce5ff; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
    .bcs-mv-type-admin_add   { color:#856404; background:#fff3cd; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
    .bcs-mv-type-admin_deduct { color:#721c24; background:#f8d7da; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }
    .bcs-mv-pos { color:#155724; font-weight:700; }
    .bcs-mv-neg { color:#721c24; font-weight:700; }

    .bcs-stat-chip { background:#fff; border:1px solid #ddd; border-radius:8px; padding:12px 20px; text-align:center; min-width:140px; }
    .bcs-stat-chip .n { font-size:24px; font-weight:800; }
    .bcs-stat-chip .l { font-size:11px; color:#888; margin-top:2px; }
    </style>

    <script>
    /* ── BCS Admin Dashboard ──────────────────────────────────────── */
    var bcsCharts = {};
    var bcsCurrentPeriod = '30d';
    var bcsMovements = [];

    // Tabs
    document.querySelectorAll('.bcs-tab').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.bcs-tab').forEach(function(b){ b.classList.remove('active'); });
            document.querySelectorAll('.bcs-panel').forEach(function(p){ p.style.display='none'; });
            btn.classList.add('active');
            var panel = document.getElementById('bcs-tab-' + btn.dataset.tab);
            if (panel) panel.style.display = '';

            // Cargar datos al abrir tab
            if (btn.dataset.tab === 'dashboard' && !btn.dataset.loaded) {
                btn.dataset.loaded = 1;
                bcsLoadDashboard(bcsCurrentPeriod);
            }
            if (btn.dataset.tab === 'movimientos' && !btn.dataset.loaded) {
                btn.dataset.loaded = 1;
                bcsLoadDashboard(bcsCurrentPeriod); // movements come with dashboard
            }
            if (btn.dataset.tab === 'reporte' && !btn.dataset.loaded) {
                btn.dataset.loaded = 1;
                bcsLoadReport('all');
            }
        });
    });

    // Period buttons (dashboard)
    document.querySelectorAll('.bcs-period-bar .bcs-pbtn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.bcs-period-bar .bcs-pbtn').forEach(function(b){ b.classList.remove('active'); });
            btn.classList.add('active');
            bcsCurrentPeriod = btn.dataset.days;
            bcsLoadDashboard(btn.dataset.days);
        });
    });

    // Load dashboard on page load
    bcsLoadDashboard('30d');

    function bcsLoadDashboard(period) {
        document.getElementById('bcs-loading').style.display = 'inline';
        jQuery.post(ajaxurl, { action: 'bcs_dashboard_stats', period: period }, function(r) {
            document.getElementById('bcs-loading').style.display = 'none';
            if (!r.success) return;
            var d = r.data;

            // KPIs
            function fmt(n) { return parseInt(n||0).toLocaleString(); }
            document.getElementById('k-circulating').textContent = '🪙 ' + fmt(d.kpis.total_circulating);
            document.getElementById('k-wallets').textContent     = fmt(d.kpis.active_wallets);
            document.getElementById('k-unlocks').textContent     = fmt(d.kpis.unlocks_period);
            document.getElementById('k-spent').textContent       = '🪙 ' + fmt(d.kpis.coins_spent_period);
            document.getElementById('k-buyers').textContent      = fmt(d.kpis.buyers_period);

            // Daily chart
            var labels = d.daily.map(function(x){ return x.day.substring(5); }); // MM-DD
            var vals   = d.daily.map(function(x){ return parseInt(x.coins); });
            if (bcsCharts.daily) bcsCharts.daily.destroy();
            var ctx1 = document.getElementById('chart-daily').getContext('2d');
            bcsCharts.daily = new Chart(ctx1, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Monedas gastadas',
                        data: vals,
                        backgroundColor: 'rgba(0,212,170,.6)',
                        borderColor: '#00d4aa',
                        borderWidth: 1,
                        borderRadius: 4,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { callback: function(v){ return '🪙'+v.toLocaleString(); } } }
                    }
                }
            });

            // Donut chart for tx types
            if (d.tx_types && d.tx_types.length) {
                var tlabels = d.tx_types.map(function(x){ return x.transaction_type; });
                var tvals   = d.tx_types.map(function(x){ return parseInt(x.total); });
                var tcolors = ['#00d4aa','#4299e1','#f6c90e','#e53e3e','#805ad5','#dd6b20'];
                if (bcsCharts.types) bcsCharts.types.destroy();
                var ctx2 = document.getElementById('chart-types').getContext('2d');
                bcsCharts.types = new Chart(ctx2, {
                    type: 'doughnut',
                    data: { labels: tlabels, datasets: [{ data: tvals, backgroundColor: tcolors, hoverOffset: 6 }] },
                    options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { boxWidth:12, font:{size:11} } } } }
                });
            }

            // Top mangas table
            var mhtml = '<table class="bcs-table"><thead><tr><th>#</th><th>Manga</th><th>Scan</th><th>Desbloques</th><th>Monedas</th></tr></thead><tbody>';
            (d.top_manga||[]).forEach(function(m,i){
                mhtml += '<tr><td>'+(i+1)+'</td><td><strong>'+esc(m.title||'ID:'+m.manga_id)+'</strong></td>'
                    +'<td>'+esc(m.scan||'—')+'</td>'
                    +'<td style="text-align:center">'+fmt(m.unlocks)+'</td>'
                    +'<td class="bcs-coins-val">🪙 '+fmt(m.coins)+'</td></tr>';
            });
            mhtml += (d.top_manga||[]).length ? '' : '<tr><td colspan="5" style="text-align:center;color:#999;">Sin datos</td></tr>';
            document.getElementById('tbl-top-manga').innerHTML = mhtml + '</tbody></table>';

            // Top users table
            var uhtml = '<table class="bcs-table"><thead><tr><th>#</th><th>Usuario</th><th>Desbloques</th><th>Monedas</th></tr></thead><tbody>';
            (d.top_users||[]).forEach(function(u,i){
                uhtml += '<tr><td>'+(i+1)+'</td><td>'+esc(u.display_name||'—')+'</td>'
                    +'<td style="text-align:center">'+fmt(u.unlocks)+'</td>'
                    +'<td class="bcs-coins-val">🪙 '+fmt(u.coins)+'</td></tr>';
            });
            uhtml += (d.top_users||[]).length ? '' : '<tr><td colspan="4" style="text-align:center;color:#999;">Sin datos</td></tr>';
            document.getElementById('tbl-top-users').innerHTML = uhtml + '</tbody></table>';

            // Scan groups
            var shtml = '<table class="bcs-table"><thead><tr><th>Grupo</th><th>Mangas</th><th>Desbloques</th><th>Monedas</th></tr></thead><tbody>';
            (d.by_scan||[]).forEach(function(s){
                shtml += '<tr><td><strong>'+esc(s.scan_group_name||'—')+'</strong></td>'
                    +'<td style="text-align:center">'+fmt(s.mangas)+'</td>'
                    +'<td style="text-align:center">'+fmt(s.unlocks)+'</td>'
                    +'<td class="bcs-coins-val">🪙 '+fmt(s.coins)+'</td></tr>';
            });
            shtml += (d.by_scan||[]).length ? '' : '<tr><td colspan="4" style="text-align:center;color:#999;">Sin datos</td></tr>';
            document.getElementById('tbl-by-scan').innerHTML = shtml + '</tbody></table>';

            // Store movements for the movements tab
            bcsMovements = d.movements || [];
            renderMovements();
        });
    }

    // Movements tab
    document.getElementById('bcs-mv-refresh').addEventListener('click', function(){
        bcsLoadDashboard(bcsCurrentPeriod);
    });
    document.getElementById('bcs-mv-search').addEventListener('input', renderMovements);
    document.getElementById('bcs-mv-type').addEventListener('change', renderMovements);

    function renderMovements() {
        var search = document.getElementById('bcs-mv-search').value.toLowerCase();
        var type   = document.getElementById('bcs-mv-type').value;
        var rows   = bcsMovements.filter(function(m){
            if (type && m.transaction_type !== type) return false;
            if (search) {
                var s = ((m.display_name||'') + ' ' + m.transaction_type + ' ' + (m.description||'')).toLowerCase();
                if (s.indexOf(search) === -1) return false;
            }
            return true;
        });

        var typeLabels = {
            'purchase': 'Recarga', 'chapter_unlock': 'Desbloqueo',
            'admin_add': 'Admin +', 'admin_deduct': 'Admin −'
        };

        var html = '<table class="bcs-table" style="min-width:700px;">'
            + '<thead><tr><th>Fecha</th><th>Usuario</th><th>Tipo</th><th>Monedas</th><th>Detalle</th></tr></thead><tbody>';
        rows.forEach(function(m) {
            var pos   = parseInt(m.coins_amount) >= 0;
            var cls   = 'bcs-mv-type-' + m.transaction_type.replace(/[^a-z_]/g,'');
            var amtCls = pos ? 'bcs-mv-pos' : 'bcs-mv-neg';
            var sign   = pos ? '+' : '';
            var label  = typeLabels[m.transaction_type] || m.transaction_type;
            html += '<tr>'
                + '<td style="white-space:nowrap;font-size:12px;color:#777;">' + m.created_at.substring(0,16) + '</td>'
                + '<td>' + esc(m.display_name||'ID:'+m.user_id) + '</td>'
                + '<td><span class="' + cls + '">' + esc(label) + '</span></td>'
                + '<td class="' + amtCls + '">' + sign + parseInt(m.coins_amount).toLocaleString() + ' 🪙</td>'
                + '<td style="font-size:12px;color:#555;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                + esc(m.description||'—') + '</td>'
                + '</tr>';
        });
        html += rows.length ? '' : '<tr><td colspan="5" style="text-align:center;color:#999;padding:20px;">Sin movimientos para los filtros seleccionados.</td></tr>';
        document.getElementById('bcs-movements-table').innerHTML = html + '</tbody></table>';
    }

    // Reporte por manga
    function bcsLoadReport(period) {
        document.querySelectorAll('#bcs-tab-reporte .bcs-pbtn').forEach(function(b){
            b.classList.toggle('active', b.dataset.days === period);
        });
        ['bcs-report-totals','bcs-report-manga','bcs-report-scan'].forEach(function(id){
            document.getElementById(id).innerHTML = '<span style="color:#999;">⏳</span>';
        });
        jQuery.post(ajaxurl, { action: 'msg_revenue_report', period: period }, function(r) {
            if (!r.success) return;
            var d = r.data;
            function fmt(n){ return parseInt(n||0).toLocaleString(); }

            document.getElementById('bcs-report-totals').innerHTML =
                '<div class="bcs-stat-chip"><div class="n">'+fmt(d.totals&&d.totals.total_unlocks)+'</div><div class="l">Desbloques</div></div>' +
                '<div class="bcs-stat-chip"><div class="n">🪙 '+fmt(d.totals&&d.totals.total_coins)+'</div><div class="l">Monedas generadas</div></div>';

            var mh = '<table class="bcs-table"><thead><tr><th>#</th><th>Manga</th><th>Scan Group</th><th style="text-align:center">Desbloques</th><th style="text-align:right">Monedas</th></tr></thead><tbody>';
            (d.by_manga||[]).forEach(function(m,i){
                mh += '<tr><td>'+(i+1)+'</td><td><strong>'+esc(m.manga_title||'ID:'+m.manga_id)+'</strong></td>'
                    +'<td>'+esc(m.scan_group_name||'—')+'</td>'
                    +'<td style="text-align:center">'+fmt(m.total_unlocks)+'</td>'
                    +'<td style="text-align:right" class="bcs-coins-val">🪙 '+fmt(m.total_coins)+'</td></tr>';
            });
            document.getElementById('bcs-report-manga').innerHTML = mh + '</tbody></table>';

            var sh = '<table class="bcs-table"><thead><tr><th>#</th><th>Grupo</th><th style="text-align:center">Mangas</th><th style="text-align:center">Desbloques</th><th style="text-align:right">Monedas</th></tr></thead><tbody>';
            (d.by_scan||[]).forEach(function(s,i){
                sh += '<tr><td>'+(i+1)+'</td><td><strong>'+esc(s.scan_group_name||'ID:'+s.scan_group_id)+'</strong></td>'
                    +'<td style="text-align:center">'+fmt(s.total_mangas)+'</td>'
                    +'<td style="text-align:center">'+fmt(s.total_unlocks)+'</td>'
                    +'<td style="text-align:right" class="bcs-coins-val">🪙 '+fmt(s.total_coins)+'</td></tr>';
            });
            document.getElementById('bcs-report-scan').innerHTML = sh + '</tbody></table>';
        });
    }

    // Form agregar/quitar
    document.getElementById('bcs-coins-form').addEventListener('submit', function(e){
        e.preventDefault();
        var btn = this.querySelector('button[type=submit]');
        var res = document.getElementById('bcs-result');
        btn.disabled = true; btn.textContent = '⏳ Procesando…';
        res.className = ''; res.textContent = '';
        jQuery.post(ajaxurl, jQuery(this).serialize() + '&action=bcs_admin_add_coins', function(r){
            res.className = r.success ? 'ok' : 'err';
            res.textContent = r.success ? '✅ ' + r.data.message : '❌ ' + (r.data&&r.data.message||'Error');
            if (r.success) document.getElementById('bcs-coins-form').reset();
        }).fail(function(){ res.className='err'; res.textContent='❌ Error de conexión.'; })
          .always(function(){ btn.disabled=false; btn.textContent='💰 Procesar'; });
    });

    function esc(s) {
        return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    </script>
    <?php
}
