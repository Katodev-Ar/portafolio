<?php
/**
 * Plugin Name: Bloom Cookie Manager
 * Plugin URI:  https://bloomscans.com
 * Description: Complete cookie consent management — banner, scanner, consent logs, geo-detection, GDPR/CCPA/LGPD compliance, and T&C enforcement with session security.
 * Version:     2.0.5
 * Author:      BloomScan
 * License:     GPL-2.0+
 * Text Domain: bloom-cookie-manager
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'BCM_VERSION',     '2.0.5' );
define( 'BCM_PLUGIN_DIR',  plugin_dir_path( __FILE__ ) );
define( 'BCM_PLUGIN_URL',  plugin_dir_url( __FILE__ ) );
define( 'BCM_PLUGIN_FILE', __FILE__ );

/* ── Core includes ── */
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-db.php';
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-scanner.php';
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-consent-log.php';
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-settings.php';
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-geo.php';              // v1.4.0
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-cookie-policy.php';    // v1.4.0
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-tc-manager.php';       // v1.7.0
require_once BCM_PLUGIN_DIR . 'includes/class-bcm-login-tc.php';           // v1.8.6
require_once BCM_PLUGIN_DIR . 'admin/class-bcm-admin.php';
require_once BCM_PLUGIN_DIR . 'public/class-bcm-public.php';

register_activation_hook( __FILE__, function () {
    BCM_DB::install();
    do_action( 'bcm_activated' );   // → BCM_TC_Manager::schedule_cron()
} );

register_deactivation_hook( __FILE__, function () {
    BCM_DB::deactivate();
    do_action( 'bcm_deactivated' ); // → BCM_TC_Manager::unschedule_cron()
} );

function bcm_init() {
    new BCM_Admin();
    new BCM_Public();
    new BCM_Cookie_Policy();   // v1.4.0 — shortcode [bcm_cookie_policy]
    new BCM_TC_Manager();      // v1.7.0 — T&C enforcement engine

    BCM_TC_Manager::register_shortcode();  // [bcm_tc_acceptance]
    new BCM_Login_TC();                    // v1.8.6 — TOS enforcement + [bcm_login_tc]
}
add_action( 'plugins_loaded', 'bcm_init' );
