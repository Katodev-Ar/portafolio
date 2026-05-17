<?php
/**
 * Plugin Name: Bloom User Profiles
 * Plugin URI:  https://bloomscans.com
 * Description: Perfiles públicos de usuario, búsqueda de usuarios en el buscador global (integrado con ajaxyLiveSearch del tema) y muro de mensajes.
 * Version:     1.1.0
 * Author:      BloomScans
 * Text Domain: bloom-user-profiles
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'BUP_VERSION', '1.1.0' );
define( 'BUP_DIR',     plugin_dir_path( __FILE__ ) );
define( 'BUP_URL',     plugin_dir_url( __FILE__ ) );

/* ── Autoload ─────────────────────────────────────────────── */
require_once BUP_DIR . 'includes/class-bup-db.php';
require_once BUP_DIR . 'includes/class-bup-ajax.php';
require_once BUP_DIR . 'includes/class-bup-profile.php';
require_once BUP_DIR . 'includes/class-bup-assets.php';

/* ── Instalación ──────────────────────────────────────────── */
register_activation_hook( __FILE__, [ 'BUP_DB', 'install' ] );

/* ── Boot ────────────────────────────────────────────────── */
add_action( 'init',             [ 'BUP_Profile', 'init' ] );

/*
 * AJAX: Búsqueda de usuarios
 * Usa el mismo admin-ajax.php que el tema y manga-scan-groups-v5.
 * El JS en bup-search.js llama a este endpoint desde el buscador de bloom-navbar.
 */
add_action( 'wp_ajax_bloom_search_users',        [ 'BUP_Ajax', 'search_users' ] );
add_action( 'wp_ajax_nopriv_bloom_search_users', [ 'BUP_Ajax', 'search_users' ] );

/*
 * AJAX: Muro de mensajes
 * Usa el nonce bup_wall_nonce generado via wp_localize_script.
 */
add_action( 'wp_ajax_bup_wall_post',        [ 'BUP_Ajax', 'wall_post' ] );
add_action( 'wp_ajax_bup_wall_load',        [ 'BUP_Ajax', 'wall_load' ] );
add_action( 'wp_ajax_nopriv_bup_wall_load', [ 'BUP_Ajax', 'wall_load' ] );

/*
 * Assets: Se enganchan en wp_enqueue_scripts.
 * - bup.css carga en todas las páginas (necesario para el dropdown del buscador).
 * - bup-search.js carga en todas las páginas NO reader (mismo criterio que bloom-navbar).
 * - bup-profile.js solo en la página de perfil.
 *
 * NOTA: usamos prioridad 20 para garantizar que manga-scan-groups-v5 (que registra
 * msgAjax en prioridad default 10) ya ha localizado su objeto JS cuando nuestro
 * script quiera leer window.msgAjax.ajaxurl.
 */
add_action( 'wp_enqueue_scripts', [ 'BUP_Assets', 'enqueue' ], 20 );

/*
 * Integración con el tema: extender la respuesta del buscador ajaxyLiveSearch.
 * El tema registra la acción "ts_ajax_search" (ajaxy-search). Nosotros no la
 * interceptamos; en su lugar añadimos nuestra propia sección de usuarios al
 * dropdown via JS (ver bup-search.js), que hace una llamada paralela a
 * bloom_search_users y combina los resultados en el dropdown personalizado.
 *
 * Esto nos permite:
 *  - No tocar el código del tema.
 *  - No romper el buscador existente de manhwas.
 *  - Añadir usuarios encima del resultado nativo.
 */

