<?php

if ( ! class_exists( 'BRG_Context_Guard_Probe' ) ) {
	class BRG_Context_Guard_Probe {
		public static function boot() {
			add_action( 'init', array( __CLASS__, 'capture_request_context' ), 1 );
		}

		public static function capture_request_context() {
			if ( is_admin() && ! wp_doing_ajax() ) {
				return;
			}

			if ( ! class_exists( 'BRG_Context_Monitor' ) ) {
				return;
			}

			$uri = isset( $_SERVER['REQUEST_URI'] ) ? (string) $_SERVER['REQUEST_URI'] : '';
			if ( '' === $uri ) {
				return;
			}

			if ( preg_match( '#/reader-bootstrap/([0-9]+)\.js(?:$|\?)#', $uri, $matches ) ) {
				BRG_Context_Monitor::instance()->record_bootstrap_hit(
					(int) $matches[1],
					self::collect_request_context()
				);
				return;
			}

			if ( preg_match( '#/reader-presence/([0-9]+)/#', $uri, $matches ) ) {
				BRG_Context_Monitor::instance()->record_presence_hit(
					(int) $matches[1],
					self::collect_request_context()
				);
				return;
			}

			if ( preg_match( '#/reader-image/([0-9]+)/#', $uri, $matches ) ) {
				BRG_Context_Monitor::instance()->record_image_probe(
					(int) $matches[1],
					self::collect_request_context()
				);
			}
		}

		protected static function collect_request_context() {
			return array(
				'referer'         => isset( $_SERVER['HTTP_REFERER'] ) ? (string) $_SERVER['HTTP_REFERER'] : '',
				'sec_fetch_site'  => isset( $_SERVER['HTTP_SEC_FETCH_SITE'] ) ? (string) $_SERVER['HTTP_SEC_FETCH_SITE'] : '',
				'sec_fetch_mode'  => isset( $_SERVER['HTTP_SEC_FETCH_MODE'] ) ? (string) $_SERVER['HTTP_SEC_FETCH_MODE'] : '',
				'sec_fetch_dest'  => isset( $_SERVER['HTTP_SEC_FETCH_DEST'] ) ? (string) $_SERVER['HTTP_SEC_FETCH_DEST'] : '',
				'has_range'       => ! empty( $_SERVER['HTTP_RANGE'] ),
				'accept'          => isset( $_SERVER['HTTP_ACCEPT'] ) ? (string) $_SERVER['HTTP_ACCEPT'] : '',
				'ua'              => isset( $_SERVER['HTTP_USER_AGENT'] ) ? (string) $_SERVER['HTTP_USER_AGENT'] : '',
			);
		}
	}

	BRG_Context_Guard_Probe::boot();
}

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class BRG_Guard {
	private const VERSION_OPTION     = 'brg_version';
	private const MAP_TTL            = 7200;
	private const COOKIE_TTL         = 900;
	private const COOKIE_PREFIX      = 'brg_ch_';
	private const ALIAS_PREFIX       = 'reader-image';
	private const BOOTSTRAP_PREFIX   = 'reader-bootstrap';
	private const BAIT_PREFIX        = 'reader-asset';
	private const PRESENCE_PREFIX    = 'reader-presence';
	private const APPEAL_PREFIX      = 'reader-appeal';
	private const RAW_MANHWAS_PREFIX = 'manhwas/';
	private const RAW_CAPS_PREFIX    = 'capitulos/';
	private const DISCORD_URL        = 'https://discord.gg/RThQxAMRhr';
	private const PAGE_WINDOW_SECONDS = 7200;
	private const INTERNAL_TOOL_WINDOW = 300;

	private static ?self $instance = null;
	private int $buffer_chapter_id = 0;

	public static function instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}

		return self::$instance;
	}

	private function __construct() {
		BRG_Monitor::instance()->bootstrap();
		BRG_Admin::instance();

		add_action( 'init', [ $this, 'register_rewrites' ] );
		add_filter( 'query_vars', [ $this, 'register_query_vars' ] );
		add_action( 'template_redirect', [ $this, 'handle_guard_requests' ], 0 );
		add_action( 'template_redirect', [ $this, 'maybe_start_output_buffer' ], 1 );
		add_action( 'admin_init', [ $this, 'maybe_upgrade' ] );
	}

	public function register_rewrites(): void {
		add_rewrite_rule(
			'^' . self::ALIAS_PREFIX . '/([0-9]+)/([a-f0-9]{20})/([^/]+)$',
			'index.php?brg_reader_image=1&brg_chapter_id=$matches[1]&brg_page_key=$matches[2]&brg_filename=$matches[3]',
			'top'
		);
		add_rewrite_rule(
			'^' . self::BOOTSTRAP_PREFIX . '/([0-9]+)\.js$',
			'index.php?brg_reader_bootstrap=1&brg_chapter_id=$matches[1]',
			'top'
		);
		add_rewrite_rule(
			'^' . self::BAIT_PREFIX . '/([0-9]+)/([a-f0-9]{20})/([^/]+)$',
			'index.php?brg_reader_bait=1&brg_chapter_id=$matches[1]&brg_bait_key=$matches[2]&brg_filename=$matches[3]',
			'top'
		);
		add_rewrite_rule(
			'^' . self::PRESENCE_PREFIX . '/([0-9]+)/([a-f0-9]{16})\.(svg|webp)$',
			'index.php?brg_reader_presence=1&brg_chapter_id=$matches[1]&brg_presence_key=$matches[2]',
			'top'
		);
		add_rewrite_rule(
			'^' . self::APPEAL_PREFIX . '/?$',
			'index.php?brg_reader_appeal=1',
			'top'
		);
	}

	public function register_query_vars( array $vars ): array {
		$vars[] = 'brg_reader_image';
		$vars[] = 'brg_reader_bootstrap';
		$vars[] = 'brg_reader_bait';
		$vars[] = 'brg_reader_presence';
		$vars[] = 'brg_reader_appeal';
		$vars[] = 'brg_chapter_id';
		$vars[] = 'brg_page_key';
		$vars[] = 'brg_bait_key';
		$vars[] = 'brg_presence_key';
		$vars[] = 'brg_filename';
		$vars[] = 'brg_protected_upload';
		return $vars;
	}

	public function maybe_upgrade(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		if ( get_option( self::VERSION_OPTION ) === BRG_VERSION ) {
			return;
		}

		$this->register_rewrites();
		flush_rewrite_rules( false );
		update_option( self::VERSION_OPTION, BRG_VERSION, false );
	}

	public function handle_guard_requests(): void {
		if ( get_query_var( 'brg_reader_image' ) ) {
			$this->disable_guard_caching();
			$this->handle_alias_request();
		}

		if ( get_query_var( 'brg_reader_bootstrap' ) ) {
			$this->disable_guard_caching();
			$this->handle_bootstrap_request();
		}

		if ( get_query_var( 'brg_reader_bait' ) ) {
			$this->disable_guard_caching();
			$this->handle_bait_request();
		}

		if ( get_query_var( 'brg_reader_presence' ) ) {
			$this->disable_guard_caching();
			$this->handle_presence_request();
		}

		if ( get_query_var( 'brg_reader_appeal' ) ) {
			$this->disable_guard_caching();
			$this->handle_appeal_request();
		}

		$raw = (string) get_query_var( 'brg_protected_upload' );
		if ( '' !== $raw ) {
			$this->disable_guard_caching();
			$this->handle_raw_upload_request( ltrim( $raw, '/' ) );
		}
	}

	public function maybe_start_output_buffer(): void {
		if ( is_admin() || wp_doing_ajax() || is_feed() || is_robots() || is_trackback() ) {
			return;
		}

		$chapter_id = $this->current_chapter_id();
		if ( ! $chapter_id ) {
			return;
		}

		$map = $this->get_chapter_map( $chapter_id );
		if ( empty( $map['raw_urls'] ) ) {
			return;
		}

		$this->buffer_chapter_id = $chapter_id;
		ob_start( [ $this, 'rewrite_chapter_output' ] );
	}

	public function rewrite_chapter_output( string $html ): string {
		if ( ! $this->buffer_chapter_id ) {
			return $html;
		}

		$map = $this->get_chapter_map( $this->buffer_chapter_id );
		if ( empty( $map['raw_urls'] ) ) {
			return $html;
		}

		$replacements = $map['raw_urls'];
		uksort(
			$replacements,
			static fn ( string $a, string $b ) => strlen( $b ) <=> strlen( $a )
		);

		$html = strtr( $html, $replacements );

		$escaped = [];
		foreach ( $replacements as $raw_url => $alias_url ) {
			$escaped[ str_replace( '/', '\/', $raw_url ) ] = str_replace( '/', '\/', $alias_url );
		}
		if ( ! empty( $escaped ) ) {
			$html = strtr( $html, $escaped );
		}

		$bootstrap = $this->build_bootstrap_script_tag( $this->buffer_chapter_id );
		if ( false !== strpos( $html, $bootstrap ) ) {
			return $html;
		}

		if ( false !== stripos( $html, '</head>' ) ) {
			$html = preg_replace( '/<\/head>/i', $bootstrap . '</head>', $html, 1 ) ?: ( $bootstrap . $html );
		} else {
			$html = $bootstrap . $html;
		}

		return $html;
	}

	public static function sign_internal_tool_url( string $url ): string {
		return self::instance()->build_internal_tool_url( $url );
	}

	private function handle_bootstrap_request(): void {
		$chapter_id = absint( get_query_var( 'brg_chapter_id' ) );
		if ( ! $chapter_id || ! $this->is_chapter_post( $chapter_id ) ) {
			$this->render_bootstrap_js( '', '', '' );
		}

		$actor  = BRG_Monitor::instance()->get_actor();
		BRG_Monitor::instance()->record_chapter_view( $actor, $chapter_id );
		$ban    = BRG_Monitor::instance()->get_active_ban( $actor );

		if ( ! $ban ) {
			$this->issue_cookie( $chapter_id );
		}

		$passive_html    = $this->build_passive_bait_markup( $chapter_id, $actor );
		$reinforced_html = '';
		$notice_html     = '';
		$presence_url    = $this->build_presence_url( $chapter_id );
		if ( BRG_Monitor::instance()->should_inject_honeypot( $actor ) ) {
			$reinforced_html = $this->build_reinforced_bait_markup( $chapter_id, $actor );
		}
		if ( $ban ) {
			$notice_html = $this->build_block_notice_markup( $ban, $actor );
		}

		$this->render_bootstrap_js( $notice_html, $passive_html, $reinforced_html, $presence_url );
	}

	private function build_bootstrap_script_tag( int $chapter_id ): string {
		$src = add_query_arg(
			'ver',
			rawurlencode( BRG_VERSION ),
			home_url( '/' . self::BOOTSTRAP_PREFIX . '/' . $chapter_id . '.js' )
		);

		return '<script src="' . esc_url( $src ) . '" data-brg-bootstrap="' . esc_attr( (string) $chapter_id ) . '"></script>';
	}

	private function render_bootstrap_js( string $notice_html, string $passive_html, string $reinforced_html, string $presence_url = '' ): void {
		while ( ob_get_level() ) {
			ob_end_clean();
		}

		status_header( 200 );
		header( 'Content-Type: application/javascript; charset=' . get_bloginfo( 'charset' ) );
		header( 'X-Robots-Tag: noindex, nofollow', true );

		$payload = wp_json_encode(
			[
				'notice'     => $notice_html,
				'passive'    => $passive_html,
				'reinforced' => $reinforced_html,
				'presence'   => $presence_url,
			],
			JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
		);

		echo "(function(){\n";
		echo 'var payload=' . ( $payload ?: '{"notice":"","passive":"","reinforced":""}' ) . ";\n";
		echo "function whenReady(fn){if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',fn,{once:true});}else{fn();}}\n";
		echo "function injectOnce(selector, html, mode){if(!html){return;} if(document.querySelector(selector)){return;} var anchor=document.querySelector('[data-brg-anchor=\"'+mode+'\"]'); if(anchor){anchor.insertAdjacentHTML('beforebegin', html); return;} if(mode==='notice'){var reader=document.querySelector('#readerarea, #images_chapter, .reading-content, .main-col, .chapter-content, .entry-content'); if(reader && reader.parentNode){reader.insertAdjacentHTML('beforebegin', html); return;}} if(document.body){if(mode==='notice'){document.body.insertAdjacentHTML('afterbegin', html);}else{document.body.insertAdjacentHTML('beforeend', html);}}}\n";
		echo "function startCountdown(){var nodes=document.querySelectorAll('[data-brg-reader-countdown]:not([data-brg-live])'); nodes.forEach(function(el){el.setAttribute('data-brg-live','1'); var secs=parseInt(el.getAttribute('data-brg-reader-countdown'),10)||0; function pad(v){return String(v).padStart(2,'0');} function tick(){if(secs<0){return;} var h=Math.floor(secs/3600),m=Math.floor((secs%3600)/60),s=secs%60; el.textContent=pad(h)+':'+pad(m)+':'+pad(s); secs--; if(secs>=0){window.setTimeout(tick,1000);}} tick();});}\n";
		echo "function sendPresence(url){if(!url){return;} var i=new Image(); i.decoding='async'; i.loading='eager'; i.src=url;}\n";
		echo "function bindAppealForms(){document.querySelectorAll('[data-brg-appeal-form]:not([data-brg-live])').forEach(function(form){form.setAttribute('data-brg-live','1'); form.addEventListener('submit',function(ev){ev.preventDefault(); var status=form.querySelector('[data-brg-appeal-status]'); if(status){status.textContent='Enviando reclamo...'; status.style.color='#c5d0db';} fetch(form.action,{method:'POST',body:new FormData(form),credentials:'same-origin'}).then(function(r){return r.json();}).then(function(data){if(status){status.textContent=(data&&data.message)?data.message:'Reclamo enviado.'; status.style.color=(data&&data.success)?'#00c896':'#fda29b';} if(data&&data.success){form.reset();}}).catch(function(){if(status){status.textContent='No pudimos enviar el reclamo ahora. Intenta de nuevo.'; status.style.color='#fda29b';}});});});}\n";
		echo "whenReady(function(){injectOnce('[data-brg-reader-notice]', payload.notice || '', 'notice'); injectOnce('.reader-media-shadow-passive,.reader-media-asset-passive,.reader-media-thumb-passive,.reader-media-stack-passive', payload.passive || '', 'passive'); injectOnce('.reader-media-shadow-reinforced,.reader-media-asset-reinforced,.reader-media-thumb-reinforced,.reader-media-stack-reinforced,.reader-media-link-reinforced,.reader-media-json-reinforced', payload.reinforced || '', 'reinforced'); sendPresence(payload.presence || ''); startCountdown(); bindAppealForms();});\n";
		echo "})();";
		exit;
	}

	private function handle_alias_request(): void {
		$chapter_id = absint( get_query_var( 'brg_chapter_id' ) );
		$page_key   = strtolower( sanitize_text_field( (string) get_query_var( 'brg_page_key' ) ) );

		if ( ! $chapter_id || ! preg_match( '/^[a-f0-9]{20}$/', $page_key ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		$actor = BRG_Monitor::instance()->get_actor();
		$ban   = BRG_Monitor::instance()->get_active_ban( $actor );
		if ( $ban ) {
			$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $ban );
		}

		$page = $this->resolve_page_entry( $chapter_id, $page_key );
		if ( empty( $page ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		if ( ! $this->has_valid_cookie( $chapter_id ) ) {
			$result = BRG_Monitor::instance()->record_denied_cookie( $actor, $chapter_id );
			if ( ! empty( $result['banned'] ) ) {
				$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $result );
			}

			$this->render_error( 403, 'Acceso denegado: la autorización del capítulo falta o venció. Recarga el capítulo e inténtalo de nuevo.' );
		}

		$result = BRG_Monitor::instance()->record_image_hit( $actor, $chapter_id );
		if ( ! empty( $result['banned'] ) ) {
			$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $result );
		}

		$this->serve_file(
			(string) $page['abs_path'],
			(string) $page['mime'],
			(string) $page['filename'],
			false
		);
	}

	private function handle_bait_request(): void {
		$chapter_id = absint( get_query_var( 'brg_chapter_id' ) );
		$bait_key   = strtolower( sanitize_text_field( (string) get_query_var( 'brg_bait_key' ) ) );
		$actor      = BRG_Monitor::instance()->get_actor();
		$ban        = BRG_Monitor::instance()->get_active_ban( $actor );

		if ( $ban ) {
			$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $ban );
		}

		if ( ! $chapter_id || ! preg_match( '/^[a-f0-9]{20}$/', $bait_key ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		$bait_kind = sanitize_key( wp_unslash( $_GET['kind'] ?? 'passive' ) );
		if ( ! in_array( $bait_kind, [ 'passive', 'reinforced' ], true ) ) {
			$bait_kind = 'passive';
		}

		if ( ! hash_equals( $this->bait_key( $chapter_id, $actor, $bait_kind ), $bait_key ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		$result = BRG_Monitor::instance()->record_honeypot_hit( $actor, $chapter_id, $bait_key, $bait_kind );
		if ( ! empty( $result['banned'] ) ) {
			$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $result );
		}

		$this->render_bait_image( $chapter_id );
	}

	private function handle_presence_request(): void {
		$chapter_id    = absint( get_query_var( 'brg_chapter_id' ) );
		$presence_key  = strtolower( sanitize_text_field( (string) get_query_var( 'brg_presence_key' ) ) );

		if ( ! $chapter_id || ! preg_match( '/^[a-f0-9]{16}$/', $presence_key ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		if ( ! hash_equals( $this->presence_key( $chapter_id ), $presence_key ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		$actor = BRG_Monitor::instance()->get_actor();
		BRG_Monitor::instance()->record_presence_hit( $actor, $chapter_id );

		while ( ob_get_level() ) {
			ob_end_clean();
		}

		status_header( 200 );
		header( 'Content-Type: image/svg+xml; charset=UTF-8' );
		header( 'Cache-Control: private, no-store, no-cache, must-revalidate, max-age=0' );
		header( 'X-Robots-Tag: noindex, nofollow', true );
		echo '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" viewBox="0 0 1 1" aria-hidden="true"><rect width="1" height="1" fill="transparent"/></svg>';
		exit;
	}

	private function handle_appeal_request(): void {
		while ( ob_get_level() ) {
			ob_end_clean();
		}

		nocache_headers();
		header( 'Content-Type: application/json; charset=' . get_bloginfo( 'charset' ) );
		header( 'X-Robots-Tag: noindex, nofollow', true );

		if ( 'POST' !== strtoupper( (string) ( $_SERVER['REQUEST_METHOD'] ?? 'GET' ) ) ) {
			status_header( 405 );
			wp_send_json(
				[
					'success' => false,
					'message' => 'Metodo no permitido.',
				],
				405
			);
		}

		$actor      = BRG_Monitor::instance()->get_actor();
		$case_id    = sanitize_text_field( wp_unslash( $_POST['brg_case_id'] ?? '' ) );
		$contact    = sanitize_text_field( wp_unslash( $_POST['brg_contact'] ?? '' ) );
		$appeal     = sanitize_textarea_field( wp_unslash( $_POST['brg_appeal_text'] ?? '' ) );
		$result     = BRG_Monitor::instance()->submit_appeal( $actor, $case_id, $appeal, $contact );
		$status     = ! empty( $result['ok'] ) ? 200 : 400;

		wp_send_json(
			[
				'success' => ! empty( $result['ok'] ),
				'message' => (string) ( $result['message'] ?? 'No pudimos procesar el reclamo.' ),
			],
			$status
		);
	}

	private function handle_raw_upload_request( string $relative_path ): void {
		$relative_path = ltrim( wp_normalize_path( rawurldecode( $relative_path ) ), '/' );
		$absolute      = $this->relative_upload_path_to_absolute( $relative_path );

		if ( $this->is_valid_internal_tool_request( $relative_path, $absolute ) ) {
			if ( ! $absolute || ! is_file( $absolute ) ) {
				$this->render_error( 404, 'La imagen solicitada no existe.' );
			}

			$this->serve_file( $absolute, $this->detect_mime( $absolute ), basename( $absolute ), true );
		}

		$actor         = BRG_Monitor::instance()->get_actor();
		$ban           = BRG_Monitor::instance()->get_active_ban( $actor );

		if ( $ban ) {
			$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $ban );
		}

		$match = $this->resolve_protected_raw_request( $relative_path );
		if ( $match ) {
			$result = BRG_Monitor::instance()->record_direct_block( $actor, (int) $match['chapter_id'], $relative_path );
			if ( ! empty( $result['banned'] ) ) {
				$this->render_error( 429, 'Demasiadas solicitudes en poco tiempo. Intenta de nuevo en unos minutos.', $result );
			}

			$this->render_error( 403, 'Esta imagen solo puede cargarse desde el lector del capítulo.' );
		}

		$upload_dir = wp_upload_dir();
		$base_dir   = wp_normalize_path( $upload_dir['basedir'] );
		$absolute   = $absolute ? wp_normalize_path( $absolute ) : wp_normalize_path( $base_dir . '/' . $relative_path );

		if ( ! str_starts_with( $absolute, $base_dir . '/' ) || ! is_file( $absolute ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		$filename = basename( $absolute );
		$mime     = $this->detect_mime( $absolute );
		$this->serve_file( $absolute, $mime, $filename, true );
	}

	private function build_internal_tool_url( string $url ): string {
		$relative_path = $this->url_to_relative_upload_path( $url );
		if ( ! $relative_path || ! $this->is_internal_tool_protected_path( $relative_path ) ) {
			return $url;
		}

		$bucket = $this->internal_tool_bucket();

		return add_query_arg(
			[
				'brg_tool' => '1',
				'brg_t'    => $bucket,
				'brg_s'    => $this->internal_tool_signature( $relative_path, $bucket ),
			],
			$url
		);
	}

	private function is_valid_internal_tool_request( string $relative_path, string $absolute = '' ): bool {
		if ( ! $this->is_internal_tool_protected_path( $relative_path ) ) {
			return false;
		}

		$tool   = sanitize_key( wp_unslash( $_GET['brg_tool'] ?? '' ) );
		$bucket = absint( $_GET['brg_t'] ?? 0 );
		$sig    = strtolower( sanitize_text_field( wp_unslash( $_GET['brg_s'] ?? '' ) ) );

		if ( '1' !== $tool || ! $bucket || ! preg_match( '/^[a-f0-9]{24}$/', $sig ) ) {
			return false;
		}

		if ( abs( $this->internal_tool_bucket() - $bucket ) > 2 ) {
			return false;
		}

		if ( ! hash_equals( $this->internal_tool_signature( $relative_path, $bucket ), $sig ) ) {
			return false;
		}

		if ( '' !== $absolute && ! is_file( $absolute ) ) {
			return false;
		}

		return true;
	}

	private function internal_tool_signature( string $relative_path, int $bucket ): string {
		return substr(
			hash_hmac( 'sha256', 'internal-raw|' . $relative_path . '|' . $bucket, wp_salt( 'auth' ) ),
			0,
			24
		);
	}

	private function internal_tool_bucket(): int {
		return (int) floor( time() / self::INTERNAL_TOOL_WINDOW );
	}

	private function is_internal_tool_protected_path( string $relative_path ): bool {
		return str_starts_with( $relative_path, self::RAW_MANHWAS_PREFIX ) || str_starts_with( $relative_path, self::RAW_CAPS_PREFIX );
	}

	private function resolve_protected_raw_request( string $relative_path ): ?array {
		$chapter_id = 0;

		if ( preg_match( '#^manhwas/([^/]+)/capitulo_([^/]+)/.+$#', $relative_path, $matches ) ) {
			$chapter_id = $this->find_chapter_by_series_slug_and_number( sanitize_title( $matches[1] ), $matches[2] );
		} elseif ( preg_match( '#^capitulos/cap-([0-9]+)/.+$#', $relative_path, $matches ) ) {
			$candidate = absint( $matches[1] );
			if ( $candidate && $this->is_chapter_post( $candidate ) ) {
				$chapter_id = $candidate;
			}
		}

		if ( ! $chapter_id ) {
			return null;
		}

		$map = $this->get_chapter_map( $chapter_id );
		if ( empty( $map['raw_paths'][ $relative_path ] ) ) {
			return null;
		}

		return [
			'chapter_id' => $chapter_id,
			'page_key'   => $map['raw_paths'][ $relative_path ],
		];
	}

	private function current_chapter_id(): int {
		if ( ! is_singular( 'post' ) ) {
			return 0;
		}

		$chapter_id = get_queried_object_id();
		if ( ! $chapter_id || ! $this->is_chapter_post( $chapter_id ) ) {
			return 0;
		}

		return empty( $this->get_chapter_images( $chapter_id ) ) ? 0 : $chapter_id;
	}

	private function is_chapter_post( int $post_id ): bool {
		if ( 'post' !== get_post_type( $post_id ) ) {
			return false;
		}

		return '' !== (string) get_post_meta( $post_id, 'ero_seri', true );
	}

	private function get_chapter_map( int $chapter_id, ?int $window = null ): array {
		$window = $window ?? $this->map_window();
		$key = 'brg_chapter_map_' . $chapter_id . '_' . $window;
		$map = get_transient( $key );
		if ( is_array( $map ) && ! empty( $map['pages'] ) ) {
			return $map;
		}

		$map = [
			'chapter_id' => $chapter_id,
			'pages'      => [],
			'raw_urls'   => [],
			'raw_paths'  => [],
		];

		$image_urls = $this->get_chapter_images( $chapter_id );
		foreach ( $image_urls as $raw_url ) {
			$relative = $this->url_to_relative_upload_path( $raw_url );
			if ( ! $relative ) {
				continue;
			}

			$absolute = $this->relative_upload_path_to_absolute( $relative );
			if ( ! $absolute || ! is_file( $absolute ) ) {
				continue;
			}

			$page_key  = $this->page_key( $chapter_id, $relative, $window );
			$filename  = basename( $absolute );
			$alias_url = home_url( '/' . self::ALIAS_PREFIX . '/' . $chapter_id . '/' . $page_key . '/' . rawurlencode( $filename ) );

			$map['pages'][ $page_key ] = [
				'raw_url'   => $raw_url,
				'relative'  => $relative,
				'abs_path'  => $absolute,
				'filename'  => $filename,
				'mime'      => $this->detect_mime( $absolute ),
				'alias_url' => $alias_url,
			];
			foreach ( $this->alternate_raw_urls( $raw_url, $relative ) as $candidate_url ) {
				$map['raw_urls'][ $candidate_url ] = $alias_url;
			}
			$map['raw_paths'][ $relative ]   = $page_key;
		}

		set_transient( $key, $map, self::MAP_TTL );
		return $map;
	}

	private function get_chapter_images( int $chapter_id ): array {
		$primary = get_post_meta( $chapter_id, '_chapter_images_urls', true );
		$images  = $this->normalize_image_meta( $primary );
		if ( ! empty( $images ) ) {
			return $images;
		}

		$fallback = get_post_meta( $chapter_id, 'ero_chapter_images', true );
		$images   = $this->normalize_image_meta( $fallback );
		if ( ! empty( $images ) ) {
			return $images;
		}

		return $this->images_from_canonical_folder( $chapter_id );
	}

	private function normalize_image_meta( $value ): array {
		if ( empty( $value ) ) {
			return [];
		}

		if ( is_string( $value ) ) {
			$decoded = json_decode( $value, true );
			if ( is_array( $decoded ) ) {
				$value = $decoded;
			} else {
				$value = preg_split( '/[\r\n,]+/', $value );
			}
		}

		if ( ! is_array( $value ) ) {
			return [];
		}

		$urls = [];
		array_walk_recursive(
			$value,
			static function ( $item ) use ( &$urls ) {
				if ( ! is_string( $item ) ) {
					return;
				}
				$item = trim( $item );
				if ( '' === $item ) {
					return;
				}
				if ( preg_match( '/\.(?:jpe?g|png|gif|webp|avif|bmp)$/i', strtok( $item, '?' ) ) ) {
					$urls[] = $item;
				}
			}
		);

		return array_values( array_unique( $urls ) );
	}

	private function images_from_canonical_folder( int $chapter_id ): array {
		$series_id    = absint( get_post_meta( $chapter_id, 'ero_seri', true ) );
		$chapter_num  = trim( (string) get_post_meta( $chapter_id, 'ero_chapter', true ) );
		$series       = $series_id ? get_post( $series_id ) : null;

		if ( ! $series || '' === $chapter_num ) {
			return [];
		}

		$upload_dir = wp_upload_dir();
		$folder     = trailingslashit( $upload_dir['basedir'] ) . 'manhwas/' . $series->post_name . '/capitulo_' . $chapter_num;
		$folder     = wp_normalize_path( $folder );

		if ( ! is_dir( $folder ) ) {
			return [];
		}

		$files = glob( $folder . '/*.{jpg,jpeg,png,gif,webp,avif,bmp}', GLOB_BRACE );
		if ( empty( $files ) ) {
			return [];
		}

		natsort( $files );
		$files = array_values( $files );
		$base  = trailingslashit( $upload_dir['baseurl'] );
		$dir   = trailingslashit( $upload_dir['basedir'] );

		return array_map(
			static function ( string $file ) use ( $base, $dir ): string {
				return $base . ltrim( str_replace( wp_normalize_path( $dir ), '', wp_normalize_path( $file ) ), '/' );
			},
			$files
		);
	}

	private function issue_cookie( int $chapter_id ): void {
		if ( headers_sent() ) {
			return;
		}

		$expires = time() + self::COOKIE_TTL;
		$payload = $chapter_id . '|' . $expires . '|' . $this->ip_anchor( $this->client_ip() );
		$sig     = hash_hmac( 'sha256', $payload, wp_salt( 'auth' ) );
		$value   = $chapter_id . '.' . $expires . '.' . $sig;

		setcookie(
			self::COOKIE_PREFIX . $chapter_id,
			$value,
			[
				'expires'  => $expires,
				'path'     => '/' . self::ALIAS_PREFIX . '/',
				'secure'   => is_ssl(),
				'httponly' => true,
				'samesite' => 'Lax',
			]
		);
	}

	private function has_valid_cookie( int $chapter_id ): bool {
		$name = self::COOKIE_PREFIX . $chapter_id;
		if ( empty( $_COOKIE[ $name ] ) ) {
			return false;
		}

		$parts = explode( '.', (string) $_COOKIE[ $name ] );
		if ( 3 !== count( $parts ) ) {
			return false;
		}

		$cookie_chapter = absint( $parts[0] );
		$expires        = absint( $parts[1] );
		$signature      = (string) $parts[2];

		if ( $cookie_chapter !== $chapter_id || ! $expires || time() > $expires ) {
			return false;
		}

		$current_anchor = $this->ip_anchor( $this->client_ip() );
		$expected_bound = hash_hmac( 'sha256', $chapter_id . '|' . $expires . '|' . $current_anchor, wp_salt( 'auth' ) );
		$expected_legacy = hash_hmac( 'sha256', $chapter_id . '|' . $expires, wp_salt( 'auth' ) );
		return hash_equals( $expected_bound, $signature ) || hash_equals( $expected_legacy, $signature );
	}

	private function page_key( int $chapter_id, string $relative_path, ?int $window = null ): string {
		$window = $window ?? $this->map_window();
		return substr( hash_hmac( 'sha256', $chapter_id . '|' . strtolower( $relative_path ) . '|' . $window, wp_salt( 'auth' ) ), 0, 20 );
	}

	private function disable_guard_caching(): void {
		if ( ! defined( 'DONOTCACHEPAGE' ) ) {
			define( 'DONOTCACHEPAGE', true );
		}

		do_action( 'litespeed_control_set_nocache', 'Bloom Reader Image Guard Route' );
		header( 'X-LiteSpeed-Cache-Control: no-cache' );
		header( 'Cache-Control: no-store, no-cache, must-revalidate, max-age=0' );
		header( 'Pragma: no-cache' );
	}

	private function bait_key( int $chapter_id, array $actor, string $kind = 'passive' ): string {
		return substr( hash_hmac( 'sha256', $chapter_id . '|' . $actor['key'] . '|bait|' . $kind, wp_salt( 'auth' ) ), 0, 20 );
	}

	private function presence_key( int $chapter_id, ?int $window = null ): string {
		$window = $window ?? (int) floor( time() / 3600 );
		return substr( hash_hmac( 'sha256', $chapter_id . '|presence|' . $window, wp_salt( 'auth' ) ), 0, 16 );
	}

	private function build_presence_url( int $chapter_id ): string {
		return home_url( '/' . self::PRESENCE_PREFIX . '/' . $chapter_id . '/' . $this->presence_key( $chapter_id ) . '.svg' );
	}

	private function bait_filename( int $chapter_id, array $actor, string $kind = 'passive' ): string {
		$seed = substr( hash_hmac( 'sha256', $chapter_id . '|' . $actor['key'] . '|bait-file|' . $kind, wp_salt( 'auth' ) ), 0, 7 );
		$number = (string) ( hexdec( $seed ) % 9000000 + 1000000 );

		return 'pag' . $number . '.webp';
	}

	private function build_bait_url( int $chapter_id, array $actor, string $kind = 'passive' ): string {
		return add_query_arg(
			'kind',
			$kind,
			home_url( '/' . self::BAIT_PREFIX . '/' . $chapter_id . '/' . $this->bait_key( $chapter_id, $actor, $kind ) . '/' . $this->bait_filename( $chapter_id, $actor, $kind ) )
		);
	}

	private function build_passive_bait_markup( int $chapter_id, array $actor ): string {
		$bait_url = $this->build_bait_url( $chapter_id, $actor, 'passive' );

		$markup  = '';
		$markup .= "<div class=\"reader-media-shadow reader-media-shadow-passive\" data-reader-media=\"" . esc_attr( $bait_url ) . "\" data-original=\"" . esc_attr( $bait_url ) . "\" hidden aria-hidden=\"true\"></div>\n";
		$markup .= "<img class=\"reader-media-asset reader-media-asset-passive\" data-src=\"" . esc_url( $bait_url ) . "\" data-gifsrc=\"" . esc_url( $bait_url ) . "\" gifsrc=\"" . esc_url( $bait_url ) . "\" alt=\"BloomScans\" width=\"1\" height=\"1\" hidden aria-hidden=\"true\" loading=\"lazy\" decoding=\"async\" referrerpolicy=\"no-referrer\" style=\"display:none !important;max-width:0 !important;max-height:0 !important;opacity:0 !important;pointer-events:none !important;\" />\n";
		$markup .= "<input class=\"reader-media-thumb reader-media-thumb-passive\" type=\"image\" data-src=\"" . esc_url( $bait_url ) . "\" alt=\"BloomScans\" width=\"1\" height=\"1\" hidden aria-hidden=\"true\" style=\"display:none !important;max-width:0 !important;max-height:0 !important;opacity:0 !important;pointer-events:none !important;\" />\n";
		$markup .= "<picture class=\"reader-media-stack reader-media-stack-passive\" hidden aria-hidden=\"true\" style=\"display:none !important;\"><source srcset=\"" . esc_url( $bait_url ) . " 1x\" /><img alt=\"BloomScans\" width=\"1\" height=\"1\" loading=\"lazy\" decoding=\"async\" style=\"display:none !important;max-width:0 !important;max-height:0 !important;opacity:0 !important;pointer-events:none !important;\" /></picture>\n";

		return $markup;
	}

	private function build_reinforced_bait_markup( int $chapter_id, array $actor ): string {
		$bait_url  = $this->build_bait_url( $chapter_id, $actor, 'reinforced' );
		$bait_json = wp_json_encode(
			[
				'original' => $bait_url,
				'full'     => $bait_url,
			],
			JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
		);

		$markup  = '';
		$markup .= "<div class=\"reader-media-shadow reader-media-shadow-reinforced\" data-reader-media=\"" . esc_attr( $bait_url ) . "\" data-original=\"" . esc_attr( $bait_url ) . "\" hidden aria-hidden=\"true\"></div>\n";
		$markup .= "<img class=\"reader-media-asset reader-media-asset-reinforced\" data-src=\"" . esc_url( $bait_url ) . "\" data-gifsrc=\"" . esc_url( $bait_url ) . "\" gifsrc=\"" . esc_url( $bait_url ) . "\" alt=\"BloomScans\" width=\"1\" height=\"1\" hidden aria-hidden=\"true\" loading=\"lazy\" decoding=\"async\" referrerpolicy=\"no-referrer\" style=\"display:none !important;max-width:0 !important;max-height:0 !important;opacity:0 !important;pointer-events:none !important;\" />\n";
		$markup .= "<input class=\"reader-media-thumb reader-media-thumb-reinforced\" type=\"image\" data-src=\"" . esc_url( $bait_url ) . "\" alt=\"BloomScans\" width=\"1\" height=\"1\" hidden aria-hidden=\"true\" style=\"display:none !important;max-width:0 !important;max-height:0 !important;opacity:0 !important;pointer-events:none !important;\" />\n";
		$markup .= "<picture class=\"reader-media-stack reader-media-stack-reinforced\" hidden aria-hidden=\"true\" style=\"display:none !important;\"><source srcset=\"" . esc_url( $bait_url ) . " 1x\" /><img alt=\"BloomScans\" width=\"1\" height=\"1\" loading=\"lazy\" decoding=\"async\" style=\"display:none !important;max-width:0 !important;max-height:0 !important;opacity:0 !important;pointer-events:none !important;\" /></picture>\n";
		$markup .= "<a class=\"reader-media-link reader-media-link-reinforced\" href=\"" . esc_url( $bait_url ) . "\" hidden aria-hidden=\"true\" tabindex=\"-1\" rel=\"nofollow noopener noreferrer\">cover</a>\n";
		$markup .= "<a class=\"reader-media-link reader-media-link-reinforced\" href=\"" . esc_url( add_query_arg( 'download', '1', $bait_url ) ) . "\" hidden aria-hidden=\"true\" tabindex=\"-1\" rel=\"nofollow noopener noreferrer\">full</a>\n";
		$markup .= "<script type=\"application/json\" class=\"reader-media-json reader-media-json-reinforced\">" . esc_html( $bait_json ) . "</script>\n";

		return $markup;
	}

	private function detect_mime( string $absolute_path ): string {
		$filetype = wp_check_filetype( $absolute_path );
		if ( ! empty( $filetype['type'] ) ) {
			return $filetype['type'];
		}

		return 'application/octet-stream';
	}

	private function serve_file( string $absolute_path, string $mime, string $filename, bool $allow_cache ): void {
		if ( ! is_file( $absolute_path ) || ! is_readable( $absolute_path ) ) {
			$this->render_error( 404, 'La imagen solicitada no existe.' );
		}

		while ( ob_get_level() ) {
			ob_end_clean();
		}

		status_header( 200 );
		header( 'Content-Type: ' . $mime );
		header( 'Content-Length: ' . filesize( $absolute_path ) );
		header( 'Content-Disposition: inline; filename="' . rawurlencode( $filename ) . '"' );
		header( 'X-Robots-Tag: noindex' );
		if ( $allow_cache ) {
			header( 'Cache-Control: public, max-age=3600' );
		} else {
			header( 'Cache-Control: private, no-store, no-cache, must-revalidate, max-age=0' );
			header( 'Pragma: no-cache' );
		}

		readfile( $absolute_path );
		exit;
	}

	private function render_error( int $status, string $message, array $meta = [] ): void {
		while ( ob_get_level() ) {
			ob_end_clean();
		}

		status_header( $status );
		nocache_headers();
		header( 'Content-Type: text/html; charset=' . get_bloginfo( 'charset' ) );
		header( 'X-Robots-Tag: noindex, nofollow', true );

		$title = $status . ' - Bloom Reader Guard';
		echo '<!doctype html><html lang="es"><head><meta charset="' . esc_attr( get_bloginfo( 'charset' ) ) . '"><meta name="viewport" content="width=device-width, initial-scale=1"><title>' . esc_html( $title ) . '</title>';
		echo '<style>body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1015;color:#f2f4f7;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;box-sizing:border-box}.brg-box{max-width:720px;width:100%;background:#171922;border:1px solid #263042;border-radius:18px;padding:28px;box-shadow:0 16px 40px rgba(0,0,0,.35)}h1{margin:0 0 10px;font-size:28px}p{margin:0;color:#c2cad6;line-height:1.6}.brg-code{display:inline-flex;align-items:center;justify-content:center;min-width:54px;height:32px;border-radius:999px;background:#00c896;color:#04110c;font-weight:700;margin-bottom:14px}.brg-meta{margin-top:16px;padding:14px 16px;border:1px solid #263042;border-radius:14px;background:#111620}.brg-meta strong{display:block;margin-bottom:6px}.brg-row{margin-top:8px;color:#d9e2ec}.brg-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}.brg-btn{display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;text-decoration:none;font-weight:600}.brg-btn-primary{background:#00c896;color:#04110c}.brg-btn-secondary{background:#232c3b;color:#f2f4f7}</style></head><body>';
		echo '<div class="brg-box"><div class="brg-code">' . esc_html( (string) $status ) . '</div><h1>Bloom Reader Guard</h1><p>' . esc_html( $message ) . '</p>';
		if ( 429 === $status && ( ! empty( $meta['ban_until'] ) || ! empty( $meta['manual'] ) ) ) {
			$ban_until = (int) $meta['ban_until'];
			$countdown = max( 0, $ban_until - time() );
			$reason_code = $this->public_reason_code( (string) ( $meta['reason'] ?? 'rate_limited' ) );
			$is_manual = ! empty( $meta['manual'] );
			$actor = BRG_Monitor::instance()->get_actor();
			$case_id = (string) ( $meta['case_id'] ?? '' );
			echo '<div class="brg-meta">';
			echo '<strong>Pausa temporal del lector</strong>';
			echo '<div class="brg-row">Codigo de revision: ' . esc_html( $reason_code ) . '</div>';
			if ( '' !== $case_id ) {
				echo '<div class="brg-row">ID del caso: <strong>' . esc_html( $case_id ) . '</strong></div>';
			}
			if ( ! empty( $actor['user_id'] ) ) {
				echo '<div class="brg-row">Cuenta asociada: #' . esc_html( (string) $actor['user_id'] ) . ' @' . esc_html( (string) ( $actor['user_login'] ?? '' ) ) . '</div>';
			}
			if ( $is_manual ) {
				echo '<div class="brg-row">Este bloqueo fue aplicado manualmente por el equipo de moderacion.</div>';
			} else {
				echo '<div class="brg-row">Vuelve a intentar: ' . esc_html( wp_date( 'Y-m-d H:i:s', $ban_until ) ) . '</div>';
				echo '<div class="brg-row">Tiempo restante: <span data-brg-countdown="' . esc_attr( (string) $countdown ) . '">' . esc_html( gmdate( 'H:i:s', $countdown ) ) . '</span></div>';
			}
			echo '<div class="brg-row">Si crees que fue un error, puedes enviar un reclamo desde aqui mismo.</div>';
			echo $this->build_appeal_form_markup( $case_id, $actor, true );
			echo '</div>';
			echo '<div class="brg-actions"><a class="brg-btn brg-btn-primary" href="' . esc_url( self::DISCORD_URL ) . '" target="_blank" rel="noopener noreferrer">Apelar en Discord</a><a class="brg-btn brg-btn-secondary" href="javascript:location.reload()">Reintentar</a></div>';
			echo '<script>(function(){var el=document.querySelector(\"[data-brg-countdown]\");if(el){var secs=parseInt(el.getAttribute(\"data-brg-countdown\"),10)||0;function pad(v){return String(v).padStart(2,\"0\");}function tick(){if(secs<0){return;}var h=Math.floor(secs/3600),m=Math.floor((secs%3600)/60),s=secs%60;el.textContent=pad(h)+\":\"+pad(m)+\":\"+pad(s);secs--;if(secs>=0){setTimeout(tick,1000);}}tick();} document.querySelectorAll(\"[data-brg-appeal-form]\").forEach(function(form){form.addEventListener(\"submit\",function(ev){ev.preventDefault();var status=form.querySelector(\"[data-brg-appeal-status]\");if(status){status.textContent=\"Enviando reclamo...\";status.style.color=\"#c5d0db\";} fetch(form.action,{method:\"POST\",body:new FormData(form),credentials:\"same-origin\"}).then(function(r){return r.json();}).then(function(data){if(status){status.textContent=(data&&data.message)?data.message:\"Reclamo enviado.\";status.style.color=(data&&data.success)?\"#00c896\":\"#fda29b\";} if(data&&data.success){form.reset();}}).catch(function(){if(status){status.textContent=\"No pudimos enviar el reclamo ahora. Intenta de nuevo.\";status.style.color=\"#fda29b\";}});});});})();</script>';
		}
		echo '</div></body></html>';
		exit;
	}

	private function render_bait_image( int $chapter_id ): void {
		while ( ob_get_level() ) {
			ob_end_clean();
		}

		$this->disable_guard_caching();
		status_header( 200 );
		header( 'Content-Type: image/svg+xml; charset=UTF-8' );
		$requested_name = sanitize_file_name( (string) get_query_var( 'brg_filename' ) );
		if ( '' === $requested_name ) {
			$requested_name = 'pag3102313.webp';
		}
		header( 'Content-Disposition: inline; filename="' . rawurlencode( $requested_name ) . '"' );
		header( 'X-Robots-Tag: noindex, nofollow', true );

		$label = 'BloomScans cover #' . $chapter_id;
		$svg   = <<<SVG
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1700" viewBox="0 0 1200 1700" role="img" aria-label="{$label}">
  <rect width="1200" height="1700" fill="#10151d"/>
  <rect x="60" y="80" width="1080" height="1540" rx="28" fill="#172130" stroke="#273447" stroke-width="6"/>
  <g fill="#203245" opacity="0.95">
    <circle cx="220" cy="260" r="120"/>
    <circle cx="920" cy="380" r="160"/>
    <circle cx="430" cy="780" r="180"/>
    <circle cx="860" cy="1060" r="130"/>
    <circle cx="300" cy="1340" r="150"/>
  </g>
  <g fill="#0ccca0" opacity="0.18">
    <rect x="120" y="210" width="820" height="150" rx="20"/>
    <rect x="180" y="640" width="760" height="120" rx="18"/>
    <rect x="150" y="1210" width="700" height="130" rx="20"/>
  </g>
  <text x="110" y="520" fill="#f2f5f7" font-family="Arial, Helvetica, sans-serif" font-size="72" font-weight="700">Bloom Scans</text>
  <text x="110" y="610" fill="#9fb4c7" font-family="Arial, Helvetica, sans-serif" font-size="34">Vista previa del lector</text>
  <text x="110" y="1000" fill="#d9e6f2" font-family="Arial, Helvetica, sans-serif" font-size="56" font-weight="700">Capitulo {$chapter_id}</text>
  <text x="110" y="1080" fill="#9fb4c7" font-family="Arial, Helvetica, sans-serif" font-size="30">BloomScans Reader Preview</text>
  <text x="110" y="1450" fill="#6fe2c2" font-family="Arial, Helvetica, sans-serif" font-size="36">bloomscans.com</text>
</svg>
SVG;

		echo $svg; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		exit;
	}

	private function build_block_notice_markup( array $ban, array $actor = [] ): string {
		$ban_until = (int) ( $ban['ban_until'] ?? 0 );
		$countdown = max( 0, $ban_until - time() );
		$is_manual = ! empty( $ban['manual'] );
		$reason_code = $this->public_reason_code( (string) ( $ban['reason'] ?? 'rate_limited' ) );
		$case_id = (string) ( $ban['case_id'] ?? '' );
		$scope = (string) ( $ban['scope'] ?? 'ip' );

		$markup = '<section class="brg-reader-notice" data-brg-reader-notice data-ban-until="' . esc_attr( (string) $ban_until ) . '" data-brg-anchor="notice" style="position:relative;z-index:9999;max-width:980px;margin:68px auto 18px;padding:18px 20px;border:1px solid #2e3746;border-radius:18px;background:rgba(17,22,32,.96);color:#f2f4f7;box-shadow:0 20px 40px rgba(0,0,0,.28);">'
			. '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;justify-content:space-between;">'
			. '<div style="max-width:680px;">'
			. '<div style="display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;background:#00c896;color:#04110c;font-weight:700;font-size:12px;margin-bottom:10px;">Reader temporalmente bloqueado</div>'
			. '<h2 style="margin:0 0 8px;font-size:22px;line-height:1.25;">Tu acceso al lector fue pausado temporalmente</h2>'
			. '<p style="margin:0;color:#c5d0db;line-height:1.65;">Codigo de revision: <strong style="color:#f2f4f7;">' . esc_html( $reason_code ) . '</strong>. ID del caso: <strong style="color:#f2f4f7;">' . esc_html( $case_id ?: 'pendiente' ) . '</strong>. Durante este tiempo las imagenes del capitulo no van a cargar.</p>';

		if ( ! empty( $actor['user_id'] ) ) {
			$markup .= '<p style="margin:10px 0 0;color:#c5d0db;line-height:1.65;">Cuenta detectada: <strong style="color:#f2f4f7;">#' . esc_html( (string) $actor['user_id'] ) . ' @' . esc_html( (string) ( $actor['user_login'] ?? '' ) ) . '</strong>. Este bloqueo tambien aplica al lector cuando entras con esta cuenta.</p>';
		}

		if ( $is_manual ) {
			$markup .= '<p style="margin:10px 0 0;color:#c5d0db;line-height:1.65;">Este bloqueo fue aplicado manualmente por el equipo. Si crees que fue un error, puedes dejar un reclamo y tambien escribirnos por Discord.</p>';
		} else {
			$target = 'user' === $scope ? 'cuenta' : ( 'network' === $scope ? 'red' : 'IP' );
			$markup .= '<p style="margin:10px 0 0;color:#c5d0db;line-height:1.65;">Vuelve a intentar a las <strong style="color:#f2f4f7;">' . esc_html( wp_date( 'Y-m-d H:i:s', $ban_until ) ) . '</strong>. Este temporizador hoy esta asociado a tu ' . esc_html( $target ) . ' detectada por el guard.</p>';
		}

		$markup .= '</div>'
			. '<div style="min-width:220px;">';

		if ( ! $is_manual ) {
			$markup .= '<div style="padding:12px 14px;border-radius:14px;background:#0f1520;border:1px solid #263042;">'
				. '<div style="font-size:12px;color:#8ea0b3;text-transform:uppercase;letter-spacing:.04em;">Tiempo restante</div>'
				. '<div data-brg-reader-countdown="' . esc_attr( (string) $countdown ) . '" style="font-size:30px;font-weight:800;margin-top:6px;">' . esc_html( gmdate( 'H:i:s', $countdown ) ) . '</div>'
				. '</div>';
		}

		$markup .= $this->build_appeal_form_markup( $case_id, $actor, false );
		$markup .= '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;">'
			. '<a href="' . esc_url( self::DISCORD_URL ) . '" target="_blank" rel="noopener noreferrer" style="display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;background:#00c896;color:#04110c;font-weight:700;text-decoration:none;">Apelar en Discord</a>'
			. '<a href="javascript:location.reload()" style="display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;background:#1e2633;color:#f2f4f7;font-weight:700;text-decoration:none;">Reintentar</a>'
			. '</div>'
			. '</div>'
			. '</div>'
			. '</section>';

		return $markup;
	}

	private function build_appeal_form_markup( string $case_id, array $actor, bool $compact ): string {
		$action      = home_url( '/' . self::APPEAL_PREFIX . '/' );
		$contact     = ! empty( $actor['user_email'] ) ? (string) $actor['user_email'] : '';
		$container   = $compact ? 'margin-top:14px;' : 'margin-top:14px;padding:12px 14px;border-radius:14px;background:#0f1520;border:1px solid #263042;';
		$field_style = 'width:100%;box-sizing:border-box;padding:10px 12px;border-radius:10px;border:1px solid #334155;background:#111827;color:#f2f4f7;';
		$grid_style  = 'display:grid;gap:10px;margin-top:12px;';

		$markup  = '<form method="post" action="' . esc_url( $action ) . '" data-brg-appeal-form style="' . esc_attr( $container ) . '">';
		$markup .= '<input type="hidden" name="brg_case_id" value="' . esc_attr( $case_id ) . '">';
		$markup .= '<div style="font-size:12px;color:#8ea0b3;text-transform:uppercase;letter-spacing:.04em;">Reclamar este bloqueo</div>';
		$markup .= '<div style="' . esc_attr( $grid_style ) . '">';
		$markup .= '<input type="text" name="brg_contact" value="' . esc_attr( $contact ) . '" placeholder="Correo o medio de contacto (opcional)" style="' . esc_attr( $field_style ) . '">';
		$markup .= '<textarea name="brg_appeal_text" rows="3" placeholder="Explica brevemente por que crees que el bloqueo fue un error." style="' . esc_attr( $field_style . 'min-height:88px;resize:vertical;' ) . '"></textarea>';
		$markup .= '</div>';
		$markup .= '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px;">';
		$markup .= '<button type="submit" style="display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;border:0;background:#2563eb;color:#fff;font-weight:700;cursor:pointer;">Enviar reclamo</button>';
		$markup .= '<span data-brg-appeal-status style="font-size:13px;color:#c5d0db;"></span>';
		$markup .= '</div>';
		$markup .= '</form>';

		return $markup;
	}

	private function resolve_page_entry( int $chapter_id, string $page_key ): ?array {
		$current_map = $this->get_chapter_map( $chapter_id );
		if ( ! empty( $current_map['pages'][ $page_key ] ) ) {
			return $current_map['pages'][ $page_key ];
		}

		$previous_window = $this->map_window() - 1;
		if ( $previous_window < 0 ) {
			return null;
		}

		$previous_map = $this->get_chapter_map( $chapter_id, $previous_window );
		return $previous_map['pages'][ $page_key ] ?? null;
	}

	private function map_window(): int {
		return (int) floor( time() / self::PAGE_WINDOW_SECONDS );
	}

	private function client_ip(): string {
		foreach ( [ 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'HTTP_CLIENT_IP', 'REMOTE_ADDR' ] as $key ) {
			if ( empty( $_SERVER[ $key ] ) ) {
				continue;
			}

			$value = trim( (string) $_SERVER[ $key ] );
			if ( 'HTTP_X_FORWARDED_FOR' === $key && false !== strpos( $value, ',' ) ) {
				$parts = explode( ',', $value );
				$value = trim( (string) reset( $parts ) );
			}

			if ( filter_var( $value, FILTER_VALIDATE_IP ) ) {
				return $value;
			}
		}

		return '0.0.0.0';
	}

	private function ip_anchor( string $ip ): string {
		if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 ) ) {
			$parts = array_pad( explode( '.', $ip ), 4, '0' );
			return $parts[0] . '.' . $parts[1] . '.' . $parts[2];
		}

		if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6 ) ) {
			$expanded = $this->expand_ipv6( $ip );
			$groups   = explode( ':', $expanded );
			return implode( ':', array_slice( $groups, 0, 4 ) );
		}

		return $ip;
	}

	private function expand_ipv6( string $ip ): string {
		$packed = @inet_pton( $ip );
		if ( false === $packed ) {
			return $ip;
		}

		$hex    = bin2hex( $packed );
		$groups = str_split( $hex, 4 );
		return implode( ':', $groups );
	}

	private function public_reason_code( string $reason ): string {
		return BRG_Monitor::instance()->reason_code( $reason );
	}

	private function url_to_relative_upload_path( string $url ): string {
		$upload_dir = wp_upload_dir();
		$baseurl    = trailingslashit( wp_normalize_path( $upload_dir['baseurl'] ) );
		$url        = wp_normalize_path( strtok( $url, '?' ) );

		if ( str_starts_with( $url, $baseurl ) ) {
			return ltrim( substr( $url, strlen( $baseurl ) ), '/' );
		}

		$parsed = wp_parse_url( $url, PHP_URL_PATH );
		if ( ! $parsed ) {
			return '';
		}

		$uploads_path = wp_parse_url( $upload_dir['baseurl'], PHP_URL_PATH );
		if ( $uploads_path && str_starts_with( $parsed, $uploads_path ) ) {
			return ltrim( substr( $parsed, strlen( $uploads_path ) ), '/' );
		}

		$uploads_marker = '/wp-content/uploads/';
		$marker_pos     = strpos( $parsed, $uploads_marker );
		if ( false !== $marker_pos ) {
			return ltrim( substr( $parsed, $marker_pos + strlen( $uploads_marker ) ), '/' );
		}

		return '';
	}

	private function alternate_raw_urls( string $raw_url, string $relative_path ): array {
		$urls      = [];
		$urls[]    = $raw_url;
		$clean_rel = ltrim( $relative_path, '/' );
		$host      = (string) wp_parse_url( home_url(), PHP_URL_HOST );

		if ( '' !== $clean_rel ) {
			$local_base = trailingslashit( wp_upload_dir()['baseurl'] );
			$urls[]     = $local_base . $clean_rel;

			if ( '' !== $host ) {
				for ( $i = 0; $i <= 3; $i++ ) {
					$urls[] = 'https://i' . $i . '.wp.com/' . $host . '/wp-content/uploads/' . $clean_rel;
				}
			}
		}

		return array_values( array_unique( $urls ) );
	}

	private function relative_upload_path_to_absolute( string $relative_path ): string {
		$upload_dir = wp_upload_dir();
		$base_dir   = wp_normalize_path( $upload_dir['basedir'] );
		$relative   = ltrim( wp_normalize_path( $relative_path ), '/' );
		$absolute   = wp_normalize_path( $base_dir . '/' . $relative );

		if ( ! str_starts_with( $absolute, $base_dir . '/' ) ) {
			return '';
		}

		return $absolute;
	}

	private function find_chapter_by_series_slug_and_number( string $series_slug, string $chapter_number ): int {
		global $wpdb;

		$series = get_page_by_path( $series_slug, OBJECT, 'manga' );
		if ( ! $series ) {
			return 0;
		}

		$chapter_number = trim( (string) $chapter_number );
		if ( '' === $chapter_number ) {
			return 0;
		}

		$sql = $wpdb->prepare(
			"SELECT p.ID
			FROM {$wpdb->posts} p
			INNER JOIN {$wpdb->postmeta} pm_num ON pm_num.post_id = p.ID AND pm_num.meta_key = 'ero_chapter'
			INNER JOIN {$wpdb->postmeta} pm_series ON pm_series.post_id = p.ID AND pm_series.meta_key = 'ero_seri'
			WHERE p.post_type = 'post'
			  AND p.post_status = 'publish'
			  AND pm_series.meta_value = %d
			  AND pm_num.meta_value = %s
			ORDER BY p.ID DESC
			LIMIT 1",
			(int) $series->ID,
			$chapter_number
		);

		return absint( $wpdb->get_var( $sql ) );
	}
}
