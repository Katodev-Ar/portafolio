<?php
/**
 * Template: Historial - DISEÑO COMPACTO
 */

if (!defined('ABSPATH')) {
    exit;
}

$user_id = get_current_user_id();
$coins_system = MSG_Coins_System::get_instance();
$balance = $coins_system->get_user_balance($user_id);

global $wpdb;
$transactions_table = $wpdb->prefix . 'coin_transactions';
$purchases_table = $wpdb->prefix . 'chapter_purchases';

$transactions = $wpdb->get_results($wpdb->prepare(
    "SELECT * FROM $transactions_table 
     WHERE user_id = %d 
     ORDER BY created_at DESC 
     LIMIT 20",
    $user_id
));

$chapter_purchases = $wpdb->get_results($wpdb->prepare(
    "SELECT cp.*, p.post_title 
     FROM $purchases_table cp
     LEFT JOIN {$wpdb->posts} p ON cp.chapter_id = p.ID
     WHERE cp.user_id = %d 
     ORDER BY cp.purchase_date DESC 
     LIMIT 20",
    $user_id
));
?>

<div class="msg-history-compact">
    <!-- Header -->
    <div class="msg-page-header">
        <div class="msg-balance-box">
            <span class="msg-balance-icon">🪙</span>
            <div>
                <div class="msg-balance-label">Saldo Actual</div>
                <div class="msg-balance-value"><?php echo number_format($balance); ?> monedas</div>
            </div>
        </div>
    </div>
    
    <h2 class="msg-page-title">📊 Mi Historial</h2>
    
    <!-- Tabs -->
    <div class="msg-tabs">
        <button class="msg-tab active" onclick="showTab('transactions')">
            💰 Transacciones
        </button>
        <button class="msg-tab" onclick="showTab('chapters')">
            📖 Capítulos
        </button>
    </div>
    
    <!-- Tab Transacciones -->
    <div id="tab-transactions" class="msg-tab-content">
        <?php if (empty($transactions)): ?>
            <div class="msg-empty">
                <div class="msg-empty-icon">💸</div>
                <p>No tienes transacciones aún</p>
                <a href="<?php echo home_url('/buy-coins'); ?>" class="msg-btn-buy">Comprar Monedas</a>
            </div>
        <?php else: ?>
            <div class="msg-list">
                <?php foreach ($transactions as $tx): 
                    $icon = $tx->transaction_type == 'purchase' ? '💳' : '📖';
                    $sign = $tx->coins_amount > 0 ? '+' : '';
                    $color = $tx->coins_amount > 0 ? '#28a745' : '#dc3545';
                ?>
                <div class="msg-item">
                    <div class="msg-item-icon"><?php echo $icon; ?></div>
                    <div class="msg-item-info">
                        <div class="msg-item-title"><?php echo esc_html($tx->description); ?></div>
                        <div class="msg-item-date"><?php echo date('d/m/Y H:i', strtotime($tx->created_at)); ?></div>
                    </div>
                    <div class="msg-item-amount" style="color: <?php echo $color; ?>">
                        <?php echo $sign . number_format($tx->coins_amount); ?> 🪙
                    </div>
                </div>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
    </div>
    
    <!-- Tab Capítulos -->
    <div id="tab-chapters" class="msg-tab-content" style="display: none;">
        <?php if (empty($chapter_purchases)): ?>
            <div class="msg-empty">
                <div class="msg-empty-icon">📚</div>
                <p>No has desbloqueado capítulos</p>
            </div>
        <?php else: ?>
            <div class="msg-list">
                <?php foreach ($chapter_purchases as $purchase): ?>
                <div class="msg-item">
                    <div class="msg-item-icon">📖</div>
                    <div class="msg-item-info">
                        <div class="msg-item-title">
                            <a href="<?php echo get_permalink($purchase->chapter_id); ?>" style="color: inherit;">
                                <?php echo esc_html($purchase->post_title ?: 'Capítulo'); ?>
                            </a>
                        </div>
                        <div class="msg-item-date"><?php echo date('d/m/Y', strtotime($purchase->purchase_date)); ?></div>
                    </div>
                    <div class="msg-item-amount" style="color: #667eea;">
                        <?php echo number_format($purchase->coins_spent); ?> 🪙
                    </div>
                </div>
                <?php endforeach; ?>
            </div>
            
            <div class="msg-summary">
                <div class="msg-summary-item">
                    <span>Total desbloqueados:</span>
                    <strong><?php echo count($chapter_purchases); ?></strong>
                </div>
                <div class="msg-summary-item">
                    <span>Total gastado:</span>
                    <strong>
                        <?php 
                        $total = array_sum(array_column($chapter_purchases, 'coins_spent'));
                        echo number_format($total);
                        ?> 🪙
                    </strong>
                </div>
            </div>
        <?php endif; ?>
    </div>
</div>

<script>
function showTab(tab) {
    // Ocultar todos
    document.querySelectorAll('.msg-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.msg-tab-content').forEach(c => c.style.display = 'none');
    
    // Mostrar seleccionado
    event.target.classList.add('active');
    document.getElementById('tab-' + tab).style.display = 'block';
}
</script>

<style>
.msg-history-compact {
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
    background: #0a0e27;
    min-height: 100vh;
}

.msg-page-header {
    text-align: center;
    margin-bottom: 30px;
}

.msg-balance-box {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    background: linear-gradient(135deg, #5B6EEA 0%, #6B4BA2 100%);
    color: white;
    padding: 15px 25px;
    border-radius: 50px;
    box-shadow: 0 4px 15px rgba(91, 110, 234, 0.4);
}

.msg-balance-icon {
    font-size: 28px;
}

.msg-balance-label {
    font-size: 11px;
    opacity: 0.9;
    text-transform: uppercase;
}

.msg-balance-value {
    font-size: 18px;
    font-weight: bold;
}

.msg-page-title {
    text-align: center;
    font-size: 32px;
    margin: 0 0 30px 0;
    color: #ffffff;
}

.msg-tabs {
    display: flex;
    gap: 10px;
    border-bottom: 2px solid #2a3555;
    margin-bottom: 25px;
}

.msg-tab {
    padding: 12px 25px;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    color: #a0a0a0;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s;
}

.msg-tab:hover {
    color: #5B6EEA;
}

.msg-tab.active {
    color: #5B6EEA;
    border-bottom-color: #5B6EEA;
}

.msg-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.msg-item {
    display: flex;
    align-items: center;
    gap: 15px;
    background: #1a1f3a;
    border: 1px solid #2a3555;
    padding: 15px;
    border-radius: 12px;
    transition: all 0.3s;
}

.msg-item:hover {
    box-shadow: 0 4px 15px rgba(91, 110, 234, 0.2);
    transform: translateY(-2px);
    border-color: #5B6EEA;
}

.msg-item-icon {
    width: 45px;
    height: 45px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(91, 110, 234, 0.15);
    border-radius: 10px;
    font-size: 22px;
    flex-shrink: 0;
}

.msg-item-info {
    flex: 1;
    min-width: 0;
}

.msg-item-title {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.msg-item-title a {
    color: #ffffff;
    text-decoration: none;
}

.msg-item-title a:hover {
    color: #5B6EEA;
}

.msg-item-date {
    font-size: 12px;
    color: #7080a0;
}

.msg-item-amount {
    font-size: 16px;
    font-weight: bold;
    flex-shrink: 0;
}

.msg-empty {
    text-align: center;
    padding: 60px 20px;
    background: #1a1f3a;
    border: 1px solid #2a3555;
    border-radius: 16px;
}

.msg-empty-icon {
    font-size: 60px;
    margin-bottom: 15px;
}

.msg-empty p {
    font-size: 16px;
    color: #a0a0a0;
    margin: 0 0 25px 0;
}

.msg-btn-buy {
    display: inline-block;
    padding: 12px 30px;
    background: linear-gradient(135deg, #5B6EEA 0%, #6B4BA2 100%);
    color: white;
    text-decoration: none;
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.3s;
}

.msg-btn-buy:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(91, 110, 234, 0.5);
}

.msg-summary {
    background: linear-gradient(135deg, #5B6EEA 0%, #6B4BA2 100%);
    color: white;
    padding: 20px;
    border-radius: 12px;
    margin-top: 25px;
    display: flex;
    justify-content: space-around;
    text-align: center;
}

.msg-summary-item span {
    display: block;
    font-size: 12px;
    opacity: 0.9;
    margin-bottom: 5px;
}

.msg-summary-item strong {
    display: block;
    font-size: 24px;
}

@media (max-width: 768px) {
    .msg-history-compact {
        padding: 15px;
    }
    
    .msg-page-title {
        font-size: 24px;
    }
    
    .msg-tabs {
        overflow-x: auto;
    }
    
    .msg-item {
        flex-wrap: wrap;
    }
    
    .msg-item-amount {
        width: 100%;
        text-align: right;
        margin-top: 10px;
    }
    
    .msg-summary {
        flex-direction: column;
        gap: 15px;
    }
}
</style>
<?php