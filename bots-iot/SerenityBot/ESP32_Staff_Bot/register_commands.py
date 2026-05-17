"""register_commands.py — Registra los slash commands globalmente en Discord."""
import urllib.request
import json

TOKEN   = "MTYOUR_DISCORD_BOT_TOKEN"
APP_ID  = "1502112062971838464"

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type":  "application/json",
    "User-Agent":    "SerenityBot/1.0",
}

COMMANDS = [
    # ── Staff ────────────────────────────────────
    {
        "name": "terminado", "description": "Registra un capítulo finalizado",
        "options": [
            {"name":"rol","type":3,"description":"Tu rol en el capítulo","required":True,
             "choices":[{"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
            {"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]},
            {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
        ]
    },
    {
        "name": "abandonar", "description": "Libera una tarea asignada",
        "options": [
            {"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]},
            {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
            {"name":"tarea","type":3,"description":"Tarea a abandonar","required":True,
             "choices":[{"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
        ]
    },
    {
        "name": "trabajos", "description": "Muestra tus capítulos del mes",
        "options": [
            {"name":"mes","type":4,"description":"Mes (número)","required":False,
             "choices":[{"name":"Enero","value":1},{"name":"Febrero","value":2},
                        {"name":"Marzo","value":3},{"name":"Abril","value":4},
                        {"name":"Mayo","value":5},{"name":"Junio","value":6},
                        {"name":"Julio","value":7},{"name":"Agosto","value":8},
                        {"name":"Septiembre","value":9},{"name":"Octubre","value":10},
                        {"name":"Noviembre","value":11},{"name":"Diciembre","value":12}]},
        ]
    },
    {
        "name": "mis_trabajos", "description": "Muestra una lista detallada de los trabajos que completaste en un mes",
        "options": [
            {"name":"mes","type":4,"description":"Mes (número)","required":False,
             "choices":[{"name":"Enero","value":1},{"name":"Febrero","value":2},
                        {"name":"Marzo","value":3},{"name":"Abril","value":4},
                        {"name":"Mayo","value":5},{"name":"Junio","value":6},
                        {"name":"Julio","value":7},{"name":"Agosto","value":8},
                        {"name":"Septiembre","value":9},{"name":"Octubre","value":10},
                        {"name":"Noviembre","value":11},{"name":"Diciembre","value":12}]},
            {"name":"anio","type":4,"description":"Año (ej. 2026)","required":False}
        ]
    },
    {
        "name": "ausente", "description": "Registra tu ausencia",
        "options": [
            {"name":"dias","type":4,"description":"Días de ausencia (1-30)","required":True},
            {"name":"motivo","type":3,"description":"Motivo de ausencia","required":True},
        ]
    },
    {"name": "cancelar_ausencia", "description": "Cancela tu ausencia (regresaste antes)"},
    {
        "name": "apodo", "description": "Configura tu nombre artístico para créditos",
        "options": [{"name":"nombre","type":3,"description":"Tu nombre artístico","required":True}]
    },
    {
        "name": "asignarme", "description": "Asígnate automáticamente a un capítulo disponible",
        "options": [
            {"name":"tarea","type":3,"description":"Tarea que buscas","required":True,
             "choices":[{"name":"🧹 Clean","value":"Clean"},{"name":"📝 Traducción","value":"Traduccion"},{"name":"✏️ Edición","value":"Edicion"}]},
            {"name":"categoria","type":3,"description":"Categoría de la serie","required":True,
             "choices":[{"name":"+15","value":"+15"},{"name":"+19","value":"+19"},{"name":"BL","value":"BL"}]},
            {"name":"idioma","type":3,"description":"Idioma preferido","required":False,
             "choices":[{"name":"Inglés","value":"Ingles"},{"name":"Coreano","value":"Coreano"},{"name":"Sin preferencia","value":"cualquiera"}]},
        ]
    },
    {
        "name": "posibles_ganadores", "description": "Muestra el ranking actual del mes",
        "options": [
            {"name":"mes","type":4,"description":"Mes","required":False,
             "choices":[{"name":"Enero","value":1},{"name":"Febrero","value":2},
                        {"name":"Marzo","value":3},{"name":"Abril","value":4},
                        {"name":"Mayo","value":5},{"name":"Junio","value":6},
                        {"name":"Julio","value":7},{"name":"Agosto","value":8},
                        {"name":"Septiembre","value":9},{"name":"Octubre","value":10},
                        {"name":"Noviembre","value":11},{"name":"Diciembre","value":12}]},
        ]
    },
    {
        "name": "creditos", "description": "Staff que trabajó en un capítulo",
        "options": [
            {"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]},
            {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
        ]
    },
    {"name": "helps", "description": "Guía de comandos del staff"},

    # ── Admin / Coordinador ───────────────────────
    {
        "name": "asignar", "description": "ADMIN: Asigna un miembro a una tarea",
        "options": [
            {"name":"usuario","type":6,"description":"Miembro del staff","required":True},
            {"name":"tarea","type":3,"description":"Tarea a asignar","required":True,
             "choices":[{"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
            {"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]},
            {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
        ]
    },
    {
        "name": "ver_asignacion", "description": "ADMIN: Estado de un capítulo",
        "options": [
            {"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]},
            {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
        ]
    },
    {
        "name": "cancelar_asignacion", "description": "ADMIN: Cancela una asignación a la fuerza",
        "options": [
            {"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]},
            {"name":"capitulo","type":3,"description":"Número de capítulo","required":True},
            {"name":"tarea","type":3,"description":"Tarea a cancelar","required":True,
             "choices":[{"name":"Traductor","value":"Traductor"},{"name":"Editor","value":"Editor"},{"name":"Cleaner","value":"Cleaner"}]},
        ]
    },
    {
        "name": "estado_serie", "description": "Estado de producción de una serie",
        "options": [{"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]}]
    },
    {
        "name": "actualizar_drive", "description": "Fuerza actualización desde Drive",
        "options": [{"name":"serie","type":7,"description":"Canal de la serie","required":True,"channel_types":[0,5]}]
    },

    {
        "name": "agregar_serie", "description": "ADMIN: Agrega una nueva serie al sistema",
        "options": [
            {"name":"canal","type":7,"description":"Canal de la serie","required":True, "channel_types": [0, 5]},

            {"name":"link_drive","type":3,"description":"URL de la carpeta en Drive","required":True},
            {"name":"categoria","type":3,"description":"Categoría de la serie","required":True,
             "choices":[{"name":"+15","value":"+15"},{"name":"+19","value":"+19"},{"name":"BL","value":"BL"}]},
            {"name":"idioma","type":3,"description":"Idioma fuente","required":True,
             "choices":[{"name":"Inglés","value":"Ingles"},{"name":"Coreano","value":"Coreano"},{"name":"Ambos","value":"Ambos"}]},
        ]
    },
    {"name": "refrescar_asignaciones", "description": "ADMIN/COORD: Verifica asignaciones en GAS"},
    {
        "name": "mis_asignaciones",
        "description": "Visualiza tus capítulos asignados actuales y su estado",
        "type": 1
    },
    {
        "name": "asignaciones_usuario",
        "description": "ADMIN/COORD: Muestra las asignaciones actuales de un usuario",
        "type": 1,
        "options": [
            {
                "name": "usuario",
                "description": "El usuario a buscar",
                "type": 6,
                "required": True
            }
        ]
    },
    {
        "name": "registrar_correo",
        "description": "Registra tu correo electrónico para tener acceso a los archivos en Drive",
        "type": 1,
        "options": [
            {
                "name": "correo",
                "description": "Tu dirección de correo electrónico (ej. nombre@gmail.com)",
                "type": 3,
                "required": True
            }
        ]
    },
    {
        "name": "quitar_staff",
        "description": "[ADMIN] Revoca accesos de Drive y asignaciones a un usuario que se retira",
        "type": 1,
        "options": [
            {
                "name": "usuario",
                "description": "El usuario al que se le revocarán los accesos",
                "type": 6,
                "required": True
            }
        ]
    },
    {
        "name": "progreso",
        "description": "Visualiza el progreso general de una serie",
        "type": 1,
        "options": [
            {
                "name": "serie_name",
                "description": "Nombre de la serie",
                "type": 3,
                "required": True,
                "autocomplete": True
            }
        ]
    },
    {
        "name": "mi_perfil",
        "description": "Muestra tu perfil de staff, estadísticas y rangos",
        "type": 1
    },
    {
        "name": "limpiar_inactivos",
        "description": "ADMIN: Reporte de staff inactivo (+30 días sin trabajar)",
        "type": 1
    },
    {
        "name": "ticket",
        "description": "Crea un canal privado de soporte (Solo en el canal correspondiente)",
        "type": 1,
        "options": [
            {
                "name": "admin",
                "description": "Selecciona al administrador con quien deseas hablar",
                "type": 6,
                "required": True
            }
        ]
    },
    {
        "name": "dar_bienvenida",
        "description": "ADMIN: Da el rol de staff y envía mensaje de bienvenida",
        "type": 1,
        "options": [
            {
                "name": "usuario",
                "description": "El usuario a dar la bienvenida",
                "type": 6,
                "required": True
            }
        ]
    },
    {
        "name": "finalizar_mes",
        "description": "ADMIN: Genera el ranking de premiación mensual y limpia la hoja de Registro",
        "type": 1,
        "options": [
            {
                "name": "mes",
                "description": "Mes a finalizar (1-12)",
                "type": 4,
                "required": False
            },
            {
                "name": "anio",
            "description": "Año a finalizar (ej. 2026)",
                "type": 4,
                "required": False
            }
        ]
    }
]


def registrar():
    url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"
    data = json.dumps(COMMANDS).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="PUT")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            print(f"OK: {len(result)} comandos registrados exitosamente.")
            for cmd in result:
                print(f"   |- /{cmd['name']} (id: {cmd['id']})")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Error {e.code}: {body}")


if __name__ == "__main__":
    print("Registrando slash commands en Discord...")
    registrar()

