<?php
/**
 * Página de Compra de Monedas — BloomScans
 * Template para shortcode [buy_coins_page] y auto-inyección en /buy-coins/
 */
if (!defined('ABSPATH')) exit;

$user_id   = get_current_user_id();
$logged_in = is_user_logged_in();
$cs        = MSG_Coins_System::get_instance();
$balance   = $logged_in ? $cs->get_user_balance($user_id) : 0;

global $wpdb;
$purchases_table    = $wpdb->prefix . 'chapter_purchases';
$transactions_table = $wpdb->prefix . 'coin_transactions';

$recent_chapters = $logged_in ? $wpdb->get_results($wpdb->prepare(
    "SELECT cp.coins_spent, cp.purchase_date, p.post_title as chapter_title
     FROM $purchases_table cp
     LEFT JOIN {$wpdb->posts} p ON p.ID = cp.chapter_id
     WHERE cp.user_id = %d ORDER BY cp.purchase_date DESC LIMIT 8",
    $user_id
)) : [];

$recent_tx = $logged_in ? $wpdb->get_results($wpdb->prepare(
    "SELECT * FROM $transactions_table WHERE user_id = %d ORDER BY created_at DESC LIMIT 8",
    $user_id
)) : [];

$packages = [
    ['emoji'=>'🌱','name'=>'Básico',  'coins'=>100,  'price'=>1,  'popular'=>false],
    ['emoji'=>'⭐','name'=>'Popular', 'coins'=>600,  'price'=>5,  'popular'=>true],
    ['emoji'=>'💎','name'=>'Premium', 'coins'=>1400, 'price'=>10, 'popular'=>false],
    ['emoji'=>'👑','name'=>'VIP',     'coins'=>3000, 'price'=>20, 'popular'=>false],
];

$plugin_url = defined('BCS_PLUGIN_URL') ? BCS_PLUGIN_URL : '';
$ajax_url   = admin_url('admin-ajax.php');
?>
<style>
.bcp-wrap {
    font-family: -apple-system, 'Segoe UI', sans-serif;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px 16px 48px;
    color: #e2e8f0;
}

/* ── HERO ── */
.bcp-hero {
    text-align: center;
    padding: 36px 20px 28px;
    position: relative;
    overflow: hidden;
}
.bcp-hero::before {
    content: '';
    position: absolute;
    top: -40px; left: 50%; transform: translateX(-50%);
    width: 500px; height: 260px;
    background: radial-gradient(ellipse, rgba(0,212,170,.18) 0%, transparent 70%);
    pointer-events: none;
}
.bcp-hero-coin { font-size: 56px; display: block; margin-bottom: 14px; filter: drop-shadow(0 0 24px rgba(0,212,170,.5)); }
.bcp-hero h1 {
    font-size: 30px; font-weight: 800; margin: 0 0 8px;
    background: linear-gradient(135deg, #00d4aa, #00fff5);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.bcp-hero p { color: rgba(255,255,255,.45); font-size: 14px; margin: 0; }

/* ── BALANCE (si está logueado) ── */
.bcp-balance-card {
    display: flex; align-items: center; justify-content: center; gap: 16px;
    background: rgba(0,212,170,.07);
    border: 1px solid rgba(0,212,170,.22);
    border-radius: 16px;
    padding: 16px 28px;
    margin: 0 auto 32px;
    max-width: 340px;
}
.bcp-bal-ico { font-size: 36px; }
.bcp-bal-num { font-size: 32px; font-weight: 800; color: #00d4aa; line-height: 1; }
.bcp-bal-lbl { font-size: 11px; color: rgba(255,255,255,.4); text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }

/* ── PAQUETES ── */
.bcp-section-title {
    font-size: 13px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; color: rgba(255,255,255,.4);
    margin: 0 0 16px; padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,.07);
}
.bcp-packages {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-bottom: 36px;
}
.bcp-pkg {
    background: #13151f;
    border: 1px solid rgba(255,255,255,.07);
    border-radius: 20px;
    padding: 26px 18px 20px;
    text-align: center;
    position: relative;
    transition: all .22s;
    cursor: pointer;
}
.bcp-pkg:hover {
    transform: translateY(-4px);
    border-color: rgba(0,212,170,.35);
    box-shadow: 0 12px 40px rgba(0,212,170,.15);
}
.bcp-pkg.popular {
    border-color: rgba(0,212,170,.45);
    background: linear-gradient(145deg, #141924, #182025);
}
.bcp-pkg-badge {
    position: absolute; top: -11px; left: 50%; transform: translateX(-50%);
    background: linear-gradient(135deg, #00d4aa, #00a896);
    color: #000; font-size: 9.5px; font-weight: 800;
    padding: 3px 14px; border-radius: 20px;
    white-space: nowrap; letter-spacing: .06em;
}
.bcp-pkg-emoji { font-size: 34px; display: block; margin-bottom: 10px; }
.bcp-pkg-name  { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: rgba(255,255,255,.45); margin-bottom: 8px; }
.bcp-pkg-coins { font-size: 40px; font-weight: 800; color: #fff; line-height: 1; margin-bottom: 2px; }
.bcp-pkg-coins-sub { font-size: 12px; color: rgba(255,255,255,.3); margin-bottom: 14px; }
.bcp-pkg-price { font-size: 22px; font-weight: 800; color: #00d4aa; margin-bottom: 18px; }
.bcp-pkg-price sup { font-size: 13px; vertical-align: top; margin-top: 4px; }
.bcp-pkg-btn {
    width: 100%; padding: 11px;
    border: none; border-radius: 11px;
    font-size: 13px; font-weight: 700; cursor: pointer;
    transition: all .2s;
    background: rgba(0,212,170,.12);
    border: 1px solid rgba(0,212,170,.28);
    color: #00d4aa;
}
.bcp-pkg:not(.popular) .bcp-pkg-btn:hover { background: rgba(0,212,170,.22); color: #fff; }
.bcp-pkg.popular .bcp-pkg-btn {
    background: linear-gradient(135deg, #00d4aa, #00a896);
    border-color: transparent; color: #000;
    box-shadow: 0 4px 16px rgba(0,212,170,.35);
}
.bcp-pkg.popular .bcp-pkg-btn:hover { transform: scale(1.03); box-shadow: 0 6px 24px rgba(0,212,170,.5); }

/* ── CARACTERÍSTICAS ── */
.bcp-features {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 10px;
    margin-bottom: 36px;
}
.bcp-feat {
    background: #13151f;
    border: 1px solid rgba(255,255,255,.06);
    border-radius: 14px;
    padding: 14px 16px;
    display: flex; align-items: center; gap: 12px;
}
.bcp-feat-ico { font-size: 22px; flex-shrink: 0; }
.bcp-feat-txt { font-size: 12.5px; color: rgba(255,255,255,.65); line-height: 1.4; }
.bcp-feat-txt strong { color: #fff; font-weight: 700; display: block; }

/* ── HISTORIAL (solo si está logueado) ── */
.bcp-history { margin-bottom: 32px; }
.bcp-history-tabs { display: flex; gap: 8px; margin-bottom: 14px; }
.bcp-htab {
    padding: 7px 16px;
    background: rgba(255,255,255,.05);
    border: 1px solid rgba(255,255,255,.09);
    border-radius: 20px;
    color: rgba(255,255,255,.5); font-size: 12.5px; font-weight: 600;
    cursor: pointer; transition: all .18s;
}
.bcp-htab.active {
    background: rgba(0,212,170,.12);
    border-color: rgba(0,212,170,.35);
    color: #00d4aa;
}
.bcp-hcontent { display: none; }
.bcp-hcontent.active { display: block; }
.bcp-hrow {
    display: flex; align-items: center; gap: 10px;
    background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.06);
    border-radius: 10px; padding: 10px 13px; margin-bottom: 7px;
    font-size: 12.5px;
}
.bcp-hr-ico { font-size: 18px; flex-shrink: 0; }
.bcp-hr-info { flex: 1; min-width: 0; }
.bcp-hr-name { color: #fff; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bcp-hr-date { font-size: 10.5px; color: rgba(255,255,255,.3); margin-top: 1px; }
.bcp-hr-amount { font-weight: 700; color: #00d4aa; white-space: nowrap; }
.bcp-hr-amount.neg { color: #fc8181; }
.bcp-empty { text-align: center; padding: 28px 10px; color: rgba(255,255,255,.25); font-size: 13px; }

/* ── FAQ ── */
.bcp-faq-item {
    background: #13151f; border: 1px solid rgba(255,255,255,.06);
    border-radius: 12px; margin-bottom: 8px; overflow: hidden;
}
.bcp-faq-q {
    padding: 13px 16px; cursor: pointer;
    font-size: 13.5px; font-weight: 600; color: rgba(255,255,255,.8);
    display: flex; justify-content: space-between; align-items: center;
    user-select: none;
}
.bcp-faq-q span { transition: transform .2s; }
.bcp-faq-q.open span { transform: rotate(180deg); }
.bcp-faq-a { display: none; padding: 0 16px 14px; font-size: 13px; color: rgba(255,255,255,.5); line-height: 1.6; }

/* ── CTA NO LOGUEADO ── */
.bcp-login-cta {
    text-align: center; padding: 40px 20px;
    background: #13151f; border: 1px solid rgba(0,212,170,.2);
    border-radius: 20px; margin-bottom: 32px;
}
.bcp-login-cta h2 { font-size: 22px; font-weight: 800; color: #fff; margin: 0 0 8px; }
.bcp-login-cta p { color: rgba(255,255,255,.45); font-size: 14px; margin: 0 0 20px; }
.bcp-login-btn {
    display: inline-block; padding: 12px 28px;
    background: linear-gradient(135deg, #00d4aa, #00a896);
    color: #000; font-weight: 800; font-size: 14px;
    border-radius: 12px; text-decoration: none;
    box-shadow: 0 4px 16px rgba(0,212,170,.35);
}
.bcp-login-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 24px rgba(0,212,170,.5); color: #000; }

@media (max-width: 480px) {
    .bcp-hero h1 { font-size: 24px; }
    .bcp-packages { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 340px) {
    .bcp-packages { grid-template-columns: 1fr; }
}
</style>

<div class="bcp-wrap">

    <!-- HERO -->
    <div class="bcp-hero">
        <span class="bcp-hero-coin">🪙</span>
        <h1>Compra Bloom Coins</h1>
        <p>Desbloquea capítulos premium al instante · Las monedas nunca expiran</p>
    </div>

    <?php if ($logged_in): ?>
    <!-- BALANCE -->
    <div class="bcp-balance-card">
        <span class="bcp-bal-ico">🪙</span>
        <div>
            <div class="bcp-bal-num"><?php echo number_format($balance); ?></div>
            <div class="bcp-bal-lbl">Tus monedas</div>
        </div>
    </div>
    <?php endif; ?>

    <!-- PAQUETES -->
    <div class="bcp-section-title">💳 Elige tu paquete</div>
    <div class="bcp-packages">
        <?php foreach ($packages as $pkg): ?>
        <div class="bcp-pkg<?php echo $pkg['popular'] ? ' popular' : ''; ?>">
            <?php if ($pkg['popular']): ?>
            <div class="bcp-pkg-badge">⭐ MÁS POPULAR</div>
            <?php endif; ?>
            <span class="bcp-pkg-emoji"><?php echo $pkg['emoji']; ?></span>
            <div class="bcp-pkg-name"><?php echo esc_html($pkg['name']); ?></div>
            <div class="bcp-pkg-coins"><?php echo number_format($pkg['coins']); ?></div>
            <div class="bcp-pkg-coins-sub">🪙 Bloom Coins</div>
            <div class="bcp-pkg-price"><sup>$</sup><?php echo $pkg['price']; ?> <small style="font-size:12px;color:rgba(255,255,255,.3);font-weight:400">USD</small></div>
            <?php if ($logged_in): ?>
            <button class="bcp-pkg-btn" onclick="bcpBuy(<?php echo $pkg['coins']; ?>, <?php echo $pkg['price']; ?>)">
                Comprar ahora
            </button>
            <?php else: ?>
            <a href="<?php echo esc_url(home_url('/mi-cuenta')); ?>" class="bcp-pkg-btn" style="display:block;text-align:center;text-decoration:none;">
                Iniciar sesión
            </a>
            <?php endif; ?>
        </div>
        <?php endforeach; ?>
    </div>

    <!-- CARACTERÍSTICAS -->
    <div class="bcp-features">
        <div class="bcp-feat">
            <span class="bcp-feat-ico">⚡</span>
            <div class="bcp-feat-txt"><strong>Entrega inmediata</strong>Las monedas aparecen en tu cuenta en segundos.</div>
        </div>
        <div class="bcp-feat">
            <span class="bcp-feat-ico">♾️</span>
            <div class="bcp-feat-txt"><strong>Sin vencimiento</strong>Tus monedas nunca caducan, úsalas cuando quieras.</div>
        </div>
        <div class="bcp-feat">
            <span class="bcp-feat-ico">📖</span>
            <div class="bcp-feat-txt"><strong>Acceso permanente</strong>Un capítulo comprado siempre estará disponible.</div>
        </div>
        <div class="bcp-feat">
            <span class="bcp-feat-ico">❤️</span>
            <div class="bcp-feat-txt"><strong>Apoya al grupo</strong>Cada compra va directo a los traductores.</div>
        </div>
    </div>

    <?php if (!$logged_in): ?>
    <!-- CTA para no logueados -->
    <div class="bcp-login-cta">
        <h2>¿Listo para desbloquear?</h2>
        <p>Crea una cuenta gratis para comprar monedas y acceder a todos los capítulos premium.</p>
        <a href="<?php echo esc_url(home_url('/mi-cuenta')); ?>" class="bcp-login-btn">
            Crear cuenta / Iniciar sesión
        </a>
    </div>
    <?php endif; ?>

    <?php if ($logged_in): ?>
    <!-- HISTORIAL -->
    <div class="bcp-section-title">📊 Tu historial</div>
    <div class="bcp-history">
        <div class="bcp-history-tabs">
            <button class="bcp-htab active" onclick="bcpTab('tx', this)">Transacciones</button>
            <button class="bcp-htab" onclick="bcpTab('ch', this)">Capítulos</button>
        </div>

        <div id="bcp-tab-tx" class="bcp-hcontent active">
            <?php if (empty($recent_tx)): ?>
            <div class="bcp-empty">💸 Aún no tienes transacciones</div>
            <?php else: foreach ($recent_tx as $tx):
                $sign  = $tx->coins_amount > 0 ? '+' : '';
                $cls   = $tx->coins_amount > 0 ? '' : ' neg';
                $icon  = $tx->transaction_type === 'purchase' ? '💳' : '📖';
            ?>
            <div class="bcp-hrow">
                <span class="bcp-hr-ico"><?php echo $icon; ?></span>
                <div class="bcp-hr-info">
                    <div class="bcp-hr-name"><?php echo esc_html(mb_substr($tx->description, 0, 40)); ?></div>
                    <div class="bcp-hr-date"><?php echo date_i18n('d M Y', strtotime($tx->created_at)); ?></div>
                </div>
                <span class="bcp-hr-amount<?php echo $cls; ?>"><?php echo $sign . number_format($tx->coins_amount); ?> 🪙</span>
            </div>
            <?php endforeach; endif; ?>
        </div>

        <div id="bcp-tab-ch" class="bcp-hcontent">
            <?php if (empty($recent_chapters)): ?>
            <div class="bcp-empty">📚 Aún no has comprado capítulos</div>
            <?php else: foreach ($recent_chapters as $ch): ?>
            <div class="bcp-hrow">
                <span class="bcp-hr-ico">📖</span>
                <div class="bcp-hr-info">
                    <div class="bcp-hr-name"><?php echo esc_html(mb_substr($ch->chapter_title ?: 'Capítulo', 0, 40)); ?></div>
                    <div class="bcp-hr-date"><?php echo date_i18n('d M Y', strtotime($ch->purchase_date)); ?></div>
                </div>
                <span class="bcp-hr-amount"><?php echo number_format($ch->coins_spent); ?> 🪙</span>
            </div>
            <?php endforeach; endif; ?>
        </div>
    </div>
    <?php endif; ?>

    <!-- FAQ -->
    <div class="bcp-section-title">❓ Preguntas frecuentes</div>
    <div class="bcp-faq">
        <?php $faqs = [
            ['¿Cómo se realizan los pagos?','Aceptamos PayPal. Escanea el código QR con la app de PayPal para completar tu pago de forma segura.'],
            ['¿Cuánto tarda en acreditarse?','Las monedas se acreditan automáticamente en segundos tras confirmarse el pago. Si hay algún problema, guarda tu ID de compra y contáctanos.'],
            ['¿Las monedas vencen?','¡No! Tus Bloom Coins nunca expiran. Puedes usarlas en cualquier momento, sin presión.'],
            ['¿Puedo pedir reembolso?','Los capítulos ya desbloqueados no son reembolsables. Sin embargo, si hubo un error en el pago, contáctanos con tu ID de compra.'],
            ['¿Qué pasa si cierro sesión?','Tus monedas y capítulos comprados quedan guardados en tu cuenta para siempre.'],
        ]; foreach ($faqs as $i => $faq): ?>
        <div class="bcp-faq-item">
            <div class="bcp-faq-q" onclick="bcpFaq(this)">
                <?php echo esc_html($faq[0]); ?> <span>▾</span>
            </div>
            <div class="bcp-faq-a"><?php echo esc_html($faq[1]); ?></div>
        </div>
        <?php endforeach; ?>
    </div>

</div><!-- .bcp-wrap -->

<script>
(function() {
    /* ── Tab switcher ── */
    window.bcpTab = function(id, btn) {
        document.querySelectorAll('.bcp-hcontent').forEach(function(el) { el.classList.remove('active'); });
        document.querySelectorAll('.bcp-htab').forEach(function(el) { el.classList.remove('active'); });
        document.getElementById('bcp-tab-' + id).classList.add('active');
        btn.classList.add('active');
    };

    /* ── FAQ accordion ── */
    window.bcpFaq = function(q) {
        var a = q.nextElementSibling;
        var isOpen = q.classList.contains('open');
        // cerrar todos
        document.querySelectorAll('.bcp-faq-q').forEach(function(el) {
            el.classList.remove('open');
            el.nextElementSibling.style.display = 'none';
        });
        if (!isOpen) {
            q.classList.add('open');
            a.style.display = 'block';
        }
    };

    /* ── Comprar (reutiliza msgBuyFromMenu si existe, sino modal propio) ── */
    window.bcpBuy = function(coins, price) {
        if (typeof window.msgBuyFromMenu === 'function') {
            window.msgBuyFromMenu(coins, price);
            return;
        }
        // Modal propio (fallback)
        var userId = <?php echo $logged_in ? (int)$user_id : 0; ?>;
        var ts = Date.now();
        var rand = Math.random().toString(36).substring(2, 8);
        var purchaseId = 'PAY_' + userId + '_' + price + '_' + ts + '_' + rand;

        var qrImage = '<?php echo esc_js($plugin_url); ?>assets/paypal-qr-1usd.png';
        if (price == 5)  qrImage = '<?php echo esc_js($plugin_url); ?>assets/paypal-qr-1usd.png';
        if (price == 10) qrImage = '<?php echo esc_js($plugin_url); ?>assets/paypal-qr-10usd.png';
        if (price == 20) qrImage = '<?php echo esc_js($plugin_url); ?>assets/paypal-qr-20usd.png';

        var old = document.getElementById('bcp-buy-modal');
        if (old) old.remove();

        var modal = document.createElement('div');
        modal.id = 'bcp-buy-modal';
        modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.88);backdrop-filter:blur(6px);z-index:1000010;display:flex;align-items:center;justify-content:center;padding:16px;';
        modal.innerHTML =
            '<div style="background:#1a1f2e;border:1px solid rgba(0,212,170,.3);padding:28px;border-radius:20px;max-width:420px;width:100%;text-align:center;position:relative;box-shadow:0 24px 80px rgba(0,0,0,.7);">' +
            '<button onclick="document.getElementById(\'bcp-buy-modal\').remove()" style="position:absolute;top:12px;right:14px;background:none;border:none;color:rgba(255,255,255,.4);font-size:22px;cursor:pointer;">✕</button>' +
            '<div style="font-size:44px;margin-bottom:12px;">🪙</div>' +
            '<h3 style="color:#fff;font-size:20px;margin:0 0 6px;">Confirmar Compra</h3>' +
            '<p style="color:rgba(255,255,255,.45);font-size:13px;margin:0 0 18px;"><strong style="color:#00d4aa;">🪙 ' + coins.toLocaleString() + ' monedas</strong> por <strong style="color:#fff;">$' + price + ' USD</strong></p>' +
            '<div style="background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.2);padding:12px;border-radius:10px;margin-bottom:14px;text-align:left;">' +
            '<p style="color:rgba(255,255,255,.4);font-size:10px;margin:0 0 5px;text-transform:uppercase;letter-spacing:1px;">Tu ID de compra:</p>' +
            '<p style="color:#00d4aa;font-size:11px;word-break:break-all;font-family:monospace;margin:0;background:rgba(0,0,0,.2);padding:7px;border-radius:6px;">' + purchaseId + '</p>' +
            '</div>' +
            '<div style="background:rgba(255,193,7,.1);border:1px solid rgba(255,193,7,.22);padding:9px 12px;border-radius:9px;margin-bottom:18px;">' +
            '<p style="color:#FFC107;margin:0;font-size:11.5px;">⚠️ <strong>Guarda este ID.</strong> Úsalo si hay algún problema.</p>' +
            '</div>' +
            '<div style="display:flex;gap:9px;">' +
            '<button onclick="document.getElementById(\'bcp-buy-modal\').remove()" style="flex:1;padding:11px;background:rgba(255,255,255,.07);color:rgba(255,255,255,.6);border:1px solid rgba(255,255,255,.12);border-radius:10px;font-size:13px;cursor:pointer;">Cancelar</button>' +
            '<button onclick="bcpShowQR(\'' + purchaseId + '\',' + coins + ',' + price + ',\'' + qrImage + '\',' + userId + ')" style="flex:2;padding:11px;background:linear-gradient(135deg,#00d4aa,#00a896);color:#000;border:none;border-radius:10px;font-size:13px;font-weight:800;cursor:pointer;">✅ Continuar al pago</button>' +
            '</div>' +
            '</div>';
        document.body.appendChild(modal);
    };

    window.bcpShowQR = function(purchaseId, coins, price, qrImage, userId) {
        fetch('<?php echo esc_js($ajax_url); ?>', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'action=msg_register_purchase&user_id=' + userId + '&coins=' + coins + '&price=' + price + '&purchase_id=' + encodeURIComponent(purchaseId)
        }).then(function(r){ return r.json(); }).then(function(d){ console.log('[Bloom] Compra registrada:', d); });

        var modal = document.getElementById('bcp-buy-modal');
        if (!modal) return;
        var inner = modal.querySelector('div');
        if (!inner) return;
        inner.innerHTML =
            '<button onclick="document.getElementById(\'bcp-buy-modal\').remove()" style="position:absolute;top:12px;right:14px;background:none;border:none;color:rgba(255,255,255,.4);font-size:22px;cursor:pointer;">✕</button>' +
            '<h3 style="color:#fff;font-size:20px;margin:0 0 8px;">Pagar con PayPal</h3>' +
            '<p style="color:rgba(255,255,255,.6);margin:0 0 14px;font-size:13px;"><strong style="color:#00d4aa;">🪙 ' + coins.toLocaleString() + '</strong> monedas · <strong style="color:#fff;">$' + price + ' USD</strong></p>' +
            '<div style="background:#fff;padding:14px;border-radius:12px;margin-bottom:14px;">' +
            '<img src="' + qrImage + '" style="width:100%;max-width:240px;height:auto;display:block;margin:0 auto;" alt="QR PayPal">' +
            '</div>' +
            '<p style="color:rgba(255,255,255,.7);font-size:13px;margin:0 0 10px;">📱 Escanea con tu app de PayPal</p>' +
            '<div id="bcp-pay-status" style="background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.25);padding:10px;border-radius:9px;margin-bottom:10px;">' +
            '<p style="color:#00d4aa;margin:0;font-size:12.5px;">✅ <strong>Entrega automática</strong> — Las monedas llegarán en segundos</p>' +
            '</div>' +
            '<p style="color:rgba(255,255,255,.2);font-size:10px;margin:0;word-break:break-all;">ID: ' + purchaseId + '</p>';

        var attempts = 0;
        var check = setInterval(function() {
            attempts++;
            fetch('<?php echo esc_js($ajax_url); ?>?action=msg_check_payment_status&purchase_id=' + encodeURIComponent(purchaseId) + '&_=' + Date.now())
                .then(function(r){ return r.json(); })
                .then(function(d) {
                    if (d.success && d.data && d.data.status === 'completed') {
                        clearInterval(check);
                        var sb = document.getElementById('bcp-pay-status');
                        if (sb) sb.innerHTML = '<p style="color:#00d4aa;margin:0;font-size:15px;font-weight:800;">🎉 ¡Pago recibido! +' + coins.toLocaleString() + ' monedas</p>';
                        setTimeout(function() {
                            var m = document.getElementById('bcp-buy-modal');
                            if (m) m.remove();
                            location.reload();
                        }, 2500);
                    } else if (attempts >= 120) clearInterval(check);
                }).catch(function(){});
        }, 5000);
    };
})();
</script>
