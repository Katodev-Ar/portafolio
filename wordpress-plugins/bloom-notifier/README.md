# 🔔 bloom-notifier

**Sistema de notificaciones push segmentadas y multicanal para WordPress.**

## 📋 Descripción
Plugin que permite enviar notificaciones push y alertas segmentadas a los usuarios de la plataforma cuando se publica nuevo contenido (capítulos, noticias, actualizaciones). Soporta múltiples canales de distribución incluyendo notificaciones in-app y webhooks de Discord.

## 🚀 Características
- Notificaciones in-app con centro de mensajes para cada usuario
- Webhook dispatcher para Discord (envío automático de embeds con metadata del capítulo)
- Segmentación por tipo de contenido y preferencias del usuario
- Cola de envío asíncrona para evitar bloquear el hilo principal de WordPress

## 💻 Tecnologías
- PHP 7.4+, WordPress Hooks & Transients API
- JavaScript, REST API
- Discord Webhook API
