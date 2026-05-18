<?php
/**
 * Plugin Name: Bloom Security Hardening
 * Description: Hardening transversal para BloomScans: headers, REST, autores, xmlrpc y registro.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Bloom_Security_Hardening {
	private const LOGIN_LIMIT            = 12;
	private const LOGIN_WINDOW           = 900;
	private const REGISTER_LIMIT         = 5;
	private const REGISTER_WINDOW        = 3600;
	private const REGISTER_MIN_FILL_TIME = 4;

	public function __construct() {
		add_action( 'init', [ $this, 'bootstrap' ], 1 );
		add_action( 'send_headers', [ $this, 'send_security_headers' ], 20 );
		add_action( 'login_init', [ $this, 'send_security_headers' ], 1 );
		add_action( 'template_redirect', [ $this, 'block_author_archives' ], 0 );
		add_action( 'register_form', [ $this, 'render_native_registration_fields' ] );
		add_action( 'bloom_security_render_registration_fields', [ $this, 'render_custom_registration_fields' ] );
		add_action( 'init', [ $this, 'handle_custom_registration' ], 1 );
		add_action( 'init', [ $this, 'handle_email_verification' ], 1 );
		add_filter( 'registration_errors', [ $this, 'validate_native_registration' ], 10, 3 );
		add_action( 'user_register', [ $this, 'maybe_mark_new_user_pending' ], 10, 1 );
		add_filter( 'authenticate', [ $this, 'limit_login_attempts' ], 40, 3 );
		add_filter( 'wp_authenticate_user', [ $this, 'block_pending_user_login' ], 20, 2 );
		add_action( 'wp_login_failed', [ $this, 'record_login_failure' ] );
		add_action( 'wp_login', [ $this, 'clear_login_limit' ], 10, 2 );
		add_filter( 'xmlrpc_enabled', '__return_false' );
		add_filter( 'wp_headers', [ $this, 'filter_wp_headers' ], 20 );
		add_filter( 'rest_endpoints', [ $this, 'filter_rest_endpoints' ], 100 );
		add_filter( 'rest_pre_dispatch', [ $this, 'guard_rest_routes' ], 10, 3 );
		add_filter( 'rest_authentication_errors', [ $this, 'guard_rest_authentication' ] );
		add_filter( 'wpseo_enable_author_sitemap', '__return_false' );
		add_filter( 'the_generator', '__return_empty_string' );
		add_action( 'wp', [ $this, 'suppress_ads_on_auth_pages' ], 1 );

		// Desactivar anuncios flotantes del tema en paginas de auth
		add_filter( 'option_floatcenter', [ $this, 'suppress_theme_floating_ads' ] );
		add_filter( 'option_floatleft', [ $this, 'suppress_theme_floating_ads' ] );
		add_filter( 'option_floatright', [ $this, 'suppress_theme_floating_ads' ] );
		add_filter( 'option_floatbottom', [ $this, 'suppress_theme_floating_ads' ] );
		add_filter( 'option_floattop', [ $this, 'suppress_theme_floating_ads' ] );

		// CSS fix: evitar truncado excesivo de titulos de cards al hacer zoom
		add_action( 'wp_head', [ $this, 'inject_zoom_safe_css' ], 99 );
	}

	/**
	 * Suprime los anuncios flotantes del tema en paginas de login/register.
	 * 
	 * @param mixed $value Valor de la opcion.
	 * @return mixed
	 */
	public function suppress_theme_floating_ads( $value ) {
		$uri = isset( $_SERVER['REQUEST_URI'] ) ? (string) wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
		if ( preg_match( '#^/login(/|\?|$)#i', $uri ) || preg_match( '#^/register(/|\?|$)#i', $uri ) || preg_match( '#^/panel-scan(/|\?|$)#i', $uri ) ) {
			return false; // El tema comprueba if($kln)
		}
		return $value;
	}

	/**
	 * CSS/JS: titulos en 2 lineas + capitulos como "Cap 09" para ahorrar espacio.
	 */
	public function inject_zoom_safe_css(): void {
		if ( is_admin() ) return;
		?>
		<style id="bloom-zoom-safe-css">
		/* ── Titulos: hasta 2 lineas antes de truncar ── */
		.listupd .utao .uta .luf h4 {
			white-space: normal !important;
			text-overflow: unset !important;
			display: -webkit-box !important;
			-webkit-line-clamp: 2;
			-webkit-box-orient: vertical;
			overflow: hidden;
			word-break: break-word;
		}
		/* ── Capitulos: flexbox para distribuir espacio correctamente ── */
		.listupd .utao .uta .luf ul li {
			display: flex !important;
			align-items: center !important;
			gap: 4px !important;
			overflow: hidden !important;
		}
		.listupd .utao .uta .luf ul li a {
			flex: 1 1 0 !important;
			min-width: 0 !important;
			max-width: unset !important;
			float: none !important;
			display: block !important;
			overflow: hidden !important;
			text-overflow: ellipsis !important;
			white-space: nowrap !important;
		}
		.listupd .utao .uta .luf ul li span {
			flex-shrink: 0 !important;
			float: none !important;
			margin-top: 0 !important;
		}
		</style>
		<script id="bloom-chapter-abbrev">
		(function () {
			function abbrevChapters() {
				document.querySelectorAll(
					'.listupd .utao .uta .luf ul li a'
				).forEach(function (a) {
					if (a.dataset.bloomDone) return;
					a.dataset.bloomDone = '1';
					var text = a.textContent.trim();
					/* Extrae el primer numero del texto del capitulo.
					   Funciona con: "Chapter 09", "Cap 9", "Capitulo 1.5", etc. */
					var m = text.match(/(\d+(?:[.,]\d+)?)/);
					if (m) {
						a.setAttribute('title', text); /* tooltip con texto completo */
						a.textContent = 'Cap\u00a0' + m[1];
					}
				});
			}
			if (document.readyState === 'loading') {
				document.addEventListener('DOMContentLoaded', abbrevChapters);
			} else {
				abbrevChapters();
			}
		})();
		</script>
		<?php
	}

	/**
	 * Elimina los scripts de Monetag en /login y /register.
	 * Los anuncios vignette/intersticial aparecen en esas paginas porque
	 * sus templates llaman wp_head() directamente (sin el tema completo),
	 * lo que da al anuncio espacio libre para expandirse.
	 */
	public function suppress_ads_on_auth_pages(): void {
		$uri = isset( $_SERVER['REQUEST_URI'] ) ? (string) wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
		$is_auth_page = (
			preg_match( '#^/login(/|\?|$)#i', $uri ) ||
			preg_match( '#^/register(/|\?|$)#i', $uri ) ||
			preg_match( '#^/panel-scan(/|\?|$)#i', $uri )
		);

		if ( ! $is_auth_page ) {
			return;
		}

		// Eliminar Monetag custom (monetag-bloom-scans)
		$mbs = class_exists( 'Monetag_Bloom_Scans' ) ? Monetag_Bloom_Scans::get_instance() : null;
		if ( $mbs ) {
			remove_action( 'wp_head', [ $mbs, 'output_monetag_scripts' ], 1 );
		}

		// Eliminar Monetag oficial si existe en varios hooks
		$hooks = [ 'wp_head', 'wp_footer', 'wp_print_scripts', 'wp_print_footer_scripts' ];
		global $wp_filter;

		foreach ( $hooks as $hook ) {
			if ( isset( $wp_filter[ $hook ] ) ) {
				foreach ( $wp_filter[ $hook ]->callbacks as $priority => $callbacks ) {
					foreach ( $callbacks as $key => $cb ) {
						$fn = $cb['function'];
						$class_name = '';
						if ( is_array( $fn ) && is_object( $fn[0] ) ) {
							$class_name = get_class( $fn[0] );
						} elseif ( is_array( $fn ) && is_string( $fn[0] ) ) {
							$class_name = $fn[0];
						} elseif ( is_string( $fn ) ) {
							$class_name = $fn;
						}

						if ( false !== stripos( $class_name, 'monetag' ) ) {
							unset( $wp_filter[ $hook ]->callbacks[ $priority ][ $key ] );
						}
					}
				}
			}
		}
	}

	public function bootstrap(): void {
		remove_action( 'wp_head', 'wp_generator' );
		remove_action( 'wp_head', 'rsd_link' );
		remove_action( 'wp_head', 'wlwmanifest_link' );
		remove_action( 'wp_head', 'rest_output_link_wp_head', 10 );
		remove_action( 'template_redirect', 'rest_output_link_header', 11 );
		remove_action( 'wp_head', 'wp_oembed_add_discovery_links' );
		remove_action( 'wp_head', 'wp_oembed_add_host_js' );
		remove_action( 'wp_head', 'wp_shortlink_wp_head', 10 );
		remove_action( 'wp_head', 'index_rel_link' );
		remove_action( 'wp_head', 'feed_links_extra', 3 );
		remove_action( 'wp_head', 'adjacent_posts_rel_link_wp_head', 10 );
		remove_action( 'wp_head', 'print_emoji_detection_script', 7 );
		remove_action( 'wp_print_styles', 'print_emoji_styles' );
		remove_action( 'admin_print_scripts', 'print_emoji_detection_script' );
		remove_action( 'admin_print_styles', 'print_emoji_styles' );
	}

	public function send_security_headers(): void {
		if ( headers_sent() ) {
			return;
		}

		header_remove( 'X-Powered-By' );
		header( 'X-Content-Type-Options: nosniff', true );
		header( 'X-Frame-Options: SAMEORIGIN', true );
		header( 'Referrer-Policy: strict-origin-when-cross-origin', true );
		header( 'Permissions-Policy: accelerometer=(), autoplay=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()',
			true );
		header( "Content-Security-Policy: upgrade-insecure-requests; base-uri 'self'; frame-ancestors 'self'; form-action 'self' https://accounts.google.com https://*.google.com https://discord.com",
			true );

		if ( is_ssl() ) {
			header( 'Strict-Transport-Security: max-age=31536000; includeSubDomains', true );
		}
	}

	public function filter_wp_headers( array $headers ): array {
		unset( $headers['X-Pingback'], $headers['x-pingback'] );
		return $headers;
	}

	public function filter_rest_endpoints( array $endpoints ): array {
		if ( current_user_can( 'list_users' ) ) {
			return $endpoints;
		}

		foreach ( array_keys( $endpoints ) as $route ) {
			if ( preg_match( '#^/wp/v2/users(?:/.*)?$#', (string) $route ) ) {
				unset( $endpoints[ $route ] );
			}
		}

		return $endpoints;
	}

	public function guard_rest_routes( $result, WP_REST_Server $server, WP_REST_Request $request ) {
		$route = (string) $request->get_route();

		if ( preg_match( '#^/wp/v2/users(?:/.*)?$#', $route ) && ! current_user_can( 'list_users' ) ) {
			return new WP_Error( 'rest_forbidden', 'User enumeration disabled.', [ 'status' => 403 ] );
		}

		if ( preg_match( '#^/(?:wp-site-health|hostinger-ai-assistant|mcp)(?:/.*)?$#', $route ) && ! current_user_can( 'manage_options' ) ) {
			return new WP_Error( 'rest_forbidden', 'Restricted REST namespace.', [ 'status' => 403 ] );
		}

		return $result;
	}

	public function guard_rest_authentication( $result ) {
		$route = isset( $_SERVER['REQUEST_URI'] ) ? (string) wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
		if ( false !== strpos( $route, '/wp-json/wp/v2/users' ) && ! current_user_can( 'list_users' ) ) {
			return new WP_Error( 'rest_forbidden', 'User enumeration disabled.', [ 'status' => 403 ] );
		}

		return $result;
	}

	public function block_author_archives(): void {
		if ( is_admin() || wp_doing_ajax() ) {
			return;
		}

		if ( is_author() && ! current_user_can( 'list_users' ) ) {
			global $wp_query;
			$wp_query->set_404();
			status_header( 404 );
			nocache_headers();
			header( 'X-Robots-Tag: noindex, nofollow', true );
			include get_query_template( '404' );
			exit;
		}
	}

	public function render_native_registration_fields(): void {
		echo $this->get_registration_fields_html( 'native' );
	}

	public function render_custom_registration_fields(): void {
		echo $this->get_registration_fields_html( 'custom' );
	}

	private function get_registration_fields_html( string $context ): string {
		$a        = wp_rand( 2, 9 );
		$b        = wp_rand( 1, 8 );
		$sum      = $a + $b;
		$ts       = time();
		$signature = wp_hash( implode( '|', [ $context, $a, $b, $sum ] ) );

		ob_start();
		?>
		<input type="hidden" name="bsh_registration_context" value="<?php echo esc_attr( $context ); ?>">
		<input type="hidden" name="bsh_ts" value="<?php echo esc_attr( (string) $ts ); ?>">
		<input type="hidden" name="bsh_challenge_a" value="<?php echo esc_attr( (string) $a ); ?>">
		<input type="hidden" name="bsh_challenge_b" value="<?php echo esc_attr( (string) $b ); ?>">
		<input type="hidden" name="bsh_challenge_sig" value="<?php echo esc_attr( $signature ); ?>">
		<div class="bsh-honeypot" style="position:absolute;left:-9999px;opacity:0;pointer-events:none" aria-hidden="true">
			<label for="bsh_company">Empresa</label>
			<input type="text" name="bsh_company" id="bsh_company" tabindex="-1" autocomplete="off">
		</div>
		<div class="form-group bsh-challenge-group">
			<label for="bsh_challenge_answer">Verificación rápida: ¿cuánto es <?php echo esc_html( (string) $a ); ?> + <?php echo esc_html( (string) $b ); ?>?</label>
			<input type="number" name="bsh_challenge_answer" id="bsh_challenge_answer" required inputmode="numeric" min="0" step="1" placeholder="Tu respuesta">
		</div>
		<?php
		return (string) ob_get_clean();
	}

	public function validate_native_registration( WP_Error $errors, string $sanitized_user_login, string $user_email ): WP_Error {
		if ( ! empty( $_REQUEST['loginSocial'] ) ) {
			return $errors;
		}

		$validation = $this->validate_registration_payload( 'native' );
		if ( is_wp_error( $validation ) ) {
			foreach ( $validation->get_error_codes() as $code ) {
				foreach ( $validation->get_error_messages( $code ) as $message ) {
					$errors->add( $code, $message );
				}
			}
		}

		return $errors;
	}

	public function handle_custom_registration(): void {
		if ( empty( $_POST['submit_registration'] ) ) {
			return;
		}

		$nonce = isset( $_POST['registration_nonce'] ) ? (string) wp_unslash( $_POST['registration_nonce'] ) : '';
		if ( ! wp_verify_nonce( $nonce, 'custom_registration' ) ) {
			return;
		}

		$validation = $this->validate_registration_payload( 'custom' );
		if ( is_wp_error( $validation ) ) {
			$this->log_event( 'registration_blocked', [ 'reason' => $validation->get_error_code() ] );
			$this->redirect_with_query(
				home_url( '/register' ),
				[
					'error' => $validation->get_error_code() ?: 'security_check_failed',
				]
			);
		}

		$username = isset( $_POST['user_login'] ) ? sanitize_user( wp_unslash( $_POST['user_login'] ) ) : '';
		$email    = isset( $_POST['user_email'] ) ? sanitize_email( wp_unslash( $_POST['user_email'] ) ) : '';
		$password = isset( $_POST['user_pass'] ) ? (string) wp_unslash( $_POST['user_pass'] ) : '';

		if ( username_exists( $username ) ) {
			$this->redirect_with_query( home_url( '/register' ), [ 'error' => 'username_exists' ] );
		}

		if ( email_exists( $email ) ) {
			$this->redirect_with_query( home_url( '/register' ), [ 'error' => 'email_exists' ] );
		}

		if ( strlen( $password ) < 8 ) {
			$this->redirect_with_query( home_url( '/register' ), [ 'error' => 'weak_password' ] );
		}

		$user_id = wp_create_user( $username, $password, $email );
		if ( is_wp_error( $user_id ) ) {
			$this->log_event( 'registration_failed', [ 'reason' => $user_id->get_error_code() ] );
			$this->redirect_with_query( home_url( '/register' ), [ 'error' => 'registration_failed' ] );
		}

		$user = new WP_User( (int) $user_id );
		$user->set_role( 'subscriber' );
		delete_transient( $this->rate_limit_key( 'register' ) );

		$this->redirect_with_query( home_url( '/login' ), [ 'registered' => 'verify' ] );
	}

	public function maybe_mark_new_user_pending( int $user_id ): void {
		if ( ! $this->is_pending_verification_flow() ) {
			return;
		}

		delete_transient( $this->rate_limit_key( 'register' ) );
		$this->mark_user_pending( $user_id, 'native' );
	}

	private function mark_user_pending( int $user_id, string $source ): void {
		if ( ! $user_id || get_user_meta( $user_id, 'bsh_email_verified_at', true ) ) {
			return;
		}

		if ( '1' === (string) get_user_meta( $user_id, 'bsh_pending_email_verification', true ) &&
			get_user_meta( $user_id, 'bsh_email_verification_token_hash', true ) ) {
			return;
		}

		$raw_token = wp_generate_password( 32, false, false );
		update_user_meta( $user_id, 'bsh_pending_email_verification', '1' );
		update_user_meta( $user_id, 'bsh_email_verification_source', $source );
		update_user_meta( $user_id, 'bsh_email_verification_created_at', time() );
		update_user_meta( $user_id, 'bsh_email_verification_token_hash', wp_hash( $raw_token ) );

		$user = get_userdata( $user_id );
		if ( ! $user || empty( $user->user_email ) ) {
			return;
		}

		$url = add_query_arg(
			[
				'bsh_verify' => 1,
				'uid'        => $user_id,
				'token'      => rawurlencode( $raw_token ),
			],
			home_url( '/login/' )
		);

		$subject = sprintf( '[%s] Verifica tu correo', wp_specialchars_decode( get_bloginfo( 'name' ), ENT_QUOTES ) );
		$message = "Hola {$user->display_name},\n\n";
		$message .= "Para activar tu cuenta en BloomScans, verifica tu correo usando este enlace:\n{$url}\n\n";
		$message .= "Si no creaste esta cuenta, ignora este mensaje.\n";
		wp_mail( $user->user_email, $subject, $message );
		$this->log_event( 'verification_email_sent', [ 'user_id' => $user_id, 'source' => $source ] );
	}

	public function handle_email_verification(): void {
		if ( empty( $_GET['bsh_verify'] ) || empty( $_GET['uid'] ) || empty( $_GET['token'] ) ) {
			return;
		}

		$user_id    = (int) $_GET['uid'];
		$raw_token  = sanitize_text_field( wp_unslash( $_GET['token'] ) );
		$stored_hash = (string) get_user_meta( $user_id, 'bsh_email_verification_token_hash', true );

		if ( ! $user_id || ! $stored_hash || ! hash_equals( $stored_hash, wp_hash( $raw_token ) ) ) {
			$this->redirect_with_query( home_url( '/login' ), [ 'verification' => 'invalid' ] );
		}

		delete_user_meta( $user_id, 'bsh_pending_email_verification' );
		delete_user_meta( $user_id, 'bsh_email_verification_token_hash' );
		update_user_meta( $user_id, 'bsh_email_verified_at', time() );
		$this->log_event( 'verification_success', [ 'user_id' => $user_id ] );

		$this->redirect_with_query( home_url( '/login' ), [ 'verified' => '1' ] );
	}

	public function limit_login_attempts( $user, string $username, string $password ) {
		if ( is_user_logged_in() || $this->is_social_login_request() ) {
			return $user;
		}

		$key   = $this->rate_limit_key( 'login' );
		$count = (int) get_transient( $key );
		if ( $count >= self::LOGIN_LIMIT ) {
			$this->log_event( 'login_rate_limited', [ 'username' => $username ] );
			return new WP_Error( 'bsh_login_rate_limited', 'Has intentado iniciar sesión demasiadas veces. Espera unos minutos e inténtalo de nuevo.' );
		}

		return $user;
	}

	public function record_login_failure( string $username ): void {
		if ( $this->is_social_login_request() ) {
			return;
		}

		$key   = $this->rate_limit_key( 'login' );
		$count = (int) get_transient( $key );
		set_transient( $key, $count + 1, self::LOGIN_WINDOW );
		$this->log_event( 'login_failed', [ 'username' => $username, 'count' => $count + 1 ] );
	}

	public function clear_login_limit( string $user_login, WP_User $user ): void {
		delete_transient( $this->rate_limit_key( 'login' ) );
	}

	public function block_pending_user_login( WP_User $user, string $password ) {
		if ( ! $user instanceof WP_User ) {
			return $user;
		}

		if ( $this->is_social_login_request() ) {
			return $user;
		}

		if ( '1' === (string) get_user_meta( $user->ID, 'bsh_pending_email_verification', true ) ) {
			return new WP_Error( 'bsh_email_unverified', 'Debes verificar tu correo antes de iniciar sesión.' );
		}

		return $user;
	}

	private function validate_registration_payload( string $expected_context ) {
		$key   = $this->rate_limit_key( 'register' );
		$count = (int) get_transient( $key );
		if ( $count >= self::REGISTER_LIMIT ) {
			$this->log_event( 'registration_rate_limited', [ 'context' => $expected_context ] );
			return new WP_Error( 'rate_limited', 'Demasiados intentos de registro. Espera un rato antes de intentar de nuevo.' );
		}

		$context = isset( $_POST['bsh_registration_context'] ) ? sanitize_key( wp_unslash( $_POST['bsh_registration_context'] ) ) : '';
		if ( $context !== $expected_context ) {
			return $this->increment_registration_limit( 'security_check_failed' );
		}

		$honeypot = isset( $_POST['bsh_company'] ) ? trim( (string) wp_unslash( $_POST['bsh_company'] ) ) : '';
		if ( '' !== $honeypot ) {
			return $this->increment_registration_limit( 'security_check_failed' );
		}

		$ts = isset( $_POST['bsh_ts'] ) ? (int) $_POST['bsh_ts'] : 0;
		if ( ! $ts || ( time() - $ts ) < self::REGISTER_MIN_FILL_TIME ) {
			return $this->increment_registration_limit( 'security_check_failed' );
		}

		$a         = isset( $_POST['bsh_challenge_a'] ) ? (int) $_POST['bsh_challenge_a'] : 0;
		$b         = isset( $_POST['bsh_challenge_b'] ) ? (int) $_POST['bsh_challenge_b'] : 0;
		$signature = isset( $_POST['bsh_challenge_sig'] ) ? (string) wp_unslash( $_POST['bsh_challenge_sig'] ) : '';
		$answer    = isset( $_POST['bsh_challenge_answer'] ) ? (int) $_POST['bsh_challenge_answer'] : -1;
		$expected  = $a + $b;
		$valid_sig = wp_hash( implode( '|', [ $expected_context, $a, $b, $expected ] ) );

		if ( ! $signature || ! hash_equals( $valid_sig, $signature ) || $answer !== $expected ) {
			return $this->increment_registration_limit( 'security_check_failed' );
		}

		return true;
	}

	private function increment_registration_limit( string $code ): WP_Error {
		$key   = $this->rate_limit_key( 'register' );
		$count = (int) get_transient( $key );
		set_transient( $key, $count + 1, self::REGISTER_WINDOW );
		$this->log_event( 'registration_validation_failed', [ 'reason' => $code, 'count' => $count + 1 ] );
		return new WP_Error( $code, 'No se pudo completar la verificación de seguridad del registro.' );
	}

	private function is_pending_verification_flow(): bool {
		if ( $this->is_social_login_request() ) {
			return false;
		}

		if ( ! empty( $_POST['submit_registration'] ) ) {
			return true;
		}

		$action = isset( $_REQUEST['action'] ) ? sanitize_key( wp_unslash( $_REQUEST['action'] ) ) : '';
		return 'register' === $action;
	}

	private function is_social_login_request(): bool {
		if ( ! empty( $_REQUEST['loginSocial'] ) ) {
			return true;
		}

		$request_uri = isset( $_SERVER['REQUEST_URI'] ) ? (string) wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
		if ( false !== stripos( $request_uri, 'nextend-social-login' ) ) {
			return true;
		}
		if ( false !== stripos( $request_uri, 'bloom_discord_callback' ) ) {
			return true;
		}
		return false;
	}

	private function rate_limit_key( string $context ): string {
		$ip = $this->client_ip();
		$ua = isset( $_SERVER['HTTP_USER_AGENT'] ) ? substr( (string) wp_unslash( $_SERVER['HTTP_USER_AGENT'] ), 0, 120 ) : '';
		return 'bsh_' . $context . '_' . md5( $ip . '|' . $ua );
	}

	private function client_ip(): string {
		foreach ( [ 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR' ] as $key ) {
			if ( empty( $_SERVER[ $key ] ) ) {
				continue;
			}

			$raw = (string) $_SERVER[ $key ];
			$ip  = trim( explode( ',', $raw )[0] );
			if ( filter_var( $ip, FILTER_VALIDATE_IP ) ) {
				return $ip;
			}
		}

		return '0.0.0.0';
	}

	private function redirect_with_query( string $url, array $query ): void {
		wp_safe_redirect( add_query_arg( $query, $url ) );
		exit;
	}

	private function log_event( string $event, array $context = [] ): void {
		$payload = wp_json_encode(
			[
				'event' => $event,
				'ip'    => $this->client_ip(),
				'ua'    => isset( $_SERVER['HTTP_USER_AGENT'] ) ? substr( (string) wp_unslash( $_SERVER['HTTP_USER_AGENT'] ), 0, 180 ) : '',
				'ctx'   => $context,
			]
		);
		error_log( 'BloomSecurity ' . $payload );
	}
}

new Bloom_Security_Hardening();
