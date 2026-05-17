<?php

if ( ! class_exists( 'BRG_Context_Admin_View' ) ) {
	class BRG_Context_Admin_View {
		public static function boot() {
			add_action( 'all_admin_notices', array( __CLASS__, 'render_guard_context_panel' ), 20 );
		}

		public static function render_guard_context_panel() {
			if ( ! self::is_guard_screen() || ! class_exists( 'BRG_Context_Monitor' ) ) {
				return;
			}

			$severity = isset( $_GET['brg_ctx_severity'] ) ? sanitize_key( wp_unslash( $_GET['brg_ctx_severity'] ) ) : '';
			$snapshot = BRG_Context_Monitor::instance()->get_admin_snapshot( $severity );
			$base_url = admin_url( 'tools.php?page=bloom-reader-guard' );

			echo '<details class="brg-admin-panel" style="margin-top:16px;">';
			echo '<summary>Ver Contexto Suplementario (Silencioso)</summary>';
			echo '<div class="brg-admin-panel-body">';
			echo '<p style="margin:0 0 12px;color:#475569;font-size:13px;">Patrones silenciosos (faltas de bootstrap, etc). Solo para diagnostico avanzado.</p>';
			
			if ( empty( $snapshot['actors'] ) ) {
				echo '<p style="margin:0;font-size:13px;">No hay eventos de contexto recientes.</p></div></details>';
				return;
			}

			echo '<table class="widefat striped" style="margin-top:10px;">';
			echo '<thead><tr><th>IP (Red)</th><th>Gravedad</th><th>Señales</th><th>Eventos</th></tr></thead><tbody>';

			foreach ( $snapshot['actors'] as $actor ) {
				$actor_events = array_values(
					array_filter(
						$snapshot['events'],
						static function( $event ) use ( $actor ) {
							return isset( $event['ip'] ) && $event['ip'] === $actor['ip'];
						}
					)
				);
				if ( $severity && empty( $actor_events ) ) {
					continue;
				}

				echo '<tr>';
				echo '<td><strong>' . esc_html( $actor['ip'] ) . '</strong><br><span style="font-size:12px;color:#64748b;">' . esc_html( $actor['network'] ) . '</span></td>';
				echo '<td><span class="brg-badge" style="background:#f1f5f9;color:#334155;">' . esc_html( isset( $actor['client_probable'] ) ? $actor['client_probable'] : '?' ) . '</span></td>';
				echo '<td>';
				if ( isset( $actor['signals']['BRG-M05'] ) ) echo '<span class="brg-badge" style="background:#fff4e5;color:#8a4b00;">Sin Boot</span> ';
				if ( isset( $actor['signals']['BRG-M07'] ) ) echo '<span class="brg-badge" style="background:#ecfdf3;color:#027a48;">Cola OK</span> ';
				echo '</td>';
				echo '<td>' . esc_html( (string) count( $actor_events ) ) . '</td>';
				echo '</tr>';
			}

			echo '</tbody></table>';
			echo '</div></details>';
		}

		protected static function is_guard_screen() {
			global $pagenow;
			return is_admin() && 'tools.php' === $pagenow && isset( $_GET['page'] ) && 'bloom-reader-guard' === sanitize_key( wp_unslash( $_GET['page'] ) );
		}

		protected static function severity_label( $severity ) {
			$map = array(
				'critical' => 'Critica',
				'high'     => 'Alta',
				'medium'   => 'Media',
				'low'      => 'Baja',
			);

			return isset( $map[ $severity ] ) ? $map[ $severity ] : 'Baja';
		}
	}

	BRG_Context_Admin_View::boot();
}

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class BRG_Admin {
	private static ?self $instance = null;

	public static function instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}

		return self::$instance;
	}

	private function __construct() {
		add_action( 'admin_menu', [ $this, 'register_menu' ] );
		add_action( 'admin_init', [ $this, 'handle_actions' ] );
	}

	public function register_menu(): void {
		add_management_page(
			'Bloom Reader Guard',
			'Bloom Reader Guard',
			'manage_options',
			'bloom-reader-guard',
			[ $this, 'render_page' ]
		);
	}

	public function handle_actions(): void {
		if ( ! is_admin() || ! current_user_can( 'manage_options' ) ) {
			return;
		}

		if ( empty( $_POST['brg_admin_action'] ) ) {
			return;
		}

		check_admin_referer( 'brg_admin_action' );

		$action      = sanitize_key( wp_unslash( $_POST['brg_admin_action'] ) );
		$monitor     = BRG_Monitor::instance();
		$ip          = sanitize_text_field( wp_unslash( $_POST['brg_ip'] ?? '' ) );
		$network     = sanitize_text_field( wp_unslash( $_POST['brg_network'] ?? '' ) );
		$user_id     = absint( wp_unslash( $_POST['brg_user_id'] ?? 0 ) );
		$login       = sanitize_text_field( wp_unslash( $_POST['brg_user_login'] ?? '' ) );
		$email       = sanitize_email( wp_unslash( $_POST['brg_user_email'] ?? '' ) );
		$appeal_id   = absint( wp_unslash( $_POST['brg_appeal_id'] ?? 0 ) );
		$appeal_note = sanitize_textarea_field( wp_unslash( $_POST['brg_appeal_note'] ?? '' ) );

		if ( in_array( $action, [ 'manual_block', 'clear_ban', 'reset_profile' ], true ) ) {
			if ( ! filter_var( $ip, FILTER_VALIDATE_IP ) ) {
				wp_safe_redirect( admin_url( 'tools.php?page=bloom-reader-guard' ) );
				exit;
			}

			if ( 'clear_ban' === $action ) {
				$monitor->clear_ip_ban( $ip );
			} elseif ( 'manual_block' === $action ) {
				$monitor->set_ip_manual_ban( $ip );
			} elseif ( 'reset_profile' === $action ) {
				$monitor->reset_ip_profile( $ip );
			}
		}

		if ( in_array( $action, [ 'network_block', 'network_clear' ], true ) ) {
			if ( '' === $network && filter_var( $ip, FILTER_VALIDATE_IP ) ) {
				$network = $monitor->network_hint( $ip );
			}

			if ( ! $monitor->is_valid_network_hint( $network ) ) {
				wp_safe_redirect( admin_url( 'tools.php?page=bloom-reader-guard' ) );
				exit;
			}

			if ( 'network_block' === $action ) {
				$monitor->set_network_manual_ban( $network );
			} elseif ( 'network_clear' === $action ) {
				$monitor->clear_network_ban( $network );
			}
		}

		if ( in_array( $action, [ 'user_block', 'user_clear', 'user_reset' ], true ) ) {
			if ( $user_id <= 0 ) {
				wp_safe_redirect( admin_url( 'tools.php?page=bloom-reader-guard' ) );
				exit;
			}

			if ( 'user_block' === $action ) {
				$monitor->set_user_manual_ban( $user_id, $login, $email );
			} elseif ( 'user_clear' === $action ) {
				$monitor->clear_user_ban( $user_id );
			} elseif ( 'user_reset' === $action ) {
				$monitor->reset_user_profile( $user_id );
			}
		}

		if ( in_array( $action, [ 'appeal_resolve', 'appeal_reject' ], true ) && $appeal_id > 0 ) {
			$monitor->update_appeal_status( $appeal_id, 'appeal_resolve' === $action ? 'resolved' : 'rejected', $appeal_note );
		}

		wp_safe_redirect( admin_url( 'tools.php?page=bloom-reader-guard' ) );
		exit;
	}

	public function render_page(): void {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'No tienes permisos para ver esta pagina.', 'default' ) );
		}

		$monitor             = BRG_Monitor::instance();
		$events              = $monitor->get_recent_events( 200 );
		$appeals             = $monitor->get_recent_appeals( 80 );
		$stats               = $monitor->get_dashboard_summary();
		$groups              = $this->group_events_by_ip( $events );
		$network_counts      = $this->count_groups_by_network( $groups );
		$selected_severity   = $this->selected_severity();
		$search_query        = $this->search_query();
		$visible_groups      = $this->filter_groups_by_query( $this->filter_groups_by_severity( $groups, $selected_severity ), $search_query );
		$visible_appeals     = $this->filter_appeals_by_query( $appeals, $search_query );
		$appeals_open_by_default = (int) ( $stats['open_appeals'] ?? 0 ) > 0 || '' !== $search_query;
		?>
		<div class="wrap brg-admin-wrap">
			<?php $this->render_page_styles(); ?>

			<div class="brg-admin-hero">
				<div>
					<h1>Bloom Reader Guard</h1>
					<p>Panel operativo del guard del reader. Ahora prioriza lectura rapida: arriba ves estado, filtros y herramientas; el detalle pesado queda dentro de cada IP.</p>
				</div>
				<div class="brg-admin-hero-note">
					<span>Mostrando <strong><?php echo esc_html( (string) count( $visible_groups ) ); ?></strong> de <strong><?php echo esc_html( (string) count( $groups ) ); ?></strong> IPs</span>
					<span>Filtro: <strong><?php echo esc_html( $this->severity_options()[ $selected_severity ] ?? 'Todas' ); ?></strong></span>
					<?php if ( '' !== $search_query ) : ?>
						<span>Busqueda: <strong><?php echo esc_html( $search_query ); ?></strong></span>
					<?php endif; ?>
				</div>
			</div>

			<div class="brg-admin-stats">
				<?php $this->render_stat_card( 'Eventos escalados', (string) $stats['total_events'] ); ?>
				<?php $this->render_stat_card( 'Bloqueos vigentes', (string) $stats['active_bans'] ); ?>
				<?php $this->render_stat_card( 'Alertas enviadas', (string) $stats['alerts_sent'] ); ?>
				<?php $this->render_stat_card( 'Toques al cebo', (string) $stats['honeypot_hits'] ); ?>
				<?php $this->render_stat_card( 'Reclamos abiertos', (string) $stats['open_appeals'] ); ?>
				<?php $this->render_stat_card( 'IPs con eventos', (string) count( $groups ) ); ?>
			</div>

			<div class="brg-admin-panel">
				<div class="brg-admin-toolbar">
					<form method="get" class="brg-admin-search">
						<input type="hidden" name="page" value="bloom-reader-guard" />
						<input type="text" name="brg_query" value="<?php echo esc_attr( $search_query ); ?>" placeholder="Buscar por caso, IP o usuario" />
						<input type="hidden" name="brg_severity" value="<?php echo esc_attr( $selected_severity ); ?>" />
						<button type="submit" class="button button-primary">Buscar</button>
						<a href="<?php echo esc_url( admin_url( 'tools.php?page=bloom-reader-guard&brg_severity=' . rawurlencode( $selected_severity ) ) ); ?>" class="button">Limpiar</a>
					</form>
					<div class="brg-admin-chips">
						<?php foreach ( $this->severity_options() as $severity_key => $severity_label ) : ?>
							<?php
							$url = add_query_arg(
								[
									'page'         => 'bloom-reader-guard',
									'brg_severity' => $severity_key,
									'brg_query'    => $search_query,
								],
								admin_url( 'tools.php' )
							);
							?>
							<a href="<?php echo esc_url( $url ); ?>" class="brg-admin-chip<?php echo $severity_key === $selected_severity ? ' is-active' : ''; ?>">
								<?php echo esc_html( $severity_label ); ?>
							</a>
						<?php endforeach; ?>
					</div>
				</div>
			</div>

			<details class="brg-admin-panel">
				<summary>Herramientas manuales rápidas</summary>
				<div class="brg-admin-panel-body">
					<div style="display:flex;gap:24px;flex-wrap:wrap;">
						<form method="post" class="brg-admin-inline-form">
							<?php wp_nonce_field( 'brg_admin_action' ); ?>
							<label>IP exacta:</label>
							<input type="text" name="brg_ip" placeholder="IPv4 o IPv6" />
							<button type="submit" name="brg_admin_action" value="manual_block" class="button button-primary">Bloquear</button>
							<button type="submit" name="brg_admin_action" value="clear_ban" class="button">Desbloquear</button>
							<button type="submit" name="brg_admin_action" value="reset_profile" class="button">Reiniciar</button>
						</form>
						<form method="post" class="brg-admin-inline-form">
							<?php wp_nonce_field( 'brg_admin_action' ); ?>
							<label>Red (/24, /64):</label>
							<input type="text" name="brg_network" placeholder="Ej: 192.168.1.0/24" />
							<button type="submit" name="brg_admin_action" value="network_block" class="button button-primary">Bloquear red</button>
							<button type="submit" name="brg_admin_action" value="network_clear" class="button">Desbloquear red</button>
						</form>
					</div>
				</div>
			</details>

			<details class="brg-admin-panel">
				<summary>Referencia rapida</summary>
				<div class="brg-admin-panel-body">
					<div class="brg-admin-legend-grid">
						<?php $this->render_legend_item( 'Sin autorizacion', 'Intentos de pedir una imagen protegida sin la cookie valida del capitulo.' ); ?>
						<?php $this->render_legend_item( 'Ruta cruda', 'Intentos de abrir la imagen real saltandose el lector protegido.' ); ?>
						<?php $this->render_legend_item( 'Senuelos', 'Activaciones de assets camuflados del lector. En publico solo se muestra el codigo BRG.' ); ?>
						<?php $this->render_legend_item( 'Sospechosa', 'La IP o cuenta entro en vigilancia reforzada. No siempre significa bloqueo inmediato.' ); ?>
						<?php $this->render_legend_item( 'Red probable', 'Agrupacion orientativa para leer mejor si varias IPs podrian venir del mismo origen.' ); ?>
					</div>
				</div>
			</details>

			<details class="brg-admin-panel" <?php echo $appeals_open_by_default ? 'open' : ''; ?>>
				<summary>Reclamos desde el lector (<?php echo esc_html( (string) count( $visible_appeals ) ); ?>)</summary>
				<div class="brg-admin-panel-body">
					<?php if ( empty( $visible_appeals ) ) : ?>
						<p class="brg-admin-empty">Todavia no hay reclamos enviados desde el lector.</p>
					<?php else : ?>
						<table class="widefat striped">
							<thead>
								<tr>
									<th>Fecha</th>
									<th>Caso</th>
									<th>Estado</th>
									<th>IP</th>
									<th>Cuenta</th>
									<th>Contacto</th>
									<th>Mensaje</th>
									<th>Acciones</th>
								</tr>
							</thead>
							<tbody>
								<?php foreach ( $visible_appeals as $appeal ) : ?>
									<tr>
										<td><?php echo esc_html( (string) ( $appeal['created_at'] ?? '' ) ); ?></td>
										<td><code><?php echo esc_html( (string) ( $appeal['case_id'] ?? '' ) ); ?></code></td>
										<td><?php echo esc_html( ucfirst( (string) ( $appeal['status'] ?? 'open' ) ) ); ?></td>
										<td><?php echo esc_html( (string) ( $appeal['ip'] ?? '' ) ); ?></td>
										<td><?php echo esc_html( $this->format_account_label( $appeal ) ); ?></td>
										<td><?php echo esc_html( (string) ( $appeal['contact'] ?? '' ) ); ?></td>
										<td style="max-width:340px;white-space:pre-wrap;"><?php echo esc_html( (string) ( $appeal['appeal_text'] ?? '' ) ); ?></td>
										<td style="min-width:240px;">
											<form method="post" style="display:flex;flex-direction:column;gap:8px;margin:0;">
												<?php wp_nonce_field( 'brg_admin_action' ); ?>
												<input type="hidden" name="brg_appeal_id" value="<?php echo esc_attr( (string) ( $appeal['id'] ?? 0 ) ); ?>" />
												<textarea name="brg_appeal_note" rows="2" placeholder="Nota interna opcional"></textarea>
												<div class="brg-admin-actions">
													<button type="submit" name="brg_admin_action" value="appeal_resolve" class="button button-primary">Resolver</button>
													<button type="submit" name="brg_admin_action" value="appeal_reject" class="button">Rechazar</button>
												</div>
											</form>
										</td>
									</tr>
								<?php endforeach; ?>
							</tbody>
						</table>
					<?php endif; ?>
				</div>
			</details>

			<?php if ( empty( $visible_groups ) ) : ?>
				<div class="brg-admin-panel">
					<p class="brg-admin-empty">No hay IPs visibles con ese filtro ahora mismo.</p>
				</div>
			<?php else : ?>
				<div class="brg-ip-table">
					<div class="brg-ip-header">
						<div>IP / Red Probable</div>
						<div>Identidad y Señales</div>
						<div>Actividad</div>
						<div>Estado</div>
						<div></div>
					</div>
					<?php foreach ( $visible_groups as $group ) : ?>
						<?php $this->render_group_box( $group, $network_counts ); ?>
					<?php endforeach; ?>
				</div>
			<?php endif; ?>
		</div>
		<?php
	}

	private function render_group_box( array $group, array $network_counts ): void {
		$monitor           = BRG_Monitor::instance();
		$profile           = $monitor->get_ip_profile( $group['ip'] );
		$snapshot          = $monitor->get_live_snapshot( $group['ip'] );
		$network_profile   = $snapshot['network_profile'] ?? [];
		$events            = $group['events'];
		$latest            = $events[0];
		$total_events      = count( $events );
		$alerts_sent       = count( array_filter( $events, static fn ( array $event ): bool => ! empty( $event['alert_sent'] ) ) );
		$suspicious        = ! empty( $profile['suspicious'] );
		$active_bans       = ! empty( $profile['ban_until'] ) && (int) $profile['ban_until'] > time();
		$network_manual_ban = ! empty( $network_profile['manual_ban'] );
		$cookie_hits       = $this->sum_int_column( $events, 'cookie_denied_hits' );
		$direct_hits       = $this->sum_int_column( $events, 'direct_blocked_hits' );
		$honeypot_hits     = $this->sum_int_column( $events, 'honeypot_hits' );
		$offense_peak      = max( (int) ( $profile['offense_count'] ?? 0 ), max( array_map( static fn ( array $event ): int => (int) $event['offense_count'], $events ) ) );
		$ua_count          = count( $group['ua_map'] );
		$network_hint      = $group['network_hint'];
		$network_count     = (int) ( $network_counts[ $network_hint ] ?? 1 );
		$manual_ban        = ! empty( $profile['manual_ban'] );
		$client_type       = $this->classify_client_type( $group, $snapshot );
		$active_case_id    = (string) ( $snapshot['active_case_id'] ?? $latest['case_id'] ?? '' );
		$user_id           = (int) ( $latest['user_id'] ?? 0 );
		$user_login        = (string) ( $latest['user_login'] ?? '' );
		$user_email        = (string) ( $latest['user_email'] ?? '' );
		$user_profile      = BRG_Monitor::instance()->get_user_profile( $user_id );
		$user_active_ban   = $user_id > 0 && ( ! empty( $user_profile['manual_ban'] ) || ( ! empty( $user_profile['ban_until'] ) && (int) $user_profile['ban_until'] > time() ) );
		$severity          = $this->severity_info( $group, $profile, $snapshot, $alerts_sent, $active_bans, $network_manual_ban, $user_active_ban );
		$default_open      = $suspicious || $active_bans || $network_manual_ban || $user_active_ban || $honeypot_hits > 0;
		?>
		<details class="brg-ip-row" <?php echo $default_open ? 'open' : ''; ?>>
			<summary>
				<div class="brg-col-ip">
					<strong><?php echo esc_html( $group['ip'] ); ?></strong><br/>
					<span><?php echo esc_html( $network_hint ); ?><?php echo $network_count > 1 ? esc_html( ' (' . $network_count . ' IPs)' ) : ''; ?></span>
				</div>
				<div class="brg-col-badges">
					<?php $this->render_badge( $severity['label'], $severity['bg'], $severity['fg'] ); ?>
					<?php $this->render_badge( $client_type['short'], $client_type['bg'], $client_type['fg'] ); ?>
					<?php if ( $manual_ban || $active_bans ) : ?>
						<?php $this->render_badge( 'IP Bloq', '#fee2e2', '#991b1b' ); ?>
					<?php endif; ?>
					<?php if ( $network_manual_ban ) : ?>
						<?php $this->render_badge( 'Red Bloq', '#ffe4e6', '#9f1239' ); ?>
					<?php endif; ?>
				</div>
				<div class="brg-col-stats">
					<strong><?php echo esc_html( (string) $total_events ); ?> eventos</strong><br/>
					<span><?php echo esc_html( (string) $ua_count ); ?> UAs distintos</span>
				</div>
				<div class="brg-col-status">
					<?php
					if ( $manual_ban || $active_bans || $network_manual_ban || $user_active_ban ) {
						echo '<span style="color:#dc2626;">Bloqueado</span>';
					} elseif ( $suspicious ) {
						echo '<span style="color:#d97706;">Sospechoso</span>';
					} else {
						echo '<span style="color:#16a34a;">Vigilado</span>';
					}
					?>
				</div>
				<div style="text-align:right;color:#94a3b8;">
					<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
				</div>
			</summary>
			
			<div class="brg-ip-row-body">
				<div>
					<div class="brg-compact-stats">
						<div class="brg-compact-stat"><strong>Eventos</strong><span><?php echo esc_html( (string) $total_events ); ?></span></div>
						<div class="brg-compact-stat"><strong>Sin Autorización</strong><span><?php echo esc_html( (string) $cookie_hits ); ?></span></div>
						<div class="brg-compact-stat"><strong>Ruta Cruda</strong><span><?php echo esc_html( (string) $direct_hits ); ?></span></div>
						<div class="brg-compact-stat"><strong>Señuelos</strong><span><?php echo esc_html( (string) $honeypot_hits ); ?></span></div>
					</div>
					
					<div style="font-size:13px; color:#475569; margin-bottom: 12px; padding:12px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px;">
						<strong>Análisis de comportamiento:</strong><br/>
						<?php echo esc_html( $client_type['note'] ); ?><br/>
						Transiciones rápidas: <?php echo esc_html( (string) ( $snapshot['rapid_image_switches'] ?? 0 ) ); ?>. Vistas HTML: <?php echo esc_html( (string) ( $snapshot['distinct_view_chapters_short'] ?? 0 ) ); ?>.
					</div>

					<details>
						<summary style="cursor:pointer;font-weight:600;font-size:13px;color:#334155;margin-bottom:8px;">Ver User-Agents (<?php echo esc_html( (string) $ua_count ); ?>)</summary>
						<ul style="margin:0;padding-left:16px;font-family:monospace;font-size:11px;color:#475569;max-height:150px;overflow-y:auto;">
							<?php foreach ( $group['ua_map'] as $ua_summary => $ua_events ) : ?>
								<li>[<?php echo esc_html( (string) count( $ua_events ) ); ?>] <?php echo esc_html( $ua_summary ); ?></li>
							<?php endforeach; ?>
						</ul>
					</details>
				</div>

				<div>
					<div class="brg-action-group">
						<strong style="font-size:12px;color:#475569;">Acciones de IP / Red</strong>
						<form method="post">
							<?php wp_nonce_field( 'brg_admin_action' ); ?>
							<input type="hidden" name="brg_ip" value="<?php echo esc_attr( $group['ip'] ); ?>" />
							<input type="hidden" name="brg_network" value="<?php echo esc_attr( $network_hint ); ?>" />
							<?php if ( $manual_ban || $active_bans ) : ?>
								<button type="submit" name="brg_admin_action" value="clear_ban" class="button">Quitar Bloqueo IP</button>
							<?php else : ?>
								<button type="submit" name="brg_admin_action" value="manual_block" class="button button-primary" style="background:#dc2626;border-color:#dc2626;">Bloquear IP</button>
							<?php endif; ?>
							
							<?php if ( $network_manual_ban ) : ?>
								<button type="submit" name="brg_admin_action" value="network_clear" class="button">Quitar Bloqueo Red</button>
							<?php else : ?>
								<button type="submit" name="brg_admin_action" value="network_block" class="button" style="color:#dc2626;border-color:#fca5a5;">Bloquear Red</button>
							<?php endif; ?>
							
							<button type="submit" name="brg_admin_action" value="reset_profile" class="button">Reset</button>
						</form>
					</div>

					<?php if ( $user_id > 0 ) : ?>
						<div class="brg-action-group">
							<strong style="font-size:12px;color:#475569;">Acciones de Cuenta (#<?php echo esc_html( (string) $user_id ); ?>)</strong>
							<form method="post">
								<?php wp_nonce_field( 'brg_admin_action' ); ?>
								<input type="hidden" name="brg_user_id" value="<?php echo esc_attr( (string) $user_id ); ?>" />
								<input type="hidden" name="brg_user_login" value="<?php echo esc_attr( $user_login ); ?>" />
								<input type="hidden" name="brg_user_email" value="<?php echo esc_attr( $user_email ); ?>" />
								<?php if ( $user_active_ban ) : ?>
									<button type="submit" name="brg_admin_action" value="user_clear" class="button">Quitar Bloqueo</button>
								<?php else : ?>
									<button type="submit" name="brg_admin_action" value="user_block" class="button button-primary" style="background:#dc2626;border-color:#dc2626;">Bloquear Cuenta</button>
								<?php endif; ?>
							</form>
						</div>
					<?php endif; ?>
					
					<div style="font-size:12px;color:#64748b;margin-top:16px;">
						<strong>Último evento:</strong> <?php echo esc_html( (string) $latest['created_at'] ); ?><br/>
						<strong>Motivo:</strong> <?php echo esc_html( $this->human_reason( (string) $latest['reason'] ) ); ?>
					</div>
				</div>
			</div>
		</details>
		<?php
	}

	private function group_events_by_ip( array $events ): array {
		$groups = [];

		foreach ( $events as $event ) {
			$ip = (string) ( $event['ip'] ?? '0.0.0.0' );
			if ( ! isset( $groups[ $ip ] ) ) {
				$groups[ $ip ] = [
					'ip'           => $ip,
					'events'       => [],
					'ua_map'       => [],
					'network_hint' => $this->network_hint( $ip ),
				];
			}

			$groups[ $ip ]['events'][] = $event;
			$ua_summary = (string) ( $event['ua_summary'] ?? 'unknown' );
			if ( ! isset( $groups[ $ip ]['ua_map'][ $ua_summary ] ) ) {
				$groups[ $ip ]['ua_map'][ $ua_summary ] = [];
			}

			$groups[ $ip ]['ua_map'][ $ua_summary ][] = $event;
		}

		uasort(
			$groups,
			static function ( array $a, array $b ): int {
				$a_time = (string) ( $a['events'][0]['created_at'] ?? '' );
				$b_time = (string) ( $b['events'][0]['created_at'] ?? '' );
				return strcmp( $b_time, $a_time );
			}
		);

		return array_values( $groups );
	}

	private function selected_severity(): string {
		$severity = sanitize_key( wp_unslash( $_GET['brg_severity'] ?? 'all' ) );
		return array_key_exists( $severity, $this->severity_options() ) ? $severity : 'all';
	}

	private function search_query(): string {
		return trim( sanitize_text_field( wp_unslash( $_GET['brg_query'] ?? '' ) ) );
	}

	private function severity_options(): array {
		return [
			'all'      => 'Todas',
			'critical' => 'Critica',
			'high'     => 'Alta',
			'medium'   => 'Media',
			'low'      => 'Baja',
		];
	}

	private function filter_groups_by_severity( array $groups, string $selected_severity ): array {
		if ( 'all' === $selected_severity ) {
			return $groups;
		}

		$filtered = [];
		foreach ( $groups as $group ) {
			$monitor         = BRG_Monitor::instance();
			$profile         = $monitor->get_ip_profile( $group['ip'] );
			$snapshot        = $monitor->get_live_snapshot( $group['ip'] );
			$network_profile = $snapshot['network_profile'] ?? [];
			$alerts_sent     = count( array_filter( $group['events'], static fn ( array $event ): bool => ! empty( $event['alert_sent'] ) ) );
			$active_bans     = ! empty( $profile['ban_until'] ) && (int) $profile['ban_until'] > time();
			$network_ban     = ! empty( $network_profile['manual_ban'] );
			$latest          = $group['events'][0] ?? [];
			$user_profile    = BRG_Monitor::instance()->get_user_profile( (int) ( $latest['user_id'] ?? 0 ) );
			$user_active_ban = ! empty( $user_profile['manual_ban'] ) || ( ! empty( $user_profile['ban_until'] ) && (int) $user_profile['ban_until'] > time() );
			$severity        = $this->severity_info( $group, $profile, $snapshot, $alerts_sent, $active_bans, $network_ban, $user_active_ban );
			if ( $severity['key'] === $selected_severity ) {
				$filtered[] = $group;
			}
		}

		return $filtered;
	}

	private function filter_groups_by_query( array $groups, string $query ): array {
		if ( '' === $query ) {
			return $groups;
		}

		$query = strtolower( $query );
		return array_values(
			array_filter(
				$groups,
				static function ( array $group ) use ( $query ): bool {
					if ( str_contains( strtolower( (string) ( $group['ip'] ?? '' ) ), $query ) ) {
						return true;
					}
					if ( str_contains( strtolower( (string) ( $group['network_hint'] ?? '' ) ), $query ) ) {
						return true;
					}
					foreach ( (array) ( $group['events'] ?? [] ) as $event ) {
						$haystack = strtolower(
							implode(
								' ',
								[
									(string) ( $event['case_id'] ?? '' ),
									(string) ( $event['user_login'] ?? '' ),
									(string) ( $event['user_email'] ?? '' ),
									(string) ( $event['ua_summary'] ?? '' ),
								]
							)
						);
						if ( str_contains( $haystack, $query ) ) {
							return true;
						}
					}

					return false;
				}
			)
		);
	}

	private function filter_appeals_by_query( array $appeals, string $query ): array {
		if ( '' === $query ) {
			return $appeals;
		}

		$query = strtolower( $query );
		return array_values(
			array_filter(
				$appeals,
				static function ( array $appeal ) use ( $query ): bool {
					$haystack = strtolower(
						implode(
							' ',
							[
								(string) ( $appeal['case_id'] ?? '' ),
								(string) ( $appeal['ip'] ?? '' ),
								(string) ( $appeal['user_login'] ?? '' ),
								(string) ( $appeal['user_email'] ?? '' ),
								(string) ( $appeal['contact'] ?? '' ),
								(string) ( $appeal['appeal_text'] ?? '' ),
							]
						)
					);
					return str_contains( $haystack, $query );
				}
			)
		);
	}

	private function count_groups_by_network( array $groups ): array {
		$counts = [];
		foreach ( $groups as $group ) {
			$key = (string) ( $group['network_hint'] ?? 'desconocida' );
			$counts[ $key ] = (int) ( $counts[ $key ] ?? 0 ) + 1;
		}

		return $counts;
	}

	private function sum_int_column( array $events, string $column ): int {
		return array_sum(
			array_map(
				static fn ( array $event ): int => (int) ( $event[ $column ] ?? 0 ),
				$events
			)
		);
	}

	private function format_sample_chapters( string $sample_json ): string {
		$sample = json_decode( $sample_json, true );
		if ( ! is_array( $sample ) || empty( $sample ) ) {
			return '-';
		}

		return implode( ', ', array_map( 'strval', $sample ) );
	}

	private function format_account_label( array $row ): string {
		$user_id = (int) ( $row['user_id'] ?? 0 );
		if ( $user_id <= 0 ) {
			return '-';
		}

		$login = (string) ( $row['user_login'] ?? '' );
		return '#' . $user_id . ( $login ? ' @' . $login : '' );
	}

	private function render_page_styles(): void {
		?>
		<style>
			@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
			.brg-admin-wrap { max-width: 1240px; font-family: 'Inter', sans-serif; color: #1e293b; }
			.brg-admin-hero { display:flex; flex-wrap:wrap; justify-content:space-between; gap:16px; margin:24px 0; align-items: center; }
			.brg-admin-hero h1 { margin:0 0 8px; font-weight: 700; font-size: 24px; color: #0f172a; }
			.brg-admin-hero p { margin:0; max-width:840px; color:#475569; font-size: 14px; }
			.brg-admin-hero-note { display:flex; gap:12px; align-items:center; color:#64748b; font-size:13px; background: #f8fafc; padding: 8px 12px; border-radius: 8px; border: 1px solid #e2e8f0; }
			
			.brg-admin-stats { display:flex; flex-wrap:wrap; gap:12px; margin:0 0 20px; }
			.brg-stat-card { flex: 1; min-width: 140px; background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:16px; box-shadow: 0 1px 2px rgba(0,0,0,0.03); border-left: 4px solid #3b82f6; }
			.brg-stat-card strong { display:block; font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; }
			.brg-stat-card span { display:block; font-size:24px; font-weight:700; color:#0f172a; margin-top:4px; }
			
			.brg-admin-toolbar { display:flex; flex-wrap:wrap; gap:16px; justify-content:space-between; align-items:center; padding:12px 16px; background:#fff; border:1px solid #e2e8f0; border-radius:12px; margin-bottom: 20px; }
			.brg-admin-search { display:flex; gap:8px; align-items:center; }
			.brg-admin-search input[type="text"] { min-width:280px; padding:8px 12px; border:1px solid #cbd5e1; border-radius:6px; font-family: 'Inter', sans-serif; font-size: 13px; }
			.brg-admin-chips { display:flex; gap:6px; flex-wrap:wrap; }
			.brg-admin-chip { padding:6px 12px; border-radius:999px; text-decoration:none; font-weight:500; font-size: 12px; border:1px solid #e2e8f0; background:#fff; color:#475569; }
			.brg-admin-chip.is-active { border-color:#3b82f6; background:#eff6ff; color:#1d4ed8; font-weight: 600; }
			
			.brg-admin-panel { background:#fff; border:1px solid #e2e8f0; border-radius:12px; margin:0 0 20px; overflow:hidden; }
			.brg-admin-panel > summary { cursor:pointer; font-weight:600; padding:12px 16px; background:#f8fafc; border-bottom: 1px solid transparent; font-size: 14px; }
			.brg-admin-panel[open] > summary { border-bottom-color: #e2e8f0; }
			.brg-admin-panel-body { padding:16px; }
			
			.brg-admin-inline-form { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
			.brg-admin-inline-form label { font-weight:600; font-size: 13px; width: 100px; }
			.brg-admin-inline-form input[type="text"] { padding:6px 10px; border:1px solid #cbd5e1; border-radius:6px; width: 200px; }
			
			.brg-ip-table { width: 100%; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; overflow: hidden; margin-bottom: 24px; }
			.brg-ip-header { display: grid; grid-template-columns: 160px 1fr 140px 160px 24px; gap: 16px; padding: 12px 16px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; font-size: 12px; font-weight: 600; color: #475569; text-transform: uppercase; }
			
			.brg-ip-row { border-bottom: 1px solid #e2e8f0; }
			.brg-ip-row:last-child { border-bottom: none; }
			.brg-ip-row > summary { display: grid; grid-template-columns: 160px 1fr 140px 160px 24px; gap: 16px; padding: 14px 16px; cursor: pointer; align-items: center; transition: background 0.2s; list-style: none; }
			.brg-ip-row > summary::-webkit-details-marker { display: none; }
			.brg-ip-row > summary:hover { background: #f8fafc; }
			.brg-ip-row[open] > summary { background: #f8fafc; border-bottom: 1px solid #e2e8f0; }
			
			.brg-col-ip strong { font-family: monospace; font-size: 14px; color: #0f172a; }
			.brg-col-ip span { font-size: 12px; color: #64748b; }
			.brg-col-badges { display: flex; flex-wrap: wrap; gap: 6px; }
			.brg-col-stats { font-size: 13px; color: #334155; }
			.brg-col-status { font-size: 12px; font-weight: 500; }
			
			.brg-ip-row-body { padding: 16px; background: #fff; display: grid; grid-template-columns: 1fr 340px; gap: 24px; }
			
			.brg-compact-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 12px; margin-bottom: 16px; }
			.brg-compact-stat { background: #f8fafc; padding: 10px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; }
			.brg-compact-stat strong { display: block; font-size: 10px; color: #64748b; text-transform: uppercase; }
			.brg-compact-stat span { display: block; font-size: 18px; font-weight: 700; color: #0f172a; margin-top: 4px; }
			
			.brg-action-group { display: flex; flex-direction: column; gap: 8px; background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 12px; }
			.brg-action-group form { margin: 0; display: flex; gap: 8px; }
			.brg-action-group .button { flex: 1; text-align: center; justify-content: center; font-size: 12px; padding: 4px 8px; min-height: 28px; line-height: normal; }
			
			.brg-badge { display:inline-flex; align-items:center; padding:4px 8px; border-radius:6px; font-size:11px; font-weight:600; border:1px solid rgba(0,0,0,0.05); }
			
			.button.button-primary { background: #2563eb; border-color: #2563eb; border-radius: 6px; color: #fff; }
			.button { border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; color: #334155; cursor: pointer; transition: all 0.2s; }
			.button:hover { background: #f1f5f9; }
			
			table.striped > tbody > tr:nth-child(odd) { background-color: #f8fafc; }
			table.widefat { width: 100%; border-radius: 8px; border: 1px solid #e2e8f0; border-collapse: collapse; }
			table.widefat th { font-weight: 600; color: #475569; padding: 10px 12px; background: #f1f5f9; border-bottom: 1px solid #e2e8f0; font-size: 12px; text-transform: uppercase; text-align: left; }
			table.widefat td { padding: 10px 12px; color: #334155; border-bottom: 1px solid #e2e8f0; font-size: 13px; }
		</style>
		<?php
	}

	private function render_stat_card( string $label, string $value ): void {
		?>
		<div class="brg-stat-card">
			<strong><?php echo esc_html( $label ); ?></strong>
			<span><?php echo esc_html( $value ); ?></span>
		</div>
		<?php
	}

	private function render_mini_stat( string $label, string $value ): void {
		?>
		<div style="padding:16px;border:1px solid #e2e8f0;border-radius:12px;background:#f8fafc;transition:background 0.2s ease;box-shadow: 0 1px 2px rgba(0,0,0,0.01);">
			<strong style="display:block;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;"><?php echo esc_html( $label ); ?></strong>
			<span style="display:block;font-size:24px;font-weight:700;color:#1e293b;line-height:1.2;margin-top:6px;"><?php echo esc_html( $value ); ?></span>
		</div>
		<?php
	}

	private function render_legend_item( string $label, string $text ): void {
		?>
		<div style="padding:16px;border:1px solid #e2e8f0;border-radius:12px;background:#ffffff;box-shadow: 0 1px 2px rgba(0,0,0,0.02);transition:border-color 0.2s;">
			<strong style="display:block;margin-bottom:6px;font-size:14px;color:#0f172a;font-weight:600;"><?php echo esc_html( $label ); ?></strong>
			<span style="font-size:13px;color:#475569;line-height:1.6;display:block;"><?php echo esc_html( $text ); ?></span>
		</div>
		<?php
	}

	private function human_reason( string $reason ): string {
		$monitor = BRG_Monitor::instance();
		$code    = $monitor->reason_code( $reason );

		$label = match ( $reason ) {
			'passive_honeypot_touched'      => 'senal pasiva del lector',
			'passive_honeypot_repeated'     => 'senal pasiva repetida',
			'honeypot_triggered'            => 'senal reforzada del lector',
			'cookie_missing_or_expired'     => 'imagen sin autorizacion',
			'multi_chapter_cookie_misses'   => 'sin autorizacion repetida multi-capitulo',
			'direct_protected_path_probe'   => 'intento de ruta cruda',
			'chapter_hopping_pattern'       => 'salto rapido entre capitulos',
			'excessive_multi_chapter_fetch' => 'descarga multi-capitulo intensa',
			'queue_like_multi_chapter_flow' => 'patron de cola multi-capitulo',
			'html_image_ratio_anomaly'      => 'ratio html -> imagenes fuera de rango',
			'manual_admin_block'            => 'bloqueo manual del admin',
			'manual_network_block'          => 'bloqueo manual por red',
			'manual_user_block'             => 'bloqueo manual de cuenta',
			'missing_presence_signal'       => 'imagenes sin presencia reciente',
			default                         => 'senal no catalogada',
		};

		return $code . ' - ' . $label;
	}

	private function network_hint( string $ip ): string {
		return BRG_Monitor::instance()->network_hint( $ip );
	}

	private function severity_info( array $group, array $profile, array $snapshot, int $alerts_sent, bool $active_bans, bool $network_manual_ban, bool $user_active_ban = false ): array {
		$offense_peak  = max( (int) ( $profile['offense_count'] ?? 0 ), max( array_map( static fn ( array $event ): int => (int) $event['offense_count'], $group['events'] ) ) );
		$cookie_hits   = $this->sum_int_column( $group['events'], 'cookie_denied_hits' );
		$direct_hits   = $this->sum_int_column( $group['events'], 'direct_blocked_hits' );
		$honeypot_hits = $this->sum_int_column( $group['events'], 'honeypot_hits' );

		if ( ! empty( $profile['manual_ban'] ) || $network_manual_ban || $user_active_ban || $alerts_sent > 0 || $offense_peak >= 4 ) {
			return [ 'key' => 'critical', 'label' => 'Critica', 'bg' => '#ffe4e6', 'fg' => '#9f1239' ];
		}

		if ( $active_bans || $offense_peak >= 3 || ! empty( $snapshot['queue_like_pattern'] ) || ! empty( $snapshot['html_image_ratio_alert'] ) || ! empty( $snapshot['multi_chapter_cookie_pattern'] ) ) {
			return [ 'key' => 'high', 'label' => 'Alta', 'bg' => '#fff7e8', 'fg' => '#b45309' ];
		}

		if ( ! empty( $profile['suspicious'] ) || $offense_peak >= 2 || $cookie_hits >= 8 || $direct_hits >= 1 || $honeypot_hits >= 2 ) {
			return [ 'key' => 'medium', 'label' => 'Media', 'bg' => '#eef4ff', 'fg' => '#1d4ed8' ];
		}

		return [ 'key' => 'low', 'label' => 'Baja', 'bg' => '#ecfeff', 'fg' => '#0f766e' ];
	}

	private function classify_client_type( array $group, array $snapshot ): array {
		$ua_blob          = strtolower( implode( ' || ', array_keys( $group['ua_map'] ) ) );
		$browser_markers  = [ 'firefox/', 'chrome/', 'edg/', 'safari/', 'opr/', 'samsungbrowser/' ];
		$rare_markers     = [ 'tachiyomi', 'mihon', 'aniyomi', 'komikku', 'yokai', 'okhttp', 'dalvik', 'cfnetwork', 'python-requests', 'wget', 'curl', 'go-http-client', 'electron', 'buscati/' ];
		$webview_markers  = [ '; wv', 'version/4.0', 'webview' ];
		$has_browser_marker = false;

		foreach ( $browser_markers as $marker ) {
			if ( str_contains( $ua_blob, $marker ) ) {
				$has_browser_marker = true;
				break;
			}
		}

		$has_rare_marker = false;
		foreach ( array_merge( $rare_markers, $webview_markers ) as $marker ) {
			if ( str_contains( $ua_blob, $marker ) ) {
				$has_rare_marker = true;
				break;
			}
		}

		$is_behavior_weird = ! empty( $snapshot['queue_like_pattern'] )
			|| ! empty( $snapshot['html_image_ratio_alert'] )
			|| ! empty( $snapshot['multi_chapter_cookie_pattern'] )
			|| ( (int) ( $snapshot['rapid_image_switches'] ?? 0 ) >= 2 && (int) ( $snapshot['distinct_image_chapters_short'] ?? 0 ) >= 2 );

		if ( $has_rare_marker || $is_behavior_weird ) {
			return [
				'label' => 'Cliente raro / app',
				'short' => 'Cliente raro',
				'bg'    => '#fff1f2',
				'fg'    => '#be123c',
				'note'  => 'La combinacion de UA y comportamiento se parece mas a una app, WebView o cliente de cola que a navegacion humana normal.',
			];
		}

		if ( $has_browser_marker ) {
			return [
				'label' => 'Navegador probable',
				'short' => 'Navegador',
				'bg'    => '#e8fff6',
				'fg'    => '#0f9f6e',
				'note'  => 'El UA parece de navegador comun y el patron reciente no muestra suficientes senales para tratarlo como cliente raro.',
			];
		}

		return [
			'label' => 'Cliente no concluyente',
			'short' => 'No concluyente',
			'bg'    => '#eef2ff',
			'fg'    => '#4338ca',
			'note'  => 'No hay suficientes pistas para llamarlo navegador limpio, pero tampoco hay un patron fuerte de app rara todavia.',
		];
	}

	private function render_badge( string $label, string $bg, string $fg ): void {
		?>
		<span class="brg-badge" style="background:<?php echo esc_attr( $bg ); ?>;color:<?php echo esc_attr( $fg ); ?>;">
			<?php echo esc_html( $label ); ?>
		</span>
		<?php
	}
}
