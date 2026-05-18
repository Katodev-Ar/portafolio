# 🔄 Ecosistema de Migración de Medios y Optimización WebP

**Pipeline automatizado de migración y optimización de activos multimedia para plataformas web de alto tráfico.**

## 📋 Descripción
Este pipeline en Python resuelve la necesidad de migrar masivamente y optimizar los archivos de uploads de WordPress (`wp-content/uploads`) a formatos de última generación sin comprometer la integridad geométrica de las imágenes (crucial para maquetado de manga y cómics) ni romper los enlaces de la base de datos de producción.

## 🚀 Características
- **Traducción de Nombres por IA (SEO Friendly):** Carga un mapa dinámico en formato TSV (`mapeo_renombres_ia_bloomscans_20260403.tsv`) que asocia nombres crudos u ofuscados con basenames descriptivos optimizados para posicionamiento orgánico.
- **Transcodificación a WebP Lossless Extrema:**
  - Convierte archivos `.jpg`, `.jpeg` y `.png` a formato `.webp`.
  - Normaliza modos de color (paletas transparentes indexadas `P`/`LA` a `RGBA`; escala de grises y CMYK a `RGB`) utilizando la librería PIL (Pillow).
  - Configura la transcodificación a compresión sin pérdida (`lossless=True`), esfuerzo computacional máximo (`method=6`) y calidad máxima (100%) para conservar el 100% de la fidelidad del manga.
- **Verificación Geométrica Estricta:** Reabre ambas imágenes (original y WebP) para validar que sus dimensiones en píxeles coincidan exactamente, interrumpiendo el flujo si ocurre alguna discrepancia.
- **SQL Search-Replace WP-CLI Automatizado:** Compila un archivo shell script (`wp_search_replace_medios.sh`) que genera de manera segura y precisa sentencias SQL ejecutables a través de WP-CLI (`wp search-replace`) para sincronizar las viejas URLs con los nuevos activos optimizados en las tablas `wp_posts` y `wp_postmeta`, respetando objetos serializados.

## 💻 Tecnologías
- **Lenguaje:** Python 3.x
- **Librerías:** PIL (Pillow)
- **Base de datos:** WP-CLI / MySQL
