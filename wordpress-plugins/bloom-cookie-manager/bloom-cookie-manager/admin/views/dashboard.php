<?php if ( ! defined( 'ABSPATH' ) ) exit;
global $wpdb;
$stats         = BCM_Consent_Log::get_stats();
$settings      = BCM_Settings::get();
$lang          = $settings['admin_lang'] ?? 'es';
$isES          = ( $lang === 'es' );
$last_scan     = $wpdb->get_row( "SELECT * FROM {$wpdb->prefix}bcm_scan_history ORDER BY id DESC LIMIT 1", ARRAY_A );
$total_cookies = (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$wpdb->prefix}bcm_cookies" );
?>
<div class="bcm-wrap">
    <div class="bcm-header">
        <div class="bcm-logo">🍪 Bloom Cookie Manager</div>
        <span class="bcm-version">v<?php echo esc_html( BCM_VERSION ); ?></span>
    </div>

    <div class="bcm-card bcm-status-card">
        <div class="bcm-status-indicator <?php echo esc_attr( $settings['banner_enabled'] ? 'active' : 'inactive' ); ?>">
            <span class="bcm-dot"></span>
            <?php echo esc_html( $settings['banner_enabled']
                ? ( $isES ? 'Banner activo' : 'Banner Active' )
                : ( $isES ? 'Banner inactivo' : 'Banner Inactive' ) ); ?>
        </div>
        <div class="bcm-status-meta">
            <span><?php echo esc_html( $isES ? 'Regulación:' : 'Regulation:' ); ?> <strong><?php echo esc_html( $settings['regulation'] ); ?></strong></span>
            <span><?php echo esc_html( $isES ? 'Sitio:' : 'Site:' ); ?> <strong><?php echo esc_html( home_url() ); ?></strong></span>
        </div>
        <a href="<?php echo esc_url( home_url() ); ?>" target="_blank" class="bcm-btn bcm-btn-outline">
            <?php echo esc_html( $isES ? 'Ver banner' : 'Preview Banner' ); ?>
        </a>
    </div>

    <div class="bcm-stats-grid">
        <div class="bcm-stat-card">
            <div class="bcm-stat-icon">📊</div>
            <div class="bcm-stat-value"><?php echo esc_html( $stats['total'] ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Consentimientos totales' : 'Total Consents' ); ?></div>
        </div>
        <div class="bcm-stat-card">
            <div class="bcm-stat-icon">✅</div>
            <div class="bcm-stat-value"><?php echo esc_html( $stats['accepted'] ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Aceptados' : 'Accepted' ); ?></div>
        </div>
        <div class="bcm-stat-card">
            <div class="bcm-stat-icon">❌</div>
            <div class="bcm-stat-value"><?php echo esc_html( $stats['rejected'] ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Rechazados' : 'Rejected' ); ?></div>
        </div>
        <div class="bcm-stat-card">
            <div class="bcm-stat-icon">🍪</div>
            <div class="bcm-stat-value"><?php echo esc_html( $total_cookies ); ?></div>
            <div class="bcm-stat-label"><?php echo esc_html( $isES ? 'Cookies registradas' : 'Cookies Tracked' ); ?></div>
        </div>
    </div>

    <div class="bcm-two-col">
        <div class="bcm-card">
            <h3><?php echo esc_html( $isES ? 'Resumen de cookies' : 'Cookie Summary' ); ?></h3>
            <div class="bcm-summary-grid">
                <div class="bcm-summary-item">
                    <strong><?php echo esc_html( $total_cookies ); ?></strong>
                    <span><?php echo esc_html( $isES ? 'Total cookies' : 'Total Cookies' ); ?></span>
                </div>
                <div class="bcm-summary-item">
                    <strong><?php echo $last_scan ? esc_html( $last_scan['scan_date'] ) : esc_html( $isES ? 'Nunca' : 'Never' ); ?></strong>
                    <span><?php echo esc_html( $isES ? 'Último escaneo' : 'Last Scan' ); ?></span>
                </div>
            </div>
            <button id="bcm-start-scan" class="bcm-btn bcm-btn-primary">
                🔍 <?php echo esc_html( $isES ? 'Iniciar escaneo' : 'Start Scan Now' ); ?>
            </button>
            <div id="bcm-scan-status" style="display:none;" class="bcm-scan-status"></div>
            <br><a href="<?php echo esc_url( admin_url( 'admin.php?page=bcm-cookies' ) ); ?>" class="bcm-link">
                <?php echo esc_html( $isES ? 'Gestionar cookies →' : 'Manage Cookies →' ); ?>
            </a>
        </div>

        <div class="bcm-card">
            <h3><?php echo esc_html( $isES ? 'Registros recientes de consentimiento' : 'Recent Consent Logs' ); ?></h3>
            <?php $logs = BCM_Consent_Log::get_recent( 5 ); ?>
            <?php if ( $logs ) : ?>
            <table class="bcm-table">
                <thead>
                    <tr>
                        <th><?php echo esc_html( $isES ? 'ID de consentimiento' : 'Consent ID' ); ?></th>
                        <th><?php echo esc_html( $isES ? 'Estado' : 'Status' ); ?></th>
                        <th><?php echo esc_html( $isES ? 'Fecha' : 'Date' ); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ( $logs as $log ) : ?>
                    <tr>
                        <td><code><?php echo esc_html( substr( $log['consent_id'], 0, 16 ) . '...' ); ?></code></td>
                        <td><span class="bcm-badge bcm-badge-<?php echo esc_attr( $log['status'] ); ?>"><?php echo esc_html( ucfirst( $log['status'] ) ); ?></span></td>
                        <td><?php echo esc_html( $log['created_at'] ); ?></td>
                    </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
            <?php else : ?>
            <p class="bcm-empty"><?php echo esc_html( $isES ? 'Todavía no hay registros de consentimiento.' : 'No consent logs yet.' ); ?></p>
            <?php endif; ?>
            <a href="<?php echo esc_url( admin_url( 'admin.php?page=bcm-consent-log' ) ); ?>" class="bcm-link">
                <?php echo esc_html( $isES ? 'Ver todos los registros →' : 'View All Logs →' ); ?>
            </a>
        </div>
    </div>
</div>
