# 🔐 bloom-recaptcha-login

**Protección anti-bot con Google reCAPTCHA v2 para formularios de login y registro en WordPress.**

## 📋 Descripción
Plugin que integra Google reCAPTCHA v2 (checkbox "No soy un robot") en los formularios de autenticación de BloomScans. Diseñado con una arquitectura de interceptación temprana que valida el token de reCAPTCHA antes de que WordPress procese las credenciales, y redirige errores directamente a la página de login personalizada.

## 🚀 Características
- **Interceptación temprana en `init` (prioridad 5):** Valida el reCAPTCHA antes de que `wp-login.php` procese las credenciales, impidiendo que el usuario vea la página nativa de WordPress
- **Política fail-open:** Si Google no responde, el login continúa normalmente para no bloquear usuarios legítimos
- **Compatibilidad con Social Login:** Detecta automáticamente callbacks de Discord OAuth2 y Nextend Social Login y las excluye de la verificación
- **Soporte para Cloudflare:** Envía la IP real del cliente (`HTTP_CF_CONNECTING_IP`) a Google para mejorar la precisión del scoring
- **Panel de configuración** en wp-admin para gestionar claves y activar/desactivar

## 💻 Tecnologías
- PHP 7.4+, WordPress `authenticate` filter
- Google reCAPTCHA v2 API
