<?php
/**
 * Sistema de Monedas - VERSIÓN ESTABLE
 */

if (!defined('ABSPATH')) {
    exit;
}

class MSG_Coins_System {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        // Crear tablas
        add_action('init', array($this, 'maybe_create_tables'));
        add_action('init', array($this, 'maybe_migrate_coins_tables'), 20);

        // Meta box para bloquear capítulos
        add_action('add_meta_boxes', array($this, 'add_chapter_lock_metabox'));
        add_action('save_post', array($this, 'save_chapter_lock_meta'), 10, 2);

        // AJAX
        add_action('wp_ajax_unlock_chapter',      array($this, 'ajax_unlock_chapter'));
        add_action('wp_ajax_msg_revenue_report',  array($this, 'ajax_revenue_report'));

        // Shortcodes
        add_shortcode('buy_coins_page', array($this, 'render_buy_coins_page'));

        // Auto-inyectar contenido en /buy-coins/ aunque no tenga shortcode
        add_filter('the_content', array($this, 'auto_inject_buy_coins_page'), 5);

        // Webhook PayPal
        add_action('wp_ajax_nopriv_paypal_ipn', array($this, 'handle_paypal_ipn'));
        add_action('wp_ajax_paypal_ipn',        array($this, 'handle_paypal_ipn'));

        // Bloqueo de capítulos — prioridad 1 para correr antes que el tema
        add_action('template_redirect', array($this, 'block_locked_chapter_access'), 1);

        // Filtro para agregar icono en títulos
        add_filter('the_title', array($this, 'add_coin_icon_to_title'), 10, 2);

        // Inyectar mapa de capítulos bloqueados en el footer (para JS de iconos)
        add_action('wp_footer', array($this, 'inject_locked_chapters_data'), 5);
    }

    /**
     * Migración: agrega manga_id y scan_group_id a chapter_purchases si no existen.
     */
    public function maybe_migrate_coins_tables() {
        global $wpdb;
        $table = $wpdb->prefix . 'chapter_purchases';
        $cols  = $wpdb->get_col("SHOW COLUMNS FROM $table", 0);
        if (!$cols) return;
        if (!in_array('manga_id', $cols)) {
            $wpdb->query("ALTER TABLE $table ADD COLUMN manga_id bigint(20) DEFAULT NULL, ADD KEY manga_id (manga_id)");
        }
        if (!in_array('scan_group_id', $cols)) {
            $wpdb->query("ALTER TABLE $table ADD COLUMN scan_group_id bigint(20) DEFAULT NULL, ADD KEY sg_id (scan_group_id)");
        }
        if (!in_array('scan_group_name', $cols)) {
            $wpdb->query("ALTER TABLE $table ADD COLUMN scan_group_name varchar(200) DEFAULT NULL");
        }
    }
    
    public function maybe_create_tables() {
        if (get_option('msg_coins_tables_created')) {
            return;
        }
        $this->create_coins_tables();
    }
    
    public function create_coins_tables() {
        global $wpdb;
        $charset_collate = $wpdb->get_charset_collate();
        
        $table_wallet = $wpdb->prefix . 'user_wallet';
        $sql_wallet = "CREATE TABLE IF NOT EXISTS $table_wallet (
            id bigint(20) NOT NULL AUTO_INCREMENT,
            user_id bigint(20) NOT NULL,
            coins_balance bigint(20) NOT NULL DEFAULT 0,
            last_updated datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY user_id (user_id)
        ) $charset_collate;";
        
        $table_purchases = $wpdb->prefix . 'chapter_purchases';
        $sql_purchases = "CREATE TABLE IF NOT EXISTS $table_purchases (
            id bigint(20) NOT NULL AUTO_INCREMENT,
            user_id bigint(20) NOT NULL,
            chapter_id bigint(20) NOT NULL,
            coins_spent int(11) NOT NULL,
            purchase_date datetime DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY user_chapter (user_id, chapter_id)
        ) $charset_collate;";
        
        $table_transactions = $wpdb->prefix . 'coin_transactions';
        $sql_transactions = "CREATE TABLE IF NOT EXISTS $table_transactions (
            id bigint(20) NOT NULL AUTO_INCREMENT,
            user_id bigint(20) NOT NULL,
            transaction_type varchar(50) NOT NULL,
            coins_amount int(11) NOT NULL,
            payment_amount decimal(10,2) DEFAULT NULL,
            payment_id varchar(255) DEFAULT NULL,
            payment_status varchar(50) DEFAULT 'pending',
            description text,
            created_at datetime DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY user_id (user_id),
            KEY payment_id (payment_id)
        ) $charset_collate;";
        
        require_once(ABSPATH . 'wp-admin/includes/upgrade.php');
        dbDelta($sql_wallet);
        dbDelta($sql_purchases);
        dbDelta($sql_transactions);
        
        update_option('msg_coins_tables_created', '1');
    }
    
    /**
     * ICONO AUTOMÁTICO - Agregar 🪙 al título
     */
    public function add_coin_icon_to_title($title, $post_id = null) {
        if (!$post_id || is_admin()) return $title;

        // No duplicar en vista singular
        if (is_singular() && get_the_ID() == $post_id) return $title;

        $is_locked = get_post_meta($post_id, '_msg_chapter_locked', true);
        if ($is_locked !== '1') return $title;

        // ¿Se liberó por tiempo? → no mostrar icono
        if ($this->chapter_is_free_by_time($post_id)) return $title;

        // ¿El usuario ya lo compró? → no mostrar icono
        if (is_user_logged_in() && $this->user_has_purchased(get_current_user_id(), $post_id)) {
            return $title;
        }

        $coin_price = get_post_meta($post_id, '_msg_coin_price', true) ?: 100;
        $free_after = (int) get_post_meta($post_id, '_msg_free_after_days', true);

        // Calcular tiempo restante para liberarse
        $countdown = '';
        if ($free_after > 0) {
            $pub_date   = get_post_field('post_date', $post_id);
            $free_ts    = strtotime($pub_date) + ($free_after * 86400);
            $remaining  = $free_ts - time();
            if ($remaining > 0) {
                $days_left  = ceil($remaining / 86400);
                $countdown  = ' <span class="msg-coin-timer" title="Gratis en ' . $days_left . ' días">' . $days_left . 'd</span>';
            }
        }

        if (strpos($title, 'msg-coin-badge') === false) {
            $title .= ' <span class="msg-coin-badge" title="' . $coin_price . ' monedas">🪙</span>' . $countdown;
        }

        return $title;
    }
    
    public function add_chapter_lock_metabox() {
        $post_types = array('post', 'wp-manga-chapter', 'manga_chapter', 'chapter');
        
        foreach ($post_types as $post_type) {
            add_meta_box(
                'msg_chapter_lock',
                '🪙 Bloqueo con Monedas',
                array($this, 'render_chapter_lock_metabox'),
                $post_type,
                'side',
                'high'
            );
        }
    }
    
    public function render_chapter_lock_metabox($post) {
        wp_nonce_field('msg_chapter_lock_nonce', 'msg_chapter_lock_nonce');

        $is_locked    = get_post_meta($post->ID, '_msg_chapter_locked', true);
        $coin_price   = get_post_meta($post->ID, '_msg_coin_price', true) ?: 100;
        $free_after   = (int)get_post_meta($post->ID, '_msg_free_after_days', true);
        $is_admin     = current_user_can('administrator');
        $pub_date     = get_post_field('post_date', $post->ID);
        $is_published = in_array(get_post_status($post->ID), ['publish','future']);

        // Calcular fecha de liberación si aplica
        $free_date_formatted = '';
        $free_date_input     = '';
        if ($free_after > 0 && $pub_date) {
            $free_ts = strtotime($pub_date) + ($free_after * 86400);
            $free_date_formatted = date('d/m/Y H:i', $free_ts);
            $free_date_input     = date('Y-m-d', $free_ts);
        }
        ?>
<style>
.mcl-box { font-family:-apple-system,BlinkMacSystemFont,sans-serif; }
.mcl-toggle-row { display:flex; align-items:center; gap:10px; padding:12px 0; border-bottom:1px solid #e0e0e0; margin-bottom:14px; }
.mcl-toggle { position:relative; display:inline-block; width:44px; height:24px; }
.mcl-toggle input { opacity:0; width:0; height:0; }
.mcl-slider { position:absolute; inset:0; background:#ccc; border-radius:24px; cursor:pointer; transition:.2s; }
.mcl-toggle input:checked + .mcl-slider { background:#6C63FF; }
.mcl-slider::before { content:''; position:absolute; height:18px; width:18px; left:3px; bottom:3px; background:#fff; border-radius:50%; transition:.2s; }
.mcl-toggle input:checked + .mcl-slider::before { transform:translateX(20px); }
.mcl-toggle-label { font-size:13px; font-weight:700; color:#1a1a2e; }
.mcl-price-row { display:flex; align-items:center; gap:8px; margin-bottom:14px; }
.mcl-price-icon { font-size:20px; }
.mcl-price-input { width:100px; padding:6px 10px; border:1px solid #ddd; border-radius:8px; font-size:15px; font-weight:700; color:#1a1a2e; }
.mcl-price-lbl { font-size:12px; color:#888; }
.mcl-divider { border:none; border-top:1px solid #eee; margin:14px 0; }
.mcl-section-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#888; margin-bottom:10px; }
.mcl-calendar-card { border:1px solid #e0e0e0; border-radius:10px; overflow:hidden; margin-bottom:12px; }
.mcl-calendar-header { background:linear-gradient(135deg,#6C63FF,#9B59B6); color:#fff; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; }
.mcl-calendar-header span { font-size:13px; font-weight:700; }
.mcl-calendar-body { padding:12px 14px; background:#f9f9ff; }
.mcl-date-options { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }
.mcl-date-chip { padding:5px 11px; border:1px solid #ddd; border-radius:20px; font-size:12px; font-weight:600; cursor:pointer; background:#fff; transition:all .15s; color:#555; }
.mcl-date-chip:hover,.mcl-date-chip.active { background:#6C63FF; border-color:#6C63FF; color:#fff; }
.mcl-date-input-row { display:flex; align-items:center; gap:8px; }
.mcl-date-input-row label { font-size:12px; color:#888; white-space:nowrap; }
.mcl-days-input { width:70px; padding:5px 8px; border:1px solid #ddd; border-radius:8px; font-size:13px; font-weight:700; text-align:center; }
.mcl-free-date-badge { background:linear-gradient(135deg,#4ADE80,#22c55e); color:#fff; border-radius:8px; padding:8px 12px; font-size:12px; font-weight:700; margin-top:8px; display:flex; align-items:center; gap:6px; }
.mcl-locked-badge { background:rgba(108,99,255,.1); border:1px solid rgba(108,99,255,.25); color:#6C63FF; border-radius:8px; padding:8px 12px; font-size:12px; font-weight:700; margin-top:8px; display:flex; align-items:center; gap:6px; }
.mcl-hint { font-size:11px; color:#aaa; margin-top:6px; }
.mcl-readonly-note { font-size:11px; color:#999; font-style:italic; }
</style>

<div class="mcl-box">
    <!-- Toggle principal -->
    <div class="mcl-toggle-row">
        <label class="mcl-toggle">
            <input type="checkbox" name="_msg_chapter_locked" value="1" id="mcl-lock-toggle"
                   <?php checked($is_locked, '1'); ?>
                   onchange="mclUpdateVisibility()">
            <span class="mcl-slider"></span>
        </label>
        <span class="mcl-toggle-label">🔒 Capítulo de pago</span>
    </div>

    <div id="mcl-locked-options" style="<?php echo $is_locked!=='1'?'display:none':''; ?>">

        <!-- Precio -->
        <div class="mcl-section-title">Precio en BloomCoins</div>
        <div class="mcl-price-row">
            <span class="mcl-price-icon">🪙</span>
            <?php if ($is_admin): ?>
            <input type="number" name="_msg_coin_price" id="mcl-price" class="mcl-price-input"
                   value="<?php echo esc_attr($coin_price); ?>" min="1" max="99999">
            <?php else: ?>
            <input type="number" value="<?php echo esc_attr($coin_price); ?>" class="mcl-price-input" readonly style="background:#f0f0f0;">
            <input type="hidden" name="_msg_coin_price" value="<?php echo esc_attr($coin_price); ?>">
            <?php endif; ?>
            <span class="mcl-price-lbl">BloomCoins</span>
        </div>

        <hr class="mcl-divider">

        <!-- Calendario de liberación -->
        <div class="mcl-section-title">⏳ Liberación automática</div>
        <?php if ($is_admin): ?>
        <div class="mcl-calendar-card">
            <div class="mcl-calendar-header">
                <span>📅 ¿Cuándo se libera gratis?</span>
                <?php if ($free_date_formatted): ?>
                <span style="font-size:11px;opacity:.85;">→ <?php echo $free_date_formatted; ?></span>
                <?php endif; ?>
            </div>
            <div class="mcl-calendar-body">
                <p style="font-size:11px;color:#666;margin:0 0 8px;">Elige cuántos días después de la publicación el capítulo se libera gratis:</p>
                <div class="mcl-date-options">
                    <span class="mcl-date-chip <?php echo $free_after===0?'active':''; ?>" onclick="mclSetDays(0,this)">🔒 Nunca</span>
                    <span class="mcl-date-chip <?php echo $free_after===7?'active':''; ?>" onclick="mclSetDays(7,this)">7 días</span>
                    <span class="mcl-date-chip <?php echo $free_after===14?'active':''; ?>" onclick="mclSetDays(14,this)">14 días</span>
                    <span class="mcl-date-chip <?php echo $free_after===30?'active':''; ?>" onclick="mclSetDays(30,this)">30 días</span>
                    <span class="mcl-date-chip <?php echo $free_after===60?'active':''; ?>" onclick="mclSetDays(60,this)">60 días</span>
                    <span class="mcl-date-chip <?php echo !in_array($free_after,[0,7,14,30,60])&&$free_after>0?'active':''; ?>" onclick="mclSetDays(-1,this)">✏️ Personalizado</span>
                </div>
                <div class="mcl-date-input-row" id="mcl-custom-days-row" style="<?php echo !in_array($free_after,[0,7,14,30,60])&&$free_after>0?'':'display:none'; ?>">
                    <label>Días:</label>
                    <input type="number" id="mcl-custom-days-val" class="mcl-days-input" min="1" max="999"
                           value="<?php echo $free_after>0?esc_attr($free_after):''; ?>"
                           oninput="mclUpdateFreeDate(this.value)">
                </div>
                <input type="hidden" name="_msg_free_after_days" id="mcl-free-after" value="<?php echo esc_attr($free_after); ?>">

                <?php if ($free_date_formatted && $free_after > 0): ?>
                <div class="mcl-free-date-badge" id="mcl-free-badge">
                    ✅ Se libera el <?php echo $free_date_formatted; ?>
                    <?php
                    $remaining = strtotime($pub_date) + ($free_after*86400) - time();
                    if ($remaining > 0) echo '(en ' . ceil($remaining/86400) . ' días)';
                    else echo '(¡Ya libre!)';
                    ?>
                </div>
                <?php elseif ($free_after === 0): ?>
                <div class="mcl-locked-badge" id="mcl-free-badge">🔒 Siempre de pago — no se libera automáticamente</div>
                <?php else: ?>
                <div id="mcl-free-badge" style="display:none;"></div>
                <?php endif; ?>

            </div>
        </div>
        <?php else: ?>
        <p class="mcl-readonly-note">Solo los administradores pueden configurar la fecha de liberación.</p>
        <input type="hidden" name="_msg_free_after_days" value="<?php echo esc_attr($free_after); ?>">
        <?php endif; ?>

        <p class="mcl-hint">El ícono 🪙 aparecerá automáticamente en la lista de capítulos del manga.</p>
    </div>
</div>

<script>
function mclUpdateVisibility() {
    var locked = document.getElementById('mcl-lock-toggle').checked;
    document.getElementById('mcl-locked-options').style.display = locked ? 'block' : 'none';
}
function mclSetDays(days, chip) {
    document.querySelectorAll('.mcl-date-chip').forEach(function(c){ c.classList.remove('active'); });
    chip.classList.add('active');
    var customRow = document.getElementById('mcl-custom-days-row');
    var hidden    = document.getElementById('mcl-free-after');
    if (days === -1) {
        customRow.style.display = 'flex';
    } else {
        customRow.style.display = 'none';
        hidden.value = days;
        mclUpdateBadge(days);
    }
}
function mclUpdateFreeDate(val) {
    document.getElementById('mcl-free-after').value = val || 0;
    mclUpdateBadge(parseInt(val)||0);
}
function mclUpdateBadge(days) {
    var badge = document.getElementById('mcl-free-badge');
    if (!badge) return;
    if (days <= 0) {
        badge.className = 'mcl-locked-badge';
        badge.innerHTML = '🔒 Siempre de pago — no se libera automáticamente';
        badge.style.display = 'flex';
    } else {
        badge.className = 'mcl-free-date-badge';
        badge.innerHTML = '⏳ Se liberará ~' + days + ' días después de la publicación';
        badge.style.display = 'flex';
    }
}
</script>
        <?php
    }

        public function save_chapter_lock_meta($post_id, $post) {
        if (!isset($_POST['msg_chapter_lock_nonce'])) return;
        if (!wp_verify_nonce($_POST['msg_chapter_lock_nonce'], 'msg_chapter_lock_nonce')) return;
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
        if (!current_user_can('edit_post', $post_id)) return;

        $is_locked = isset($_POST['_msg_chapter_locked']) ? '1' : '0';
        update_post_meta($post_id, '_msg_chapter_locked', $is_locked);

        if (current_user_can('administrator')) {
            $coin_price = absint($_POST['_msg_coin_price'] ?? 100);
            if ($coin_price < 1) $coin_price = 100;
            update_post_meta($post_id, '_msg_coin_price', $coin_price);

            $free_after = absint($_POST['_msg_free_after_days'] ?? 0);
            update_post_meta($post_id, '_msg_free_after_days', $free_after);
        }
    }
    
    public function get_user_balance($user_id) {
        global $wpdb;
        $table = $wpdb->prefix . 'user_wallet';
        
        $balance = $wpdb->get_var($wpdb->prepare(
            "SELECT coins_balance FROM $table WHERE user_id = %d",
            $user_id
        ));
        
        return $balance ? intval($balance) : 0;
    }
    
    public function add_coins($user_id, $coins, $payment_amount = 0, $payment_id = '', $description = '') {
        global $wpdb;
        $wallet_table = $wpdb->prefix . 'user_wallet';
        $tx_table = $wpdb->prefix . 'coin_transactions';
        
        $wpdb->query($wpdb->prepare(
            "INSERT INTO $wallet_table (user_id, coins_balance) VALUES (%d, %d) 
             ON DUPLICATE KEY UPDATE coins_balance = coins_balance + %d",
            $user_id, $coins, $coins
        ));
        
        $wpdb->insert($tx_table, array(
            'user_id' => $user_id,
            'transaction_type' => 'purchase',
            'coins_amount' => $coins,
            'payment_amount' => $payment_amount,
            'payment_id' => $payment_id,
            'payment_status' => 'completed',
            'description' => $description
        ));
        
        return true;
    }
    
    public function user_has_purchased($user_id, $chapter_id) {
        // Verificar si el capítulo ya se liberó por tiempo
        if ($this->chapter_is_free_by_time($chapter_id)) {
            return true;
        }
        global $wpdb;
        $table = $wpdb->prefix . 'chapter_purchases';
        $purchased = $wpdb->get_var($wpdb->prepare(
            "SELECT id FROM $table WHERE user_id = %d AND chapter_id = %d",
            $user_id, $chapter_id
        ));
        return !empty($purchased);
    }

    /**
     * Verifica si el capítulo se liberó gratis por haber pasado X días.
     */
    public function chapter_is_free_by_time(int $chapter_id): bool {
        $free_after = (int) get_post_meta($chapter_id, '_msg_free_after_days', true);
        if ($free_after <= 0) return false;

        $pub_date = get_post_field('post_date', $chapter_id);
        if (!$pub_date) return false;

        $free_timestamp = strtotime($pub_date) + ($free_after * 86400);
        return time() >= $free_timestamp;
    }
    
    public function block_locked_chapter_access() {
        // Funciona en cualquier post singular
        if (!is_singular()) return;
        global $post;
        if (!$post) return;

        $is_locked = get_post_meta($post->ID, '_msg_chapter_locked', true);
        if ($is_locked !== '1') return;

        // Solo los super-admins (manage_options) pueden ver todo sin pagar
        // Nota: los admins normales también deben pagar para ver el flujo real
        if (current_user_can('manage_options')) return;

        // ¿Se liberó por tiempo?
        if ($this->chapter_is_free_by_time($post->ID)) return;

        // ¿Ya lo compró?
        if (is_user_logged_in() && $this->user_has_purchased(get_current_user_id(), $post->ID)) return;

        // Interceptar toda la salida del tema con output buffering
        // Esto garantiza el bloqueo incluso si el tema llama template_redirect antes
        ob_start(function($output) use ($post) {
            return ''; // Descartar todo el output del tema
        });

        // Limpiar buffer y mostrar página de bloqueo
        ob_end_clean();
        $this->render_blocked_page($post->ID);
        exit;
    }
    
    private function render_blocked_page($chapter_id) {
        $coin_price = (int) get_post_meta($chapter_id, '_msg_coin_price', true);
        if ($coin_price < 1) $coin_price = 100;

        $chapter_title  = get_the_title($chapter_id);
        $manga_id       = (int) get_post_meta($chapter_id, 'ero_seri', true);
        $manga_url      = $manga_id ? get_permalink($manga_id) : home_url('/');
        $manga_title    = $manga_id ? get_the_title($manga_id) : '';

        $user_logged_in = is_user_logged_in();
        $user_id        = $user_logged_in ? get_current_user_id() : 0;
        $user_balance   = $user_id ? $this->get_user_balance($user_id) : 0;
        $has_enough     = $user_balance >= $coin_price;

        $ajax_url       = admin_url('admin-ajax.php');
        $nonce          = $user_id ? wp_create_nonce('unlock_chapter_' . $user_id) : '';
        $login_url      = wp_login_url(get_permalink($chapter_id));
        $buy_url        = home_url('/buy-coins');

        // Enviar headers correctos antes de output
        if (!headers_sent()) {
            status_header(200);
            header('Content-Type: text/html; charset=UTF-8');
        }
        ?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Capítulo de pago — <?php echo esc_html($chapter_title); ?></title>
    <?php wp_head(); ?>
    <style>
    html, body {
        margin: 0; padding: 0;
        background: #0a0e1a !important;
        color: #fff;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    * { box-sizing: border-box; }

    .bcs-wall {
        width: 100%;
        max-width: 520px;
        margin: 20px auto;
        padding: 20px;
        text-align: center;
    }
    .bcs-manga-back {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #aaa;
        text-decoration: none;
        font-size: 13px;
        margin-bottom: 28px;
        transition: color .2s;
    }
    .bcs-manga-back:hover { color: #00d4aa; }

    .bcs-lock-icon {
        width: 80px; height: 80px;
        background: linear-gradient(135deg, #1a2540, #0f1626);
        border: 2px solid rgba(0,212,170,.3);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 36px;
        margin: 0 auto 24px;
    }
    .bcs-wall h1 {
        font-size: 20px;
        font-weight: 700;
        margin: 0 0 6px;
        color: #fff;
    }
    .bcs-wall .bcs-subtitle {
        font-size: 14px;
        color: #8892a4;
        margin: 0 0 28px;
    }

    .bcs-price-card {
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
        border: 1px solid rgba(0,212,170,.35);
        border-radius: 18px;
        padding: 28px 24px;
        margin-bottom: 20px;
    }
    .bcs-price-label { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #8892a4; margin-bottom: 8px; }
    .bcs-price-value { font-size: 52px; font-weight: 900; color: #00d4aa; line-height: 1; margin-bottom: 4px; }
    .bcs-price-unit  { font-size: 14px; color: #8892a4; }

    .bcs-balance-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: rgba(255,255,255,.04);
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 12px;
        padding: 14px 18px;
        margin: 16px 0;
        font-size: 14px;
    }
    .bcs-balance-row .bcs-bal-lbl { color: #8892a4; }
    .bcs-balance-row .bcs-bal-val { font-weight: 700; font-size: 16px; }
    .bcs-balance-row .bcs-bal-ok  { color: #00d4aa; }
    .bcs-balance-row .bcs-bal-low { color: #ff6b6b; }

    .bcs-btn {
        display: block;
        width: 100%;
        padding: 16px 24px;
        border: none;
        border-radius: 14px;
        font-size: 16px;
        font-weight: 700;
        cursor: pointer;
        text-decoration: none;
        text-align: center;
        transition: all .25s;
        margin-top: 12px;
    }
    .bcs-btn-primary {
        background: linear-gradient(135deg, #00d4aa, #00a896);
        color: #fff;
    }
    .bcs-btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,212,170,.35); color: #fff; }
    .bcs-btn-primary:disabled { opacity: .6; cursor: not-allowed; transform: none; }
    .bcs-btn-secondary {
        background: rgba(255,255,255,.06);
        border: 1px solid rgba(255,255,255,.12);
        color: #ccc;
    }
    .bcs-btn-secondary:hover { background: rgba(255,255,255,.1); color: #fff; }

    .bcs-warn { color: #ff6b6b; font-size: 13px; margin: 10px 0 0; }
    .bcs-msg  { margin: 12px 0; font-size: 14px; padding: 12px; border-radius: 10px; display: none; }
    .bcs-msg.ok  { background: rgba(0,212,170,.15); border: 1px solid rgba(0,212,170,.3); color: #00d4aa; }
    .bcs-msg.err { background: rgba(255,107,107,.15); border: 1px solid rgba(255,107,107,.3); color: #ff6b6b; }
    </style>
</head>
<body>
<div class="bcs-wall">

    <?php if ($manga_url && $manga_title): ?>
    <a href="<?php echo esc_url($manga_url); ?>" class="bcs-manga-back">
        ← <?php echo esc_html($manga_title); ?>
    </a>
    <?php endif; ?>

    <div class="bcs-lock-icon">🔒</div>
    <h1><?php echo esc_html($chapter_title); ?></h1>
    <p class="bcs-subtitle">Este capítulo es exclusivo para suscriptores con monedas</p>

    <div class="bcs-price-card">
        <div class="bcs-price-label">Precio de desbloqueo</div>
        <div class="bcs-price-value">🪙 <?php echo number_format($coin_price); ?></div>
        <div class="bcs-price-unit">monedas</div>

        <?php if ($user_logged_in): ?>
        <div class="bcs-balance-row">
            <span class="bcs-bal-lbl">Tu saldo</span>
            <span class="bcs-bal-val <?php echo $has_enough ? 'bcs-bal-ok' : 'bcs-bal-low'; ?>">
                🪙 <?php echo number_format($user_balance); ?>
            </span>
        </div>
        <?php endif; ?>
    </div>

    <div class="bcs-msg" id="bcs-msg"></div>

    <?php if ($user_logged_in): ?>
        <?php if ($has_enough): ?>
            <button class="bcs-btn bcs-btn-primary" id="bcs-unlock-btn" onclick="bcsUnlock()">
                💳 Desbloquear por <?php echo number_format($coin_price); ?> 🪙
            </button>
        <?php else: ?>
            <p class="bcs-warn">⚠️ No tienes suficientes monedas</p>
            <a href="<?php echo esc_url($buy_url); ?>" class="bcs-btn bcs-btn-primary">💰 Comprar Monedas</a>
        <?php endif; ?>
        <a href="<?php echo esc_url($manga_url ?: home_url('/')); ?>" class="bcs-btn bcs-btn-secondary">← Volver al manga</a>
    <?php else: ?>
        <a href="<?php echo esc_url($login_url); ?>" class="bcs-btn bcs-btn-primary">🔐 Iniciar sesión para desbloquear</a>
        <a href="<?php echo esc_url($manga_url ?: home_url('/')); ?>" class="bcs-btn bcs-btn-secondary">← Volver al manga</a>
    <?php endif; ?>
</div>

<script>
function bcsUnlock() {
    var btn = document.getElementById('bcs-unlock-btn');
    var msg = document.getElementById('bcs-msg');
    if (!confirm('¿Desbloquear este capítulo por <?php echo (int)$coin_price; ?> monedas?')) return;

    btn.disabled = true;
    btn.textContent = '⏳ Procesando...';
    msg.className = 'bcs-msg'; msg.style.display = 'none';

    var body = new URLSearchParams({
        action:     'unlock_chapter',
        chapter_id: '<?php echo (int)$chapter_id; ?>',
        nonce:      '<?php echo esc_js($nonce); ?>'
    });

    fetch('<?php echo esc_url($ajax_url); ?>', {
        method:  'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body:    body.toString()
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            msg.className = 'bcs-msg ok';
            msg.textContent = '✅ ¡Capítulo desbloqueado! Redirigiendo...';
            msg.style.display = 'block';
            setTimeout(function() { location.reload(); }, 1200);
        } else {
            msg.className = 'bcs-msg err';
            msg.textContent = '❌ ' + (data.data ? data.data.message : 'Error al desbloquear');
            msg.style.display = 'block';
            btn.disabled = false;
            btn.textContent = '💳 Desbloquear por <?php echo (int)$coin_price; ?> 🪙';
        }
    })
    .catch(function() {
        msg.className = 'bcs-msg err';
        msg.textContent = '❌ Error de conexión. Intenta de nuevo.';
        msg.style.display = 'block';
        btn.disabled = false;
        btn.textContent = '💳 Desbloquear por <?php echo (int)$coin_price; ?> 🪙';
    });
}
</script>
<?php wp_footer(); ?>
</body>
</html>
        <?php
    }
    
    public function ajax_unlock_chapter() {
        $user_id = get_current_user_id();
        if (!$user_id) {
            wp_send_json_error(array('message' => 'Inicia sesión'));
        }
        
        $chapter_id = absint($_POST['chapter_id']);
        $nonce = sanitize_text_field($_POST['nonce']);
        
        if (!wp_verify_nonce($nonce, 'unlock_chapter_' . $user_id)) {
            wp_send_json_error(array('message' => 'Nonce inválido'));
        }
        
        $coin_price = get_post_meta($chapter_id, '_msg_coin_price', true);
        if (empty($coin_price)) $coin_price = 100;
        
        $balance = $this->get_user_balance($user_id);
        
        if ($balance < $coin_price) {
            wp_send_json_error(array('message' => 'Saldo insuficiente'));
        }
        
        global $wpdb;
        $wallet_table = $wpdb->prefix . 'user_wallet';
        $purchases_table = $wpdb->prefix . 'chapter_purchases';
        $tx_table = $wpdb->prefix . 'coin_transactions';
        
        $wpdb->update($wallet_table, 
            array('coins_balance' => $balance - $coin_price), 
            array('user_id' => $user_id)
        );
        
        // Obtener manga padre y scan group para el reporte
        $manga_id       = (int) get_post_meta($chapter_id, 'ero_seri', true);
        $scan_group_id   = null;
        $scan_group_name = null;
        if ($manga_id) {
            $terms = wp_get_object_terms($manga_id, 'scan_group', ['fields' => 'all']);
            if (!empty($terms) && !is_wp_error($terms)) {
                $scan_group_id   = $terms[0]->term_id;
                $scan_group_name = $terms[0]->name;
            } else {
                // Fallback: buscar por autor del capítulo
                $author_id = (int) get_post_field('post_author', $chapter_id);
                $scan = get_user_meta($author_id, 'msg_scan_group_id', true);
                if ($scan) { $scan_group_id = $scan; }
            }
        }

        $wpdb->insert($purchases_table, array(
            'user_id'         => $user_id,
            'chapter_id'      => $chapter_id,
            'coins_spent'     => $coin_price,
            'manga_id'        => $manga_id ?: null,
            'scan_group_id'   => $scan_group_id,
            'scan_group_name' => $scan_group_name,
        ));

        $wpdb->insert($tx_table, array(
            'user_id'          => $user_id,
            'transaction_type' => 'chapter_unlock',
            'coins_amount'     => -$coin_price,
            'payment_status'   => 'completed',
            'description'      => 'Desbloqueo capítulo ID: ' . $chapter_id
        ));
        
        wp_send_json_success(array('message' => 'Desbloqueado'));
    }
    
    public function handle_paypal_ipn() {
        error_log('[PayPal IPN] Recibido');
        
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            status_header(405);
            die('Method not allowed');
        }
        
        $payment_status = isset($_POST['payment_status']) ? sanitize_text_field($_POST['payment_status']) : '';
        $txn_id = isset($_POST['txn_id']) ? sanitize_text_field($_POST['txn_id']) : '';
        $payer_email = isset($_POST['payer_email']) ? sanitize_email($_POST['payer_email']) : '';
        $mc_gross = isset($_POST['mc_gross']) ? floatval($_POST['mc_gross']) : 0;
        
        if ($payment_status !== 'Completed') {
            status_header(200);
            die('Not completed');
        }
        
        $user = get_user_by('email', $payer_email);
        if (!$user) {
            error_log('[PayPal IPN] Usuario no encontrado');
            status_header(200);
            die('User not found');
        }
        
        global $wpdb;
        $tx_table = $wpdb->prefix . 'coin_transactions';
        $existing = $wpdb->get_var($wpdb->prepare(
            "SELECT id FROM $tx_table WHERE payment_id = %s",
            $txn_id
        ));
        
        if ($existing) {
            status_header(200);
            die('Duplicate');
        }
        
        $coins = 0;
        if ($mc_gross == 1) $coins = 100;
        elseif ($mc_gross == 10) $coins = 1000;
        elseif ($mc_gross == 20) $coins = 2000;
        
        if ($coins == 0) {
            status_header(200);
            die('Invalid amount');
        }
        
        $this->add_coins($user->ID, $coins, $mc_gross, $txn_id, "PayPal automático - $mc_gross USD");
        
        error_log("[PayPal IPN] ✅ $coins monedas → usuario #{$user->ID}");
        
        status_header(200);
        die('OK');
    }
    
    public function render_buy_coins_page() {
        ob_start();
        include MSG_PLUGIN_DIR . 'templates/buy-coins-page-DEFINITIVO.php';
        return ob_get_clean();
    }

    /* ══════════════════════════════════════════════════
       FEATURE 4 — REPORTE DE INGRESOS (AJAX)
    ══════════════════════════════════════════════════ */

    /**
     * Devuelve reporte de monedas generadas por manga y por scan.
     * Solo accesible para administradores.
     */
    public function ajax_revenue_report() {
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => 'Sin permisos']);
        }
        global $wpdb;
        $purchases = $wpdb->prefix . 'chapter_purchases';

        $period = sanitize_text_field($_POST['period'] ?? 'all');
        $where  = '';
        if ($period === '30d') $where = "WHERE cp.purchase_date >= DATE_SUB(NOW(), INTERVAL 30 DAY)";
        if ($period === '7d')  $where = "WHERE cp.purchase_date >= DATE_SUB(NOW(), INTERVAL 7 DAY)";

        // ── Por manga ──────────────────────────────────────────────
        $by_manga = $wpdb->get_results(
            "SELECT
                cp.manga_id,
                p.post_title   AS manga_title,
                cp.scan_group_name,
                COUNT(*)        AS total_unlocks,
                SUM(cp.coins_spent) AS total_coins
             FROM $purchases cp
             LEFT JOIN {$wpdb->posts} p ON p.ID = cp.manga_id
             $where
             GROUP BY cp.manga_id
             ORDER BY total_coins DESC
             LIMIT 50"
        );

        // ── Por scan group ──────────────────────────────────────────
        $where_scan = $where
            ? "$where AND cp.scan_group_id IS NOT NULL"
            : "WHERE cp.scan_group_id IS NOT NULL";

        $by_scan = $wpdb->get_results(
            "SELECT
                cp.scan_group_id,
                cp.scan_group_name,
                COUNT(DISTINCT cp.manga_id) AS total_mangas,
                COUNT(*)                    AS total_unlocks,
                SUM(cp.coins_spent)         AS total_coins
             FROM $purchases cp
             $where_scan
             GROUP BY cp.scan_group_id
             ORDER BY total_coins DESC"
        );

        // ── Totales globales ────────────────────────────────────────
        $totals = $wpdb->get_row(
            "SELECT COUNT(*) AS total_unlocks, SUM(coins_spent) AS total_coins FROM $purchases $where"
        );

        wp_send_json_success([
            'by_manga'       => $by_manga,
            'by_scan'        => $by_scan,
            'totals'         => $totals,
            'period'         => $period,
        ]);
    }

    /**
     * Inyecta en el footer un mapa JSON de capítulos bloqueados para que el JS
     * del tema pueda mostrar el ícono 🪙 junto a cada capítulo en la lista.
     * También marca con CSS las filas bloqueadas.
     */
    public function inject_locked_chapters_data() {
        if (is_admin()) return;

        // Solo en páginas de manga singular o taxonomías de manga
        global $post;
        $manga_id = 0;
        if (is_singular()) {
            // Podría ser la página del manga
            if ($post && $post->post_type === 'manga') {
                $manga_id = $post->ID;
            }
            // O podría ser una página de capítulo — obtener su manga padre
            if ($post && $post->post_type === 'post') {
                $manga_id = (int) get_post_meta($post->ID, 'ero_seri', true);
            }
        }

        // Si no encontramos manga_id, intentar con el post actual
        if (!$manga_id && $post) {
            $manga_id = (int) get_post_meta($post->ID, 'ero_seri', true);
        }

        if (!$manga_id) return;

        global $wpdb;
        $user_id = get_current_user_id();

        // Obtener todos los capítulos bloqueados del manga
        $chapters = $wpdb->get_results($wpdb->prepare(
            "SELECT p.ID, p.post_title,
                    pm_price.meta_value AS price,
                    pm_free.meta_value  AS free_after,
                    p.post_date
             FROM {$wpdb->posts} p
             INNER JOIN {$wpdb->postmeta} pm_lock
                ON pm_lock.post_id = p.ID
               AND pm_lock.meta_key = '_msg_chapter_locked'
               AND pm_lock.meta_value = '1'
             LEFT JOIN {$wpdb->postmeta} pm_price
                ON pm_price.post_id = p.ID
               AND pm_price.meta_key = '_msg_coin_price'
             LEFT JOIN {$wpdb->postmeta} pm_free
                ON pm_free.post_id  = p.ID
               AND pm_free.meta_key = '_msg_free_after_days'
             LEFT JOIN {$wpdb->postmeta} pm_seri
                ON pm_seri.post_id  = p.ID
               AND pm_seri.meta_key = 'ero_seri'
             WHERE pm_seri.meta_value = %d
               AND p.post_status = 'publish'",
            $manga_id
        ));

        if (empty($chapters)) return;

        $locked_map  = []; // chapter_url => price  (for matching by href)
        $locked_ids  = []; // post_id => price        (for matching by ?p=ID)

        foreach ($chapters as $ch) {
            // Skip if already free by time
            if ($this->chapter_is_free_by_time($ch->ID)) continue;
            // Skip if user already purchased
            if ($user_id && $this->user_has_purchased($user_id, $ch->ID)) continue;

            $price = max(1, (int)($ch->price ?: 100));
            $permalink = get_permalink($ch->ID);

            $locked_ids[$ch->ID]   = $price;
            $locked_map[$permalink] = $price;
        }

        if (empty($locked_ids)) return;

        $json_ids = wp_json_encode($locked_ids);
        $json_map = wp_json_encode($locked_map);

        echo '<style>
.bcs-locked-li .chapternum { position: relative; }
.bcs-coin-chip {
    display: inline-flex; align-items: center; gap: 2px;
    background: linear-gradient(135deg, rgba(0,212,170,.2), rgba(0,168,150,.1));
    border: 1px solid rgba(0,212,170,.45);
    color: #00d4aa; font-size: 10px; font-weight: 800;
    padding: 2px 7px; border-radius: 20px;
    margin-left: 6px; vertical-align: middle;
    white-space: nowrap; letter-spacing: .4px;
    cursor: default;
}
</style>
<script>
(function() {
    var lockedIds  = ' . $json_ids . ';
    var lockedUrls = ' . $json_map . ';

    function normalizeUrl(u) {
        try { return new URL(u).pathname + new URL(u).search; } catch(e) { return u; }
    }

    // Build normalized url map
    var normalizedMap = {};
    Object.keys(lockedUrls).forEach(function(u) {
        normalizedMap[normalizeUrl(u)] = lockedUrls[u];
    });

    function markLocked() {
        var items = document.querySelectorAll(
            "#chapterlist li, .eplister li, .bxcl li, .clstyle li, " +
            ".chbox, .eph-num"
        );
        items.forEach(function(li) {
            var a = li.tagName === "A" ? li : li.querySelector("a");
            if (!a) return;
            var href = a.getAttribute("href") || "";

            var price = null;

            // Match by normalized URL
            var norm = normalizeUrl(href);
            if (normalizedMap[norm] !== undefined) {
                price = normalizedMap[norm];
            }

            // Match by ?p=ID in URL
            if (price === null) {
                var m = href.match(/[?&]p=(\d+)/);
                if (m && lockedIds[m[1]] !== undefined) {
                    price = lockedIds[m[1]];
                }
            }

            // Match by data-id attribute
            if (price === null) {
                var did = li.getAttribute("data-id") || li.getAttribute("data-chapter-id");
                if (did && lockedIds[did] !== undefined) {
                    price = lockedIds[did];
                }
            }

            if (price === null) return;

            // Tag the li as locked
            var parentLi = li.closest("li") || li;
            parentLi.classList.add("bcs-locked-li");

            // Add chip to chapternum span
            var numEl = parentLi.querySelector(".chapternum");
            if (numEl && !numEl.querySelector(".bcs-coin-chip")) {
                numEl.insertAdjacentHTML("beforeend",
                    "<span class=\"bcs-coin-chip\">🪙 " + price + "</span>"
                );
            } else if (!numEl) {
                // Fallback: insert after the link text
                if (a && !a.querySelector(".bcs-coin-chip")) {
                    a.insertAdjacentHTML("beforeend",
                        " <span class=\"bcs-coin-chip\">🪙 " + price + "</span>"
                    );
                }
            }
        });
    }

    // Run at multiple timings to catch AJAX-loaded lists
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", markLocked);
    } else {
        markLocked();
    }
    setTimeout(markLocked, 500);
    setTimeout(markLocked, 1500);
    setTimeout(markLocked, 3000);

    // Also observe DOM mutations (for infinite scroll / AJAX loads)
    if (window.MutationObserver) {
        var obs = new MutationObserver(function(mutations) {
            var relevant = mutations.some(function(m) {
                return m.addedNodes.length > 0;
            });
            if (relevant) markLocked();
        });
        document.addEventListener("DOMContentLoaded", function() {
            var target = document.getElementById("chapterlist") || document.body;
            obs.observe(target, { childList: true, subtree: true });
        });
    }
})();
</script>' . "\n";
    }

    /**
     * Auto-inyectar la página de compra de monedas en /buy-coins/
     * Funciona aunque la página de WordPress no tenga el shortcode manualmente.
     */
    public function auto_inject_buy_coins_page($content) {
        if (!is_page()) return $content;
        global $post;
        if (!$post) return $content;
        // Detectar por slug o por shortcode ya presente
        $slug = $post->post_name;
        if ($slug !== 'buy-coins' && $slug !== 'compra-coins' && $slug !== 'comprar-coins') {
            return $content;
        }
        // Si el shortcode ya está en el contenido, dejar que lo procese normalmente
        if (has_shortcode($post->post_content, 'buy_coins_page')) {
            return $content;
        }
        // Inyectar directamente
        return $this->render_buy_coins_page();
    }

}

MSG_Coins_System::get_instance();