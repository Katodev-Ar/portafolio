<?php
/**
 * Plugin Name: Bloom reCAPTCHA Login
 * Plugin URI:  https://bloomscans.com
 * Description: Agrega reCAPTCHA v2 (checkbox) al formulario de login para prevenir accesos automatizados.
 * Version:     1.0.0
 * Author:      BloomScans
 * Text Domain: bloom-recaptcha-login
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class Bloom_Recaptcha_Login {

	private const VERIFY_URL = 'https://www.google.com/recaptcha/api/siteverify';

	/** Evita validar el mismo token dos veces en la misma request. */
	private static bool $recaptcha_ok = false;

	private static ?self $instance = null;

	public static function instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'admin_menu',                     [ $this, 'add_admin_page' ] );
		add_action( 'admin_init',                     [ $this, 'register_settings' ] );
		add_action( 'bloom_login_before_submit',      [ $this, 'render_recaptcha_widget' ] );
		add_action( 'bloom_login_enqueue_scripts',    [ $this, 'enqueue_recaptcha_script' ] );
		add_action( 'bloom_register_before_submit',   [ $this, 'render_recaptcha_widget' ] );
		// Intercepta ANTES de que wp-login.php procese el login y redirige
		// a nuestra pagina personalizada si el reCAPTCHA falla.
		add_action( 'init',                          [ $this, 'intercept_login_post' ], 5 );
		add_action( 'init',                          [ $this, 'intercept_registration_post' ], 5 );
		// Capa de respaldo para clients no-browser (XML-RPC aun bloqueado aparte).
		add_filter( 'authenticate',                   [ $this, 'validate_recaptcha' ], 30, 3 );
	}

	/* ==========================================================
	 * Admin settings
	 * ========================================================== */

	public function add_admin_page(): void {
		add_options_page(
			'Bloom reCAPTCHA Login',
			'reCAPTCHA Login',
			'manage_options',
			'bloom-recaptcha-login',
			[ $this, 'render_admin_page' ]
		);
	}

	public function register_settings(): void {
		register_setting( 'brl_settings', 'brl_site_key',   [ 'sanitize_callback' => 'sanitize_text_field' ] );
		register_setting( 'brl_settings', 'brl_secret_key', [ 'sanitize_callback' => 'sanitize_text_field' ] );
		register_setting( 'brl_settings', 'brl_enabled',    [ 'sanitize_callback' => 'absint' ] );
	}

	public function render_admin_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		?>
		<div class="wrap">
			<h1>Bloom reCAPTCHA Login</h1>
			<p>Configura las claves de Google reCAPTCHA v2 (checkbox).<br>
			   Obtenlas desde <a href="https://www.google.com/recaptcha/admin" target="_blank" rel="noopener">Google reCAPTCHA Admin</a>.</p>

			<form method="post" action="options.php">
				<?php settings_fields( 'brl_settings' ); ?>

				<table class="form-table" role="presentation">
					<tr>
						<th scope="row"><label for="brl_enabled">Habilitado</label></th>
						<td>
							<input type="checkbox" name="brl_enabled" id="brl_enabled" value="1"
								<?php checked( get_option( 'brl_enabled', 0 ), 1 ); ?>>
							<span class="description">Mostrar reCAPTCHA en el formulario de login.</span>
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="brl_site_key">Site Key</label></th>
						<td>
							<input type="text" name="brl_site_key" id="brl_site_key"
								value="<?php echo esc_attr( get_option( 'brl_site_key', '' ) ); ?>"
								class="regular-text" autocomplete="off">
						</td>
					</tr>
					<tr>
						<th scope="row"><label for="brl_secret_key">Secret Key</label></th>
						<td>
							<input type="password" name="brl_secret_key" id="brl_secret_key"
								value="<?php echo esc_attr( get_option( 'brl_secret_key', '' ) ); ?>"
								class="regular-text" autocomplete="off">
						</td>
					</tr>
				</table>

				<?php submit_button( 'Guardar cambios' ); ?>
			</form>

			<hr>
			<h2>Instrucciones rapidas</h2>
			<ol>
				<li>Ve a <a href="https://www.google.com/recaptcha/admin" target="_blank" rel="noopener">Google reCAPTCHA Admin</a>.</li>
				<li>Registra un nuevo sitio con tipo <strong>reCAPTCHA v2 - Casilla "No soy un robot"</strong>.</li>
				<li>En dominios agrega <code>bloomscans.com</code>.</li>
				<li>Copia la <strong>Site Key</strong> y la <strong>Secret Key</strong> aqui.</li>
				<li>Activa la casilla <em>Habilitado</em>.</li>
				<li>Listo. El checkbox de reCAPTCHA aparecera en el formulario de login.</li>
			</ol>
		</div>
		<?php
	}

	/* ==========================================================
	 * Helpers
	 * ========================================================== */

	private function is_enabled(): bool {
		return (bool) get_option( 'brl_enabled', 0 );
	}

	private function site_key(): string {
		return (string) get_option( 'brl_site_key', '' );
	}

	private function secret_key(): string {
		return (string) get_option( 'brl_secret_key', '' );
	}

	private function is_social_login_request(): bool {
		if ( ! empty( $_REQUEST['loginSocial'] ) ) {
			return true;
		}
		$uri = isset( $_SERVER['REQUEST_URI'] ) ? (string) wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
		if ( false !== stripos( $uri, 'nextend-social-login' ) ) {
			return true;
		}
		if ( false !== stripos( $uri, 'bloom_discord_callback' ) ) {
			return true;
		}
		return false;
	}

	/* ==========================================================
	 * Early interception: redirect reCAPTCHA errors back to /login/
	 * ========================================================== */

	/**
	 * Runs on `init` (priority 5), before wp-login.php processes the form.
	 * If reCAPTCHA is missing or fails we redirect to the custom login page
	 * with an error code, never showing wp-login.php to the user.
	 */
	public function intercept_login_post(): void {
		// Solo POST a wp-login.php
		if ( 'POST' !== ( $_SERVER['REQUEST_METHOD'] ?? '' ) ) {
			return;
		}
		$script = isset( $_SERVER['SCRIPT_FILENAME'] ) ? basename( (string) $_SERVER['SCRIPT_FILENAME'] ) : '';
		if ( 'wp-login.php' !== $script ) {
			return;
		}
		$action = isset( $_POST['action'] ) ? sanitize_key( $_POST['action'] ) : 'login';
		if ( 'login' !== $action ) {
			return;
		}
		// Solo si vienen credenciales (intento real de login)
		if ( empty( $_POST['log'] ) && empty( $_POST['pwd'] ) ) {
			return;
		}
		if ( $this->is_social_login_request() ) {
			return;
		}
		if ( ! $this->is_enabled() || ! $this->secret_key() ) {
			return;
		}

		$recaptcha_response = isset( $_POST['g-recaptcha-response'] )
			? sanitize_text_field( wp_unslash( $_POST['g-recaptcha-response'] ) )
			: '';

		$error_code = null;

		if ( empty( $recaptcha_response ) ) {
			$error_code = 'recaptcha_missing';
		} else {
			$verify = wp_remote_post(
				self::VERIFY_URL,
				[
					'timeout' => 10,
					'body'    => [
						'secret'   => $this->secret_key(),
						'response' => $recaptcha_response,
						'remoteip' => $this->client_ip(),
					],
				]
			);
			if ( ! is_wp_error( $verify ) ) {
				$body = json_decode( wp_remote_retrieve_body( $verify ), true );
				if ( empty( $body['success'] ) ) {
					$error_code = 'recaptcha_failed';
				}
			}
			// Si Google no responde (is_wp_error), fail-open: continua el login
		}

		if ( null === $error_code ) {
			self::$recaptcha_ok = true; // Marca validado: el filtro authenticate saltea la verificacion
			return; // reCAPTCHA OK, WordPress sigue procesando normalmente
		}

		// Construir URL de retorno conservando usuario y redirect_to
		$login_url = home_url( '/login/' );
		$args      = [ 'bloom_error' => $error_code ];

		if ( ! empty( $_POST['log'] ) ) {
			$args['log'] = rawurlencode( sanitize_text_field( wp_unslash( $_POST['log'] ) ) );
		}
		if ( ! empty( $_POST['redirect_to'] ) ) {
			$args['redirect_to'] = rawurlencode( esc_url_raw( wp_unslash( $_POST['redirect_to'] ) ) );
		}

		wp_safe_redirect( add_query_arg( $args, $login_url ) );
		exit;
	}

	/**
	 * Intercepta el POST del formulario de registro antes de que el plugin principal lo procese.
	 * Si el reCAPTCHA falla, redirige de vuelta a /register/ con bloom_error.
	 */
	public function intercept_registration_post(): void {
		if ( ! isset( $_POST['submit_registration'] ) ) {
			return;
		}
		if ( ! $this->is_plugin_active() ) {
			return;
		}

		$error_code       = null;
		$recaptcha_response = isset( $_POST['g-recaptcha-response'] )
			? sanitize_text_field( wp_unslash( $_POST['g-recaptcha-response'] ) )
			: '';

		if ( empty( $recaptcha_response ) ) {
			$error_code = 'recaptcha_missing';
		} else {
			$verify = wp_remote_post(
				self::VERIFY_URL,
				[
					'timeout' => 10,
					'body'    => [
						'secret'   => $this->secret_key(),
						'response' => $recaptcha_response,
						'remoteip' => $this->client_ip(),
					],
				]
			);
			if ( ! is_wp_error( $verify ) ) {
				$body = json_decode( wp_remote_retrieve_body( $verify ), true );
				if ( empty( $body['success'] ) ) {
					$error_code = 'recaptcha_failed';
				}
			}
			// Si Google no responde (is_wp_error), fail-open: continua el registro
		}

		if ( null === $error_code ) {
			return; // reCAPTCHA OK, el plugin principal procesa el registro
		}

		$register_url = home_url( '/register/' );
		wp_safe_redirect( add_query_arg( 'bloom_error', $error_code, $register_url ) );
		exit;
	}

	/* ==========================================================
	 * Frontend: render widget + enqueue script
	 * ========================================================== */

	public function enqueue_recaptcha_script(): void {
		if ( ! $this->is_enabled() || ! $this->site_key() ) {
			return;
		}
		// Enqueue the reCAPTCHA API script
		wp_enqueue_script( 'google-recaptcha', 'https://www.google.com/recaptcha/api.js', [], null, true );
	}

	public function render_recaptcha_widget(): void {
		if ( ! $this->is_enabled() || ! $this->site_key() ) {
			return;
		}
		?>
		<div class="form-group" style="margin-bottom:16px;display:flex;justify-content:center;">
			<div class="g-recaptcha" data-sitekey="<?php echo esc_attr( $this->site_key() ); ?>" data-theme="dark"></div>
		</div>
		<script src="https://www.google.com/recaptcha/api.js" async defer></script>
		<?php
	}

	/* ==========================================================
	 * Server-side validation (hooks into `authenticate`)
	 * ========================================================== */

	/**
	 * Priority 30 — runs before Bloom Security Hardening rate limiter (40).
	 * If reCAPTCHA fails, the login is blocked before credentials are even checked.
	 */
	public function validate_recaptcha( $user, string $username, string $password ) {
		// Si el interceptor ya valido el token en esta request, no volver a verificar
		// (los tokens de Google son de un solo uso — doble verificacion siempre falla).
		if ( self::$recaptcha_ok ) {
			return $user;
		}

		// Skip for social login requests
		if ( $this->is_social_login_request() ) {
			return $user;
		}

		// Skip if already logged in or plugin not enabled
		if ( is_user_logged_in() || ! $this->is_enabled() || ! $this->secret_key() ) {
			return $user;
		}

		// Only validate on actual login submissions with credentials
		if ( empty( $username ) && empty( $password ) ) {
			return $user;
		}

		// Skip for wp-admin / API / CLI
		if ( defined( 'WP_CLI' ) || defined( 'REST_REQUEST' ) || ( defined( 'XMLRPC_REQUEST' ) && XMLRPC_REQUEST ) ) {
			return $user;
		}

		$recaptcha_response = isset( $_POST['g-recaptcha-response'] ) ? sanitize_text_field( wp_unslash( $_POST['g-recaptcha-response'] ) ) : '';

		if ( empty( $recaptcha_response ) ) {
			return new WP_Error(
				'brl_recaptcha_missing',
				'Debes completar la verificacion reCAPTCHA antes de iniciar sesion.'
			);
		}

		// Verify with Google
		$verify = wp_remote_post(
			self::VERIFY_URL,
			[
				'timeout' => 10,
				'body'    => [
					'secret'   => $this->secret_key(),
					'response' => $recaptcha_response,
					'remoteip' => $this->client_ip(),
				],
			]
		);

		if ( is_wp_error( $verify ) ) {
			// If Google is unreachable, allow login (fail-open) to not lock out users
			$this->log( 'verify_unreachable', [ 'error' => $verify->get_error_message() ] );
			return $user;
		}

		$body = json_decode( wp_remote_retrieve_body( $verify ), true );

		if ( empty( $body['success'] ) ) {
			$this->log( 'verify_failed', [ 'errors' => $body['error-codes'] ?? [] ] );
			return new WP_Error(
				'brl_recaptcha_failed',
				'La verificacion reCAPTCHA fallo. Intentalo de nuevo.'
			);
		}

		return $user;
	}

	/* ==========================================================
	 * Utilities
	 * ========================================================== */

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

	private function log( string $event, array $context = [] ): void {
		$payload = wp_json_encode( [
			'event' => 'brl_' . $event,
			'ip'    => $this->client_ip(),
			'ctx'   => $context,
		] );
		error_log( 'BloomRecaptcha ' . $payload );
	}
}

Bloom_Recaptcha_Login::instance();
