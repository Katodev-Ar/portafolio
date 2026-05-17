# 📖 Gemini Manga Summary — Plugin de WordPress

Plugin que genera automáticamente un **resumen de ~500 palabras** de cada capítulo de manga usando **Google Gemini Vision**, y lo muestra debajo de la sección de comentarios.

---

## 🚀 Instalación

1. Sube la carpeta `gemini-manga-summary/` a `/wp-content/plugins/`
2. Activa el plugin desde **WordPress Admin → Plugins**
3. Ve a **Ajustes → Gemini Summary** y configura:
   - Tu **API Key de Google Gemini** (obtenla en https://aistudio.google.com/app/apikey)
   - El **modelo** (se recomienda `gemini-1.5-flash` por velocidad y costo)
   - El **post_type** de tus capítulos
   - El **prompt** (puedes dejarlo por defecto)

---

## ⚙️ Compatibilidad con tus plugins

El plugin detecta imágenes del capítulo en este orden de prioridad:

| Método | Descripción |
|--------|-------------|
| **A** | Meta `ero_chapter_images` (usado en `single-chapter-mcm.php`) |
| **B** | Attachments adjuntos al post |
| **C** | Carpeta `/uploads/capitulos/cap-{ID}/` ← **tu manga-uploads-organizer** ✅ |
| **D** | Metas genéricas: `chapter_images`, `_images`, `ts_reader_img` |

Tu plugin `manga-uploads-organizer` guarda las imágenes en `/capitulos/cap-{ID}/`, así que el **método C** lo detectará automáticamente.

---

## 🔄 Flujo automático

```
Admin sube ZIP con imágenes
        ↓
Plugin manga-uploads-organizer extrae imágenes → /uploads/capitulos/cap-{ID}/
        ↓
Se publica el capítulo (post_status → publish)
        ↓
gemini-manga-summary detecta la transición
        ↓
Se programa tarea asíncrona (WP Cron, 2 segundos después)
        ↓
Se leen las imágenes y se envían a Gemini en base64
        ↓
Gemini devuelve el resumen de 500 palabras
        ↓
Se guarda en post_meta: _gms_chapter_summary
        ↓
Se muestra debajo de los comentarios del capítulo ✅
```

---

## 🎨 Dónde aparece el resumen

El resumen se muestra **automáticamente debajo de los comentarios** de cada capítulo, sin necesidad de modificar el tema.

También puedes insertarlo manualmente en cualquier lugar con el shortcode:
```
[gms_summary]
[gms_summary id="1234"]
```

---

## 🔧 Configuración del post_type

Si tu tema MangaReader usa un post_type diferente, ajústalo en los ajustes del plugin.

Valores comunes:
- `wp-manga-chapter` — MangaPress / Madara
- `post` — si los capítulos son posts normales
- `chapter` — algunos temas personalizados

Para encontrar el post_type de tus capítulos, instala un plugin como **Show Current Template** o revisa el código del tema.

---

## ⚡ Generación manual

En la página de ajustes hay una sección para **regenerar el resumen** de cualquier capítulo introduciendo su ID de WordPress. Útil para capítulos ya publicados antes de instalar el plugin.

---

## 📊 Costos estimados (Gemini 1.5 Flash)

| Páginas por capítulo | Costo aproximado |
|----------------------|-----------------|
| 20 páginas           | ~$0.002         |
| 40 páginas           | ~$0.004         |
| 60 páginas (límite)  | ~$0.006         |

*Precios aproximados. Consulta https://ai.google.dev/pricing*

---

## 🐛 Solución de problemas

**El resumen no aparece:**
- Verifica que la API Key sea correcta en Ajustes → Gemini Summary
- Comprueba que el post_type coincide con el de tus capítulos
- Usa la herramienta de regeneración manual para probar
- Activa `WP_DEBUG` y revisa `/wp-content/debug.log`

**Timeout en la generación:**
- El plugin tiene timeout de 120 segundos
- Si falla, genera manualmente desde los ajustes del plugin
- Considera reducir páginas enviadas (por defecto máximo 60)

**Las imágenes no se detectan:**
- Verifica que la carpeta `/uploads/capitulos/cap-{ID}/` existe con imágenes
- Prueba la regeneración manual con el ID del capítulo

---

## 📁 Estructura del plugin

```
gemini-manga-summary/
├── gemini-manga-summary.php   ← Plugin principal
├── comments-wrapper.php       ← Template wrapper para comentarios
└── README.md                  ← Este archivo
```
