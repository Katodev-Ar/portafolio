<?php
/**
 * Plugin Name: Bloom Discord Login
 * Plugin URI:  https://bloomscans.com
 * Description: Login social con Discord via OAuth2 propio. Independiente de Nextend.
 * Version:     1.0.0
 * Author:      BloomScans
 * Text Domain: bloom-discord-login
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'BDL_VERSION', '1.0.0' );
define( 'BDL_DIR', plugin_dir_path( __FILE__ ) );

final class Bloom_Discord_Login {

	/* ── Discord OAuth2 endpoints ──────────────────────── */
	private const AUTHORIZE_URL = 'https://discord.com/api/oauth2/authorize';
	private const TOKEN_URL     = 'https://discord.com/api/oauth2/token';
	private const USER_URL      = 'https://discord.com/api/users/@me';

	/* ── Singleton ─────────────────────────────────────── */
	private static ?self $instance = null;

	public static function instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {
		add_action( 'init',                        [ $this, 'handle_discord_flow' ], 5 );
		add_action( 'admin_menu',                  [ $this, 'add_admin_page' ] );
		add_action( 'admin_init',                  [ $this, 'register_settings' ] );
		add_action( 'bloom_login_social_buttons',  [ $this, 'render_discord_button_login' ] );
		add_action( 'bloom_register_social_buttons', [ $this, 'render_discord_button_register' ] );
	}

	/* ==========================================================
	 * Admin settings
	 * ========================================================== */

	public function add_admin_page(): void {
		add_options_page(
			'Bloom Discord Login',
			'Discord Login',
			'manage_options',
			'bloom-discord-login',
			[ $this, 'render_admin_page' ]
		);
	}

	public function register_settings(): void {
		register_setting( 'bdl_settings', 'bdl_client_id',     [ 'sanitize_callback' => 'sanitize_text_field' ] );
		register_setting( 'bdl_settings', 'bdl_client_secret', [ 'sanitize_callback' => 'sanitize_text_field' ] );
		register_setting( 'bdl_settings', 'bdl_enabled',       [ 'sanitize_callback' => 'absint' ] );
	}

	public function render_admin_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}
		require_once BDL_DIR . 'admin-settings.php';
	}

	/* ==========================================================
	 * Helpers
	 * ========================================================== */

	private function is_enabled(): bool {
		return (bool) get_option( 'bdl_enabled', 0 );
	}

	private function client_id(): string {
		return (string) get_option( 'bdl_client_id', '' );
	}

	private function client_secret(): string {
		return (string) get_option( 'bdl_client_secret', '' );
	}

	private function redirect_uri(): string {
		return home_url( '/?bloom_discord_callback=1' );
	}

	/* ==========================================================
	 * Render Discord buttons
	 * ========================================================== */

	public function render_discord_button_login(): void {
		$this->render_discord_button( 'login' );
	}

	public function render_discord_button_register(): void {
		$this->render_discord_button( 'register' );
	}

	private function render_discord_button( string $context ): void {
		if ( ! $this->is_enabled() || ! $this->client_id() ) {
			return;
		}

		$state = wp_generate_password( 32, false, false );
		set_transient( 'bdl_state_' . $state, $context, 600 );

		$auth_url = add_query_arg(
			[
				'client_id'     => $this->client_id(),
				'redirect_uri'  => rawurlencode( $this->redirect_uri() ),
				'response_type' => 'code',
				'scope'         => 'identify email',
				'state'         => $state,
				'prompt'        => 'consent',
			],
			self::AUTHORIZE_URL
		);
		?>
		<a href="<?php echo esc_url( $auth_url ); ?>" class="discord-login-btn" style="
			display:flex;align-items:center;justify-content:center;gap:12px;
			width:100%;padding:14px 20px;border-radius:10px;
			border:2px solid rgba(255,255,255,0.08);
			background:#5865F2;color:#ffffff;font-size:15px;font-weight:600;
			text-decoration:none;transition:all 0.2s ease;margin-top:10px;
		">
			<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
				<path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
			</svg>
			<span>Continuar con Discord</span>
		</a>
		<?php
	}

	/* ==========================================================
	 * OAuth2 flow: handle callback
	 * ========================================================== */

	public function handle_discord_flow(): void {
		/* ── Step 1: catch the callback ── */
		if ( empty( $_GET['bloom_discord_callback'] ) ) {
			return;
		}

		if ( ! $this->is_enabled() ) {
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}

		/* ── Validate state (CSRF) ── */
		$state = isset( $_GET['state'] ) ? sanitize_text_field( wp_unslash( $_GET['state'] ) ) : '';
		$saved = get_transient( 'bdl_state_' . $state );
		if ( ! $state || false === $saved ) {
			$this->log( 'state_invalid', [] );
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}
		delete_transient( 'bdl_state_' . $state );

		/* ── Get the authorization code ── */
		$code = isset( $_GET['code'] ) ? sanitize_text_field( wp_unslash( $_GET['code'] ) ) : '';
		if ( ! $code ) {
			// user cancelled or error
			wp_safe_redirect( home_url( '/login' ) );
			exit;
		}

		/* ── Step 2: exchange code for token ── */
		$token_response = wp_remote_post(
			self::TOKEN_URL,
			[
				'timeout' => 15,
				'body'    => [
					'client_id'     => $this->client_id(),
					'client_secret' => $this->client_secret(),
					'grant_type'    => 'authorization_code',
					'code'          => $code,
					'redirect_uri'  => $this->redirect_uri(),
				],
			]
		);

		if ( is_wp_error( $token_response ) ) {
			$this->log( 'token_exchange_failed', [ 'error' => $token_response->get_error_message() ] );
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}

		$token_body = json_decode( wp_remote_retrieve_body( $token_response ), true );
		if ( empty( $token_body['access_token'] ) ) {
			$this->log( 'token_missing', [ 'body' => wp_remote_retrieve_body( $token_response ) ] );
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}

		$access_token = $token_body['access_token'];

		/* ── Step 3: fetch Discord user info ── */
		$user_response = wp_remote_get(
			self::USER_URL,
			[
				'timeout' => 10,
				'headers' => [
					'Authorization' => 'Bearer ' . $access_token,
				],
			]
		);

		if ( is_wp_error( $user_response ) ) {
			$this->log( 'user_fetch_failed', [ 'error' => $user_response->get_error_message() ] );
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}

		$discord_user = json_decode( wp_remote_retrieve_body( $user_response ), true );
		if ( empty( $discord_user['id'] ) ) {
			$this->log( 'user_data_invalid', [] );
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}

		$discord_id       = sanitize_text_field( $discord_user['id'] );
		$discord_username  = isset( $discord_user['username'] ) ? sanitize_text_field( $discord_user['username'] ) : '';
		$discord_email     = isset( $discord_user['email'] ) ? sanitize_email( $discord_user['email'] ) : '';
		$discord_avatar    = isset( $discord_user['avatar'] ) ? sanitize_text_field( $discord_user['avatar'] ) : '';
		$discord_verified  = ! empty( $discord_user['verified'] );

		/* ── Step 4: find or create WP user ── */
		$wp_user_id = $this->find_or_create_user( $discord_id, $discord_username, $discord_email, $discord_avatar, $discord_verified );

		if ( ! $wp_user_id ) {
			wp_safe_redirect( home_url( '/login?login=failed' ) );
			exit;
		}

		/* ── Step 5: log in ── */
		wp_set_current_user( $wp_user_id );
		wp_set_auth_cookie( $wp_user_id, true );
		do_action( 'wp_login', get_userdata( $wp_user_id )->user_login, get_userdata( $wp_user_id ) );

		$this->log( 'login_success', [ 'user_id' => $wp_user_id, 'discord_id' => $discord_id ] );

		wp_safe_redirect( home_url() );
		exit;
	}

	/* ==========================================================
	 * User resolution
	 * ========================================================== */

	/**
	 * Find existing WP user by discord_id meta or email, or create a new one.
	 *
	 * @return int|false  WP user ID or false on failure.
	 */
	private function find_or_create_user( string $discord_id, string $username, string $email, string $avatar, bool $verified ) {
		/* ── 1. By discord_id ── */
		$users_by_meta = get_users( [
			'meta_key'   => 'bdl_discord_id',
			'meta_value' => $discord_id,
			'number'     => 1,
			'fields'     => 'ID',
		] );

		if ( ! empty( $users_by_meta ) ) {
			$uid = (int) $users_by_meta[0];
			$this->update_discord_meta( $uid, $discord_id, $username, $avatar );
			return $uid;
		}

		/* ── 2. By email ── */
		if ( $email && $verified ) {
			$existing = get_user_by( 'email', $email );
			if ( $existing ) {
				$this->update_discord_meta( $existing->ID, $discord_id, $username, $avatar );
				$this->log( 'account_linked_by_email', [ 'user_id' => $existing->ID, 'discord_id' => $discord_id ] );
				return $existing->ID;
			}
		}

		/* ── 3. Create new user ── */
		$wp_username = $this->generate_unique_username( $username );
		$wp_password = wp_generate_password( 24, true, true );

		$user_data = [
			'user_login' => $wp_username,
			'user_pass'  => $wp_password,
			'user_email' => $email ?: $wp_username . '@discord.placeholder',
			'role'       => 'subscriber',
		];

		$user_id = wp_insert_user( $user_data );
		if ( is_wp_error( $user_id ) ) {
			$this->log( 'user_creation_failed', [ 'error' => $user_id->get_error_message() ] );
			return false;
		}

		// Mark as email-verified since Discord already verified it
		if ( $email && $verified ) {
			update_user_meta( $user_id, 'bsh_email_verified_at', time() );
		}

		$this->update_discord_meta( $user_id, $discord_id, $username, $avatar );
		$this->log( 'user_created', [ 'user_id' => $user_id, 'discord_id' => $discord_id ] );

		return $user_id;
	}

	private function update_discord_meta( int $user_id, string $discord_id, string $username, string $avatar ): void {
		update_user_meta( $user_id, 'bdl_discord_id', $discord_id );
		update_user_meta( $user_id, 'bdl_discord_username', $username );
		if ( $avatar ) {
			update_user_meta( $user_id, 'bdl_discord_avatar', $avatar );
		}
		update_user_meta( $user_id, 'bdl_discord_linked_at', time() );
	}

	private function generate_unique_username( string $base ): string {
		$base = sanitize_user( $base, true );
		if ( ! $base ) {
			$base = 'discord_user';
		}

		$candidate = $base;
		$suffix    = 1;
		while ( username_exists( $candidate ) ) {
			$candidate = $base . $suffix;
			$suffix++;
		}
		return $candidate;
	}

	/* ==========================================================
	 * Logging
	 * ========================================================== */

	private function log( string $event, array $context ): void {
		$payload = wp_json_encode( [
			'event'  => 'bdl_' . $event,
			'ctx'    => $context,
		] );
		error_log( 'BloomDiscordLogin ' . $payload );
	}
}

Bloom_Discord_Login::instance();
