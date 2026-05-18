# 🛡️ bloom-security-hardening

**Escudo de seguridad perimetral, firewall inteligente y optimizador de rendimiento a medida para WordPress.**

## 📋 Descripción
Este plugin de seguridad a nivel de servidor proporciona blindaje contra ataques automatizados de fuerza bruta, spam, scraping y enumeración de usuarios REST API. Además, optimiza el rendimiento y la interfaz al remover dinámicamente callbacks de redes publicitarias intrusivas (como Monetag) en páginas de autenticación, logrando un flujo de login totalmente premium y libre de inyecciones publicitarias.

## 🚀 Características
- **Control de Tasa Inteligente por Fingerprint:** 
  - Limita logins (máx 12 intentos/15 min) y registros (máx 5/hora).
  - Almacena de forma segura bloqueos usando transients de WordPress encriptados bajo un hash md5 único de IP real (con soporte para IP real detrás del proxy Cloudflare) y User Agent (`md5($ip . '|' . $ua)`).
- **Trilogía Defensiva de Registro de Usuarios:**
  - *Decoy Honeypot:* Campo invisible en CSS (`bsh_company`) que atrapa y bloquea instantáneamente registros automatizados de bots.
  - *Time Lock Lockout:* Detecta registros completados en menos de 4 segundos, cancelándolos al instante para mitigar bots headless superrápidos.
  - *Desafíos Criptográficos Firmados:* Genera sumas matemáticas dinámicas cuyas firmas se firman criptográficamente en el servidor mediante `wp_hash()` (incorporando las sales de WordPress), haciendo imposible el spoofing de respuestas sin conocer la clave secreta local.
- **Doble Factor de Verificación por Email (2FA Link):** Bloquea los registros nativos bajo un estado pendiente (`bsh_pending_email_verification`), generando tokens hash de alta entropía (32 caracteres) enviados vía email transaccional para confirmar la legitimidad del usuario.
- **Supresor de Publicidad "On-the-Fly" (`suppress_ads_on_auth_pages`):** Intercepta e inspecciona dinámicamente todos los hooks de renderizado nativos (`wp_filter`) en las páginas de login/registro para buscar callbacks que contengan referencias de anuncios (como Monetag) y removerlas del ciclo de ejecución, eliminando shifts visuales y scripts publicitarios.
- **REST API Guard & Anti-Enumeration:**
  - Elimina `/wp/v2/users` de los endpoints REST públicos.
  - Intercepta el pre-despacho de llamadas asíncronas para retornar 403 Forbidden a peticiones de escaneo maliciosas, a la vez que preserva el correcto funcionamiento del Site Health nativo y plugins del sistema.
  - Deshabilita los archivos de autores para prevenir el escaneo y robo de nombres de usuario.
- **Inyección de Cabeceras de Seguridad y Reparación CSS Zoom:**
  - Enforcea cabeceras `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security` y CSP rígidos.
  - Inyecta hojas de estilo personalizadas para corregir desbordamientos provocados por el zoom del navegador en la cuadrícula del catálogo manga.

## 💻 Tecnologías
- **Backend:** PHP 7.4+, WordPress Core API, WordPress Transient API
- **Seguridad:** Criptografía Simétrica (`wp_hash`), HTTP Client Fingerprinting, Honeypots
