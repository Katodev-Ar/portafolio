# SerenityStaff Lite — ESP32-S3 Edition

Bot de gestión de staff de Bloom Scans adaptado para MicroPython en ESP32-S3,
usando Google Apps Script como puente para Sheets y Drive.

---

## Estructura de archivos

```
ESP32_Staff_Bot/
├── config.py         ← ⚠️ EDITAR PRIMERO (WiFi, tokens, IDs)
├── main.py           ← Loop principal del ESP32
├── wifi_manager.py   ← Conexión WiFi
├── gas_client.py     ← Cliente HTTP para Google Apps Script
├── discord_http.py   ← Cliente REST de Discord
├── helpers.py        ← Funciones puras (sin IO)
├── comandos.py       ← Lógica de comandos del staff
├── coordinador.py    ← Lógica de coordinación + Drive
└── Code.gs           ← Apps Script (copiar al editor de GAS)
```

---

## Arquitectura

```
Discord ──webhook──► Google Apps Script (GAS)
                           │
                           │  Stores in "PendingCmds" sheet
                           ▼
                     ESP32-S3 polls GAS every 5s
                           │
                    dispatch() → comandos.py / coordinador.py
                           │
                    gas_client.py → GAS → Sheets / Drive
                           │
                    discord_http.py → Discord REST API
```

El ESP32 **no recibe WebSocket**. El GAS actúa como cola de mensajes.

---

## Configuración paso a paso

### 1. Google Apps Script

1. Abre el Spreadsheet de Bloom Scans.
2. **Extensiones → Apps Script**.
3. Pega el contenido de `Code.gs` en el editor.
4. En la línea `SPREADSHEET_ID`, verifica que sea `1U_28Ggvm_ulCnpXASBkhzXH3VTBt79dCUS8gxRgWINk`.
5. Pon tu Bot Token en `DISCORD_BOT_TOKEN`.
6. **Implementar → Nueva implementación** → Tipo: Aplicación web.
   - Ejecutar como: **Yo**
   - Quién tiene acceso: **Cualquier usuario**
7. Copia la URL del deployment (ya tienes una: la del enunciado).

### 2. Hojas de Google Sheets requeridas

Crea estas hojas si no existen (los nombres son exactos):

| Hoja          | Columnas                                                                               |
|---------------|----------------------------------------------------------------------------------------|
| Series        | Nombre, Canal_ID, Link_Drive, Folder_ID, Categoria, Idioma, Fecha_Agregada, Admin_ID, Admin_Nombre |
| Asignaciones  | Proyecto, Capítulo, Tarea, Usuario, Estado, ID_Usuario                                |
| Registro      | Fecha, Usuario, Proyecto, Capítulo, Tarea, ID_Usuario                                 |
| Usuarios      | user_id, last_msg, ausencia_hasta                                                      |
| Apodos        | user_id, apodo                                                                         |
| Config        | clave, valor → agregar fila: `ticket_count` / `0`                                    |
| PendingCmds   | id, command, interaction_id, interaction_token, user_id, user_name, channel_id, guild_id, roles, is_admin, options, processed, created_at |

### 3. Discord — Registrar Slash Commands

Los slash commands deben registrarse **una vez** en Discord via la API.
Ejecuta este script Python en tu PC (solo una vez):

```python
import requests, json

TOKEN = "TU_BOT_TOKEN"
APP_ID = "TU_APPLICATION_ID"
GAS_URL = "https://script.google.com/macros/s/AKfycby36VIxUtlFdc3kQnU0GEI2Sg6K0O_QhT_P1mLGFFKvMB0lNdvjkvQGqSq1Uf9BeOJk/exec"

headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

commands = [
    {"name": "terminado", "description": "Registra un capítulo finalizado",
     "options": [
       {"name":"rol","type":3,"description":"Tu rol","required":True,"choices":[
         {"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
       {"name":"serie","type":7,"description":"Canal de la serie","required":True},
       {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
     ]},
    {"name": "trabajos", "description": "Muestra tus trabajos del mes"},
    {"name": "ausente", "description": "Registra tu ausencia",
     "options": [
       {"name":"dias","type":4,"description":"Días de ausencia","required":True},
       {"name":"motivo","type":3,"description":"Motivo","required":True},
     ]},
    {"name": "cancelar_ausencia", "description": "Cancela tu ausencia"},
    {"name": "apodo", "description": "Configura tu nombre artístico",
     "options": [{"name":"nombre","type":3,"description":"Tu apodo","required":True}]},
    {"name": "posibles_ganadores", "description": "Ranking mensual actual"},
    {"name": "helps", "description": "Muestra los comandos disponibles"},
    {"name": "asignarme", "description": "Asígnate a un capítulo disponible",
     "options": [
       {"name":"tarea","type":3,"description":"Tarea","required":True,"choices":[
         {"name":"Clean","value":"Clean"},{"name":"Traducción","value":"Traduccion"},{"name":"Edición","value":"Edicion"}]},
       {"name":"categoria","type":3,"description":"Categoría","required":True,"choices":[
         {"name":"+15","value":"+15"},{"name":"+19","value":"+19"},{"name":"BL","value":"BL"}]},
       {"name":"idioma","type":3,"description":"Idioma","required":False,"choices":[
         {"name":"Inglés","value":"Ingles"},{"name":"Coreano","value":"Coreano"},{"name":"Sin preferencia","value":"cualquiera"}]},
     ]},
    {"name": "asignar", "description": "ADMIN: Asigna a un miembro",
     "options": [
       {"name":"usuario","type":6,"description":"Miembro","required":True},
       {"name":"tarea","type":3,"description":"Tarea","required":True,"choices":[
         {"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
       {"name":"serie","type":7,"description":"Canal de la serie","required":True},
       {"name":"capitulo","type":3,"description":"Capítulo","required":True},
     ]},
    {"name": "cancelar_asignacion", "description": "ADMIN: Cancela una asignación",
     "options": [
       {"name":"serie","type":7,"description":"Canal","required":True},
       {"name":"capitulo","type":3,"description":"Capítulo","required":True},
       {"name":"tarea","type":3,"description":"Tarea","required":True,"choices":[
         {"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
     ]},
    {"name": "estado_serie", "description": "Estado de producción de una serie",
     "options": [{"name":"serie","type":7,"description":"Canal","required":True}]},
    {"name": "actualizar_drive", "description": "Fuerza actualización del Drive",
     "options": [{"name":"serie","type":7,"description":"Canal","required":True}]},
    {"name": "agregar_serie", "description": "ADMIN: Agrega nueva serie",
     "options": [
       {"name":"canal","type":7,"description":"Canal","required":True},
       {"name":"link_drive","type":3,"description":"URL del Drive","required":True},
       {"name":"categoria","type":3,"description":"Categoría","required":True,"choices":[
         {"name":"+15","value":"+15"},{"name":"+19","value":"+19"},{"name":"BL","value":"BL"}]},
       {"name":"idioma","type":3,"description":"Idioma","required":True,"choices":[
         {"name":"Inglés","value":"Ingles"},{"name":"Coreano","value":"Coreano"},{"name":"Ambos","value":"Ambos"}]},
     ]},
]

# Registrar globalmente (tarda ~1 hora en propagarse)
r = requests.put(
    f"https://discord.com/api/v10/applications/{APP_ID}/commands",
    headers=headers, json=commands
)
print(r.status_code, r.json())
```

### 4. Cloudflare Worker (Proxy de Seguridad)

Discord **exige** validar firmas criptográficas Ed25519 para webhooks, y Apps Script no lo soporta nativamente. Usaremos un Cloudflare Worker gratuito como puente.

1. Crea una cuenta gratuita en [Cloudflare Workers](https://workers.cloudflare.com/).
2. Haz clic en **Create Application** → **Create Worker**.
3. Ponle un nombre (ej. `bloom-bot-proxy`) y haz clic en **Deploy**.
4. Haz clic en **Edit code**.
5. Reemplaza todo el código por el contenido del archivo `cloudflare_worker.js`.
6. Haz clic en **Save and deploy**.
7. En el menú lateral izquierdo de tu Worker, ve a **Settings** → **Variables**.
8. Añade dos **Environment Variables** (en texto plano):
   - `DISCORD_PUBLIC_KEY`: Pega aquí tu **PUBLIC KEY** del Discord Developer Portal.
   - `GAS_URL`: Pega aquí la **URL de tu Google Apps Script** (la que termina en `/exec`).
9. Guarda y copia la **URL de tu Cloudflare Worker** (ej. `https://bloom-bot-proxy.tu-usuario.workers.dev`).

### 5. Discord — Configurar Webhook URL

En el [Portal de Desarrolladores de Discord](https://discord.com/developers/applications/):
- Ve a **General Information**.
- Pega la URL de tu **Cloudflare Worker** en el campo **INTERACTIONS ENDPOINT URL**.
- Guarda los cambios. (Discord enviará un PING al Worker, que validará la firma y responderá automáticamente).

### 6. ESP32-S3 — Flashear MicroPython

1. Descarga el firmware de MicroPython para ESP32-S3 desde:
   `https://micropython.org/download/ESP32_GENERIC_S3/`

2. Flashea con `esptool`:
   ```bash
   esptool.py --chip esp32s3 erase_flash
   esptool.py --chip esp32s3 write_flash -z 0 ESP32_GENERIC_S3-SPIRAM-vX.Y.Z.bin
   ```

3. Sube los archivos con `mpremote` o **Thonny**:
   ```bash
   mpremote cp config.py :config.py
   mpremote cp wifi_manager.py :wifi_manager.py
   mpremote cp gas_client.py :gas_client.py
   mpremote cp discord_http.py :discord_http.py
   mpremote cp helpers.py :helpers.py
   mpremote cp comandos.py :comandos.py
   mpremote cp coordinador.py :coordinador.py
   mpremote cp main.py :main.py
   ```

4. Edita `config.py` con tus datos **antes** de subirlo.

5. Reinicia el ESP32 y monitorea la consola serial:
   ```bash
   mpremote connect /dev/ttyUSB0
   ```
   Verás:
   ```
   ========================================
     SerenityStaff Lite — ESP32-S3
     MicroPython + GAS Bridge
   ========================================
   [WiFi] Conectando a 'TU_SSID'...
   [WiFi] Conectado. IP: 192.168.x.x
   [main] Sistema listo. Iniciando polling...
   ```

---

## Relay de PC (opcional)

Si quieres controlar el encendido de una PC:

1. Conecta el relay al pin definido en `config.py` → `RELAY_PIN = 4`.
2. Usa el comando `/relay_pc` desde Discord (solo admins).
3. El relay se activa por 500ms (simula pulso del botón de encendido).

---

## Comandos disponibles

### Staff
| Comando | Descripción |
|---------|-------------|
| `/terminado` | Registra un capítulo finalizado |
| `/abandonar` | Libera una tarea asignada |
| `/trabajos` | Muestra tus caps del mes |
| `/ausente` | Registra tu ausencia |
| `/cancelar_ausencia` | Cancela tu ausencia |
| `/apodo` | Configura nombre artístico |
| `/asignarme` | Auto-asignación |
| `/posibles_ganadores` | Ranking actual |
| `/helps` | Guía de comandos |

### Admin/Coordinador
| Comando | Descripción |
|---------|-------------|
| `/asignar` | Asigna un miembro a una tarea |
| `/cancelar_asignacion` | Cancela una asignación |
| `/estado_serie` | Estado de producción |
| `/actualizar_drive` | Sincroniza desde Drive |
| `/agregar_serie` | Agrega nueva serie |

---

## Notas técnicas

- **No hay SQLite local** en el ESP32. Toda la persistencia es en Google Sheets vía GAS.
- El **polling es cada 5 segundos** por defecto. Ajusta `POLL_INTERVAL_S` en `main.py`.
- Las **tareas periódicas** (Drive sync, reporte semanal, alerta de inactividad) se ejecutan con `utime.time()` como timer, sin asyncio.
- Si el ESP32 se queda sin memoria (`MemoryError`), `gc.collect()` se llama automáticamente.
- La hoja `PendingCmds` actúa como cola. Se puede limpiar manualmente borrando filas `processed=TRUE`.
