# 💬 bloom-reader-anchored-comments

**Sistema de comentarios anclados al estilo Medium/Figma adaptado para paneles manga en WordPress.**

## 📋 Descripción
Este plugin MU (Must-Use) de WordPress permite a los usuarios anclar comentarios interactivos directamente sobre coordenadas relativas y porcentuales (`x_pct`, `y_pct`) en paneles de imágenes de manga específicos. Esto fomenta la interacción precisa en puntos específicos de la lectura y una experiencia de usuario sumamente fluida.

## 🚀 Características
- **Almacenamiento Altamente Optimizado:** En lugar de crear complejas tablas SQL personalizadas, utiliza la tabla nativa `wp_comments` de WordPress como almacén de datos, asociando las coordenadas y los índices de imágenes en metadatos del comentario (`comment_meta`).
- **Resizing & Transcoding WebP en Caliente:** Al subir imágenes en las respuestas, utiliza el editor de imágenes integrado de WordPress (`wp_get_image_editor`) para escalar la imagen a 768x768 píxeles de máxima anchura/altura, reducir la calidad al 60% (para ahorro radical de ancho de banda) y transcodificarla directamente a formato WebP de última generación.
- **Formateador BBCode Seguro:** Integra un motor robusto regex de reemplazo para convertir sintaxis BBCode (`[b]`, `[i]`, `[spoiler]`, `[url]`, `[img]`, `[gif]`) en marcado HTML seguro. Los enlaces externos y recursos de medios se sanitizan estrictamente mediante `wp_http_validate_url` para prevenir ataques XSS.
- **Auto-Moderación y Reportes por AJAX:**
  - Registra likes y reportes de manera asíncrona mediante llamadas `admin-ajax.php`.
  - Almacena los reportes bajo un array serializado de IDs de usuario (`lrs_anchor_report_user`).
  - Si un comentario acumula 3 o más reportes de usuarios únicos, el plugin degrada automáticamente el comentario a `'hold'` (cola de moderación) de forma autónoma.
- **Carga Diferida y Estilos Responsivos:** Utiliza vanilla JavaScript interactivo y CSS adaptativo para posicionar de forma dinámica las burbujas flotantes de comentarios sobre las imágenes del reader, recalculando posiciones relativas tras el reajuste del lienzo.

## 💻 Tecnologías
- **Backend:** PHP 7.4+, WordPress Core APIs (Comments, Image Editors, AJAX)
- **Frontend:** Vanilla JavaScript (ES6+), CSS3 HSL Variables
- **Formatos:** WebP, JSON
