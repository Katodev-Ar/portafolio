# 🌐 Plugins WordPress — BloomScans Platform

**Suite de plugins personalizados para la plataforma [bloomscans.com](https://bloomscans.com)**

## Descripción
Esta colección representa el ecosistema completo de plugins WordPress desarrollados a medida para una plataforma web de lectura de manga. Cada plugin resuelve una necesidad específica que no existía en el mercado, optimizando la administración y el flujo de los usuarios.

## Plugins incluidos

### 💰 bloom-coins-system (v1.0 → v1.3)
Sistema de monedas virtuales con integración completa de **MercadoPago** y **PayPal**. Procesa transacciones automatizadas mediante webhooks IPN verificados del lado del servidor. El sistema ha sido testeado, validado y se encuentra **completamente listo para producción**.

### 🍪 bloom-cookie-manager (v1.8 → v2.0.5)
Gestión avanzada de sesiones web y cookies con 10+ versiones de desarrollo.

### 🔔 bloom-notifier (v2 → v3)
Sistema de notificaciones push para alertar a los usuarios sobre nuevo contenido.

### 📦 subida-zip-bloom (v3.3 → v3.5.4)
Módulo de carga masiva de capítulos via archivos ZIP. Automatiza la extracción, procesamiento y publicación de contenido.

### 🔐 bloom-discord-login
Autenticación OAuth2 que permite a los usuarios iniciar sesión con su cuenta de Discord.

### 🛡️ bloom-recaptcha-login
Protección anti-bot integrando Google reCAPTCHA en el flujo de registro/login.

### 👤 bloom-user-profiles
Sistema completo de perfiles de usuario con avatares personalizados, estadísticas de lectura y preferencias.

### 🖼️ bloom-reader-image-guard
Protección anti-descarga de imágenes del lector de manga, implementando técnicas de ofuscación del DOM.

### 💬 bloom-reader-anchored-comments
Sistema de comentarios manga anclados al estilo Medium/Figma. Soporta BBCode de formato, transcodificación WebP en caliente a 60% de calidad al subir imágenes, y auto-moderación en cola de hold al acumular 3 reportes únicos.

### 🛡️ bloom-security-hardening
Escudo anti-hackers completo: rate-limiting por hash md5 de fingerprint IP+UA, honeypot decoy, firma criptográfica matemática validada con `wp_hash`, bloqueo de enumeración de usuarios REST API, y un supresor que intercepta hooks nativos de WordPress para desactivar anuncios Monetag en caliente en páginas de autenticación.

### 🔏 bloom-internal-raw-image-exception
Proxy de streaming seguro con prevención activa de directory traversal comparando rutas contra la uploads base canónica, permitiendo a los colaboradores del panel administrativo ver imágenes protegidas con cero retardo.

## Tecnologías
- PHP 7.4+
- WordPress Hooks & Actions API
- MySQL / MariaDB
- JavaScript (ES6+)
- CSS3
- OAuth2 (Discord, Google)
- Webhooks (MercadoPago, PayPal)
