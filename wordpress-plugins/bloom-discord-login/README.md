# 🔐 bloom-discord-login

**Autenticación OAuth2 con Discord para WordPress — implementación nativa, ligera y segura.**

## 📋 Descripción
Plugin independiente que permite a los usuarios iniciar sesión en BloomScans utilizando su cuenta de Discord, sin depender de plugins pesados de terceros como Nextend. Implementa el flujo completo de OAuth2 Authorization Code Grant con protección CSRF, resolución inteligente de cuentas y logging estructurado.

## 🚀 Características
- **Flujo OAuth2 completo:** Authorization Code → Token Exchange → User Info fetch
- **Protección CSRF:** Genera estados temporales únicos (`wp_generate_password`) almacenados en transients de WordPress con expiración de 10 minutos
- **Resolución inteligente de cuentas:**
  1. Busca por `bdl_discord_id` en user meta (usuario recurrente)
  2. Si el email verificado de Discord coincide con una cuenta local, las vincula automáticamente
  3. Si no existe, crea un nuevo usuario Subscriber con contraseña segura de 24 caracteres
- **Generador de usernames únicos** con sufijos numéricos incrementales para evitar colisiones
- **Bypass de verificación local** cuando Discord ya verificó el email (`bsh_email_verified_at`)

## 💻 Tecnologías
- PHP 7.4+, WordPress Core APIs
- Discord OAuth2 API, `wp_remote_post`/`wp_remote_get`
