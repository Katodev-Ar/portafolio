<?php
/**
 * Plugin Name: Bloom Internal Raw Image Exception
 * Description: Permite acceso interno autenticado a imágenes crudas protegidas para herramientas del panel.
 */

if (!defined('ABSPATH')) {
    exit;
}

if (!function_exists('biri_get_requested_raw_path')) {
    function biri_get_requested_raw_path(): string
    {
        $uri = isset($_SERVER['REQUEST_URI']) ? (string) $_SERVER['REQUEST_URI'] : '';
        if ($uri === '') {
            return '';
        }

        $uploads = wp_upload_dir();
        $baseurl = isset($uploads['baseurl']) ? (string) $uploads['baseurl'] : '';
        $basedir = isset($uploads['basedir']) ? (string) $uploads['basedir'] : '';
        if ($baseurl === '' || $basedir === '') {
            return '';
        }

        $request_path = rawurldecode((string) parse_url($uri, PHP_URL_PATH));
        $uploads_path = (string) parse_url($baseurl, PHP_URL_PATH);
        if ($request_path === '' || $uploads_path === '' || strpos($request_path, $uploads_path) !== 0) {
            return '';
        }

        $relative = ltrim(substr($request_path, strlen($uploads_path)), '/');
        if ($relative === '') {
            return '';
        }

        $target = wp_normalize_path(trailingslashit($basedir) . $relative);
        $real = realpath($target);
        if (!$real) {
            return '';
        }

        $real = wp_normalize_path($real);
        $root = wp_normalize_path((string) realpath($basedir));
        if ($root === '') {
            $root = wp_normalize_path($basedir);
        }

        if (strpos($real, trailingslashit($root)) !== 0 && $real !== $root) {
            return '';
        }

        return $real;
    }
}

if (!function_exists('biri_is_protected_chapter_raw')) {
    function biri_is_protected_chapter_raw(string $path): bool
    {
        if ($path === '') {
            return false;
        }

        $uploads = wp_upload_dir();
        $basedir = wp_normalize_path((string) ($uploads['basedir'] ?? ''));
        if ($basedir === '') {
            return false;
        }

        $relative = ltrim(str_replace(trailingslashit($basedir), '', wp_normalize_path($path)), '/');

        return (bool) preg_match('#^(manhwas|capitulos)/#i', $relative);
    }
}

if (!function_exists('biri_same_site_internal_referer')) {
    function biri_same_site_internal_referer(): bool
    {
        $referer = wp_get_referer();
        if (!$referer && !empty($_SERVER['HTTP_REFERER'])) {
            $referer = (string) $_SERVER['HTTP_REFERER'];
        }
        if (!$referer) {
            return false;
        }

        $home = wp_parse_url(home_url('/'));
        $ref  = wp_parse_url($referer);
        if (!$home || !$ref) {
            return false;
        }

        $home_host = strtolower((string) ($home['host'] ?? ''));
        $ref_host  = strtolower((string) ($ref['host'] ?? ''));
        if ($home_host === '' || $ref_host === '' || $home_host !== $ref_host) {
            return false;
        }

        $path = (string) ($ref['path'] ?? '');
        if (strpos($path, '/panel-scan/') !== false || strpos($path, '/wp-admin/') !== false) {
            return true;
        }

        parse_str((string) ($ref['query'] ?? ''), $query);
        if (!empty($query['panel'])) {
            $panel = (string) $query['panel'];
            if (in_array($panel, ['chapter_edit', 'manga_edit', 'scans', 'blogs', 'blog_edit'], true)) {
                return true;
            }
        }

        return false;
    }
}

if (!function_exists('biri_current_user_internal_tool_access')) {
    function biri_current_user_internal_tool_access(): bool
    {
        if (!is_user_logged_in()) {
            return false;
        }

        if (current_user_can('manage_options')) {
            return true;
        }

        if (biri_same_site_internal_referer()) {
            return true;
        }

        return false;
    }
}

if (!function_exists('biri_stream_local_image')) {
    function biri_stream_local_image(string $path): void
    {
        $type = wp_check_filetype($path);
        $mime = !empty($type['type']) ? $type['type'] : 'application/octet-stream';
        $size = @filesize($path);

        if (!headers_sent()) {
            status_header(200);
            header('Content-Type: ' . $mime);
            header('X-Bloom-Internal-Raw-Bypass: 1');
            header('Cache-Control: private, no-store, max-age=0');
            if ($size !== false) {
                header('Content-Length: ' . (string) $size);
            }
        }

        @readfile($path);
        exit;
    }
}

add_action('init', function () {
    $path = biri_get_requested_raw_path();
    if ($path === '' || !biri_is_protected_chapter_raw($path)) {
        return;
    }

    if (!biri_current_user_internal_tool_access()) {
        return;
    }

    biri_stream_local_image($path);
}, 0);
