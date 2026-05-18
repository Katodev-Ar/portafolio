# 🔏 bloom-internal-raw-image-exception

**Proxy seguro de bypass y streaming controlado para imágenes crudas protegidas en WordPress.**

## 📋 Descripción
Este plugin resuelve un reto común en plataformas web de distribución de cómics y manga: cómo proteger las imágenes de los capítulos (evitando hotlinking, descargas ilegales y scraping externo) mientras se permite que herramientas de maquetación del panel de administración (`/panel-scan/` o `wp-admin`) carguen y previsualicen de manera transparente y eficiente dichos recursos locales.

## 🚀 Características
- **Prevención Absoluta de Directory Traversal:** 
  - Al interceptar peticiones de imágenes a través del hook `init`.
  - Normaliza la ruta solicitada mediante `wp_normalize_path` y comprueba de forma canónica con `realpath()` que el archivo final resuelto resida estrictamente dentro de la ruta del uploads base (`basedir`). Cualquier inyección maliciosa tipo `../` aborta la petición al instante.
- **Validador de Referrers de Confianza (`biri_same_site_internal_referer`):**
  - Analiza tanto el host principal del sitio como el host del referrer mediante `wp_parse_url`, asegurando coincidencia estricta (`$home_host === $ref_host`).
  - Inspecciona que la ruta del referrer proceda de un panel de edición administrativo de scans o consultas de paneles específicos (`chapter_edit`, `manga_edit`, `scans`, etc.).
- **Streaming Directo Serverless Performante:**
  - Evita consumir grandes cantidades de memoria en PHP al leer archivos grandes.
  - Detecta de manera dinámica el mime-type del archivo local con `wp_check_filetype`.
  - Inyecta cabeceras personalizadas de no-caché (`Cache-Control: private, no-store, max-age=0`) y de bypass (`X-Bloom-Internal-Raw-Bypass: 1`).
  - Utiliza la función de bajo nivel altamente optimizada **`readfile($path)`** para transferir directamente el flujo de bytes del archivo físico de disco a la salida del servidor HTTP con un overhead de memoria insignificante.

## 💻 Tecnologías
- **Backend:** PHP 7.4+, WordPress Core API
- **Seguridad:** Directory Traversal Guards, Canonical Path Normalization, Same-Site Referrer Checking
