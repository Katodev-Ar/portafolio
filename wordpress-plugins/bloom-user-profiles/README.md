# 👤 bloom-user-profiles

**Sistema completo de perfiles públicos de usuario con muro de mensajes y búsqueda integrada para WordPress.**

## 📋 Descripción
Plugin que extiende WordPress con perfiles públicos de usuario personalizados, muro de mensajes estilo red social, y búsqueda de usuarios integrada al buscador nativo del tema manga. Arquitectura modular basada en clases (`BUP_DB`, `BUP_Ajax`, `BUP_Profile`, `BUP_Assets`).

## 🚀 Características
- **Perfiles públicos** con avatares personalizados y estadísticas de lectura
- **Muro de mensajes** con publicaciones y respuestas vía AJAX (`bup_wall_post`, `bup_wall_load`)
- **Búsqueda de usuarios** integrada en el dropdown del buscador global del tema manga sin modificar el código del tema (inyección paralela via JS)
- **Tabla SQL personalizada** para mensajes del muro (`BUP_DB::install`)

## 💻 Tecnologías
- PHP 7.4+, WordPress Core APIs
- JavaScript (ES6+), CSS3
- AJAX, MySQL
