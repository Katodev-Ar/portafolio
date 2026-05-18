# 🖨️ PrintBridge

**Hub de automatización de impresión digital masiva con servidor local FastAPI.**

## 📋 Descripción
Servidor local basado en FastAPI que funciona como un centro de impresión en red, procesando colas asíncronas de documentos, gestionando flujos de impresión y ejecutando wrappers de traducción en segundo plano. Incluye interfaz en la bandeja del sistema de Windows para control rápido.

## 🚀 Características
- Servidor FastAPI local con endpoints REST para enviar trabajos de impresión
- Cola de impresión asíncrona con prioridades y reintentos
- Interfaz en la system tray de Windows para monitoreo y control
- Procesamiento de imágenes para sublimación con ajustes de color y tamaño

## 💻 Tecnologías
- Python 3, FastAPI, Uvicorn
- Pillow, win32print
- System Tray (pystray)
