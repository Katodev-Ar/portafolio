# Plan de Desarrollo a Futuro: Proyecto Serenity

Este es un plan estructurado (Roadmap) para implementar todas las mejoras solicitadas, priorizando las opciones que elegiste (Buzón, Drive y Clipboard) para empezar a crear un ecosistema verdaderamente interconectado.

---

## 🚀 FASE 1: El Ecosistema Compartido (Prioridad Absoluta)
*Estas son las 3 características que elegiste. Su objetivo es derribar la barrera entre tu celular y tu PC.*

### 1. El "Buzón de Serenity" (Dropzone en la PWA)
- **Desarrollo Backend:** Crear un endpoint `/upload` en Flask (`main.py`) que reciba archivos binarios (imágenes, documentos).
- **Desarrollo Frontend:** Añadir un botón flotante o sección "Subir" en la UI (HTML/JS) que abra el selector de archivos del celular.
- **Integración IA:** Si el archivo es una imagen, pasarla automáticamente a `gemini-1.5-pro` (o flash) usando la API de Vertex AI Multimodal, devolviendo el análisis al chat.

### 2. Sincronización Inversa por Google Drive
- **Configuración Local:** Crear un directorio `C:\Serenity_Share` y mapearlo a Google Drive para Escritorio.
- **Servicio de Monitoreo:** Usar la librería `watchdog` en Python para que el PC Agent vigile los cambios en esa carpeta.
- **Acciones Automáticas:** Cuando un archivo caiga ahí desde tu celular, el agente registrará el evento y (dependiendo de la extensión) podrá auto-procesarlo o avisarte.

### 3. Portapapeles (Clipboard) Universal Bi-direccional
- **Backend:** Crear endpoints `/clipboard/get` y `/clipboard/set` usando la librería `pyperclip` de Python.
- **Frontend:** Añadir un widget en la UI web que muestre el portapapeles actual de la PC y permita escribir/pegar texto para enviarlo a la PC.
- **Uso IA:** Permitir comandos como *"Serenity, resume lo que tengo en el portapapeles"*.

---

## 🎨 FASE 2: UI, UX y Calidad de Vida (Victorias Rápidas)
*Mejoras visuales y controles básicos que enriquecen mucho la experiencia diaria.*

- **Controles Multimedia y Volumen:** Añadir un slider de 0-100% y botones Play/Pause/Next (`pycaw` y Teclas Virtuales). (Funciones 19, 20)
- **Gestor de Procesos en Vivo:** Un botón para abrir una ventana modal con los top 10 procesos y poder matarlos. (Función 21)
- **Visor de Pantalla en Vivo:** Un endpoint `/screenshot` con `mss` para ver qué está pasando en el monitor desde el celular. (Función 11)
- **Notificaciones Toast:** Cambiar las alertas invasivas por notificaciones modernas en la parte inferior de la pantalla. (Función 10)
- **Modo Apaisado (Landscape):** Adaptar el CSS para cuando gires el teléfono. (Función 9)
- **Cierre Forzado (Anti-Congelamiento):** Botón de emergencia para matar tareas que no responden. (Función 24)

---

## 🤖 FASE 3: Interacción Avanzada y Agente IA
*Subiendo el nivel intelectual de Serenity.*

- **Comandos por Voz:** Integrar `Web Speech API` en el PWA para hablarle directo al celular. (Función 12)
- **Botones Dinámicos en Chat:** Que Serenity responda con botones clicables (Ej: `[Sí, cerrar Chrome]`). (Función 14)
- **Contexto Activo:** Usar `pygetwindow` para que Gemini sepa qué programa estás usando ahora mismo. (Función 15)
- **Traductor / Copiloto en Pantalla:** Que procese el texto seleccionado o en portapapeles y muestre resultados. (Funciones 13, 46)
- **Programación Natural:** Entrenar al LLM para entender intenciones complejas como "Apaga la PC cuando termine X". (Función 17)
- **Buscador Semántico y de Archivos:** Integrar herramientas de búsqueda (`grep` o similares) guiadas por IA. (Funciones 16, 47)
- **Agente Autónomo Primitivo:** Control de mouse y teclado usando `pyautogui` para automatizar clics. (Función 49)

---

## 🔒 FASE 4: Seguridad, Infraestructura y Monitoreo Fuerte
*Cimentando la aplicación para que nunca falle y sea segura.*

- **Empaquetado `.EXE`:** Usar PyInstaller para tener un binario instalable y que corra como Servicio de Windows silencioso. (Función 39)
- **PIN de Acceso a PWA:** Bloquear la interfaz web para que nadie en la misma red (o por internet) pueda entrar sin clave. (Función 26)
- **Dominio Propio Cloudflare:** Configurar el tunnel a `tudominio.com` fijo. (Función 31)
- **Base de Datos SQLite:** Reemplazar los JSON por una DB estructurada y robusta. (Función 37)
- **Alertas de Inicio de Sesión y Modo Stealth:** Telegram bot para avisos, y un "botón del pánico" para ocultar todo. (Funciones 27, 28)
- **Análisis Predictivo / Auto-Debug:** Integrar análisis de Blue Screens (BSOD) y leer `LibreHardwareMonitor` de forma experta. (Funciones 2, 44, 50)
- **Contenedores y Actualizaciones OTA:** Correr partes en Docker (WSL2) y permitir auto-actualización vía Git. (Funciones 35, 36)

---

## Próximos Pasos (Sugerencia de Acción)
Para mantener el flujo, sugiero que empecemos por programar el **Portapapeles Universal** y el **Buzón en el PWA**. Son cambios a nivel de código (`main.py` y el HTML) que no requieren instalar nada extra en tu PC y te darán valor inmediato.

¿Damos luz verde para iniciar con la FASE 1?
