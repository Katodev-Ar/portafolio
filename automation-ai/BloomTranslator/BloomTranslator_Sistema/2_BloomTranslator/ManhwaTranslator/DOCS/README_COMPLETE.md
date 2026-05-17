# 🌸 MANHWA TRANSLATOR - SISTEMA COMPLETO

## 📦 COMPONENTES DEL SISTEMA

```
manhwa-translator/
├── server_COMPLETE.py         # Servidor Flask (Render)
├── app_desktop_COMPLETE.py    # Aplicación Desktop
├── credentials.json           # Credenciales Google (crear)
├── models/                    # Modelos para Clean
│   ├── noise0_scale2_0x_model.bin
│   ├── noise0_scale2_0x_model.param
│   └── ... (todos los modelos)
└── requirements.txt           # Dependencias
```

---

## 🚀 INSTALACIÓN

### 1. SERVIDOR (Render.com)

```bash
# 1. Subir server_COMPLETE.py a Render
# 2. Configurar variables de entorno:
GEMINI_API_KEY=tu_api_key_de_gemini

# 3. El servidor se auto-inicializa con SQLite
```

### 2. DESKTOP APP

#### Opción A: Ejecutar con Python

```bash
pip install pillow requests opencv-python numpy google-auth-oauthlib google-api-python-client

python app_desktop_COMPLETE.py
```

#### Opción B: Compilar a .EXE

```bash
# Instalar PyInstaller
pip install pyinstaller

# Crear carpeta models con los archivos .bin y .param
mkdir models
# Copiar todos los modelos a la carpeta models

# Compilar
pyinstaller --onefile --windowed \
  --add-data "models:models" \
  --name "ManhwaTranslator" \
  app_desktop_COMPLETE.py

# El .exe estará en dist/ManhwaTranslator.exe
```

---

## 🔑 CONFIGURACIÓN GOOGLE DRIVE

### Paso 1: Crear Proyecto en Google Cloud

1. Ve a: https://console.cloud.google.com
2. Crea nuevo proyecto: "Manhwa Translator"
3. Activa Google Drive API
4. Ve a "Credenciales" → "Crear credenciales" → "OAuth 2.0"
5. Tipo de aplicación: "Aplicación de escritorio"
6. Descarga el JSON como `credentials.json`
7. Coloca `credentials.json` junto al .exe

### Paso 2: Configurar URL de Redirección

```
URIs de redirección autorizados:
http://localhost:8080/
```

---

## 💰 SISTEMA DE CRÉDITOS

| Acción | Costo |
|--------|-------|
| Cargar imágenes | **GRATIS** |
| OCR | **1 crédito POR IMAGEN** |
| Clean | **1 crédito POR IMAGEN** |
| Exportar coordenadas | **1 crédito TOTAL** |
| Crear conjunto etiquetas | **1 crédito TOTAL** |
| Traducir | Variable (según longitud) |

---

## 👥 USUARIOS Y MODOS

### MODO LOCAL (Usuarios Normales)

**¿Quién?** Cualquier scan que compre licencia

**Características:**
- ✅ Cargar imágenes desde PC
- ✅ Crear conjuntos de etiquetas ilimitados
- ✅ Exportar todo localmente
- ✅ Sin restricciones

**Flujo:**
```
1. Abrir app → Modo Local
2. Cargar imágenes desde PC
3. Seleccionar áreas / Auto OCR
4. Ejecutar OCR
5. Traducir
6. (Opcional) Clean
7. (Opcional) Exportar coordenadas
8. Exportar todo
```

### MODO BLOOM STAFF

**¿Quién?** Tu equipo de traducción

**Características:**
- ✅ Login con Google Drive obligatorio
- ✅ Solo series que TÚ agregues
- ✅ Guardar directo en Drive
- ❌ NO pueden cargar imágenes locales
- ✅ Crear sus propias etiquetas

**Flujo:**
```
1. Abrir app → Modo Bloom Staff
2. Login con Google
3. Seleccionar serie (que tú agregaste)
4. Seleccionar capítulo (1-999)
5. App descarga imágenes de RAW/
6. Trabajar (OCR, traducir, etc.)
7. Guardar en Drive → TRADUCCION/
```

**Estructura del Drive:**
```
Serie X/
├── RAW/ (o 1_RAW/)
│   ├── 1/
│   │   ├── 01.jpg
│   │   ├── 02.jpg
│   ├── 7/
│   │   ├── 01.jpg
│   │   ├── 02.jpg
├── TRADUCCION/ (o 2_TRADUCCION/)
    ├── Traduccion_1.txt
    ├── Transcripcion_1.txt
    ├── Traduccion_7.txt
```

---

## 🏷️ SISTEMA DE ETIQUETAS

### ¿Qué son?

Marcadores que se insertan al **inicio de cada línea** para clasificar el tipo de texto:

- **D:** Diálogo
- **P:** Pensamiento
- **C:** Cartelera
- **N:** Narración
- **G:** Gritos
- etc.

### ¿Para qué sirven?

Al exportar coordenadas JSON, el script de Photoshop lee las etiquetas y aplica **fuentes diferentes automáticamente**.

### Crear Conjunto

```
1. Ajustes → Etiquetas → Crear Conjunto
2. Nombre: "+15"
3. Costo: 1 crédito
4. Agregar hasta 15 etiquetas:
   - D: [F1] Diálogo
   - P: [F2] Pensamiento
   - C: [F3] Cartelera
   - ...
5. Guardar
```

### Usar Etiquetas

```
Estás en transcripción:
1. Hola como estas█

Presionas F1 o click en botón "D:"

Resultado:
1. D: Hola como estas
2. █ (cursor en siguiente línea)

Si había P: y presionas D:
ANTES: 1. P: Hola
DESPUÉS: 1. D: Hola
```

### Atajos de Teclado

- F1-F12 configurables
- Funciona en Transcripción y Traducción
- Auto-avanza a siguiente línea

---

## 📤 EXPORTACIÓN

### 1. Exportar Todo (.txt)

Genera archivo con formato:

```
==========================================================
MANHWA TRANSLATOR - EXPORTACIÓN COMPLETA
Fecha: 2025-02-24 15:30:00
Total de imágenes: 3
Total de bloques: 45
==========================================================

┌────────────────────────────────────────────────────────┐
│                TRANSCRIPCIÓN ORIGINAL                  │
└────────────────────────────────────────────────────────┘

=== 01.jpg ===
1. Texto original
2. Más texto...

┌────────────────────────────────────────────────────────┐
│                    TRADUCCIÓN                          │
└────────────────────────────────────────────────────────┘

1. D: Texto traducido
2. P: Más texto...

┌────────────────────────────────────────────────────────┐
│                     GLOSARIO                           │
└────────────────────────────────────────────────────────┘

- Protagonista: Sofia
...
```

### 2. Exportar Coordenadas (.json)

**Costo: 1 crédito**

Genera JSON con posiciones exactas:

```json
{
  "timestamp": "2025-02-24T15:30:00",
  "total_images": 3,
  "images": [
    {
      "filename": "01.jpg",
      "selections": [
        {
          "id": 1,
          "x": 100,
          "y": 200,
          "width": 300,
          "height": 50,
          "text": "Hola",
          "tag": "D:",
          "translated": "D: Hello"
        }
      ]
    }
  ]
}
```

### 3. Guardar en Drive (Solo Staff)

- Sube directo a carpeta `TRADUCCION/`
- Pregunta qué guardar: Transcripción / Traducción / Ambas
- Formato: `Traduccion_7.txt`, `Transcripcion_7.txt`

---

## 🧹 FUNCIÓN CLEAN

### ¿Qué hace?

Elimina el texto de las imágenes usando inpainting AI.

### Costo

1 crédito por imagen

### Resultado

ZIP con imágenes limpias:
```
cleaned_images_20250224_153045.zip
├── cleaned_01.jpg
├── cleaned_02.jpg
└── cleaned_03.jpg
```

### Calidad

Usa OpenCV inpainting básico. Para mejor calidad, necesitarías modelos ncnn.

---

## 🎮 CONTROLES

| Acción | Control |
|--------|---------|
| Crear selección | Click izquierdo + arrastrar |
| Borrar selección | Click derecho sobre área |
| Zoom In | Ctrl + Scroll arriba |
| Zoom Out | Ctrl + Scroll abajo |
| Siguiente imagen | Scroll abajo al final |
| Imagen anterior | Scroll arriba al inicio |
| Insertar etiqueta | F1-F12 (según configuración) |

---

## 📚 GESTIÓN DE SERIES (Admin)

### Agregar Serie

**Endpoint:** `POST /api/series/add`

```json
{
  "admin_key": "TU_LICENCIA_ADMIN",
  "name": "Para tu final perfecto",
  "drive_link": "https://drive.google.com/drive/folders/FOLDER_ID"
}
```

### Eliminar Serie

**Endpoint:** `POST /api/series/delete`

```json
{
  "admin_key": "TU_LICENCIA_ADMIN",
  "series_id": 1
}
```

### Listar Series

**Endpoint:** `POST /api/series/list`

```json
{
  "key": "LICENCIA_STAFF"
}
```

---

## 🔐 LICENCIAS

### Crear Licencia Principal

```sql
INSERT INTO licenses (key, type, credits, is_staff)
VALUES ('BLOOM-MAIN-001', 'Professional', 1000, 1);
```

### Crear Licencia Usuario Normal

```sql
INSERT INTO licenses (key, type, credits, is_staff)
VALUES ('USER-001', 'Basic', 100, 0);
```

### Crear Clave de Recarga

```sql
INSERT INTO reload_keys (key, credits, used)
VALUES ('RELOAD-100', 100, 0);
```

---

## ⚠️ SOLUCIÓN DE PROBLEMAS

### "Timeout" al validar licencia

→ Servidor Render despertando. Espera 60 segundos.

### "Archivo credentials.json no encontrado"

→ Descarga credenciales de Google Cloud Console.

### "No se encontró carpeta RAW"

→ Verifica estructura del Drive: `RAW/` o `1_RAW/`

### Selecciones lentas

→ Reduce zoom antes de seleccionar.

### Imágenes en desorden

→ Usa nombres: 01.jpg, 02.jpg, 03.jpg

---

## 📊 BASE DE DATOS

### Tablas

- **licenses**: Licencias principales
- **reload_keys**: Claves de recarga
- **series**: Series disponibles (staff)
- **usage_log**: Registro de uso

### Consultas Útiles

```sql
-- Ver todas las licencias
SELECT * FROM licenses;

-- Ver series disponibles
SELECT * FROM series;

-- Ver uso de créditos
SELECT license_key, action, credits_spent, timestamp
FROM usage_log
ORDER BY timestamp DESC
LIMIT 100;
```

---

## 🚀 DEPLOYMENT

### Servidor (Render)

1. Conecta repo Git
2. Build command: `pip install -r requirements.txt`
3. Start command: `python server_COMPLETE.py`
4. Variables de entorno: `GEMINI_API_KEY`

### Desktop App

1. Compilar con PyInstaller
2. Incluir carpeta `models/`
3. Incluir `credentials.json`
4. Distribuir .exe

---

## 📞 SOPORTE

Si hay problemas:

1. ✅ Verificar conexión a internet
2. ✅ Verificar licencia válida con créditos
3. ✅ Verificar `credentials.json` (para staff)
4. ✅ Verificar estructura del Drive
5. ✅ Revisar logs del servidor

---

**¡Sistema completo listo para producción!** 🎉
