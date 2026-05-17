<?php
/**
 * Integración del Sistema de Monedas con el Menú de Usuario
 * COLORES: #1a1f2e (fondo), #00d4aa (verde agua acento)
 */

if (!defined('ABSPATH')) {
    exit;
}

class MSG_Coins_User_Menu_Integration {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        add_action('wp_footer', array($this, 'add_balance_to_user_menu'), 11);
    }
    
    public function add_balance_to_user_menu() {
        if (!is_user_logged_in()) {
            return;
        }
        
        if (!class_exists('MSG_Coins_System')) {
            return;
        }
        
        $user_id = get_current_user_id();
        $coins_system = MSG_Coins_System::get_instance();
        $balance = $coins_system->get_user_balance($user_id);
        
        global $wpdb;
        $transactions_table = $wpdb->prefix . 'coin_transactions';
        $purchases_table = $wpdb->prefix . 'chapter_purchases';
        
        $transactions = $wpdb->get_results($wpdb->prepare(
            "SELECT * FROM $transactions_table WHERE user_id = %d ORDER BY created_at DESC LIMIT 10",
            $user_id
        ));
        
        $chapter_purchases = $wpdb->get_results($wpdb->prepare(
            "SELECT cp.*, p.post_title FROM $purchases_table cp
             LEFT JOIN {$wpdb->posts} p ON cp.chapter_id = p.ID
             WHERE cp.user_id = %d ORDER BY cp.purchase_date DESC LIMIT 10",
            $user_id
        ));
        
        $packages = array(
            array('emoji' => '🌱', 'name' => 'Básico',  'coins' => 100,  'price' => 1),
            array('emoji' => '⭐', 'name' => 'Popular', 'coins' => 600,  'price' => 5),
            array('emoji' => '💎', 'name' => 'Premium', 'coins' => 1400, 'price' => 10),
            array('emoji' => '👑', 'name' => 'VIP',     'coins' => 3000, 'price' => 20),
        );
        ?>
        
        <script>
        (function() {
            // Función global para actualizar saldo
            window.msgUpdateBalance = function() {
                fetch('<?php echo admin_url('admin-ajax.php'); ?>?action=get_user_balance&_=' + Date.now())
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            const balanceEl = document.querySelector('.msg-coins-value');
                            if (balanceEl) {
                                balanceEl.textContent = data.data.balance.toLocaleString();
                                console.log('[Coins] Saldo actualizado:', data.data.balance);
                            }
                        }
                    })
                    .catch(err => console.error('[Coins] Error actualizando saldo:', err));
            };
            
            function addBalanceWidget() {
                const userInfo = document.querySelector('.msg-user-info');
                
                if (!userInfo) {
                    setTimeout(addBalanceWidget, 500);
                    return;
                }
                
                if (document.querySelector('.msg-coins-section')) {
                    return;
                }
                
                const coinsSection = document.createElement('div');
                coinsSection.className = 'msg-coins-section';
                coinsSection.innerHTML = `
                    <div id="msg-coins-main" class="msg-coins-view">
                        <div class="msg-coins-balance-display">
                            <div class="msg-coins-icon">🪙</div>
                            <div class="msg-coins-amount">
                                <span class="msg-coins-label">Tus Monedas</span>
                                <span class="msg-coins-value"><?php echo number_format($balance); ?></span>
                            </div>
                        </div>
                        <div class="msg-coins-buttons">
                            <button class="msg-coin-action-btn" onclick="msgShowCoinsView('buy')">
                                <span class="msg-btn-icon">💳</span>
                                <span>Comprar</span>
                            </button>
                            <button class="msg-coin-action-btn" onclick="msgShowCoinsView('history')">
                                <span class="msg-btn-icon">📊</span>
                                <span>Historial</span>
                            </button>
                        </div>
                    </div>
                    
                    <div id="msg-coins-buy" class="msg-coins-view" style="display: none;">
                        <div class="msg-coins-header">
                            <button class="msg-coins-back" onclick="msgShowCoinsView('main')">← Atrás</button>
                            <h4>Comprar Monedas</h4>
                        </div>
                        <div class="msg-coins-packages">
                            <?php foreach ($packages as $pkg): ?>
                            <div class="msg-coin-package">
                                <div class="msg-pkg-info">
                                    <span class="msg-pkg-coins"><?php echo $pkg['emoji']; ?> 🪙 <?php echo number_format($pkg['coins']); ?> <small style="opacity:.6;font-size:10px"><?php echo esc_html($pkg['name']); ?></small></span>
                                    <span class="msg-pkg-price">$<?php echo $pkg['price']; ?> USD</span>
                                </div>
                                <button class="msg-pkg-buy-btn" onclick="msgBuyFromMenu(<?php echo $pkg['coins']; ?>, <?php echo $pkg['price']; ?>)">
                                    Comprar
                                </button>
                            </div>
                            <?php endforeach; ?>
                        </div>
                        <p class="msg-coins-note">💡 Las monedas nunca expiran · <a href="<?php echo home_url('/buy-coins'); ?>" style="color:#00d4aa;text-decoration:none;">Ver más →</a></p>
                    </div>
                    
                    <div id="msg-coins-history" class="msg-coins-view" style="display: none;">
                        <div class="msg-coins-header">
                            <button class="msg-coins-back" onclick="msgShowCoinsView('main')">← Atrás</button>
                            <h4>Historial</h4>
                        </div>
                        
                        <div class="msg-history-tabs">
                            <button class="msg-history-tab active" onclick="msgShowHistoryTab('tx')">Transacciones</button>
                            <button class="msg-history-tab" onclick="msgShowHistoryTab('ch')">Capítulos</button>
                        </div>
                        
                        <div id="msg-history-tx" class="msg-history-content">
                            <?php if (empty($transactions)): ?>
                                <div class="msg-empty-state">
                                    <div class="msg-empty-icon">💸</div>
                                    <p>Sin transacciones</p>
                                </div>
                            <?php else: ?>
                                <div class="msg-history-list">
                                    <?php foreach ($transactions as $tx): 
                                        $icon = $tx->transaction_type == 'purchase' ? '💳' : '📖';
                                        $sign = $tx->coins_amount > 0 ? '+' : '';
                                        $color = $tx->coins_amount > 0 ? '#00d4aa' : '#ff6b6b';
                                    ?>
                                    <div class="msg-history-row">
                                        <span class="msg-h-icon"><?php echo $icon; ?></span>
                                        <div class="msg-h-info">
                                            <div class="msg-h-desc"><?php echo esc_html(substr($tx->description, 0, 25)); ?>...</div>
                                            <div class="msg-h-date"><?php echo date('d/m/Y', strtotime($tx->created_at)); ?></div>
                                        </div>
                                        <span class="msg-h-amount" style="color: <?php echo $color; ?>">
                                            <?php echo $sign . number_format($tx->coins_amount); ?> 🪙
                                        </span>
                                    </div>
                                    <?php endforeach; ?>
                                </div>
                            <?php endif; ?>
                        </div>
                        
                        <div id="msg-history-ch" class="msg-history-content" style="display: none;">
                            <?php if (empty($chapter_purchases)): ?>
                                <div class="msg-empty-state">
                                    <div class="msg-empty-icon">📚</div>
                                    <p>Sin capítulos</p>
                                </div>
                            <?php else: ?>
                                <div class="msg-history-list">
                                    <?php foreach ($chapter_purchases as $purchase): ?>
                                    <div class="msg-history-row">
                                        <span class="msg-h-icon">📖</span>
                                        <div class="msg-h-info">
                                            <div class="msg-h-desc">
                                                <a href="<?php echo get_permalink($purchase->chapter_id); ?>" style="color: inherit;">
                                                    <?php echo esc_html(substr($purchase->post_title ?: 'Capítulo', 0, 25)); ?>
                                                </a>
                                            </div>
                                            <div class="msg-h-date"><?php echo date('d/m/Y', strtotime($purchase->purchase_date)); ?></div>
                                        </div>
                                        <span class="msg-h-amount" style="color: #00d4aa;">
                                            <?php echo number_format($purchase->coins_spent); ?> 🪙
                                        </span>
                                    </div>
                                    <?php endforeach; ?>
                                </div>
                            <?php endif; ?>
                        </div>
                    </div>
                `;
                
                userInfo.parentElement.insertBefore(coinsSection, userInfo.nextSibling);
            }
            
            window.msgShowCoinsView = function(view) {
                document.getElementById('msg-coins-main').style.display = 'none';
                document.getElementById('msg-coins-buy').style.display = 'none';
                document.getElementById('msg-coins-history').style.display = 'none';
                document.getElementById('msg-coins-' + view).style.display = 'block';
            };
            
            window.msgShowHistoryTab = function(tab) {
                const tabs = document.querySelectorAll('.msg-history-tab');
                tabs.forEach(t => t.classList.remove('active'));
                event.target.classList.add('active');
                
                document.getElementById('msg-history-tx').style.display = 'none';
                document.getElementById('msg-history-ch').style.display = 'none';
                document.getElementById('msg-history-' + tab).style.display = 'block';
            };
            
            window.msgBuyFromMenu = function(coins, price) {
                var userId = <?php echo get_current_user_id(); ?>;
                var timestamp = Date.now();
                var random = Math.random().toString(36).substring(2, 8);
                var purchaseId = 'PAY_' + userId + '_' + price + '_' + timestamp + '_' + random;

                // Seleccionar QR según precio (usar el más cercano disponible)
                var qrImage = '<?php echo BCS_PLUGIN_URL; ?>assets/paypal-qr-1usd.png';
                if (price == 5)  qrImage = '<?php echo BCS_PLUGIN_URL; ?>assets/paypal-qr-1usd.png'; // usar QR $1 para $5
                if (price == 10) qrImage = '<?php echo BCS_PLUGIN_URL; ?>assets/paypal-qr-10usd.png';
                if (price == 20) qrImage = '<?php echo BCS_PLUGIN_URL; ?>assets/paypal-qr-20usd.png';

                var existing = document.getElementById('msg-buy-modal');
                if (existing) existing.remove();

                var modal = document.createElement('div');
                modal.id = 'msg-buy-modal';
                modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:999999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.85);';

                modal.innerHTML =
                    '<div style="background:#1a1f3a;padding:30px;border-radius:16px;max-width:420px;width:90%;text-align:center;position:relative;box-shadow:0 10px 40px rgba(0,0,0,0.5);">' +
                    '<button onclick="document.getElementById(\'msg-buy-modal\').remove()" style="position:absolute;top:12px;right:12px;background:none;border:none;color:#fff;font-size:24px;cursor:pointer;line-height:1;">✕</button>' +
                    '<div style="font-size:44px;margin-bottom:12px;">🪙</div>' +
                    '<h3 style="color:#fff;font-size:20px;margin:0 0 18px 0;">Confirmar Compra</h3>' +
                    '<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);padding:15px;border-radius:10px;margin-bottom:15px;text-align:left;">' +
                    '<div style="display:flex;justify-content:space-between;margin-bottom:8px;"><span style="color:rgba(255,255,255,0.6);font-size:13px;">Monedas:</span><strong style="color:#00d4aa;">🪙 ' + coins.toLocaleString() + '</strong></div>' +
                    '<div style="display:flex;justify-content:space-between;"><span style="color:rgba(255,255,255,0.6);font-size:13px;">Precio:</span><strong style="color:#fff;">$' + price + ' USD</strong></div>' +
                    '</div>' +
                    '<div style="background:rgba(0,212,170,0.08);border:1px solid rgba(0,212,170,0.25);padding:12px;border-radius:8px;margin-bottom:12px;text-align:left;">' +
                    '<p style="color:rgba(255,255,255,0.5);font-size:11px;margin:0 0 6px 0;text-transform:uppercase;letter-spacing:1px;">Tu ID de compra:</p>' +
                    '<p style="color:#00d4aa;font-size:11px;word-break:break-all;font-family:monospace;margin:0;background:rgba(0,0,0,0.2);padding:8px;border-radius:5px;">' + purchaseId + '</p>' +
                    '</div>' +
                    '<div style="background:rgba(255,193,7,0.1);border:1px solid rgba(255,193,7,0.25);padding:10px;border-radius:8px;margin-bottom:18px;">' +
                    '<p style="color:#FFC107;margin:0;font-size:12px;line-height:1.5;">⚠️ <strong>Guarda este ID.</strong> Si hay algún problema, úsalo para reclamar tus monedas.</p>' +
                    '</div>' +
                    '<div style="display:flex;gap:10px;">' +
                    '<button onclick="document.getElementById(\'msg-buy-modal\').remove()" style="flex:1;padding:12px;background:rgba(255,255,255,0.08);color:#fff;border:1px solid rgba(255,255,255,0.15);border-radius:8px;font-size:14px;cursor:pointer;">Cancelar</button>' +
                    '<button onclick="msgBuyShowQR(\'' + purchaseId + '\',' + coins + ',' + price + ',\'' + qrImage + '\',' + userId + ')" style="flex:2;padding:12px;background:linear-gradient(135deg,#00d4aa,#00a896);color:#000;border:none;border-radius:8px;font-size:14px;font-weight:bold;cursor:pointer;">✅ Continuar al pago</button>' +
                    '</div>' +
                    '</div>';

                document.body.appendChild(modal);
            };

            window.msgBuyShowQR = function(purchaseId, coins, price, qrImage, userId) {
                fetch('<?php echo admin_url('admin-ajax.php'); ?>', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: 'action=msg_register_purchase&user_id=' + userId + '&coins=' + coins + '&price=' + price + '&purchase_id=' + encodeURIComponent(purchaseId)
                }).then(function(r){ return r.json(); }).then(function(d){ console.log('[Payment] Registrado:', d); });

                var modal = document.getElementById('msg-buy-modal');
                if (!modal) return;
                var inner = modal.querySelector('div');
                if (!inner) return;

                inner.innerHTML =
                    '<button onclick="document.getElementById(\'msg-buy-modal\').remove()" style="position:absolute;top:12px;right:12px;background:none;border:none;color:#fff;font-size:24px;cursor:pointer;line-height:1;">✕</button>' +
                    '<h3 style="color:#fff;font-size:20px;margin:0 0 10px 0;">Pagar con PayPal</h3>' +
                    '<p style="color:rgba(255,255,255,0.7);margin:0 0 15px 0;"><strong style="color:#00d4aa;">🪙 ' + coins.toLocaleString() + ' monedas</strong> por <strong style="color:#00d4aa;">$' + price + ' USD</strong></p>' +
                    '<div style="background:#fff;padding:15px;border-radius:12px;margin-bottom:15px;">' +
                    '<img src="' + qrImage + '" style="width:100%;max-width:260px;height:auto;display:block;margin:0 auto;" alt="QR PayPal">' +
                    '</div>' +
                    '<p style="color:rgba(255,255,255,0.8);font-size:13px;margin:0 0 12px 0;">📱 Escanea con tu app de PayPal</p>' +
                    '<div id="msg-pay-status" style="background:rgba(76,175,80,0.1);border:1px solid rgba(76,175,80,0.3);padding:12px;border-radius:8px;margin-bottom:12px;">' +
                    '<p style="color:#4CAF50;margin:0;font-size:13px;">✅ <strong>Entrega automática</strong> - Las monedas llegarán en segundos</p>' +
                    '</div>' +
                    '<p style="color:rgba(255,255,255,0.35);font-size:10px;margin:0;word-break:break-all;">ID: ' + purchaseId + '</p>';

                var attempts = 0;
                var check = setInterval(function() {
                    attempts++;
                    fetch('<?php echo admin_url('admin-ajax.php'); ?>?action=msg_check_payment_status&purchase_id=' + encodeURIComponent(purchaseId) + '&_=' + Date.now())
                        .then(function(r){ return r.json(); })
                        .then(function(data) {
                            if (data.success && data.data && data.data.status === 'completed') {
                                clearInterval(check);
                                var statusBox = document.getElementById('msg-pay-status');
                                if (statusBox) {
                                    statusBox.style.background = 'rgba(76,175,80,0.25)';
                                    statusBox.innerHTML = '<p style="color:#4CAF50;margin:0;font-size:15px;font-weight:bold;">🎉 ¡Pago recibido! +' + coins.toLocaleString() + ' monedas agregadas</p>';
                                }
                                setTimeout(function() {
                                    var m = document.getElementById('msg-buy-modal');
                                    if (m) m.remove();
                                    location.reload();
                                }, 2500);
                            } else if (attempts >= 120) {
                                clearInterval(check);
                            }
                        }).catch(function(){});
                }, 5000);
            };
            
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', addBalanceWidget);
            } else {
                addBalanceWidget();
            }
        })();
        </script>
        
        <style>
        .msg-coins-section {
            padding: 0;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            background: linear-gradient(135deg, rgba(0, 212, 170, 0.05) 0%, rgba(0, 212, 170, 0.02) 100%);
        }
        
        .msg-coins-view {
            padding: 20px;
        }
        
        .msg-coins-balance-display {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 15px;
        }
        
        .msg-coins-icon {
            width: 42px;
            height: 42px;
            background: rgba(0, 212, 170, 0.15);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
        }
        
        .msg-coins-amount {
            flex: 1;
        }
        
        .msg-coins-label {
            display: block;
            font-size: 11px;
            color: rgba(255, 255, 255, 0.7);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 2px;
        }
        
        .msg-coins-value {
            display: block;
            font-size: 22px;
            font-weight: bold;
            color: #ffffff;
        }
        
        .msg-coins-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        .msg-coin-action-btn {
            background: rgba(0, 212, 170, 0.1);
            border: 1px solid rgba(0, 212, 170, 0.3);
            color: #00d4aa;
            padding: 10px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }
        
        .msg-coin-action-btn:hover {
            background: rgba(0, 212, 170, 0.2);
            border-color: rgba(0, 212, 170, 0.5);
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 212, 170, 0.2);
        }
        
        .msg-coins-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .msg-coins-back {
            background: rgba(0, 212, 170, 0.1);
            border: 1px solid rgba(0, 212, 170, 0.3);
            color: #00d4aa;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .msg-coins-back:hover {
            background: rgba(0, 212, 170, 0.2);
        }
        
        .msg-coins-header h4 {
            margin: 0;
            color: #ffffff;
            font-size: 14px;
            font-weight: 600;
        }
        
        .msg-coins-packages {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-bottom: 12px;
        }
        
        .msg-coin-package {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(0, 212, 170, 0.05);
            border: 1px solid rgba(0, 212, 170, 0.2);
            padding: 12px;
            border-radius: 10px;
            transition: all 0.3s;
        }
        
        .msg-coin-package:hover {
            background: rgba(0, 212, 170, 0.1);
            border-color: rgba(0, 212, 170, 0.4);
        }
        
        .msg-pkg-info {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        
        .msg-pkg-coins {
            font-size: 14px;
            font-weight: 600;
            color: #ffffff;
        }
        
        .msg-pkg-price {
            font-size: 12px;
            color: rgba(255, 255, 255, 0.7);
        }
        
        .msg-pkg-buy-btn {
            background: linear-gradient(135deg, #00d4aa 0%, #00a896 100%);
            border: none;
            color: #ffffff;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 2px 8px rgba(0, 212, 170, 0.3);
        }
        
        .msg-pkg-buy-btn:hover {
            transform: scale(1.05);
            box-shadow: 0 4px 12px rgba(0, 212, 170, 0.5);
        }
        
        .msg-coins-note {
            text-align: center;
            font-size: 11px;
            color: rgba(255, 255, 255, 0.6);
            margin: 0;
        }
        
        .msg-history-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }
        
        .msg-history-tab {
            flex: 1;
            background: rgba(0, 212, 170, 0.05);
            border: 1px solid rgba(0, 212, 170, 0.2);
            color: rgba(255, 255, 255, 0.7);
            padding: 8px;
            border-radius: 8px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .msg-history-tab.active {
            background: rgba(0, 212, 170, 0.15);
            border-color: rgba(0, 212, 170, 0.4);
            color: #00d4aa;
        }
        
        .msg-history-content {
            max-height: 220px;
            overflow-y: auto;
        }
        
        .msg-history-content::-webkit-scrollbar {
            width: 4px;
        }
        
        .msg-history-content::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
        }
        
        .msg-history-content::-webkit-scrollbar-thumb {
            background: rgba(0, 212, 170, 0.3);
            border-radius: 4px;
        }
        
        .msg-history-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        
        .msg-history-row {
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(0, 212, 170, 0.05);
            border: 1px solid rgba(0, 212, 170, 0.1);
            padding: 10px;
            border-radius: 8px;
            font-size: 12px;
        }
        
        .msg-h-icon {
            font-size: 18px;
            width: 32px;
            height: 32px;
            background: rgba(0, 212, 170, 0.1);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .msg-h-info {
            flex: 1;
            min-width: 0;
        }
        
        .msg-h-desc {
            color: #ffffff;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 2px;
        }
        
        .msg-h-desc a {
            color: inherit;
            text-decoration: none;
        }
        
        .msg-h-desc a:hover {
            color: #00d4aa;
        }
        
        .msg-h-date {
            font-size: 10px;
            color: rgba(255, 255, 255, 0.5);
        }
        
        .msg-h-amount {
            font-weight: 600;
            font-size: 13px;
        }
        
        .msg-empty-state {
            text-align: center;
            padding: 30px 10px;
        }
        
        .msg-empty-icon {
            font-size: 36px;
            margin-bottom: 10px;
        }
        
        .msg-empty-state p {
            color: rgba(255, 255, 255, 0.5);
            font-size: 12px;
            margin: 0;
        }
        </style>
        <?php
    }
}

MSG_Coins_User_Menu_Integration::get_instance();