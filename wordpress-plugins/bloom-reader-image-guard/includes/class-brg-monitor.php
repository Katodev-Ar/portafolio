<?php

if ( ! class_exists( 'BRG_Context_Monitor' ) ) {
	class BRG_Context_Monitor {
		const OPTION_KEY          = 'brg_ctx_monitor_state';
		const SHORT_WINDOW        = 300;
		const BURST_WINDOW        = 75;
		const BOOTSTRAP_TTL       = 300;
		const PRESENCE_TTL        = 300;
		const STALE_BOOTSTRAP_AGE = 120;
		const MAX_EVENTS          = 180;
		const MAX_LOG_ITEMS       = 120;
		// Actor TTL: remove actors unseen for more than 1 hour (3600s).
		const ACTOR_TTL           = 3600;
		// Hard cap on actors stored in a single option to prevent unbounded growth.
		const MAX_ACTORS          = 2000;

		protected static $instance = null;

		public static function instance() {
			if ( null === self::$instance ) {
				self::$instance = new self();
			}

			return self::$instance;
		}

		public function record_bootstrap_hit( $chapter_id, $context = array() ) {
			$ip    = $this->current_ip();
			$state = $this->get_state();
			$actor = $this->ensure_actor( $state, $ip, isset( $context['ua'] ) ? $context['ua'] : '' );
			$now   = time();

			$actor['last_seen']                 = $now;
			$actor['last_bootstrap_ts']         = $now;
			$actor['bootstrap_map'][ $chapter_id ] = $now;
			$actor['bootstrap_log'][]           = array(
				'ts'      => $now,
				'chapter' => (int) $chapter_id,
			);
			$actor['bootstrap_log']             = $this->trim_log( $actor['bootstrap_log'] );

			$state['actors'][ $ip ] = $actor;
			$this->save_state( $state );
		}

		public function record_presence_hit( $chapter_id, $context = array() ) {
			$ip    = $this->current_ip();
			$state = $this->get_state();
			$actor = $this->ensure_actor( $state, $ip, isset( $context['ua'] ) ? $context['ua'] : '' );
			$now   = time();

			$actor['last_seen']                    = $now;
			$actor['last_presence_ts']             = $now;
			$actor['presence_map'][ $chapter_id ]  = $now;
			$actor['presence_log'][]               = array(
				'ts'      => $now,
				'chapter' => (int) $chapter_id,
			);
			$actor['presence_log']                 = $this->trim_log( $actor['presence_log'] );

			$state['actors'][ $ip ] = $actor;
			$this->save_state( $state );
		}

		public function record_image_probe( $chapter_id, $context = array() ) {
			$ip        = $this->current_ip();
			$ua        = isset( $context['ua'] ) ? (string) $context['ua'] : '';
			$state     = $this->get_state();
			$actor     = $this->ensure_actor( $state, $ip, $ua );
			$now       = time();
			$bootstrap = isset( $actor['bootstrap_map'][ $chapter_id ] ) ? (int) $actor['bootstrap_map'][ $chapter_id ] : 0;
			$presence  = isset( $actor['presence_map'][ $chapter_id ] ) ? (int) $actor['presence_map'][ $chapter_id ] : 0;
			$age       = $bootstrap > 0 ? max( 0, $now - $bootstrap ) : null;
			$presence_age = $presence > 0 ? max( 0, $now - $presence ) : null;
			$recent    = null !== $age && $age <= self::BOOTSTRAP_TTL;
			$stale     = null !== $age && $age > self::STALE_BOOTSTRAP_AGE;
			$presence_recent = null !== $presence_age && $presence_age <= self::PRESENCE_TTL;
			$weird     = $this->is_weird_request_context( $context );
			$has_range = ! empty( $context['has_range'] );

			$actor['last_seen'] = $now;

			$actor['image_log'][] = array(
				'ts'                => $now,
				'chapter'           => (int) $chapter_id,
				'bootstrap_recent'  => $recent ? 1 : 0,
				'bootstrap_age'     => null === $age ? -1 : (int) $age,
				'stale_bootstrap'   => $stale ? 1 : 0,
				'presence_recent'   => $presence_recent ? 1 : 0,
				'presence_age'      => null === $presence_age ? -1 : (int) $presence_age,
				'weird_context'     => $weird ? 1 : 0,
				'has_range'         => $has_range ? 1 : 0,
				'referer_present'   => empty( $context['referer'] ) ? 0 : 1,
				'sec_fetch_dest'    => isset( $context['sec_fetch_dest'] ) ? (string) $context['sec_fetch_dest'] : '',
				'sec_fetch_site'    => isset( $context['sec_fetch_site'] ) ? (string) $context['sec_fetch_site'] : '',
				'sec_fetch_mode'    => isset( $context['sec_fetch_mode'] ) ? (string) $context['sec_fetch_mode'] : '',
				'accept'            => isset( $context['accept'] ) ? substr( (string) $context['accept'], 0, 180 ) : '',
			);
			$actor['image_log']  = $this->trim_log( $actor['image_log'] );

			$metrics = $this->build_behavior_metrics( $actor, $chapter_id, $context );
			$event   = $this->evaluate_and_save( $actor, $metrics, $chapter_id, $ua );

			$state['actors'][ $ip ] = $actor;
			if ( ! empty( $event ) ) {
				$state['events'][] = $event;
				$state['events']   = $this->trim_events( $state['events'] );
			}
			$this->save_state( $state );

			return $metrics;
		}

		public function get_admin_snapshot( $severity_filter = '' ) {
			$state  = $this->get_state();
			$events = array();

			foreach ( $state['events'] as $event ) {
				if ( $severity_filter && $severity_filter !== $event['severity'] ) {
					continue;
				}
				$events[] = $event;
			}

			$actors = array_values( $state['actors'] );
			usort(
				$actors,
				static function( $left, $right ) {
					return (int) $right['last_seen'] - (int) $left['last_seen'];
				}
			);

			return array(
				'actors' => $actors,
				'events' => $events,
				'counts' => $this->summarize_severity_counts( $state['events'] ),
			);
		}

		protected function build_behavior_metrics( $actor, $chapter_id, $context ) {
			$now                 = time();
			$recent_images       = array();
			$recent_bootstraps   = array();
			$recent_presences    = array();
			$chapters_short      = array();
			$parallel_recent     = array();
			$missing_bootstrap   = 0;
			$stale_bootstrap     = 0;
			$missing_presence    = 0;
			$weird_context       = 0;
			$accept_weird_hits   = 0;
			$range_hits          = 0;
			$rapid_switches      = 0;
			$previous_hit        = null;

			foreach ( $actor['bootstrap_log'] as $bootstrap_hit ) {
				if ( ( $now - (int) $bootstrap_hit['ts'] ) <= self::SHORT_WINDOW ) {
					$recent_bootstraps[] = $bootstrap_hit;
				}
			}

			foreach ( $actor['presence_log'] as $presence_hit ) {
				if ( ( $now - (int) $presence_hit['ts'] ) <= self::SHORT_WINDOW ) {
					$recent_presences[] = $presence_hit;
				}
			}

			foreach ( $actor['image_log'] as $image_hit ) {
				$age = $now - (int) $image_hit['ts'];
				if ( $age > self::SHORT_WINDOW ) {
					continue;
				}

				$recent_images[] = $image_hit;
				$chapters_short[ (int) $image_hit['chapter'] ] = true;
				if ( 0 === (int) $image_hit['bootstrap_recent'] ) {
					$missing_bootstrap++;
				}
				if ( ! empty( $image_hit['stale_bootstrap'] ) ) {
					$stale_bootstrap++;
				}
				if ( empty( $image_hit['presence_recent'] ) ) {
					$missing_presence++;
				}
				if ( ! empty( $image_hit['weird_context'] ) ) {
					$weird_context++;
				}
				$accept_header = isset( $image_hit['accept'] ) ? trim( (string) $image_hit['accept'] ) : '';
				if ( '' === $accept_header || '*/*' === $accept_header ) {
					$accept_weird_hits++;
				}
				if ( ! empty( $image_hit['has_range'] ) ) {
					$range_hits++;
				}
				if ( $age <= 120 ) {
					$parallel_recent[ (int) $image_hit['chapter'] ] = true;
				}
				if ( $previous_hit && ( (int) $previous_hit['chapter'] !== (int) $image_hit['chapter'] ) && ( (int) $image_hit['ts'] - (int) $previous_hit['ts'] ) <= 8 ) {
					$rapid_switches++;
				}
				$previous_hit = $image_hit;
			}

			$latest = ! empty( $recent_images ) ? end( $recent_images ) : null;

			return array(
				'images_short'                 => count( $recent_images ),
				'distinct_chapters_short'      => count( $chapters_short ),
				'bootstrap_hits_short'         => count( $recent_bootstraps ),
				'images_without_recent_bootstrap' => $missing_bootstrap,
				'images_with_stale_bootstrap'  => $stale_bootstrap,
				'presence_hits_short'          => count( $recent_presences ),
				'images_without_recent_presence' => $missing_presence,
				'parallel_chapters_in_flight'  => count( $parallel_recent ),
				'rapid_chapter_switches'       => $rapid_switches,
				'weird_context_hits'           => $weird_context,
				'accept_weird_hits'            => $accept_weird_hits,
				'range_hits'                   => $range_hits,
				'bootstrap_image_ratio'        => count( $recent_bootstraps ) > 0 ? round( count( $recent_images ) / max( 1, count( $recent_bootstraps ) ), 2 ) : count( $recent_images ),
				'latest_bootstrap_age'         => $latest ? (int) $latest['bootstrap_age'] : -1,
				'current_chapter'              => (int) $chapter_id,
				'referer_present'              => empty( $context['referer'] ) ? 0 : 1,
				'sec_fetch_dest'               => isset( $context['sec_fetch_dest'] ) ? (string) $context['sec_fetch_dest'] : '',
			);
		}

		protected function evaluate_and_save( &$actor, $metrics, $chapter_id, $ua ) {
			$code     = '';
			$severity = '';

			if ( $metrics['images_without_recent_bootstrap'] >= 12 && $metrics['distinct_chapters_short'] >= 3 ) {
				$code     = 'BRG-M05';
				$severity = 'high';
			} elseif ( $metrics['images_with_stale_bootstrap'] >= 10 && $metrics['images_short'] >= 14 ) {
				$code     = 'BRG-M06';
				$severity = 'medium';
			} elseif ( $metrics['distinct_chapters_short'] >= 4 && $metrics['parallel_chapters_in_flight'] >= 3 && $metrics['bootstrap_image_ratio'] >= 10 ) {
				$code     = 'BRG-M07';
				$severity = 'high';
			} elseif ( $metrics['images_without_recent_presence'] >= 10 && $metrics['presence_hits_short'] <= 0 && $metrics['images_short'] >= 12 && $metrics['bootstrap_hits_short'] >= 1 ) {
				$code     = 'BRG-M09';
				$severity = 'medium';
			} elseif ( ( $metrics['weird_context_hits'] >= 6 && $metrics['images_short'] >= 8 ) || ( $metrics['range_hits'] >= 2 && $metrics['images_short'] >= 6 ) || ( $metrics['images_without_recent_presence'] >= 8 && $metrics['accept_weird_hits'] >= 4 ) ) {
				$code     = 'BRG-M08';
				$severity = 'medium';
			}

			if ( ! $code ) {
				$actor['client_probable'] = $this->classify_client( $metrics );
				return null;
			}

			$dedupe_key = $code . ':' . (int) floor( time() / 90 );
			if ( isset( $actor['dedupe'][ $dedupe_key ] ) ) {
				$actor['client_probable'] = $this->classify_client( $metrics );
				return null;
			}

			$actor['dedupe'][ $dedupe_key ] = time();
			$actor['signals'][ $code ]      = isset( $actor['signals'][ $code ] ) ? (int) $actor['signals'][ $code ] + 1 : 1;
			$actor['severity'][ $severity ] = isset( $actor['severity'][ $severity ] ) ? (int) $actor['severity'][ $severity ] + 1 : 1;
			$actor['events_total']          = isset( $actor['events_total'] ) ? (int) $actor['events_total'] + 1 : 1;
			$actor['client_probable']       = $this->classify_client( $metrics );

			return array(
				'ts'                    => time(),
				'ip'                    => $actor['ip'],
				'network'               => $actor['network'],
				'ua'                    => $ua,
				'chapter'               => (int) $chapter_id,
				'severity'              => $severity,
				'code'                  => $code,
				'client_probable'       => $actor['client_probable'],
				'images_without_bootstrap' => $metrics['images_without_recent_bootstrap'],
				'stale_bootstrap_hits'  => $metrics['images_with_stale_bootstrap'],
				'parallel_chapters'     => $metrics['parallel_chapters_in_flight'],
				'bootstrap_ratio'       => $metrics['bootstrap_image_ratio'],
				'presence_hits'         => $metrics['presence_hits_short'],
				'images_without_presence' => $metrics['images_without_recent_presence'],
				'weird_context_hits'    => $metrics['weird_context_hits'],
				'accept_weird_hits'     => $metrics['accept_weird_hits'],
				'range_hits'            => $metrics['range_hits'],
			);
		}

		protected function classify_client( $metrics ) {
			if ( $metrics['images_without_recent_bootstrap'] >= 8 && $metrics['images_without_recent_presence'] >= 8 && $metrics['weird_context_hits'] >= 4 ) {
				return 'Cliente raro / parser';
			}
			if ( $metrics['distinct_chapters_short'] >= 4 && $metrics['bootstrap_image_ratio'] >= 10 ) {
				return 'Browser/downloader integrado';
			}
			if ( $metrics['presence_hits_short'] >= 1 && 'image' === $metrics['sec_fetch_dest'] && $metrics['referer_present'] ) {
				return 'Navegador probable';
			}
			return 'Cliente no concluyente';
		}

		protected function is_weird_request_context( $context ) {
			$referer = isset( $context['referer'] ) ? trim( (string) $context['referer'] ) : '';
			$site    = isset( $context['sec_fetch_site'] ) ? trim( (string) $context['sec_fetch_site'] ) : '';
			$mode    = isset( $context['sec_fetch_mode'] ) ? trim( (string) $context['sec_fetch_mode'] ) : '';
			$dest    = isset( $context['sec_fetch_dest'] ) ? trim( (string) $context['sec_fetch_dest'] ) : '';
			$accept  = isset( $context['accept'] ) ? trim( (string) $context['accept'] ) : '';

			if ( ! empty( $context['has_range'] ) ) {
				return true;
			}
			if ( '' === $referer ) {
				return true;
			}
			if ( '' !== $dest && 'image' !== $dest ) {
				return true;
			}
			if ( '' !== $mode && ! in_array( $mode, array( 'no-cors', 'cors' ), true ) ) {
				return true;
			}
			if ( '' !== $site && ! in_array( $site, array( 'same-origin', 'same-site', 'none' ), true ) ) {
				return true;
			}
			if ( '' === $accept || '*/*' === $accept ) {
				return true;
			}

			return false;
		}

		protected function summarize_severity_counts( $events ) {
			$counts = array(
				'critical' => 0,
				'high'     => 0,
				'medium'   => 0,
				'low'      => 0,
			);

			foreach ( $events as $event ) {
				$severity = isset( $event['severity'] ) ? $event['severity'] : 'low';
				if ( ! isset( $counts[ $severity ] ) ) {
					$counts[ $severity ] = 0;
				}
				$counts[ $severity ]++;
			}

			return $counts;
		}

		protected function ensure_actor( &$state, $ip, $ua ) {
			if ( empty( $state['actors'][ $ip ] ) ) {
				$state['actors'][ $ip ] = array(
					'ip'             => $ip,
					'network'        => $this->probable_network( $ip ),
					'last_seen'      => 0,
					'last_bootstrap_ts' => 0,
					'bootstrap_map'  => array(),
					'bootstrap_log'  => array(),
					'presence_map'   => array(),
					'presence_log'   => array(),
					'image_log'      => array(),
					'uas'            => array(),
					'signals'        => array(),
					'severity'       => array(),
					'events_total'   => 0,
					'client_probable'=> 'Cliente no concluyente',
					'dedupe'         => array(),
				);
			}

			if ( '' !== $ua ) {
				$state['actors'][ $ip ]['uas'][ $ua ] = isset( $state['actors'][ $ip ]['uas'][ $ua ] ) ? (int) $state['actors'][ $ip ]['uas'][ $ua ] + 1 : 1;
			}

			return $state['actors'][ $ip ];
		}

		protected function trim_log( $log ) {
			if ( count( $log ) > self::MAX_LOG_ITEMS ) {
				$log = array_slice( $log, -1 * self::MAX_LOG_ITEMS );
			}

			return array_values( $log );
		}

		protected function trim_events( $events ) {
			if ( count( $events ) > self::MAX_EVENTS ) {
				$events = array_slice( $events, -1 * self::MAX_EVENTS );
			}

			return array_values( $events );
		}

		protected function current_ip() {
			foreach ( array( 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR' ) as $key ) {
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

		protected function probable_network( $ip ) {
			if ( false !== strpos( $ip, ':' ) ) {
				$parts = explode( ':', $ip );
				$parts = array_pad( $parts, 4, '0' );
				return implode( ':', array_slice( $parts, 0, 4 ) ) . '::/64';
			}

			$parts = explode( '.', $ip );
			$parts = array_pad( $parts, 4, '0' );
			return $parts[0] . '.' . $parts[1] . '.' . $parts[2] . '.0/24';
		}

		protected function get_state() {
			$state = get_option(
				self::OPTION_KEY,
				array(
					'actors' => array(),
					'events' => array(),
				)
			);

			if ( ! is_array( $state ) ) {
				$state = array(
					'actors' => array(),
					'events' => array(),
				);
			}

			return $state;
		}

		protected function evict_stale_actors( array $state ): array {
			if ( empty( $state['actors'] ) || ! is_array( $state['actors'] ) ) {
				return $state;
			}

			$cutoff = time() - self::ACTOR_TTL;
			foreach ( $state['actors'] as $ip => $actor ) {
				if ( (int) ( $actor['last_seen'] ?? 0 ) < $cutoff ) {
					unset( $state['actors'][ $ip ] );
				}
			}

			// Hard cap: if still over limit, keep the most recently seen actors.
			if ( count( $state['actors'] ) > self::MAX_ACTORS ) {
				uasort(
					$state['actors'],
					static function ( $a, $b ) {
						return (int) ( $b['last_seen'] ?? 0 ) - (int) ( $a['last_seen'] ?? 0 );
					}
				);
				$state['actors'] = array_slice( $state['actors'], 0, self::MAX_ACTORS, true );
			}

			return $state;
		}

		protected function save_state( $state ) {
			$state = $this->evict_stale_actors( $state );
			update_option( self::OPTION_KEY, $state, false );
		}
	}
}

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class BRG_Monitor {
	private const STATE_PREFIX      = 'brg_actor_';
	private const PROFILE_PREFIX    = 'brg_profile_';
	private const USER_PROFILE_PREFIX = 'brg_user_profile_';
	private const UA_PROFILE_PREFIX = 'brg_ua_';
	private const NETWORK_PROFILE_PREFIX = 'brg_network_';
	private const STATE_TTL         = 172800;
	private const MAX_IMAGE_EVENTS  = 500;
	private const MAX_VIEW_EVENTS   = 90;
	private const MAX_PRESENCE_EVENTS = 90;
	private const MAX_DENIED_EVENTS = 30;
	private const MAX_DIRECT_EVENTS = 30;
	private const MAX_HONEYPOT_EVENTS = 12;
	private const TABLE_VERSION     = '1.3.0';

	private static ?self $instance = null;

	public static function instance(): self {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}

		return self::$instance;
	}

	public function bootstrap(): void {
		if ( get_option( 'brg_table_version' ) === self::TABLE_VERSION ) {
			return;
		}

		$this->maybe_create_table();
		update_option( 'brg_table_version', self::TABLE_VERSION, false );
	}

	public function get_actor(): array {
		$ip         = $this->client_ip();
		$user_agent = substr( isset( $_SERVER['HTTP_USER_AGENT'] ) ? (string) wp_unslash( $_SERVER['HTTP_USER_AGENT'] ) : 'unknown', 0, 500 );
		$ua_hash    = hash( 'sha256', $user_agent );
		$network    = $this->network_hint( $ip );
		$user       = wp_get_current_user();
		$user_id    = $user instanceof WP_User ? (int) $user->ID : 0;
		$user_login = $user_id > 0 ? (string) $user->user_login : '';
		$user_email = $user_id > 0 ? (string) $user->user_email : '';

		return [
			'ip'         => $ip,
			'user_agent' => $user_agent,
			'ua_hash'    => $ua_hash,
			'key'        => hash( 'sha256', strtolower( $ip ) . '|' . $ua_hash ),
			'ip_hash'    => hash( 'sha256', strtolower( $ip ) ),
			'state_key'  => hash( 'sha256', strtolower( $ip ) ),
			'network_hint' => $network,
			'network_hash' => hash( 'sha256', strtolower( $network ) ),
			'ua_summary' => $this->summarize_ua( $user_agent ),
			'user_id'    => $user_id,
			'user_login' => $user_login,
			'user_email' => $user_email,
		];
	}

	public function get_active_ban( array $actor ): ?array {
		$state = $this->get_state( $actor );
		$now   = time();

		if ( ! empty( $state['manual_ban'] ) ) {
			return [
				'ban_until'     => 0,
				'offense_count' => (int) ( $state['offense_count'] ?? 0 ),
				'reason'        => 'manual_admin_block',
				'manual'        => true,
				'case_id'       => (string) ( $state['active_case_id'] ?? '' ),
				'scope'         => 'ip',
			];
		}

		$user_profile = $this->get_user_profile( (int) ( $actor['user_id'] ?? 0 ) );
		if ( ! empty( $user_profile['manual_ban'] ) ) {
			return [
				'ban_until'     => 0,
				'offense_count' => max( (int) ( $state['offense_count'] ?? 0 ), (int) ( $user_profile['offense_count'] ?? 0 ) ),
				'reason'        => 'manual_user_block',
				'manual'        => true,
				'case_id'       => (string) ( $user_profile['active_case_id'] ?? '' ),
				'scope'         => 'user',
				'user_id'       => (int) ( $actor['user_id'] ?? 0 ),
				'user_login'    => (string) ( $actor['user_login'] ?? '' ),
			];
		}

		$network_profile = $this->get_network_profile( $actor['network_hint'] ?? '' );
		if ( ! empty( $network_profile['manual_ban'] ) ) {
			return [
				'ban_until'     => 0,
				'offense_count' => max( (int) ( $state['offense_count'] ?? 0 ), (int) ( $network_profile['offense_count'] ?? 0 ) ),
				'reason'        => 'manual_network_block',
				'manual'        => true,
				'case_id'       => (string) ( $network_profile['active_case_id'] ?? '' ),
				'scope'         => 'network',
				'network'       => (string) ( $actor['network_hint'] ?? '' ),
			];
		}

		if ( ! empty( $state['ban_until'] ) && (int) $state['ban_until'] > $now ) {
			return [
				'ban_until'     => (int) $state['ban_until'],
				'offense_count' => (int) ( $state['offense_count'] ?? 0 ),
				'reason'        => (string) ( $state['last_reason'] ?? 'rate_limited' ),
				'manual'        => false,
				'case_id'       => (string) ( $state['active_case_id'] ?? '' ),
				'scope'         => 'ip',
			];
		}

		if ( (int) ( $actor['user_id'] ?? 0 ) > 0 && ! empty( $user_profile['ban_until'] ) && (int) $user_profile['ban_until'] > $now ) {
			return [
				'ban_until'     => (int) $user_profile['ban_until'],
				'offense_count' => max( (int) ( $state['offense_count'] ?? 0 ), (int) ( $user_profile['offense_count'] ?? 0 ) ),
				'reason'        => (string) ( $user_profile['last_reason'] ?? 'rate_limited' ),
				'manual'        => false,
				'case_id'       => (string) ( $user_profile['active_case_id'] ?? '' ),
				'scope'         => 'user',
				'user_id'       => (int) ( $actor['user_id'] ?? 0 ),
				'user_login'    => (string) ( $actor['user_login'] ?? '' ),
			];
		}

		return null;
	}

	public function record_chapter_view( array $actor, int $chapter_id ): array {
		$state                  = $this->get_state( $actor );
		$now                    = time();
		$state['last_seen']     = $now;
		$state['chapter_views'] = $this->append_event(
			(array) ( $state['chapter_views'] ?? [] ),
			[
				't' => $now,
				'c' => $chapter_id,
			],
			self::MAX_VIEW_EVENTS
		);

		return $this->evaluate_and_save( $actor, $state );
	}

	public function record_presence_hit( array $actor, int $chapter_id ): array {
		$state                    = $this->get_state( $actor );
		$now                      = time();
		$state['last_seen']       = $now;
		$state['presence_events'] = $this->append_event(
			(array) ( $state['presence_events'] ?? [] ),
			[
				't' => $now,
				'c' => $chapter_id,
			],
			self::MAX_PRESENCE_EVENTS
		);

		$this->save_hot_state( $actor, $state );

		return [
			'banned'        => false,
			'ban_until'     => (int) ( $state['ban_until'] ?? 0 ),
			'offense_count' => (int) ( $state['offense_count'] ?? 0 ),
			'reason'        => (string) ( $state['last_reason'] ?? '' ),
		];
	}

	public function record_image_hit( array $actor, int $chapter_id ): array {
		$state                 = $this->get_state( $actor );
		$now                   = time();
		$state['last_seen']    = $now;
		$state['image_events'] = $this->append_event(
			(array) ( $state['image_events'] ?? [] ),
			[
				't' => $now,
				'c' => $chapter_id,
			],
			self::MAX_IMAGE_EVENTS
		);

		$state = $this->prune_state( $state );
		if ( $this->should_evaluate_image_state( $state ) ) {
			return $this->evaluate_and_save( $actor, $state );
		}

		$this->save_hot_state( $actor, $state );

		return [
			'banned'        => false,
			'ban_until'     => 0,
			'offense_count' => (int) ( $state['offense_count'] ?? 0 ),
			'reason'        => '',
		];
	}

	public function record_denied_cookie( array $actor, int $chapter_id ): array {
		$state                  = $this->get_state( $actor );
		$now                    = time();
		$state['last_seen']     = $now;
		$state['denied_cookie'] = $this->append_event(
			(array) ( $state['denied_cookie'] ?? [] ),
			[
				't' => $now,
				'c' => $chapter_id,
			],
			self::MAX_DENIED_EVENTS
		);

		return $this->evaluate_and_save( $actor, $state );
	}

	public function record_direct_block( array $actor, int $chapter_id, string $relative_path ): array {
		$state                  = $this->get_state( $actor );
		$now                    = time();
		$state['last_seen']     = $now;
		$state['direct_blocks'] = $this->append_event(
			(array) ( $state['direct_blocks'] ?? [] ),
			[
				't' => $now,
				'c' => $chapter_id,
				'p' => substr( $relative_path, 0, 190 ),
			],
			self::MAX_DIRECT_EVENTS
		);

		return $this->evaluate_and_save( $actor, $state );
	}

	public function record_honeypot_hit( array $actor, int $chapter_id, string $token, string $kind = 'reinforced' ): array {
		$state                   = $this->get_state( $actor );
		$now                     = time();
		$state['last_seen']      = $now;
		$kind                    = in_array( $kind, [ 'passive', 'reinforced' ], true ) ? $kind : 'reinforced';
		$bucket                  = 'passive' === $kind ? 'passive_honeypot_hits' : 'honeypot_hits';
		$state[ $bucket ]        = $this->append_event(
			(array) ( $state[ $bucket ] ?? [] ),
			[
				't' => $now,
				'c' => $chapter_id,
				'h' => substr( $token, 0, 40 ),
				'k' => $kind,
			],
			self::MAX_HONEYPOT_EVENTS
		);

		if ( 'passive' === $kind ) {
			$state['suspicious']   = 1;
			$state['last_reason']  = 'passive_honeypot_touched';
			$this->persist_event( $actor, $state, true );
		}

		return $this->evaluate_and_save( $actor, $state );
	}

	public function should_inject_honeypot( array $actor ): bool {
		$state = $this->prune_state( $this->get_state( $actor ) );

		if ( (int) ( $state['offense_count'] ?? 0 ) >= 1 || ! empty( $state['suspicious'] ) ) {
			return true;
		}

		if ( $this->count_recent( (array) ( $state['denied_cookie'] ?? [] ), 600 ) >= 4 ) {
			return true;
		}

		if ( $this->count_recent( (array) ( $state['direct_blocks'] ?? [] ), 600 ) >= 2 ) {
			return true;
		}

		$image_recent = $this->recent_events( (array) ( $state['image_events'] ?? [] ), 600 );
		$distinct     = $this->distinct_chapter_count( $image_recent );
		if ( $distinct >= 4 ) {
			return true;
		}

		$metrics = $this->build_behavior_metrics( $state );
		if ( ! empty( $metrics['queue_like_pattern'] ) || ! empty( $metrics['html_image_ratio_alert'] ) || ! empty( $metrics['presence_image_ratio_alert'] ) ) {
			return true;
		}

		if ( (int) $metrics['denied_count_short'] >= 4 && (int) $metrics['distinct_denied_chapters'] >= 2 ) {
			return true;
		}

		return count( $image_recent ) >= 60 && $distinct >= 2;
	}

	public function get_ip_profile( string $ip ): array {
		$profile = get_option( self::PROFILE_PREFIX . hash( 'sha256', strtolower( $ip ) ), [] );
		if ( ! is_array( $profile ) ) {
			$profile = [];
		}

		return array_merge(
			[
				'ip'                 => $ip,
				'offense_count'      => 0,
				'ban_until'          => 0,
				'last_reason'        => '',
				'last_offense_at'    => 0,
				'last_alerted_count' => 0,
				'suspicious'         => 0,
				'manual_ban'         => 0,
				'manual_ban_set_at'  => 0,
				'first_seen'         => 0,
				'last_seen'          => 0,
				'active_case_id'     => '',
				'last_case_id'       => '',
			],
			$profile
		);
	}

	public function get_user_profile( int $user_id ): array {
		if ( $user_id <= 0 ) {
			return [
				'user_id'             => 0,
				'user_login'          => '',
				'user_email'          => '',
				'offense_count'       => 0,
				'ban_until'           => 0,
				'last_reason'         => '',
				'last_offense_at'     => 0,
				'last_alerted_count'  => 0,
				'suspicious'          => 0,
				'manual_ban'          => 0,
				'manual_ban_set_at'   => 0,
				'first_seen'          => 0,
				'last_seen'           => 0,
				'active_case_id'      => '',
				'last_case_id'        => '',
			];
		}

		$profile = get_option( self::USER_PROFILE_PREFIX . $user_id, [] );
		if ( ! is_array( $profile ) ) {
			$profile = [];
		}

		return array_merge(
			[
				'user_id'             => $user_id,
				'user_login'          => '',
				'user_email'          => '',
				'offense_count'       => 0,
				'ban_until'           => 0,
				'last_reason'         => '',
				'last_offense_at'     => 0,
				'last_alerted_count'  => 0,
				'suspicious'          => 0,
				'manual_ban'          => 0,
				'manual_ban_set_at'   => 0,
				'first_seen'          => 0,
				'last_seen'           => 0,
				'active_case_id'      => '',
				'last_case_id'        => '',
			],
			$profile
		);
	}

	public function get_network_profile( string $network ): array {
		if ( ! $this->is_valid_network_hint( $network ) ) {
			return [
				'network'           => $network,
				'offense_count'     => 0,
				'manual_ban'        => 0,
				'manual_ban_set_at' => 0,
				'last_seen'         => 0,
				'active_case_id'    => '',
			];
		}

		$profile = get_option( self::NETWORK_PROFILE_PREFIX . hash( 'sha256', strtolower( $network ) ), [] );
		if ( ! is_array( $profile ) ) {
			$profile = [];
		}

		return array_merge(
			[
				'network'           => $network,
				'offense_count'     => 0,
				'manual_ban'        => 0,
				'manual_ban_set_at' => 0,
				'last_seen'         => 0,
				'active_case_id'    => '',
			],
			$profile
		);
	}

	public function get_ua_profile( string $ua_hash ): array {
		$key = self::UA_PROFILE_PREFIX . substr( $ua_hash, 0, 16 );
		$profile = get_option( $key, [] );
		if ( ! is_array( $profile ) ) {
			$profile = [];
		}

		return array_merge(
			[
				'ua_hash'       => $ua_hash,
				'offense_count' => 0,
				'last_seen'     => 0,
				'last_reason'   => '',
			],
			$profile
		);
	}

	public function clear_ip_ban( string $ip ): bool {
		$profile              = $this->get_ip_profile( $ip );
		$profile['ban_until'] = 0;
		$profile['manual_ban'] = 0;
		$profile['manual_ban_set_at'] = 0;
		$profile['active_case_id'] = '';
		update_option( self::PROFILE_PREFIX . hash( 'sha256', strtolower( $ip ) ), $profile, false );
		delete_transient( self::STATE_PREFIX . hash( 'sha256', strtolower( $ip ) ) );
		return true;
	}

	public function clear_user_ban( int $user_id ): bool {
		if ( $user_id <= 0 ) {
			return false;
		}

		$profile                    = $this->get_user_profile( $user_id );
		$profile['ban_until']       = 0;
		$profile['manual_ban']      = 0;
		$profile['manual_ban_set_at'] = 0;
		$profile['active_case_id']  = '';
		update_option( self::USER_PROFILE_PREFIX . $user_id, $profile, false );
		return true;
	}

	public function clear_network_ban( string $network ): bool {
		if ( ! $this->is_valid_network_hint( $network ) ) {
			return false;
		}

		$profile                      = $this->get_network_profile( $network );
		$profile['manual_ban']        = 0;
		$profile['manual_ban_set_at'] = 0;
		$profile['active_case_id']    = '';
		update_option( self::NETWORK_PROFILE_PREFIX . hash( 'sha256', strtolower( $network ) ), $profile, false );
		return true;
	}

	public function set_ip_manual_ban( string $ip ): bool {
		$profile                       = $this->get_ip_profile( $ip );
		$profile['manual_ban']         = 1;
		$profile['manual_ban_set_at']  = time();
		$profile['suspicious']         = 1;
		$profile['last_reason']        = 'manual_admin_block';
		$profile['last_seen']          = time();
		$profile['active_case_id']     = $this->generate_case_id( [ 'ip' => $ip, 'user_id' => 0 ], 'manual_admin_block' );
		$profile['last_case_id']       = $profile['active_case_id'];
		if ( empty( $profile['first_seen'] ) ) {
			$profile['first_seen'] = time();
		}
		update_option( self::PROFILE_PREFIX . hash( 'sha256', strtolower( $ip ) ), $profile, false );
		return true;
	}

	public function set_user_manual_ban( int $user_id, string $user_login = '', string $user_email = '' ): bool {
		if ( $user_id <= 0 ) {
			return false;
		}

		$profile                      = $this->get_user_profile( $user_id );
		$profile['manual_ban']        = 1;
		$profile['manual_ban_set_at'] = time();
		$profile['suspicious']        = 1;
		$profile['last_reason']       = 'manual_user_block';
		$profile['last_seen']         = time();
		$profile['user_login']        = $user_login ?: (string) ( $profile['user_login'] ?? '' );
		$profile['user_email']        = $user_email ?: (string) ( $profile['user_email'] ?? '' );
		$profile['active_case_id']    = $this->generate_case_id( [ 'ip' => 'account', 'user_id' => $user_id ], 'manual_user_block' );
		$profile['last_case_id']      = $profile['active_case_id'];
		if ( empty( $profile['first_seen'] ) ) {
			$profile['first_seen'] = time();
		}
		update_option( self::USER_PROFILE_PREFIX . $user_id, $profile, false );
		return true;
	}

	public function set_network_manual_ban( string $network ): bool {
		if ( ! $this->is_valid_network_hint( $network ) ) {
			return false;
		}

		$profile                      = $this->get_network_profile( $network );
		$profile['manual_ban']        = 1;
		$profile['manual_ban_set_at'] = time();
		$profile['last_seen']         = time();
		$profile['active_case_id']    = $this->generate_case_id( [ 'ip' => $network, 'user_id' => 0 ], 'manual_network_block' );
		update_option( self::NETWORK_PROFILE_PREFIX . hash( 'sha256', strtolower( $network ) ), $profile, false );
		return true;
	}

	public function reset_ip_profile( string $ip ): bool {
		$profile = $this->get_ip_profile( $ip );
		$profile['offense_count']      = 0;
		$profile['ban_until']          = 0;
		$profile['last_reason']        = '';
		$profile['last_offense_at']    = 0;
		$profile['last_alerted_count'] = 0;
		$profile['suspicious']         = 0;
		$profile['manual_ban']         = 0;
		$profile['manual_ban_set_at']  = 0;
		$profile['active_case_id']     = '';
		update_option( self::PROFILE_PREFIX . hash( 'sha256', strtolower( $ip ) ), $profile, false );
		delete_transient( self::STATE_PREFIX . hash( 'sha256', strtolower( $ip ) ) );
		return true;
	}

	public function reset_user_profile( int $user_id ): bool {
		if ( $user_id <= 0 ) {
			return false;
		}

		$profile = $this->get_user_profile( $user_id );
		$profile['offense_count']      = 0;
		$profile['ban_until']          = 0;
		$profile['last_reason']        = '';
		$profile['last_offense_at']    = 0;
		$profile['last_alerted_count'] = 0;
		$profile['suspicious']         = 0;
		$profile['manual_ban']         = 0;
		$profile['manual_ban_set_at']  = 0;
		$profile['active_case_id']     = '';
		update_option( self::USER_PROFILE_PREFIX . $user_id, $profile, false );
		return true;
	}

	public function get_live_snapshot( string $ip ): array {
		$actor   = [
			'ip'           => $ip,
			'ip_hash'      => hash( 'sha256', strtolower( $ip ) ),
			'state_key'    => hash( 'sha256', strtolower( $ip ) ),
			'network_hint' => $this->network_hint( $ip ),
			'user_id'      => 0,
		];
		$state   = $this->prune_state( $this->get_state( $actor ) );
		$metrics = $this->build_behavior_metrics( $state );

		return array_merge(
			[
				'network_profile' => $this->get_network_profile( $actor['network_hint'] ),
				'network_hint'    => $actor['network_hint'],
				'active_case_id'  => (string) ( $state['active_case_id'] ?? '' ),
			],
			$metrics
		);
	}

	public function is_valid_network_hint( string $network ): bool {
		return 1 === preg_match( '/^\d{1,3}(?:\.\d{1,3}){3}\/24$/', $network )
			|| 1 === preg_match( '/^[a-f0-9:]+::\/64$/i', $network );
	}

	public function reason_code( string $reason ): string {
		return match ( $reason ) {
			'passive_honeypot_touched'      => 'BRG-H01',
			'passive_honeypot_repeated'     => 'BRG-H02',
			'honeypot_triggered'            => 'BRG-H03',
			'cookie_missing_or_expired'     => 'BRG-C01',
			'multi_chapter_cookie_misses'   => 'BRG-C02',
			'direct_protected_path_probe'   => 'BRG-R01',
			'chapter_hopping_pattern'       => 'BRG-M01',
			'excessive_multi_chapter_fetch' => 'BRG-M02',
			'queue_like_multi_chapter_flow' => 'BRG-M03',
			'html_image_ratio_anomaly'      => 'BRG-M04',
			'manual_admin_block'            => 'BRG-A01',
			'manual_network_block'          => 'BRG-A02',
			'manual_user_block'             => 'BRG-A03',
			'missing_presence_signal'       => 'BRG-M09',
			default                         => 'BRG-X00',
		};
	}

	private function get_all_profiles(): array {
		global $wpdb;

		$rows = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT option_value FROM {$wpdb->options} WHERE option_name LIKE %s",
				self::PROFILE_PREFIX . '%'
			),
			ARRAY_A
		); // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching

		$profiles = [];
		foreach ( $rows as $row ) {
			$value = maybe_unserialize( $row['option_value'] ?? '' );
			if ( is_array( $value ) ) {
				$profiles[] = $value;
			}
		}

		return $profiles;
	}

	private function get_all_user_profiles(): array {
		global $wpdb;

		$rows = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT option_value FROM {$wpdb->options} WHERE option_name LIKE %s",
				self::USER_PROFILE_PREFIX . '%'
			),
			ARRAY_A
		); // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching

		$profiles = [];
		foreach ( $rows as $row ) {
			$value = maybe_unserialize( $row['option_value'] ?? '' );
			if ( is_array( $value ) ) {
				$profiles[] = $value;
			}
		}

		return $profiles;
	}

	private function get_all_network_profiles(): array {
		global $wpdb;

		$rows = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT option_value FROM {$wpdb->options} WHERE option_name LIKE %s",
				self::NETWORK_PROFILE_PREFIX . '%'
			),
			ARRAY_A
		); // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching

		$profiles = [];
		foreach ( $rows as $row ) {
			$value = maybe_unserialize( $row['option_value'] ?? '' );
			if ( is_array( $value ) ) {
				$profiles[] = $value;
			}
		}

		return $profiles;
	}

	public function get_recent_events( int $limit = 100 ): array {
		global $wpdb;

		$table = $wpdb->prefix . 'bloom_reader_guard_events';
		$limit = max( 1, min( 500, $limit ) );

		$query = $wpdb->prepare( "SELECT * FROM {$table} ORDER BY id DESC LIMIT %d", $limit ); // phpcs:ignore WordPress.DB.PreparedSQL.NotPrepared
		return $wpdb->get_results( $query, ARRAY_A ) ?: [];
	}

	public function get_recent_appeals( int $limit = 100, string $status = 'all' ): array {
		global $wpdb;

		$table = $wpdb->prefix . 'bloom_reader_guard_appeals';
		$limit = max( 1, min( 500, $limit ) );

		if ( in_array( $status, [ 'open', 'resolved', 'rejected' ], true ) ) {
			$query = $wpdb->prepare( "SELECT * FROM {$table} WHERE status = %s ORDER BY id DESC LIMIT %d", $status, $limit ); // phpcs:ignore WordPress.DB.PreparedSQL.NotPrepared
		} else {
			$query = $wpdb->prepare( "SELECT * FROM {$table} ORDER BY id DESC LIMIT %d", $limit ); // phpcs:ignore WordPress.DB.PreparedSQL.NotPrepared
		}

		return $wpdb->get_results( $query, ARRAY_A ) ?: [];
	}

	public function submit_appeal( array $actor, string $case_id, string $appeal_text, string $contact = '' ): array {
		global $wpdb;

		$case_id     = strtoupper( preg_replace( '/[^A-Z0-9-]/', '', $case_id ) );
		$appeal_text = trim( wp_strip_all_tags( $appeal_text ) );
		$contact     = trim( sanitize_text_field( $contact ) );

		if ( '' === $case_id || strlen( $case_id ) < 6 ) {
			return [ 'ok' => false, 'message' => 'El identificador del caso no es válido.' ];
		}

		if ( '' === $appeal_text || strlen( $appeal_text ) < 8 ) {
			return [ 'ok' => false, 'message' => 'Cuéntanos un poco más para que el equipo pueda revisarlo.' ];
		}

		$table = $wpdb->prefix . 'bloom_reader_guard_appeals';
		$state = $this->get_state( $actor );
		$reason = (string) ( $state['last_reason'] ?? '' );
		if ( '' === $reason && (int) ( $actor['user_id'] ?? 0 ) > 0 ) {
			$user_profile = $this->get_user_profile( (int) $actor['user_id'] );
			$reason = (string) ( $user_profile['last_reason'] ?? '' );
		}
		$recent_duplicate = (int) $wpdb->get_var(
			$wpdb->prepare(
				"SELECT COUNT(*) FROM {$table} WHERE case_id = %s AND ip = %s AND status = 'open' AND created_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE)",
				$case_id,
				(string) ( $actor['ip'] ?? '' )
			)
		); // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
		if ( $recent_duplicate > 0 ) {
			return [ 'ok' => true, 'message' => 'Ya tenemos un reclamo abierto para este caso. El equipo lo va a revisar.' ];
		}

		$wpdb->insert( // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			$table,
			[
				'created_at'  => current_time( 'mysql', true ),
				'updated_at'  => current_time( 'mysql', true ),
				'case_id'     => $case_id,
				'status'      => 'open',
				'ip'          => (string) ( $actor['ip'] ?? '' ),
				'network_hint'=> (string) ( $actor['network_hint'] ?? '' ),
				'user_id'     => (int) ( $actor['user_id'] ?? 0 ),
				'user_login'  => (string) ( $actor['user_login'] ?? '' ),
				'user_email'  => (string) ( $actor['user_email'] ?? '' ),
				'contact'     => $contact,
				'reason'      => $reason,
				'appeal_text' => $appeal_text,
				'admin_note'  => '',
			]
		);

		return [
			'ok'      => true,
			'message' => 'Tu reclamo quedó enviado. El equipo ya puede verlo en el panel admin.',
		];
	}

	public function update_appeal_status( int $appeal_id, string $status, string $admin_note = '' ): bool {
		global $wpdb;

		if ( ! in_array( $status, [ 'open', 'resolved', 'rejected' ], true ) ) {
			return false;
		}

		$table = $wpdb->prefix . 'bloom_reader_guard_appeals';
		return false !== $wpdb->update( // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			$table,
			[
				'status'     => $status,
				'admin_note' => sanitize_textarea_field( $admin_note ),
				'updated_at' => current_time( 'mysql', true ),
			],
			[ 'id' => $appeal_id ],
			[ '%s', '%s', '%s' ],
			[ '%d' ]
		);
	}

	public function get_dashboard_summary(): array {
		global $wpdb;

		$table       = $wpdb->prefix . 'bloom_reader_guard_events';
		$appeals_table = $wpdb->prefix . 'bloom_reader_guard_appeals';
		$profiles    = $this->get_all_profiles();
		$user_profiles = $this->get_all_user_profiles();
		$networks    = $this->get_all_network_profiles();
		$active_bans = 0;
		$now         = time();
		foreach ( $profiles as $profile ) {
			if ( ! empty( $profile['manual_ban'] ) || ( ! empty( $profile['ban_until'] ) && (int) $profile['ban_until'] > $now ) ) {
				$active_bans++;
			}
		}
		foreach ( $networks as $network ) {
			if ( ! empty( $network['manual_ban'] ) ) {
				$active_bans++;
			}
		}
		foreach ( $user_profiles as $profile ) {
			if ( ! empty( $profile['manual_ban'] ) || ( ! empty( $profile['ban_until'] ) && (int) $profile['ban_until'] > $now ) ) {
				$active_bans++;
			}
		}

		return [
			'total_events'  => (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$table}" ), // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			'active_bans'   => $active_bans,
			'alerts_sent'   => (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$table} WHERE alert_sent = 1" ), // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			'honeypot_hits' => (int) $wpdb->get_var( "SELECT COALESCE(SUM(honeypot_hits),0) FROM {$table}" ), // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			'open_appeals'  => (int) $wpdb->get_var( "SELECT COUNT(*) FROM {$appeals_table} WHERE status = 'open'" ), // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
		];
	}

	private function evaluate_and_save( array $actor, array $state ): array {
		$state  = $this->prune_state( $state );
		$result = [
			'banned'        => false,
			'ban_until'     => 0,
			'offense_count' => (int) ( $state['offense_count'] ?? 0 ),
			'reason'        => '',
		];

		$threshold = $this->find_threshold_reason( $state );
		if ( $threshold ) {
			$result = $this->register_offense( $actor, $state, $threshold['reason'], $threshold['lock_seconds'] );
			$state  = $result['state'];
			unset( $result['state'] );
		}

		$this->save_state( $actor, $state );
		return $result;
	}

	private function register_offense( array $actor, array $state, string $reason, int $lock_seconds ): array {
		$now         = time();
		$reason_locks = (array) ( $state['reason_locks'] ?? [] );
		$until       = (int) ( $reason_locks[ $reason ] ?? 0 );
		if ( $until > $now ) {
			return [
				'banned'        => ! empty( $state['ban_until'] ) && (int) $state['ban_until'] > $now,
				'ban_until'     => (int) ( $state['ban_until'] ?? 0 ),
				'offense_count' => (int) ( $state['offense_count'] ?? 0 ),
				'reason'        => (string) ( $state['last_reason'] ?? $reason ),
				'state'         => $state,
			];
		}

		$state['offense_count']   = (int) ( $state['offense_count'] ?? 0 ) + 1;
		$state['last_offense_at'] = $now;
		$state['last_reason']     = $reason;
		$state['active_case_id']  = $this->generate_case_id( $actor, $reason );
		$state['last_case_id']    = $state['active_case_id'];
		$reason_locks[ $reason ]  = $now + $lock_seconds;
		$state['reason_locks']    = $reason_locks;

		$combined_offense = (int) $state['offense_count'];
		if ( $this->should_track_ua_profile( $actor ) ) {
			$ua_profile                  = $this->get_ua_profile( $actor['ua_hash'] );
			$ua_profile['offense_count'] = max( (int) $ua_profile['offense_count'], (int) $state['offense_count'] );
			$ua_profile['last_seen']     = $now;
			$ua_profile['last_reason']   = $reason;
			update_option( self::UA_PROFILE_PREFIX . substr( $actor['ua_hash'], 0, 16 ), $ua_profile, false );
			$combined_offense = max( $combined_offense, (int) $ua_profile['offense_count'] );
			$state['offense_count'] = max( (int) $state['offense_count'], $combined_offense );
		}

		$ban_seconds = $this->ban_seconds_for_offense( $combined_offense );
		if ( $ban_seconds > 0 ) {
			$state['ban_until'] = max( (int) ( $state['ban_until'] ?? 0 ), $now + $ban_seconds );
		}

		if ( (int) ( $actor['user_id'] ?? 0 ) > 0 ) {
			$this->sync_user_profile_from_state( $actor, $state );
		}

		$this->persist_event( $actor, $state, true );

		if ( (int) $state['offense_count'] >= 4 ) {
			$state['suspicious'] = 1;
			$this->maybe_send_alert( $actor, $state );
		}

			return [
				'banned'        => ! empty( $state['ban_until'] ) && (int) $state['ban_until'] > $now,
				'ban_until'     => (int) ( $state['ban_until'] ?? 0 ),
				'offense_count' => (int) $state['offense_count'],
				'reason'        => $reason,
				'case_id'       => (string) ( $state['active_case_id'] ?? '' ),
				'scope'         => ( (int) ( $actor['user_id'] ?? 0 ) > 0 ) ? 'user' : 'ip',
				'state'         => $state,
			];
	}

	private function find_threshold_reason( array $state ): ?array {
		$denied_window = $this->recent_events( (array) ( $state['denied_cookie'] ?? [] ), 240 );
		$denied_recent = $this->count_recent( (array) ( $state['denied_cookie'] ?? [] ), 60 );
		$denied_distinct = $this->distinct_chapter_count( $denied_window );
		$denied_switches = $this->rapid_transition_count( $denied_window, 25 );

		if ( count( $denied_window ) >= 12 && $denied_distinct >= 3 && $denied_switches >= 2 ) {
			return [
				'reason'       => 'multi_chapter_cookie_misses',
				'lock_seconds' => 900,
			];
		}

		if ( $denied_recent >= 8 ) {
			return [
				'reason'       => 'cookie_missing_or_expired',
				'lock_seconds' => 60,
			];
		}

		$direct_recent = $this->count_recent( (array) ( $state['direct_blocks'] ?? [] ), 600 );
		if ( $direct_recent >= 5 ) {
			return [
				'reason'       => 'direct_protected_path_probe',
				'lock_seconds' => 600,
			];
		}

		$honeypot_recent = $this->count_recent_kind( (array) ( $state['honeypot_hits'] ?? [] ), 3600, 'reinforced' );
		if ( $honeypot_recent >= 1 ) {
			return [
				'reason'       => 'honeypot_triggered',
				'lock_seconds' => 3600,
			];
		}

		$passive_recent = $this->count_recent_kind( (array) ( $state['passive_honeypot_hits'] ?? [] ), 86400, 'passive' );
		if ( $passive_recent >= 2 ) {
			return [
				'reason'       => 'passive_honeypot_repeated',
				'lock_seconds' => 1800,
			];
		}

		$metrics = $this->build_behavior_metrics( $state );

		if ( ! empty( $metrics['queue_like_pattern'] ) ) {
			return [
				'reason'       => 'queue_like_multi_chapter_flow',
				'lock_seconds' => 900,
			];
		}

		if ( ! empty( $metrics['html_image_ratio_alert'] ) ) {
			return [
				'reason'       => 'html_image_ratio_anomaly',
				'lock_seconds' => 600,
			];
		}

		if ( ! empty( $metrics['presence_image_ratio_alert'] ) ) {
			return [
				'reason'       => 'missing_presence_signal',
				'lock_seconds' => 600,
			];
		}

		if ( $metrics['distinct_image_chapters_short'] >= 4 && $metrics['rapid_image_switches'] >= 2 && $metrics['image_count_short'] >= 18 ) {
			return [
				'reason'       => 'chapter_hopping_pattern',
				'lock_seconds' => 600,
			];
		}

		if ( $metrics['image_count_long'] > 160 && $metrics['distinct_image_chapters_long'] >= 3 ) {
			return [
				'reason'       => 'excessive_multi_chapter_fetch',
				'lock_seconds' => 600,
			];
		}

		return null;
	}

	private function prune_state( array $state ): array {
		$now = time();

		$state['first_seen']     = (int) ( $state['first_seen'] ?? $now );
		$state['last_seen']      = (int) ( $state['last_seen'] ?? $now );
		$state['chapter_views']  = $this->recent_events( (array) ( $state['chapter_views'] ?? [] ), 600 );
		$state['presence_events'] = $this->recent_events( (array) ( $state['presence_events'] ?? [] ), 600 );
		$state['image_events']   = $this->recent_events( (array) ( $state['image_events'] ?? [] ), 600 );
		$state['denied_cookie']  = $this->recent_events( (array) ( $state['denied_cookie'] ?? [] ), 600 );
		$state['direct_blocks']  = $this->recent_events( (array) ( $state['direct_blocks'] ?? [] ), 600 );
		$state['honeypot_hits']  = $this->recent_events( (array) ( $state['honeypot_hits'] ?? [] ), 3600 );
		$state['passive_honeypot_hits'] = $this->recent_events( (array) ( $state['passive_honeypot_hits'] ?? [] ), 86400 );
		$state['reason_locks']   = array_filter(
			(array) ( $state['reason_locks'] ?? [] ),
			static fn ( $ts ) => (int) $ts > $now
		);

		if ( ! empty( $state['ban_until'] ) && (int) $state['ban_until'] <= $now ) {
			$state['ban_until'] = 0;
		}

		return $state;
	}

	private function ban_seconds_for_offense( int $offense_count ): int {
		return match ( $offense_count ) {
			1       => 0,
			2       => 300,
			3       => 1800,
			4       => 21600,
			default => 86400,
		};
	}

	private function persist_event( array $actor, array $state, bool $allow_duplicate_reason = false ): void {
		global $wpdb;

		$table = $wpdb->prefix . 'bloom_reader_guard_events';
		$metrics = $this->build_behavior_metrics( $state );
		if ( ! $allow_duplicate_reason ) {
			$existing = (int) $wpdb->get_var(
				$wpdb->prepare(
					"SELECT COUNT(*) FROM {$table} WHERE ip = %s AND ua_hash = %s AND reason = %s AND created_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 MINUTE)",
					$actor['ip'],
					$actor['ua_hash'],
					(string) ( $state['last_reason'] ?? '' )
				)
			); // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			if ( $existing > 0 ) {
				return;
			}
		}

		$data  = [
			'created_at'           => current_time( 'mysql', true ),
			'ip'                   => $actor['ip'],
			'network_hint'         => (string) ( $actor['network_hint'] ?? '' ),
			'ua_hash'              => $actor['ua_hash'],
			'ua_summary'           => $actor['ua_summary'],
			'user_id'              => (int) ( $actor['user_id'] ?? 0 ),
			'user_login'           => (string) ( $actor['user_login'] ?? '' ),
			'user_email'           => (string) ( $actor['user_email'] ?? '' ),
			'offense_count'        => (int) ( $state['offense_count'] ?? 0 ),
			'ban_until'            => ! empty( $state['ban_until'] ) ? gmdate( 'Y-m-d H:i:s', (int) $state['ban_until'] ) : null,
			'reason'               => (string) ( $state['last_reason'] ?? '' ),
			'case_id'              => (string) ( $state['active_case_id'] ?? '' ),
			'cookie_denied_hits'   => $this->count_recent( (array) ( $state['denied_cookie'] ?? [] ), 600 ),
			'direct_blocked_hits'  => $this->count_recent( (array) ( $state['direct_blocks'] ?? [] ), 600 ),
			'honeypot_hits'        => $this->count_recent( (array) ( $state['honeypot_hits'] ?? [] ), 3600 ) + $this->count_recent( (array) ( $state['passive_honeypot_hits'] ?? [] ), 86400 ),
			'distinct_chapters'    => max( (int) $metrics['distinct_image_chapters_long'], (int) $metrics['distinct_denied_chapters'] ),
			'sample_chapters'      => wp_json_encode( $this->sample_chapters( $state ) ),
			'suspicious'           => ! empty( $state['suspicious'] ) ? 1 : 0,
			'alert_sent'           => 0,
		];

		$wpdb->insert( $table, $data ); // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
	}

	private function maybe_send_alert( array $actor, array &$state ): void {
		$last_alerted = (int) ( $state['last_alerted_count'] ?? 0 );
		$current      = (int) ( $state['offense_count'] ?? 0 );
		if ( $current < 4 || $current <= $last_alerted ) {
			return;
		}

		$subject = '[BloomScans Guard] IP bloqueada temporalmente por scraping';
		$body    = [];
		$body[]  = 'IP: ' . $actor['ip'];
		$body[]  = 'Caso: ' . (string) ( $state['active_case_id'] ?? '' );
		$body[]  = 'UA: ' . $actor['ua_summary'];
		$body[]  = 'UA hash: ' . $actor['ua_hash'];
		if ( ! empty( $actor['user_id'] ) ) {
			$body[] = 'Usuario: #' . (int) $actor['user_id'] . ' @' . (string) ( $actor['user_login'] ?? '' ) . ' <' . (string) ( $actor['user_email'] ?? '' ) . '>';
		}
		$body[]  = 'Ofensas acumuladas: ' . $current;
		$body[]  = 'Motivo: ' . (string) ( $state['last_reason'] ?? 'unknown' );
		$body[]  = 'Bloqueado hasta: ' . ( ! empty( $state['ban_until'] ) ? wp_date( 'Y-m-d H:i:s', (int) $state['ban_until'] ) : 'sin bloqueo' );
		$body[]  = 'Hits por cookie invalida: ' . $this->count_recent( (array) ( $state['denied_cookie'] ?? [] ), 600 );
		$body[]  = 'Accesos directos bloqueados: ' . $this->count_recent( (array) ( $state['direct_blocks'] ?? [] ), 600 );
		$body[]  = 'Hits al cebo: ' . ( $this->count_recent( (array) ( $state['honeypot_hits'] ?? [] ), 3600 ) + $this->count_recent( (array) ( $state['passive_honeypot_hits'] ?? [] ), 86400 ) );
		$metrics = $this->build_behavior_metrics( $state );
		$body[]  = 'Vistas HTML recientes: ' . (int) $metrics['chapter_view_count_short'];
		$body[]  = 'Imagenes recientes: ' . (int) $metrics['image_count_short'];
		$body[]  = 'Ratio HTML->imagenes: ' . (string) $metrics['image_to_view_ratio'];
		$body[]  = 'Saltos rapidos de capitulo: ' . (int) $metrics['rapid_image_switches'];
		$body[]  = 'Capitulos de muestra: ' . implode( ', ', $this->sample_chapters( $state ) );
		$body[]  = 'Primera vez visto: ' . wp_date( 'Y-m-d H:i:s', (int) ( $state['first_seen'] ?? time() ) );
		$body[]  = 'Ultima actividad: ' . wp_date( 'Y-m-d H:i:s', (int) ( $state['last_seen'] ?? time() ) );

		wp_mail( get_option( 'admin_email' ), $subject, implode( "\n", $body ) );
		$state['last_alerted_count'] = $current;

		global $wpdb;
		$table = $wpdb->prefix . 'bloom_reader_guard_events';
		$wpdb->update( // phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery,WordPress.DB.DirectDatabaseQuery.NoCaching
			$table,
			[ 'alert_sent' => 1 ],
			[
				'ip'            => $actor['ip'],
				'ua_hash'       => $actor['ua_hash'],
				'offense_count' => $current,
			],
			[ '%d' ],
			[ '%s', '%s', '%d' ]
		);
	}

	private function maybe_create_table(): void {
		global $wpdb;

		require_once ABSPATH . 'wp-admin/includes/upgrade.php';

		$table   = $wpdb->prefix . 'bloom_reader_guard_events';
		$charset = $wpdb->get_charset_collate();
		$sql     = "CREATE TABLE {$table} (
			id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
			created_at datetime NOT NULL,
			ip varchar(64) NOT NULL,
			network_hint varchar(64) NOT NULL,
			ua_hash char(64) NOT NULL,
			ua_summary varchar(255) NOT NULL,
			user_id bigint(20) unsigned NOT NULL DEFAULT 0,
			user_login varchar(191) NOT NULL,
			user_email varchar(191) NOT NULL,
			offense_count smallint unsigned NOT NULL DEFAULT 0,
			ban_until datetime NULL,
			reason varchar(80) NOT NULL,
			case_id varchar(32) NOT NULL,
			cookie_denied_hits int unsigned NOT NULL DEFAULT 0,
			direct_blocked_hits int unsigned NOT NULL DEFAULT 0,
			honeypot_hits int unsigned NOT NULL DEFAULT 0,
			distinct_chapters int unsigned NOT NULL DEFAULT 0,
			sample_chapters longtext NULL,
			suspicious tinyint(1) NOT NULL DEFAULT 0,
			alert_sent tinyint(1) NOT NULL DEFAULT 0,
			PRIMARY KEY  (id),
			KEY ip (ip),
			KEY case_id (case_id),
			KEY user_id (user_id),
			KEY created_at (created_at),
			KEY suspicious (suspicious)
		) {$charset};";

		dbDelta( $sql );

		$appeals_table = $wpdb->prefix . 'bloom_reader_guard_appeals';
		$appeals_sql   = "CREATE TABLE {$appeals_table} (
			id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
			created_at datetime NOT NULL,
			updated_at datetime NOT NULL,
			case_id varchar(32) NOT NULL,
			status varchar(20) NOT NULL DEFAULT 'open',
			ip varchar(64) NOT NULL,
			network_hint varchar(64) NOT NULL,
			user_id bigint(20) unsigned NOT NULL DEFAULT 0,
			user_login varchar(191) NOT NULL,
			user_email varchar(191) NOT NULL,
			contact varchar(191) NOT NULL,
			reason varchar(80) NOT NULL,
			appeal_text longtext NOT NULL,
			admin_note longtext NULL,
			PRIMARY KEY  (id),
			KEY case_id (case_id),
			KEY status (status),
			KEY ip (ip),
			KEY user_id (user_id),
			KEY created_at (created_at)
		) {$charset};";

		dbDelta( $appeals_sql );
	}

	private function get_state( array $actor ): array {
		$state = get_transient( self::STATE_PREFIX . $actor['state_key'] );
		if ( ! is_array( $state ) ) {
			$now   = time();
			$state = [
				'chapter_views'    => [],
				'presence_events'  => [],
				'image_events'     => [],
				'denied_cookie'    => [],
				'direct_blocks'    => [],
				'honeypot_hits'    => [],
				'passive_honeypot_hits' => [],
				'reason_locks'     => [],
				'active_case_id'   => '',
				'last_case_id'     => '',
			];
		}

		$profile = $this->get_ip_profile( $actor['ip'] );
		foreach ( [ 'first_seen', 'last_seen', 'offense_count', 'ban_until', 'last_reason', 'last_offense_at', 'last_alerted_count', 'suspicious', 'manual_ban', 'manual_ban_set_at', 'active_case_id', 'last_case_id' ] as $key ) {
			$state[ $key ] = $profile[ $key ] ?? ( $state[ $key ] ?? 0 );
		}
		$state['active_case_id'] = (string) ( $state['active_case_id'] ?? '' );
		$state['last_case_id']   = (string) ( $state['last_case_id'] ?? '' );

		return $state;
	}

	private function save_state( array $actor, array $state ): void {
		$this->save_hot_state( $actor, $state );

		$profile = $this->get_ip_profile( $actor['ip'] );
		foreach ( [ 'first_seen', 'last_seen', 'offense_count', 'ban_until', 'last_reason', 'last_offense_at', 'last_alerted_count', 'suspicious', 'manual_ban', 'manual_ban_set_at', 'active_case_id', 'last_case_id' ] as $key ) {
			$profile[ $key ] = $state[ $key ] ?? $profile[ $key ] ?? 0;
		}
		update_option( self::PROFILE_PREFIX . $actor['ip_hash'], $profile, false );

		if ( (int) ( $actor['user_id'] ?? 0 ) > 0 ) {
			$this->sync_user_profile_from_state( $actor, $state );
		}

		if ( ! empty( $actor['network_hint'] ) && $this->is_valid_network_hint( (string) $actor['network_hint'] ) ) {
			$network = $this->get_network_profile( (string) $actor['network_hint'] );
			$network['last_seen'] = (int) ( $state['last_seen'] ?? time() );
			$network['offense_count'] = max( (int) ( $network['offense_count'] ?? 0 ), (int) ( $state['offense_count'] ?? 0 ) );
			if ( ! empty( $state['active_case_id'] ) ) {
				$network['active_case_id'] = (string) $state['active_case_id'];
			}
			update_option( self::NETWORK_PROFILE_PREFIX . hash( 'sha256', strtolower( (string) $actor['network_hint'] ) ), $network, false );
		}
	}

	private function save_hot_state( array $actor, array $state ): void {
		$hot_state = [
			'chapter_views'         => (array) ( $state['chapter_views'] ?? [] ),
			'presence_events'       => (array) ( $state['presence_events'] ?? [] ),
			'image_events'          => (array) ( $state['image_events'] ?? [] ),
			'denied_cookie'         => (array) ( $state['denied_cookie'] ?? [] ),
			'direct_blocks'         => (array) ( $state['direct_blocks'] ?? [] ),
			'honeypot_hits'         => (array) ( $state['honeypot_hits'] ?? [] ),
			'passive_honeypot_hits' => (array) ( $state['passive_honeypot_hits'] ?? [] ),
			'reason_locks'          => (array) ( $state['reason_locks'] ?? [] ),
			'first_seen'            => (int) ( $state['first_seen'] ?? time() ),
			'last_seen'             => (int) ( $state['last_seen'] ?? time() ),
			'offense_count'         => (int) ( $state['offense_count'] ?? 0 ),
			'ban_until'             => (int) ( $state['ban_until'] ?? 0 ),
			'last_reason'           => (string) ( $state['last_reason'] ?? '' ),
			'last_offense_at'       => (int) ( $state['last_offense_at'] ?? 0 ),
			'last_alerted_count'    => (int) ( $state['last_alerted_count'] ?? 0 ),
			'suspicious'            => ! empty( $state['suspicious'] ) ? 1 : 0,
			'manual_ban'            => ! empty( $state['manual_ban'] ) ? 1 : 0,
			'manual_ban_set_at'     => (int) ( $state['manual_ban_set_at'] ?? 0 ),
			'active_case_id'        => (string) ( $state['active_case_id'] ?? '' ),
			'last_case_id'          => (string) ( $state['last_case_id'] ?? '' ),
		];

		set_transient( self::STATE_PREFIX . $actor['state_key'], $hot_state, self::STATE_TTL );
	}

	private function sync_user_profile_from_state( array $actor, array $state ): void {
		$user_id = (int) ( $actor['user_id'] ?? 0 );
		if ( $user_id <= 0 ) {
			return;
		}

		$profile = $this->get_user_profile( $user_id );
		$profile['user_login']       = (string) ( $actor['user_login'] ?? $profile['user_login'] ?? '' );
		$profile['user_email']       = (string) ( $actor['user_email'] ?? $profile['user_email'] ?? '' );
		$profile['last_seen']        = max( (int) ( $profile['last_seen'] ?? 0 ), (int) ( $state['last_seen'] ?? time() ) );
		$profile['first_seen']       = empty( $profile['first_seen'] ) ? (int) ( $state['first_seen'] ?? time() ) : (int) $profile['first_seen'];
		$profile['offense_count']    = max( (int) ( $profile['offense_count'] ?? 0 ), (int) ( $state['offense_count'] ?? 0 ) );
		$profile['ban_until']        = max( (int) ( $profile['ban_until'] ?? 0 ), (int) ( $state['ban_until'] ?? 0 ) );
		$profile['last_reason']      = (string) ( $state['last_reason'] ?? $profile['last_reason'] ?? '' );
		$profile['last_offense_at']  = max( (int) ( $profile['last_offense_at'] ?? 0 ), (int) ( $state['last_offense_at'] ?? 0 ) );
		$profile['last_alerted_count'] = max( (int) ( $profile['last_alerted_count'] ?? 0 ), (int) ( $state['last_alerted_count'] ?? 0 ) );
		$profile['suspicious']       = ! empty( $state['suspicious'] ) ? 1 : (int) ( $profile['suspicious'] ?? 0 );
		if ( ! empty( $state['active_case_id'] ) ) {
			$profile['active_case_id'] = (string) $state['active_case_id'];
			$profile['last_case_id']   = (string) $state['active_case_id'];
		}
		update_option( self::USER_PROFILE_PREFIX . $user_id, $profile, false );
	}

	private function generate_case_id( array $actor, string $reason ): string {
		$seed = implode(
			'|',
			[
				(string) ( $actor['ip'] ?? '0.0.0.0' ),
				(string) ( $actor['user_id'] ?? 0 ),
				$reason,
				microtime( true ),
				wp_generate_password( 6, false, false ),
			]
		);

		return 'BRG-' . strtoupper( substr( hash( 'sha256', $seed ), 0, 10 ) );
	}

	private function append_event( array $events, array $event, int $max ): array {
		$events[] = $event;
		if ( count( $events ) > $max ) {
			$events = array_slice( $events, -1 * $max );
		}

		return $events;
	}

	private function count_recent( array $events, int $window_seconds ): int {
		return count( $this->recent_events( $events, $window_seconds ) );
	}

	private function count_recent_kind( array $events, int $window_seconds, string $kind ): int {
		return count(
			array_filter(
				$this->recent_events( $events, $window_seconds ),
				static fn ( array $event ): bool => (string) ( $event['k'] ?? '' ) === $kind
			)
		);
	}

	private function recent_events( array $events, int $window_seconds ): array {
		$cutoff = time() - $window_seconds;
		return array_values(
			array_filter(
				$events,
				static fn ( $event ) => isset( $event['t'] ) && (int) $event['t'] >= $cutoff
			)
		);
	}

	private function distinct_chapter_count( array $events ): int {
		$chapters = [];
		foreach ( $events as $event ) {
			if ( empty( $event['c'] ) ) {
				continue;
			}
			$chapters[ (string) $event['c'] ] = true;
		}

		return count( $chapters );
	}

	private function rapid_transition_count( array $events, int $within_seconds ): int {
		if ( count( $events ) < 2 ) {
			return 0;
		}

		usort(
			$events,
			static fn ( array $a, array $b ): int => (int) ( $a['t'] ?? 0 ) <=> (int) ( $b['t'] ?? 0 )
		);

		$count = 0;
		$prev  = null;
		foreach ( $events as $event ) {
			if ( null === $prev ) {
				$prev = $event;
				continue;
			}

			$prev_chapter = (int) ( $prev['c'] ?? 0 );
			$chapter      = (int) ( $event['c'] ?? 0 );
			$delta        = abs( (int) ( $event['t'] ?? 0 ) - (int) ( $prev['t'] ?? 0 ) );

			if ( $chapter && $prev_chapter && $chapter !== $prev_chapter && $delta <= $within_seconds ) {
				$count++;
			}

			$prev = $event;
		}

		return $count;
	}

	private function build_behavior_metrics( array $state ): array {
		$views_short    = $this->recent_events( (array) ( $state['chapter_views'] ?? [] ), 240 );
		$views_long     = $this->recent_events( (array) ( $state['chapter_views'] ?? [] ), 600 );
		$presence_short = $this->recent_events( (array) ( $state['presence_events'] ?? [] ), 240 );
		$presence_long  = $this->recent_events( (array) ( $state['presence_events'] ?? [] ), 600 );
		$images_short   = $this->recent_events( (array) ( $state['image_events'] ?? [] ), 240 );
		$images_long    = $this->recent_events( (array) ( $state['image_events'] ?? [] ), 600 );
		$denied_short   = $this->recent_events( (array) ( $state['denied_cookie'] ?? [] ), 240 );
		$view_count     = count( $views_short );
		$presence_count = count( $presence_short );
		$image_count    = count( $images_short );
		$view_ratio     = $view_count > 0 ? round( $image_count / $view_count, 2 ) : ( $image_count > 0 ? 999.0 : 0.0 );
		$presence_ratio = $presence_count > 0 ? round( $image_count / $presence_count, 2 ) : ( $image_count > 0 ? 999.0 : 0.0 );
		$distinct_img  = $this->distinct_chapter_count( $images_short );
		$distinct_view = $this->distinct_chapter_count( $views_short );
		$rapid_img     = $this->rapid_transition_count( $images_short, 25 );

		$multi_cookie_pattern = count( $denied_short ) >= 12
			&& $this->distinct_chapter_count( $denied_short ) >= 3
			&& $this->rapid_transition_count( $denied_short, 25 ) >= 2;

		$html_ratio_alert = $image_count >= 42
			&& $distinct_img >= 3
			&& ( $view_count <= 1 || $view_ratio >= 22 );

		$presence_ratio_alert = $image_count >= 30
			&& $distinct_img >= 3
			&& ( $presence_count <= 0 || $presence_ratio >= 22 );

		$queue_like_pattern = $image_count >= 30
			&& $distinct_img >= 3
			&& $rapid_img >= 2
			&& ( $view_count <= 1 || $view_ratio >= 18 || $distinct_img >= 4 );

		return [
			'chapter_view_count_short'      => $view_count,
			'chapter_view_count_long'       => count( $views_long ),
			'presence_count_short'          => $presence_count,
			'presence_count_long'           => count( $presence_long ),
			'image_count_short'             => $image_count,
			'image_count_long'              => count( $images_long ),
			'denied_count_short'            => count( $denied_short ),
			'distinct_image_chapters_short' => $distinct_img,
			'distinct_image_chapters_long'  => $this->distinct_chapter_count( $images_long ),
			'distinct_view_chapters_short'  => $distinct_view,
			'distinct_denied_chapters'      => $this->distinct_chapter_count( $denied_short ),
			'rapid_image_switches'          => $rapid_img,
			'rapid_denied_switches'         => $this->rapid_transition_count( $denied_short, 25 ),
			'image_to_view_ratio'           => $view_ratio,
			'image_to_presence_ratio'       => $presence_ratio,
			'multi_chapter_cookie_pattern'  => $multi_cookie_pattern,
			'html_image_ratio_alert'        => $html_ratio_alert,
			'presence_image_ratio_alert'    => $presence_ratio_alert,
			'queue_like_pattern'            => $queue_like_pattern,
		];
	}

	private function should_evaluate_image_state( array $state ): bool {
		if ( ! empty( $state['manual_ban'] ) || ! empty( $state['suspicious'] ) ) {
			return true;
		}

		if ( (int) ( $state['offense_count'] ?? 0 ) > 0 || ! empty( $state['reason_locks'] ) ) {
			return true;
		}

		if ( ! empty( $state['denied_cookie'] ) || ! empty( $state['direct_blocks'] ) || ! empty( $state['honeypot_hits'] ) || ! empty( $state['passive_honeypot_hits'] ) ) {
			return true;
		}

		$metrics = $this->build_behavior_metrics( $state );
		if ( ! empty( $metrics['queue_like_pattern'] ) || ! empty( $metrics['html_image_ratio_alert'] ) || ! empty( $metrics['presence_image_ratio_alert'] ) || ! empty( $metrics['multi_chapter_cookie_pattern'] ) ) {
			return true;
		}

		if ( (int) $metrics['distinct_image_chapters_short'] >= 2 || (int) $metrics['distinct_image_chapters_long'] >= 2 ) {
			return true;
		}

		if ( (int) $metrics['rapid_image_switches'] >= 1 || (int) $metrics['rapid_denied_switches'] >= 1 ) {
			return true;
		}

		return false;
	}

	private function sample_chapters( array $state ): array {
		$sample   = [];
		$combined = array_merge( (array) ( $state['chapter_views'] ?? [] ), (array) ( $state['presence_events'] ?? [] ), (array) ( $state['image_events'] ?? [] ), (array) ( $state['denied_cookie'] ?? [] ), (array) ( $state['direct_blocks'] ?? [] ), (array) ( $state['honeypot_hits'] ?? [] ), (array) ( $state['passive_honeypot_hits'] ?? [] ) );
		usort(
			$combined,
			static fn ( $a, $b ) => (int) ( $b['t'] ?? 0 ) <=> (int) ( $a['t'] ?? 0 )
		);

		foreach ( $combined as $event ) {
			$chapter_id = (int) ( $event['c'] ?? 0 );
			if ( ! $chapter_id || isset( $sample[ $chapter_id ] ) ) {
				continue;
			}

			$title               = get_the_title( $chapter_id );
			$sample[ $chapter_id ] = $title ? sprintf( '#%d %s', $chapter_id, $title ) : '#' . $chapter_id;
			if ( count( $sample ) >= 5 ) {
				break;
			}
		}

		return array_values( $sample );
	}

	private function summarize_ua( string $user_agent ): string {
		$user_agent = trim( $user_agent );
		if ( '' === $user_agent ) {
			return 'unknown';
		}

		return substr( preg_replace( '/\s+/', ' ', $user_agent ), 0, 180 );
	}

	private function should_track_ua_profile( array $actor ): bool {
		$user_agent = strtolower( (string) ( $actor['user_agent'] ?? '' ) );
		if ( '' === $user_agent || 'unknown' === $user_agent ) {
			return false;
		}

		if ( false === strpos( $user_agent, 'mozilla/5.0' ) ) {
			return true;
		}

		$browser_markers = [ 'chrome/', 'firefox/', 'safari/', 'edg/', 'opr/', 'brave', 'vivaldi' ];
		foreach ( $browser_markers as $marker ) {
			if ( false !== strpos( $user_agent, $marker ) ) {
				return false;
			}
		}

		return true;
	}

	public function network_hint( string $ip ): string {
		if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 ) ) {
			$parts = explode( '.', $ip );
			return sprintf( '%s.%s.%s.0/24', $parts[0] ?? '0', $parts[1] ?? '0', $parts[2] ?? '0' );
		}

		if ( filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6 ) ) {
			$packed = @inet_pton( $ip );
			if ( false !== $packed ) {
				$parts = array_values( unpack( 'n8', $packed ) );
				return sprintf( '%x:%x:%x:%x::/64', $parts[0] ?? 0, $parts[1] ?? 0, $parts[2] ?? 0, $parts[3] ?? 0 );
			}
		}

		return 'red desconocida';
	}

	private function client_ip(): string {
		$candidates = [
			'HTTP_CF_CONNECTING_IP',
			'HTTP_X_FORWARDED_FOR',
			'HTTP_CLIENT_IP',
			'REMOTE_ADDR',
		];

		foreach ( $candidates as $key ) {
			if ( empty( $_SERVER[ $key ] ) ) {
				continue;
			}

			$value = (string) $_SERVER[ $key ];
			if ( 'HTTP_X_FORWARDED_FOR' === $key ) {
				$parts = explode( ',', $value );
				$value = trim( (string) reset( $parts ) );
			}

			if ( filter_var( $value, FILTER_VALIDATE_IP ) ) {
				return $value;
			}
		}

		return '0.0.0.0';
	}
}
