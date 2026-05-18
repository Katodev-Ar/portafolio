# 💰 bloom-coins-system

**Sistema completo de monedas virtuales con integración de pasarelas de pago internacionales para WordPress.**

## 📋 Descripción
Plugin que implementa una economía virtual dentro de la plataforma BloomScans. Los usuarios pueden comprar monedas a través de MercadoPago o PayPal y canjearlas para desbloquear capítulos premium. Incluye un dashboard administrativo completo con gráficos Chart.js interactivos y gestión avanzada de wallets.

## 🚀 Características
- **Wallet de usuario** con balance persistente en tabla SQL personalizada (`user_wallet`)
- **Integración con MercadoPago y PayPal** vía webhooks IPN verificados del lado del servidor
- **Bloqueo de capítulos premium** con liberación automática temporal (`_msg_free_after_days`)
- **Badge dinámico 🪙** inyectado en los listados de capítulos via JS con `MutationObserver` para paginación AJAX
- **Dashboard administrativo** con KPIs en tiempo real, gráficos de actividad diaria (Chart.js), top mangas, top compradores y reportes por grupo de scan
- **Gestión de créditos** para agregar/quitar monedas manualmente con auditoría completa

## 💻 Tecnologías
- PHP 7.4+, WordPress Core APIs, MySQL
- JavaScript (ES6+), Chart.js 4
- MercadoPago IPN, PayPal Webhooks
