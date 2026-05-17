<?php
/**
 * Wrapper del template de comentarios.
 * Incluye el template original y luego agrega el resumen de Gemini debajo.
 * 
 * Este archivo se coloca en: wp-content/plugins/gemini-manga-summary/comments-wrapper.php
 */

// Incluir el template original de comentarios del tema
if ( ! empty( $GLOBALS['gms_original_comments_template'] ) ) {
    include $GLOBALS['gms_original_comments_template'];
}

// Mostrar el resumen IA debajo de los comentarios
echo gms_render_summary_box( get_the_ID() );
