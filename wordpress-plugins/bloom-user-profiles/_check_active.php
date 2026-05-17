<?php
define('ABSPATH', '/home/u402841112/domains/bloomscans.com/public_html/');
require_once ABSPATH . 'wp-load.php';
$plugins = get_option('active_plugins', array());
foreach ($plugins as $p) {
    echo $p . "\n";
}
