<?php
/**
 * Bloom Discord Login - Admin Settings Page
 *
 * Rendered inside wp-admin via Bloom_Discord_Login::render_admin_page().
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}
?>
<div class="wrap">
	<h1>Bloom Discord Login</h1>
	<p>Configura las credenciales de la aplicacion OAuth2 de Discord.<br>
	   Obtenlas desde <a href="https://discord.com/developers/applications" target="_blank" rel="noopener">Discord Developer Portal</a>.</p>

	<form method="post" action="options.php">
		<?php settings_fields( 'bdl_settings' ); ?>

		<table class="form-table" role="presentation">
			<tr>
				<th scope="row"><label for="bdl_enabled">Habilitado</label></th>
				<td>
					<input type="checkbox" name="bdl_enabled" id="bdl_enabled" value="1"
						<?php checked( get_option( 'bdl_enabled', 0 ), 1 ); ?>>
					<span class="description">Mostrar boton de Discord en login y registro.</span>
				</td>
			</tr>
			<tr>
				<th scope="row"><label for="bdl_client_id">Client ID</label></th>
				<td>
					<input type="text" name="bdl_client_id" id="bdl_client_id"
						value="<?php echo esc_attr( get_option( 'bdl_client_id', '' ) ); ?>"
						class="regular-text" autocomplete="off">
				</td>
			</tr>
			<tr>
				<th scope="row"><label for="bdl_client_secret">Client Secret</label></th>
				<td>
					<input type="password" name="bdl_client_secret" id="bdl_client_secret"
						value="<?php echo esc_attr( get_option( 'bdl_client_secret', '' ) ); ?>"
						class="regular-text" autocomplete="off">
					<p class="description">No compartir. Se guarda cifrado en la base de datos de WordPress.</p>
				</td>
			</tr>
			<tr>
				<th scope="row">Redirect URI</th>
				<td>
					<code><?php echo esc_html( home_url( '/?bloom_discord_callback=1' ) ); ?></code>
					<p class="description">Copia esta URL exacta en la seccion <strong>Redirects</strong> de tu aplicacion en Discord Developer Portal.</p>
				</td>
			</tr>
		</table>

		<?php submit_button( 'Guardar cambios' ); ?>
	</form>

	<hr>
	<h2>Instrucciones rapidas</h2>
	<ol>
		<li>Ve a <a href="https://discord.com/developers/applications" target="_blank" rel="noopener">Discord Developer Portal</a>.</li>
		<li>Crea una nueva aplicacion (o usa una existente).</li>
		<li>En la seccion <strong>OAuth2</strong>, copia el <strong>Client ID</strong> y genera un <strong>Client Secret</strong>.</li>
		<li>En <strong>Redirects</strong>, agrega la URL mostrada arriba.</li>
		<li>Pega las credenciales aqui y activa la casilla <em>Habilitado</em>.</li>
		<li>Listo. El boton de Discord aparecera en las paginas de login y registro.</li>
	</ol>
</div>
