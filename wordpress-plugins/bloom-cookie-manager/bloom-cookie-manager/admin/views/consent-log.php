<?php if ( ! defined( 'ABSPATH' ) ) exit;
$s    = BCM_Settings::get();
$lang = $s['admin_lang'] ?? 'es';
$isES = ( $lang === 'es' );
$stats = BCM_Consent_Log::get_stats();
$logs  = BCM_Consent_Log::get_recent( 100 );
?>
<div class="bcm-wrap">
    <div class="bcm-header">
        <h1>📋 <?php echo esc_html( $isES ? 'Registro de consentimientos' : 'Consent Log' ); ?></h1>
        <div style="display:flex;gap:8px;align-items:center">
            <button id="bcm-export-csv" class="bcm-btn bcm-btn-outline">
                ⬇ <?php echo esc_html( $isES ? 'Exportar CSV' : 'Export CSV' ); ?>
            </button>
        </div>
    </div>

    <div class="bcm-stats-grid">
        <div class="bcm-stat-card">
            <div class="bcm-stat-value"><?php echo esc_html( $stats['total'] ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Total' : 'Total' ); ?></div>
        </div>
        <div class="bcm-stat-card">
            <div class="bcm-stat-value" style="color:#22c55e"><?php echo esc_html( $stats['accepted'] ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Aceptados' : 'Accepted' ); ?></div>
        </div>
        <div class="bcm-stat-card">
            <div class="bcm-stat-value" style="color:#ef4444"><?php echo esc_html( $stats['rejected'] ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Rechazados' : 'Rejected' ); ?></div>
        </div>
        <div class="bcm-stat-card">
            <div class="bcm-stat-value"><?php echo esc_html( $stats['rate'] ); ?>%</div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Tasa de aceptación' : 'Acceptance Rate' ); ?></div>
        </div>
    </div>

    <!-- GDPR Art. 17 — Right to Erasure -->
    <div class="bcm-card" style="margin-bottom:16px">
        <h3><?php echo esc_html( $isES ? 'Derecho de supresión (GDPR Art. 17)' : 'Right to Erasure (GDPR Art. 17)' ); ?></h3>
        <p class="bcm-hint">
            <?php echo esc_html( $isES
                ? 'Elimina todos los registros de consentimiento asociados a una dirección IP específica.'
                : 'Delete all consent records associated with a specific IP address.' ); ?>
        </p>
        <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
            <input type="text" id="bcm-delete-ip" placeholder="192.168.1.1" style="width:220px">
            <button id="bcm-delete-by-ip" class="bcm-btn bcm-btn-danger">
                🗑 <?php echo esc_html( $isES ? 'Eliminar registros' : 'Delete Records' ); ?>
            </button>
            <span id="bcm-delete-ip-result" style="font-size:.85rem;color:var(--bcm-success,#22c55e);display:none"></span>
        </div>
    </div>

    <div class="bcm-card">
        <h3><?php echo esc_html( $isES ? 'Registros de consentimiento' : 'Consent Records' ); ?></h3>
        <?php if ( $logs ) : ?>
        <div style="overflow-x:auto">
        <table class="bcm-table">
            <thead>
                <tr>
                    <th><?php echo esc_html( $isES ? 'ID de consentimiento' : 'Consent ID' ); ?></th>
                    <th><?php echo esc_html( $isES ? 'Estado' : 'Status' ); ?></th>
                    <th><?php echo esc_html( $isES ? 'Regulación' : 'Regulation' ); ?></th>
                    <th><?php echo esc_html( $isES ? 'Dirección IP' : 'IP Address' ); ?></th>
                    <th><?php echo esc_html( $isES ? 'Categorías' : 'Categories' ); ?></th>
                    <th><?php echo esc_html( $isES ? 'Fecha / hora (UTC)' : 'Date / Time (UTC)' ); ?></th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ( $logs as $log ) :
                    $cats_raw = json_decode( $log['categories'], true );
                    // Sanitize each category slug decoded from DB JSON before output
                    $cats = is_array( $cats_raw )
                        ? array_map( 'sanitize_text_field', array_map( 'strval', $cats_raw ) )
                        : [];
                    $reg  = $log['regulation'] ?? 'GDPR';
                ?>
                <tr>
                    <td><code class="bcm-consent-id"><?php echo esc_html( $log['consent_id'] ); ?></code></td>
                    <td><span class="bcm-badge bcm-badge-<?php echo esc_attr( $log['status'] ); ?>"><?php echo esc_html( ucfirst( $log['status'] ) ); ?></span></td>
                    <td><span class="bcm-badge bcm-badge-reg"><?php echo esc_html( $reg ); ?></span></td>
                    <td><?php echo esc_html( $log['ip_address'] ); ?></td>
                    <td><?php echo esc_html( implode( ', ', $cats ) ); ?></td>
                    <td><?php echo esc_html( $log['created_at'] ); ?></td>
                </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
        </div>
        <?php else : ?>
        <p class="bcm-empty"><?php echo esc_html( $isES ? 'Todavía no hay registros de consentimiento.' : 'No consent logs recorded yet.' ); ?></p>
        <?php endif; ?>
    </div>
</div>
