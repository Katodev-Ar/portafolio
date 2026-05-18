<?php
/**
 * Plugin Name: Bloom Reader Anchored Comments
 * Description: Comentarios anclados en el reader de BloomScans usando wp_comments como fuente de verdad.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function bloom_reader_anchor_is_chapter( $post_id = 0 ): bool {
	if ( function_exists( 'lunatoons_is_chapter' ) && ! $post_id ) {
		return (bool) lunatoons_is_chapter();
	}

	$post_id = $post_id ? (int) $post_id : (int) get_queried_object_id();
	if ( ! $post_id || 'post' !== get_post_type( $post_id ) ) {
		return false;
	}

	return (bool) get_post_meta( $post_id, 'ero_seri', true );
}

function bloom_reader_anchor_post_is_public_chapter( int $post_id ): bool {
	$post = get_post( $post_id );
	if ( ! $post || 'publish' !== $post->post_status ) {
		return false;
	}

	return bloom_reader_anchor_is_chapter( $post_id );
}

function bloom_reader_anchor_asset_path( string $file ): string {
	return WPMU_PLUGIN_DIR . '/bloom-reader-anchored-comments/assets/' . ltrim( $file, '/' );
}

function bloom_reader_anchor_asset_url( string $file ): string {
	return content_url( 'mu-plugins/bloom-reader-anchored-comments/assets/' . ltrim( $file, '/' ) );
}

function bloom_reader_anchor_render_comment_markup( string $text ): string {
	$text = trim( $text );
	if ( '' === $text ) {
		return '';
	}

	$text = preg_replace( '/\[(img|gif)\]\s*file:\/\/\/.*?(?:\[\/\1\]|$)/is', '', $text );
	$text = preg_replace( '/\[(img|gif)\]\s*(?!https?:\/\/).*?(?:\[\/\1\]|$)/is', '', $text );
	$text = preg_replace( '/file:\/\/\/\S+/i', '', $text );
	$text = trim( (string) $text );
	if ( '' === $text ) {
		return '';
	}

	$parts = preg_split(
		'/(\[(?:img|gif)\]\s*https?:\/\/.+?\[\/(?:img|gif)\])/is',
		$text,
		-1,
		PREG_SPLIT_DELIM_CAPTURE | PREG_SPLIT_NO_EMPTY
	);

	if ( ! is_array( $parts ) ) {
		$parts = [ $text ];
	}

	$html = '';
	foreach ( $parts as $part ) {
		if ( preg_match( '/^\[(img|gif)\]\s*(https?:\/\/.+?)\s*\[\/\1\]$/is', $part, $matches ) ) {
			$url = wp_http_validate_url( trim( $matches[2] ) );
			if ( $url ) {
				$kind        = strtolower( $matches[1] );
				$target_id   = function_exists( 'wp_unique_id' ) ? wp_unique_id( 'lrs-anchor-media-' ) : uniqid( 'lrs-anchor-media-', false );
				$view_label  = ( 'gif' === $kind ) ? 'Ver GIF' : 'Ver imagen';
				$close_label = ( 'gif' === $kind ) ? 'Ocultar GIF' : 'Ocultar imagen';
				$fallback    = ( 'gif' === $kind ) ? 'Abrir GIF' : 'Abrir imagen';
				$html       .= sprintf(
					'<div class="lrs-anchor-media-block lrs-anchor-media-block-%1$s"><button type="button" class="lrs-anchor-media-toggle" data-target="%2$s" data-open-label="%3$s" data-close-label="%4$s">%3$s</button><div id="%2$s" class="lrs-anchor-media-view lrs-anchor-media-view-%1$s" data-kind="%1$s" hidden><img class="lrs-anchor-media-image lrs-anchor-media-image-%1$s" data-src="%5$s" alt="" loading="lazy" decoding="async"><a class="lrs-anchor-media-fallback" href="%5$s" target="_blank" rel="nofollow ugc noopener" hidden>%6$s</a></div></div>',
					esc_attr( $kind ),
					esc_attr( $target_id ),
					esc_attr( $view_label ),
					esc_attr( $close_label ),
					esc_url( $url ),
					esc_html( $fallback )
				);
			}
			continue;
		}

		$safe = esc_html( $part );
		$safe = preg_replace( '/\[b\](.*?)\[\/b\]/is', '<strong>$1</strong>', $safe );
		$safe = preg_replace( '/\[i\](.*?)\[\/i\]/is', '<em>$1</em>', $safe );
		$safe = preg_replace( '/\[spoiler\](.*?)\[\/spoiler\]/is', '<span class="lrs-anchor-spoiler">$1</span>', $safe );
		$safe = preg_replace_callback(
			'/\[url=(https?:\/\/[^\]\s]+)\](.*?)\[\/url\]/is',
			static function ( array $matches ): string {
				$url   = esc_url( html_entity_decode( $matches[1], ENT_QUOTES | ENT_HTML5, 'UTF-8' ) );
				$label = $matches[2];
				if ( ! $url ) {
					return $label;
				}

				return sprintf(
					'<a href="%1$s" target="_blank" rel="nofollow ugc noopener">%2$s</a>',
					$url,
					$label
				);
			},
			$safe
		);
		$safe = make_clickable( nl2br( $safe ) );
		$html .= '<div class="lrs-anchor-copy">' . $safe . '</div>';
	}

	return $html;
}

function bloom_reader_anchor_comment_html( WP_Comment $comment ): string {
	return bloom_reader_anchor_render_comment_markup( (string) $comment->comment_content );
}

function bloom_reader_anchor_human_time( WP_Comment $comment ): string {
	$comment_ts = strtotime( (string) $comment->comment_date_gmt . ' GMT' );
	if ( ! $comment_ts ) {
		$comment_ts = (int) current_time( 'timestamp', true );
	}

	$time = human_time_diff(
		$comment_ts,
		(int) current_time( 'timestamp', true )
	);

	return sprintf( '%s ago', $time );
}

function bloom_reader_anchor_like_user_ids( int $comment_id ): array {
	return array_values(
		array_unique(
			array_map(
				'intval',
				(array) get_comment_meta( $comment_id, 'lrs_anchor_like_user', false )
			)
		)
	);
}

function bloom_reader_anchor_comment_payload( WP_Comment $comment ): array {
	$current_user_id = (int) get_current_user_id();
	$reporters       = array_map( 'intval', (array) get_comment_meta( $comment->comment_ID, 'lrs_anchor_report_user', false ) );
	$likes           = bloom_reader_anchor_like_user_ids( (int) $comment->comment_ID );

	return [
		'id'            => (int) $comment->comment_ID,
		'parent_id'     => (int) $comment->comment_parent,
		'author'        => get_comment_author( $comment ),
		'author_user_id'=> (int) $comment->user_id,
		'avatar'        => get_avatar_url( $comment, [ 'size' => 40 ] ),
		'content'       => bloom_reader_anchor_comment_html( $comment ),
		'content_raw'   => (string) $comment->comment_content,
		'time'          => bloom_reader_anchor_human_time( $comment ),
		'date'          => get_comment_date( '', $comment ),
		'report_count'  => count( $reporters ),
		'reported'      => $current_user_id ? in_array( $current_user_id, $reporters, true ) : false,
		'like_count'    => count( $likes ),
		'liked'         => $current_user_id ? in_array( $current_user_id, $likes, true ) : false,
	];
}

function bloom_reader_anchor_get_grouped_comments( int $post_id ): array {
	$comments = get_comments(
		[
			'post_id'    => $post_id,
			'status'     => 'approve',
			'orderby'    => 'comment_date_gmt',
			'order'      => 'ASC',
			'number'     => 0,
			'meta_query' => [
				[
					'key'   => 'lrs_anchor_type',
					'value' => 'anchored',
				],
			],
		]
	);

	$groups = [];

	foreach ( $comments as $comment ) {
		$group_id = (string) get_comment_meta( $comment->comment_ID, 'lrs_anchor_group', true );
		if ( '' === $group_id ) {
			$group_id = (string) ( $comment->comment_parent ?: $comment->comment_ID );
		}

		$image_index = (int) get_comment_meta( $comment->comment_ID, 'lrs_anchor_image_index', true );
		$x_pct       = (float) get_comment_meta( $comment->comment_ID, 'lrs_anchor_x_pct', true );
		$y_pct       = (float) get_comment_meta( $comment->comment_ID, 'lrs_anchor_y_pct', true );
		$image_key   = (string) get_comment_meta( $comment->comment_ID, 'lrs_anchor_image_key', true );

		if ( ! isset( $groups[ $group_id ] ) ) {
			$groups[ $group_id ] = [
				'group'           => $group_id,
				'root_comment_id' => (int) $comment->comment_ID,
				'image_index'     => $image_index,
				'x_pct'           => $x_pct,
				'y_pct'           => $y_pct,
				'image_key'       => $image_key,
				'count'           => 0,
				'comments'        => [],
			];
		}

		if ( 0 === (int) $comment->comment_parent ) {
			$groups[ $group_id ]['root_comment_id'] = (int) $comment->comment_ID;
			$groups[ $group_id ]['image_index']     = $image_index;
			$groups[ $group_id ]['x_pct']           = $x_pct;
			$groups[ $group_id ]['y_pct']           = $y_pct;
			$groups[ $group_id ]['image_key']       = $image_key;
		}

		$groups[ $group_id ]['count']++;
		$groups[ $group_id ]['comments'][] = bloom_reader_anchor_comment_payload( $comment );
	}

	$groups = array_values( $groups );

	usort(
		$groups,
		static function ( array $a, array $b ): int {
			$cmp = (int) $a['image_index'] <=> (int) $b['image_index'];
			if ( 0 !== $cmp ) {
				return $cmp;
			}

			return (float) $a['y_pct'] <=> (float) $b['y_pct'];
		}
	);

	$total_comments = 0;
	foreach ( $groups as $group ) {
		$total_comments += (int) $group['count'];
	}

	return [
		'groups'          => $groups,
		'total_groups'    => count( $groups ),
		'total_comments'  => $total_comments,
	];
}

function bloom_reader_anchor_find_group_root( int $post_id, string $group_id ): ?WP_Comment {
	$comments = get_comments(
		[
			'post_id'    => $post_id,
			'status'     => 'all',
			'orderby'    => 'comment_date_gmt',
			'order'      => 'ASC',
			'number'     => 0,
			'meta_query' => [
				[
					'key'   => 'lrs_anchor_group',
					'value' => $group_id,
				],
			],
		]
	);

	if ( empty( $comments ) ) {
		return null;
	}

	foreach ( $comments as $comment ) {
		if ( 0 === (int) $comment->comment_parent ) {
			return $comment;
		}
	}

	return $comments[0];
}

function bloom_reader_anchor_save_meta( int $comment_id, array $meta ): void {
	foreach ( $meta as $key => $value ) {
		update_comment_meta( $comment_id, $key, $value );
	}
}

add_action( 'wp_ajax_bloom_reader_anchor_fetch', 'bloom_reader_anchor_fetch_ajax' );
add_action( 'wp_ajax_nopriv_bloom_reader_anchor_fetch', 'bloom_reader_anchor_fetch_ajax' );

function bloom_reader_anchor_fetch_ajax(): void {
	$post_id = isset( $_POST['post_id'] ) ? (int) $_POST['post_id'] : 0;
	if ( ! $post_id || ! bloom_reader_anchor_post_is_public_chapter( $post_id ) ) {
		wp_send_json_error( [ 'message' => 'Chapter not found.' ], 404 );
	}

	$data               = bloom_reader_anchor_get_grouped_comments( $post_id );
	$data['save_nonce'] = wp_create_nonce( 'bloom_reader_anchor_comments' );

	wp_send_json_success( $data );
}

add_action( 'wp_ajax_bloom_reader_anchor_save', 'bloom_reader_anchor_save_ajax' );
add_action( 'wp_ajax_nopriv_bloom_reader_anchor_save', 'bloom_reader_anchor_save_ajax' );

function bloom_reader_anchor_save_ajax(): void {
	if ( ! is_user_logged_in() ) {
		wp_send_json_error( [ 'message' => 'Debes iniciar sesion para comentar.' ], 401 );
	}

	$nonce = isset( $_POST['nonce'] ) ? (string) $_POST['nonce'] : '';
	if ( ! wp_verify_nonce( $nonce, 'bloom_reader_anchor_comments' ) ) {
		wp_send_json_error(
			[
				'message'    => 'Tu sesion de comentarios expiro. Recarga la pagina e intenta de nuevo.',
				'code'       => 'invalid_nonce',
				'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
			],
			403
		);
	}

	$post_id = isset( $_POST['post_id'] ) ? (int) $_POST['post_id'] : 0;
	if ( ! $post_id || ! bloom_reader_anchor_post_is_public_chapter( $post_id ) ) {
		wp_send_json_error( [ 'message' => 'Capitulo invalido.' ], 404 );
	}

	$content = isset( $_POST['content'] ) ? trim( wp_unslash( (string) $_POST['content'] ) ) : '';
	if ( '' === $content ) {
		wp_send_json_error( [ 'message' => 'Escribe un comentario antes de publicar.' ], 400 );
	}

	$mode         = isset( $_POST['mode'] ) ? sanitize_key( (string) $_POST['mode'] ) : 'new';
	$parent_id    = isset( $_POST['parent_id'] ) ? (int) $_POST['parent_id'] : 0;
	$anchor_group = isset( $_POST['anchor_group'] ) ? sanitize_text_field( (string) $_POST['anchor_group'] ) : '';
	$image_index  = isset( $_POST['image_index'] ) ? (int) $_POST['image_index'] : 0;
	$x_pct        = isset( $_POST['x_pct'] ) ? max( 0, min( 100, (float) $_POST['x_pct'] ) ) : 0;
	$y_pct        = isset( $_POST['y_pct'] ) ? max( 0, min( 100, (float) $_POST['y_pct'] ) ) : 0;
	$image_key    = isset( $_POST['image_key'] ) ? sanitize_text_field( (string) $_POST['image_key'] ) : '';

	if ( 'reply' === $mode ) {
		$root = bloom_reader_anchor_find_group_root( $post_id, $anchor_group );
		if ( ! $root ) {
			wp_send_json_error( [ 'message' => 'No se encontro el hilo seleccionado.' ], 404 );
		}

		$parent_comment = $parent_id ? get_comment( $parent_id ) : null;
		if ( $parent_comment instanceof WP_Comment && (int) $parent_comment->comment_post_ID !== $post_id ) {
			$parent_comment = null;
		}

		$parent_id   = $parent_comment ? (int) $parent_comment->comment_ID : (int) $root->comment_ID;
		$image_index = (int) get_comment_meta( $root->comment_ID, 'lrs_anchor_image_index', true );
		$x_pct       = (float) get_comment_meta( $root->comment_ID, 'lrs_anchor_x_pct', true );
		$y_pct       = (float) get_comment_meta( $root->comment_ID, 'lrs_anchor_y_pct', true );
		$image_key   = (string) get_comment_meta( $root->comment_ID, 'lrs_anchor_image_key', true );
	}

	$current_user = wp_get_current_user();
	$comment_id   = wp_new_comment(
		wp_slash(
			[
				'comment_post_ID'      => $post_id,
				'comment_parent'       => $parent_id,
				'comment_content'      => $content,
				'user_id'              => (int) $current_user->ID,
				'comment_author'       => $current_user->display_name,
				'comment_author_email' => $current_user->user_email,
				'comment_author_url'   => $current_user->user_url,
			]
		),
		true
	);

	if ( is_wp_error( $comment_id ) ) {
		wp_send_json_error( [ 'message' => $comment_id->get_error_message() ], 400 );
	}

	if ( 'reply' !== $mode || '' === $anchor_group ) {
		$anchor_group = (string) $comment_id;
	}

	bloom_reader_anchor_save_meta(
		(int) $comment_id,
		[
			'lrs_anchor_type'        => 'anchored',
			'lrs_anchor_group'       => $anchor_group,
			'lrs_anchor_image_index' => $image_index,
			'lrs_anchor_x_pct'       => $x_pct,
			'lrs_anchor_y_pct'       => $y_pct,
			'lrs_anchor_image_key'   => $image_key,
		]
	);

	$status = wp_get_comment_status( $comment_id );

	wp_send_json_success(
		[
			'message'      => ( 'approved' === $status ) ? 'Comentario publicado.' : 'Comentario enviado y pendiente de moderacion.',
			'comment_id'   => (int) $comment_id,
			'anchor_group' => $anchor_group,
			'approved'     => ( 'approved' === $status ),
			'groups'       => bloom_reader_anchor_get_grouped_comments( $post_id ),
			'save_nonce'   => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		]
	);
}

add_filter( 'pre_comment_approved', 'bloom_reader_anchor_auto_approve_chapter_comments', 20, 2 );

function bloom_reader_anchor_auto_approve_chapter_comments( $approved, $commentdata ) {
	if ( ! is_array( $commentdata ) ) {
		return $approved;
	}

	$post_id = isset( $commentdata['comment_post_ID'] ) ? (int) $commentdata['comment_post_ID'] : 0;
	if ( ! $post_id || ! bloom_reader_anchor_post_is_public_chapter( $post_id ) ) {
		return $approved;
	}

	if ( 'spam' === $approved || 'trash' === $approved ) {
		return $approved;
	}

	return 1;
}

add_action( 'wp_ajax_bloom_reader_anchor_report', 'bloom_reader_anchor_report_ajax' );
add_action( 'wp_ajax_nopriv_bloom_reader_anchor_report', 'bloom_reader_anchor_report_ajax' );

function bloom_reader_anchor_report_ajax(): void {
	if ( ! is_user_logged_in() ) {
		wp_send_json_error( [ 'message' => 'Debes iniciar sesion para reportar comentarios.' ], 401 );
	}

	$nonce = isset( $_POST['nonce'] ) ? (string) $_POST['nonce'] : '';
	if ( ! wp_verify_nonce( $nonce, 'bloom_reader_anchor_comments' ) ) {
		wp_send_json_error(
			[
				'message'    => 'Tu sesion expiro. Recarga la pagina e intenta de nuevo.',
				'code'       => 'invalid_nonce',
				'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
			],
			403
		);
	}

	$comment_id = isset( $_POST['comment_id'] ) ? (int) $_POST['comment_id'] : 0;
	$comment    = $comment_id ? get_comment( $comment_id ) : null;
	if ( ! ( $comment instanceof WP_Comment ) ) {
		wp_send_json_error( [ 'message' => 'Comentario invalido.' ], 404 );
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_post_is_public_chapter( $post_id ) ) {
		wp_send_json_error( [ 'message' => 'Comentario invalido.' ], 404 );
	}

	$current_user_id = (int) get_current_user_id();
	if ( $current_user_id === (int) $comment->user_id ) {
		wp_send_json_error( [ 'message' => 'No puedes reportar tu propio comentario.' ], 400 );
	}

	$reporters = array_map( 'intval', (array) get_comment_meta( $comment_id, 'lrs_anchor_report_user', false ) );
	if ( in_array( $current_user_id, $reporters, true ) ) {
		wp_send_json_error(
			[
				'message'    => 'Ya reportaste este comentario.',
				'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
			],
			409
		);
	}

	add_comment_meta( $comment_id, 'lrs_anchor_report_user', $current_user_id, false );
	$reporters = array_map( 'intval', (array) get_comment_meta( $comment_id, 'lrs_anchor_report_user', false ) );
	update_comment_meta( $comment_id, 'lrs_anchor_report_count', count( $reporters ) );

	if ( count( $reporters ) >= 3 && 'approved' === wp_get_comment_status( $comment_id ) ) {
		wp_set_comment_status( $comment_id, 'hold', true );
	}

wp_send_json_success(
		[
			'message'      => 'Comentario reportado.',
			'comment_id'   => $comment_id,
			'report_count' => count( $reporters ),
			'groups'       => bloom_reader_anchor_get_grouped_comments( $post_id ),
			'save_nonce'   => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		]
	);
}

add_action( 'wp_ajax_bloom_reader_anchor_like', 'bloom_reader_anchor_like_ajax' );
add_action( 'wp_ajax_nopriv_bloom_reader_anchor_like', 'bloom_reader_anchor_like_ajax' );

function bloom_reader_anchor_like_ajax(): void {
	if ( ! is_user_logged_in() ) {
		wp_send_json_error( [ 'message' => 'Debes iniciar sesion para dar me gusta.' ], 401 );
	}

	$nonce = isset( $_POST['nonce'] ) ? (string) $_POST['nonce'] : '';
	if ( ! wp_verify_nonce( $nonce, 'bloom_reader_anchor_comments' ) ) {
		wp_send_json_error(
			[
				'message'    => 'Tu sesion expiro. Recarga la pagina e intenta de nuevo.',
				'code'       => 'invalid_nonce',
				'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
			],
			403
		);
	}

	$comment_id = isset( $_POST['comment_id'] ) ? (int) $_POST['comment_id'] : 0;
	$comment    = $comment_id ? get_comment( $comment_id ) : null;
	if ( ! ( $comment instanceof WP_Comment ) ) {
		wp_send_json_error( [ 'message' => 'Comentario invalido.' ], 404 );
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_post_is_public_chapter( $post_id ) ) {
		wp_send_json_error( [ 'message' => 'Comentario invalido.' ], 404 );
	}

	$current_user_id = (int) get_current_user_id();
	$likes           = bloom_reader_anchor_like_user_ids( $comment_id );
	$liked           = in_array( $current_user_id, $likes, true );

	if ( $liked ) {
		delete_comment_meta( $comment_id, 'lrs_anchor_like_user', $current_user_id );
	} else {
		add_comment_meta( $comment_id, 'lrs_anchor_like_user', $current_user_id, false );
	}

	$likes = bloom_reader_anchor_like_user_ids( $comment_id );
	update_comment_meta( $comment_id, 'lrs_anchor_like_count', count( $likes ) );

	wp_send_json_success(
		[
			'message'      => $liked ? 'Ya no te gusta este comentario.' : 'Te gusta este comentario.',
			'comment_id'   => $comment_id,
			'liked'        => ! $liked,
			'like_count'   => count( $likes ),
			'groups'       => bloom_reader_anchor_get_grouped_comments( $post_id ),
			'save_nonce'   => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		]
	);
}

add_action( 'wp_ajax_bloom_reader_anchor_upload', 'bloom_reader_anchor_upload_ajax' );

function bloom_reader_anchor_upload_ajax(): void {
	if ( ! is_user_logged_in() ) {
		wp_send_json_error( [ 'message' => 'Debes iniciar sesion para subir archivos.' ], 401 );
	}

	$nonce = isset( $_POST['nonce'] ) ? (string) $_POST['nonce'] : '';
	if ( ! wp_verify_nonce( $nonce, 'bloom_reader_anchor_comments' ) ) {
		wp_send_json_error(
			[
				'message'    => 'Tu sesion expiro. Recarga la pagina e intenta de nuevo.',
				'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
			],
			403
		);
	}

	if ( empty( $_FILES['file'] ) || ! is_array( $_FILES['file'] ) ) {
		wp_send_json_error( [ 'message' => 'No se recibio ningun archivo.' ], 400 );
	}

	$kind      = isset( $_POST['kind'] ) ? sanitize_key( (string) $_POST['kind'] ) : 'image';
	$file      = $_FILES['file'];
	$file_size = isset( $file['size'] ) ? (int) $file['size'] : 0;

	if ( 'gif' === $kind ) {
		$allowed_mimes = [ 'gif' => 'image/gif' ];
		$max_size      = 4 * MB_IN_BYTES;
	} else {
		$allowed_mimes = [
			'jpg|jpeg|jpe' => 'image/jpeg',
			'png'          => 'image/png',
			'webp'         => 'image/webp',
		];
		$max_size      = 3 * MB_IN_BYTES;
	}

	if ( $file_size <= 0 || $file_size > $max_size ) {
		wp_send_json_error( [ 'message' => 'El archivo es demasiado pesado para subirlo.' ], 400 );
	}

	require_once ABSPATH . 'wp-admin/includes/file.php';
	require_once ABSPATH . 'wp-admin/includes/image.php';
	require_once ABSPATH . 'wp-admin/includes/media.php';

	$upload = wp_handle_upload(
		$file,
		[
			'test_form' => false,
			'mimes'     => $allowed_mimes,
		]
	);

	if ( ! empty( $upload['error'] ) ) {
		wp_send_json_error( [ 'message' => (string) $upload['error'] ], 400 );
	}

	$url      = (string) $upload['url'];
	$file_path = (string) $upload['file'];

	if ( 'gif' !== $kind ) {
		$editor = wp_get_image_editor( $file_path );
		if ( ! is_wp_error( $editor ) ) {
			$size = $editor->get_size();
			if ( is_array( $size ) ) {
				$editor->resize( 768, 768, false );
			}
			if ( method_exists( $editor, 'set_quality' ) ) {
				$editor->set_quality( 60 );
			}

			$webp_path = preg_replace( '/\.[^.]+$/', '.webp', $file_path );
			$saved     = $editor->save( $webp_path, 'image/webp' );
			if ( ! is_wp_error( $saved ) && ! empty( $saved['path'] ) ) {
				if ( $saved['path'] !== $file_path && file_exists( $file_path ) ) {
					@unlink( $file_path );
				}
				$file_path = (string) $saved['path'];
				$url       = trailingslashit( dirname( $url ) ) . basename( $file_path );
			}
		}
	}

	$tag = sprintf(
		'[%1$s]%2$s[/%1$s]',
		esc_html( 'gif' === $kind ? 'gif' : 'img' ),
		esc_url_raw( $url )
	);

	wp_send_json_success(
		[
			'message'    => 'Archivo subido.',
			'kind'       => ( 'gif' === $kind ) ? 'gif' : 'img',
			'url'        => esc_url_raw( $url ),
			'tag'        => $tag,
			'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		]
	);
}

add_action( 'wp_ajax_bloom_reader_anchor_delete', 'bloom_reader_anchor_delete_ajax' );

function bloom_reader_anchor_delete_ajax(): void {
	if ( ! is_user_logged_in() ) {
		wp_send_json_error( [ 'message' => 'Debes iniciar sesion para eliminar comentarios.' ], 401 );
	}

	$nonce = isset( $_POST['nonce'] ) ? (string) $_POST['nonce'] : '';
	if ( ! wp_verify_nonce( $nonce, 'bloom_reader_anchor_comments' ) ) {
		wp_send_json_error(
			[
				'message'    => 'Tu sesion expiro. Recarga la pagina e intenta de nuevo.',
				'save_nonce' => wp_create_nonce( 'bloom_reader_anchor_comments' ),
			],
			403
		);
	}

	$comment_id = isset( $_POST['comment_id'] ) ? (int) $_POST['comment_id'] : 0;
	$comment    = $comment_id ? get_comment( $comment_id ) : null;
	if ( ! ( $comment instanceof WP_Comment ) ) {
		wp_send_json_error( [ 'message' => 'Comentario invalido.' ], 404 );
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_post_is_public_chapter( $post_id ) ) {
		wp_send_json_error( [ 'message' => 'Comentario invalido.' ], 404 );
	}

	$current_user_id = (int) get_current_user_id();
	if ( ! current_user_can( 'moderate_comments' ) && $current_user_id !== (int) $comment->user_id ) {
		wp_send_json_error( [ 'message' => 'No tienes permiso para eliminar este comentario.' ], 403 );
	}

	$deleted = wp_delete_comment( $comment_id, true );
	if ( ! $deleted ) {
		wp_send_json_error( [ 'message' => 'No se pudo eliminar el comentario.' ], 500 );
	}

	wp_send_json_success(
		[
			'message'      => 'Comentario eliminado.',
			'comment_id'   => $comment_id,
			'groups'       => bloom_reader_anchor_get_grouped_comments( $post_id ),
			'save_nonce'   => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		]
	);
}

add_action( 'wp_head', 'bloom_reader_anchor_print_styles', 1000 );

function bloom_reader_anchor_print_styles(): void {
	if ( is_admin() || ! bloom_reader_anchor_is_chapter() ) {
		return;
	}

	$css_path = bloom_reader_anchor_asset_path( 'reader-anchors.css' );
	$css_url  = bloom_reader_anchor_asset_url( 'reader-anchors.css' );

	if ( file_exists( $css_path ) ) {
		echo '<link rel="stylesheet" id="bloom-reader-anchor-comments-css" href="' . esc_url( add_query_arg( 'ver', rawurlencode( (string) filemtime( $css_path ) ), $css_url ) ) . '" media="all" />';
	}
}

add_action( 'wp_footer', 'bloom_reader_anchor_print_assets', 120 );

function bloom_reader_anchor_print_assets(): void {
	if ( is_admin() || ! bloom_reader_anchor_is_chapter() ) {
		return;
	}

	$post_id  = (int) get_queried_object_id();
	$js_path  = bloom_reader_anchor_asset_path( 'reader-anchors.js' );
	$js_url   = bloom_reader_anchor_asset_url( 'reader-anchors.js' );
	$version  = file_exists( $js_path ) ? (string) filemtime( $js_path ) : (string) time();
	$config   = [
		'ajaxUrl'    => admin_url( 'admin-ajax.php' ),
		'nonce'      => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		'saveNonce'  => wp_create_nonce( 'bloom_reader_anchor_comments' ),
		'postId'     => $post_id,
		'isLoggedIn' => is_user_logged_in(),
		'currentUserId' => (int) get_current_user_id(),
		'viewerKey'  => is_user_logged_in() ? 'u' . get_current_user_id() : 'guest',
		'loginUrl'   => wp_login_url( get_permalink( $post_id ) ),
		'strings'    => [
			'buttonTitle'      => 'Comentarios',
			'emptyHint'        => 'Selecciona un numerito o usa Shift+click / triple click para comentar en una parte concreta.',
			'emptyHintMobile'  => 'Toca un numerito o usa triple tap en modo comentario para comentar justo en ese punto.',
			'newCommentTitle'  => 'Comentar en esta parte',
			'replyHere'        => 'Responder aqui',
			'newThreadHere'    => 'Nuevo hilo aqui',
			'cancel'           => 'Cancelar',
			'publish'          => 'Publicar comentario',
			'readMore'         => 'Leer mas...',
			'commentsTitle'    => 'Comentarios',
			'loginRequired'    => 'Debes iniciar sesion para comentar en un punto exacto del capitulo.',
			'loginButton'      => 'Iniciar sesion',
			'chooseAction'     => 'Hay un hilo cerca de este punto. Elige como quieres comentar.',
			'loading'          => 'Cargando comentarios...',
			'genericError'     => 'No se pudo completar la accion. Intenta de nuevo.',
			'scrollHint'       => 'Los numeritos se vuelven mas visibles al scrollear y bajan su opacidad al quedar quietos.',
			'report'           => 'Reportar',
			'reported'         => 'Reportado',
			'reportedMessage'  => 'Comentario reportado.',
			'alreadyReported'  => 'Ya reportaste este comentario.',
			'like'             => 'Me gusta',
			'liked'            => 'Te gusta',
			'likeLogin'        => 'Debes iniciar sesion para dar me gusta.',
			'copyComment'      => 'Copiar comentario',
			'copyUserName'     => 'Copiar nombre de usuario',
			'copyCommentId'    => 'Copiar ID de comentario',
			'copyUserId'       => 'Copiar ID de usuario',
			'moderateComment'  => 'Moderar comentario',
			'deleteComment'    => 'Eliminar comentario',
			'deleteConfirm'    => 'Este comentario se eliminara de forma permanente. Continuar?',
			'toolbarBold'      => 'B',
			'toolbarItalic'    => 'I',
			'toolbarLink'      => 'Link',
			'toolbarSpoiler'   => 'Spoiler',
			'toolbarEmoji'     => 'Emoji',
			'toolbarImage'     => 'Img',
			'toolbarGif'       => 'GIF',
			'promptLink'       => 'Pega la URL que quieres enlazar:',
			'promptImage'      => 'Pega la URL de la imagen:',
			'promptGif'        => 'Pega la URL del GIF:',
			'uploading'        => 'Subiendo...',
			'uploadFailed'     => 'No se pudo subir el archivo.',
			'viewImage'        => 'Ver imagen',
			'hideImage'        => 'Ocultar imagen',
			'viewGif'          => 'Ver GIF',
			'hideGif'          => 'Ocultar GIF',
		],
		'canModerate' => current_user_can( 'moderate_comments' ),
		'commentAdminBase' => admin_url( 'comment.php?action=editcomment&c=' ),
	];

	echo '<script id="bloom-reader-anchor-config">window.bloomReaderAnchors=' . wp_json_encode( $config ) . ';</script>';

	if ( file_exists( $js_path ) ) {
		echo '<script src="' . esc_url( add_query_arg( 'ver', rawurlencode( $version ), $js_url ) ) . '"></script>';
	}
}

add_filter( 'comment_text', 'bloom_reader_anchor_format_comment_text', 5, 3 );

function bloom_reader_anchor_format_comment_text( string $comment_text, $comment = null, $args = [] ): string {
	if ( is_admin() ) {
		return $comment_text;
	}

	if ( ! ( $comment instanceof WP_Comment ) ) {
		return $comment_text;
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_is_chapter( $post_id ) ) {
		return $comment_text;
	}

	return bloom_reader_anchor_render_comment_markup( (string) $comment->comment_content );
}

add_filter( 'comment_text', 'bloom_reader_anchor_append_jump_link', 20, 3 );

function bloom_reader_anchor_append_jump_link( string $comment_text, $comment = null, $args = [] ): string {
	if ( is_admin() ) {
		return $comment_text;
	}

	if ( ! ( $comment instanceof WP_Comment ) ) {
		return $comment_text;
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_is_chapter( $post_id ) ) {
		return $comment_text;
	}

	if ( 'anchored' !== (string) get_comment_meta( $comment->comment_ID, 'lrs_anchor_type', true ) ) {
		return $comment_text;
	}

	$group_id = (string) get_comment_meta( $comment->comment_ID, 'lrs_anchor_group', true );
	if ( '' === $group_id ) {
		$group_id = (string) ( $comment->comment_parent ?: $comment->comment_ID );
	}

	$page = max( 1, (int) get_comment_meta( $comment->comment_ID, 'lrs_anchor_image_index', true ) + 1 );
	$label = sprintf( 'Ir al punto comentado (página %d)', $page );
	$button = sprintf(
		'<p class="lrs-anchor-jump-wrap"><button type="button" class="lrs-anchor-jump" data-group="%s">%s</button></p>',
		esc_attr( $group_id ),
		esc_html( $label )
	);

	return $comment_text . $button;
}

add_filter( 'comment_text', 'bloom_reader_anchor_append_report_link', 25, 3 );

function bloom_reader_anchor_append_report_link( string $comment_text, $comment = null, $args = [] ): string {
	if ( is_admin() ) {
		return $comment_text;
	}

	if ( ! ( $comment instanceof WP_Comment ) ) {
		return $comment_text;
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_is_chapter( $post_id ) ) {
		return $comment_text;
	}

	if ( ! is_user_logged_in() || (int) get_current_user_id() === (int) $comment->user_id ) {
		return $comment_text;
	}

	$button = sprintf(
		'<p class="lrs-anchor-jump-wrap"><button type="button" class="lrs-anchor-report" data-comment-id="%d">%s</button></p>',
		(int) $comment->comment_ID,
		esc_html__( 'Reportar comentario', 'bloomscans' )
	);

	return $comment_text . $button;
}

add_filter( 'comment_text', 'bloom_reader_anchor_append_like_link', 27, 3 );

function bloom_reader_anchor_append_like_link( string $comment_text, $comment = null, $args = [] ): string {
	if ( is_admin() ) {
		return $comment_text;
	}

	if ( ! ( $comment instanceof WP_Comment ) ) {
		return $comment_text;
	}

	$post_id = (int) $comment->comment_post_ID;
	if ( ! $post_id || ! bloom_reader_anchor_is_chapter( $post_id ) ) {
		return $comment_text;
	}

	$current_user_id = (int) get_current_user_id();
	$likes           = bloom_reader_anchor_like_user_ids( (int) $comment->comment_ID );
	$liked           = $current_user_id ? in_array( $current_user_id, $likes, true ) : false;

	$button = sprintf(
		'<p class="lrs-anchor-like-wrap"><button type="button" class="lrs-anchor-like%1$s" data-comment-id="%2$d" data-liked="%3$d"><span class="lrs-anchor-like-heart" aria-hidden="true">❤</span><span class="lrs-anchor-like-label">%4$s</span><span class="lrs-anchor-like-count">%5$d</span></button></p>',
		$liked ? ' is-liked' : '',
		(int) $comment->comment_ID,
		$liked ? 1 : 0,
		esc_html__( 'Me gusta', 'bloomscans' ),
		count( $likes )
	);

	return $comment_text . $button;
}
