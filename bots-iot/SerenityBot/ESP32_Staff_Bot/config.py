# config.py — Configuración central del bot ESP32
# ============================================================
# EDITA ESTE ARCHIVO CON TUS DATOS ANTES DE FLASHEAR AL ESP32
# ============================================================

# --- Wi-Fi ---
WIFI_SSID = "Fliacorbalan"
WIFI_PASSWORD = "Pollofrito"

# --- Google Apps Script ---
GAS_URL = "https://script.google.com/macros/s/AKfycbx01DK4HVjAtr3dSSvW51McjTyGJstuEUl917X9p6238nSGsF4PdpUdg8K6aQPTA2ac/exec"

# --- Discord Bot Token (para enviar mensajes via HTTP a Discord) ---
DISCORD_BOT_TOKEN  = "MTYOUR_DISCORD_BOT_TOKEN"
APPLICATION_ID     = "1502112062971838464"

# --- IDs de Discord ---
ADMIN_CHANNEL_ID       = "1432254360666247168"
AVISOS_CHANNEL_ID      = "1444910811863711825"
STAFF_ROLE_ID          = "1132158706851786854"
CANAL_JUSTIFICACION_ID = "1458363364727328903"
CANAL_TICKET_COMANDO   = "1459418420436013282"
BIENVENIDA_CHANNEL_ID  = "1458357173737361520"
REGLAS_CHANNEL_ID      = "1458360744893481045"
CANAL_CREDITOS_APODO   = "1458363518725390452"
CANAL_ASIGNACIONES_LOG = "1460771399999160442"
CANAL_COORDINADORES_ID = "1483864769239978064"
COORDINADOR_ROLE_ID    = "1460674417460777138"

# --- IDs especiales ---
ITSUKI_ID = "1154257480734490664"

OWNER_SHEET_TITLES = {
    "1154257480734490664": "Itsuki",
    "643559580990701596":  "Kato",
    "1203552106041180220": "Celeste",
    "1123475061664387093": "El pirateador",
}

CANALES_TERMINADOS = [
    "1458345407959797902",
    "1458345512624459951",
    "1458345602151878767",
]

# --- Estructura de producción ---
SERIE_HEADERS = ["Cap", "Idioma", "RAW", "Clean", "Traduccion", "Edicion", "Recorte", "Subido_Web", "Fecha_RAW"]
BLOCK_WIDTH   = 11

CARPETAS_DRIVE = {
    "RAW":       "1_RAW",
    "Clean":     "2_CLRD",
    "Traduccion":"3_TRADUCCION",
    "Edicion":   "4_TYPE",
    "Recorte":   "5_RECORTES",
}

# --- Timing de tareas (segundos) ---
INACTIVIDAD_LOOP_S   = 86400   # 24 horas
REVISION_DRIVE_S     = 43200   # 12 horas
REPORTE_SEMANAL_S    = 604800  # 7 días
HEARTBEAT_S          = 30      # watchdog / keep-alive

# --- Relay GPIO (control de PC, opcional) ---
RELAY_PIN = 4  # Pin GPIO del ESP32-S3 conectado al relay

