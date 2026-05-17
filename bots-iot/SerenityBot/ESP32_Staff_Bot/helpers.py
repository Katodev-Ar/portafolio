# helpers.py — Funciones de utilidad puras (sin IO), portables a MicroPython
# ============================================================

import re


def parsear_capitulos(texto: str) -> list:
    """
    Parsea un string de capítulos que puede ser:
    - Un solo cap: "5" → ["5"]
    - Un rango: "1-5" → ["1","2","3","4","5"]
    - Una lista: "1,3,7" → ["1","3","7"]
    - Combinación: "1-3,7,10-12" → ["1","2","3","7","10","11","12"]
    """
    resultado = []
    texto = str(texto or "").strip()
    partes = [p.strip() for p in texto.split(",") if p.strip()]
    for parte in partes:
        if "-" in parte:
            extremos = parte.split("-", 1)
            try:
                inicio = int(extremos[0])
                fin = int(extremos[1])
                for i in range(inicio, fin + 1):
                    resultado.append(str(i))
            except ValueError:
                resultado.append(parte)
        else:
            resultado.append(parte)
    return resultado if resultado else [texto]

# ─────────────────────────────────────────
#  NORMALIZACIÓN DE TAREAS
# ─────────────────────────────────────────

_TAREA_EQUIV = {
    "Clean":      "Cleaner",
    "Cleaner":    "Cleaner",
    "Traduccion": "Traductor",
    "Traductor":  "Traductor",
    "Edicion":    "Editor",
    "Editor":     "Editor",
}

def normalizar_tarea(tarea: str) -> str:
    return _TAREA_EQUIV.get(str(tarea or "").strip(), str(tarea or "").strip())


# Mapeo inverso: de nombre "display" al nombre de columna del Sheet
_TAREA_A_COLUMNA = {
    "Cleaner":   "Clean",
    "Clean":     "Clean",
    "Traductor": "Traduccion",
    "Traduccion":"Traduccion",
    "Editor":    "Edicion",
    "Edicion":   "Edicion",
}

def tarea_a_columna_sheet(tarea: str) -> str:
    return _TAREA_A_COLUMNA.get(str(tarea or "").strip(), str(tarea or "").strip())


# ─────────────────────────────────────────
#  NÚMEROS DE CAPÍTULO
# ─────────────────────────────────────────

_PATRONES_CAP = [
    r'(?:cap(?:itulo)?|chapter|ch|episodio|ep)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)',
    r'(?:traduccion|traduccion|trad|clean|clrd|edicion|edicion|type|recorte|raw)\s*[:#-]?\s*(\d+(?:[.-]\d+)?)',
    r'(\d+(?:[.-]\d+)?)',
]

def extraer_numero_cap(nombre: str) -> str:
    """
    Extrae el número de capítulo de un string.
    Ej: 'Chapter_40-5' → '40-5', 'Clean_15' → '15', '34' → '34'
    """
    texto = re.sub(r'\.[a-zA-Z0-9]+$', '', str(nombre or '')).strip()
    if not texto:
        return ""
    texto_low = texto.lower().replace('_', ' ')
    for patron in _PATRONES_CAP:
        m = re.search(patron, texto_low)
        if m:
            return m.group(1).replace('.', '-')
    return texto.strip()


def caps_coinciden(cap_a: str, cap_b: str) -> bool:
    return extraer_numero_cap(str(cap_a)) == extraer_numero_cap(str(cap_b))


def ordenar_cap(cap: str) -> tuple:
    """Clave de ordenamiento numérico para caps con subíndices (ej: '40-5')."""
    partes = str(cap).split('-')
    try:
        return (int(partes[0]), int(partes[1]) if len(partes) > 1 else 0)
    except Exception:
        return (0, 0)


# ─────────────────────────────────────────
#  NORMALIZACIÓN DE NOMBRES
# ─────────────────────────────────────────

def series_coinciden(a: str, b: str) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


def normalizar_nombre_drive(nombre: str) -> str:
    """Quita tildes y pasa a minúsculas (versión MicroPython sin unicodedata)."""
    # MicroPython no tiene unicodedata; hacemos un mapa manual de los más comunes
    mapa = {
        'á':'a','é':'e','í':'i','ó':'o','ú':'u',
        'Á':'a','É':'e','Í':'i','Ó':'o','Ú':'u',
        'ñ':'n','Ñ':'n','ü':'u','Ü':'u',
    }
    resultado = []
    for ch in str(nombre or ""):
        resultado.append(mapa.get(ch, ch))
    return "".join(resultado).lower().strip()


def carpeta_drive_coincide(etapa: str, nombre_carpeta: str) -> bool:
    nombre_n = normalizar_nombre_drive(nombre_carpeta)
    aliases = {
        "RAW":       ["1_raw"],
        "Clean":     ["2_clrd", "2_clean"],
        "Traduccion":["3_traduccion", "3_tl", "tl"],
        "Edicion":   ["4_type", "4_ts", "ts"],
        "Recorte":   ["5_recortes"],
    }
    return any(a in nombre_n for a in aliases.get(etapa, []))


# ─────────────────────────────────────────
#  CATEGORÍA / IDIOMA
# ─────────────────────────────────────────

def normalizar_categoria(valor: str) -> str:
    t = str(valor or "").strip()
    if t in {"15", "+15"}:
        return "+15"
    if t in {"19", "+19"}:
        return "+19"
    return t


def normalizar_idioma(valor: str) -> str:
    equiv = {
        "ingles": "Ingles", "inglés": "Ingles",
        "coreano": "Coreano",
        "ambos": "Ambos",
    }
    return equiv.get(str(valor or "").strip().lower(), str(valor or "").strip())


# ─────────────────────────────────────────
#  ASIGNACIONES
# ─────────────────────────────────────────

def fila_asignacion_coincide(fila: dict, proyecto: str, capitulo: str,
                              tarea: str = None, usuario_id=None,
                              estado: str = None,
                              incluir_terminadas: bool = True) -> bool:
    if not series_coinciden(fila.get('Proyecto', ''), proyecto):
        return False
    cap_fila = fila.get('Capitulo', fila.get('Capítulo', ''))
    if not caps_coinciden(cap_fila, capitulo):
        return False
    if tarea is not None:
        if normalizar_tarea(fila.get('Tarea')) != normalizar_tarea(tarea):
            return False
    if usuario_id is not None and str(fila.get('ID_Usuario', '')) != str(usuario_id):
        return False
    if estado is not None and fila.get('Estado') != estado:
        return False
    if not incluir_terminadas and fila.get('Estado') == "Terminado":
        return False
    return True


def fila_registro_coincide(fila: dict, proyecto: str, capitulo: str,
                            tarea: str = None, usuario_id=None) -> bool:
    if not series_coinciden(fila.get('Proyecto', ''), proyecto):
        return False
    cap_fila = fila.get('Capitulo', fila.get('Capítulo', ''))
    if not caps_coinciden(cap_fila, capitulo):
        return False
    if tarea is not None and fila.get('Tarea') != tarea:
        return False
    if usuario_id is not None and str(fila.get('ID_Usuario', '')) != str(usuario_id):
        return False
    return True


# ─────────────────────────────────────────
#  FECHAS (sin datetime, MicroPython-safe)
# ─────────────────────────────────────────

def timestamp_now_iso(rtc=None) -> str:
    """
    Retorna timestamp ISO si se pasa un objeto RTC de MicroPython,
    o una cadena vacía como fallback.
    """
    if rtc is None:
        try:
            import utime
            t = utime.localtime()
            return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*t[:6])
        except Exception:
            return ""
    try:
        dt = rtc.datetime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            dt[0], dt[1], dt[2], dt[4], dt[5], dt[6]
        )
    except Exception:
        return ""


def fecha_hoy(rtc=None) -> str:
    """Retorna 'YYYY-MM-DD'."""
    ts = timestamp_now_iso(rtc)
    return ts[:10] if ts else ""


def parse_fecha_mes_anio(fecha_iso: str) -> tuple:
    """Extrae (mes, anio) de 'YYYY-MM-DD HH:MM:SS'."""
    try:
        partes = fecha_iso[:10].split('-')
        return int(partes[1]), int(partes[0])
    except Exception:
        return 0, 0


def filtrar_registros_por_mes(registros: list, mes: int, anio: int) -> list:
    resultado = []
    for reg in registros:
        f = str(reg.get('Fecha', ''))
        if not f:
            continue
        m, a = parse_fecha_mes_anio(f)
        if m == mes and a == anio:
            resultado.append(reg)
    return resultado


# ─────────────────────────────────────────
#  RANKING
# ─────────────────────────────────────────

def calcular_ranking(registros: list) -> list:
    """
    Retorna lista ordenada de dicts:
    [{"user_id": ..., "nombre": ..., "count": ...}, ...]
    """
    temp = {}
    for reg in registros:
        uid = str(reg.get('ID_Usuario', ''))
        if not uid:
            continue
        if uid not in temp:
            temp[uid] = {"user_id": uid, "nombre": reg.get('Usuario', ''), "count": 0}
        temp[uid]["count"] += 1
    return sorted(temp.values(), key=lambda x: -x["count"])


# ─────────────────────────────────────────
#  REGEX HELPERS
# ─────────────────────────────────────────

def extraer_folder_id(link: str) -> str:
    """Extrae el ID de una carpeta de Drive desde su URL."""
    patrones = [
        r'folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
    ]
    for p in patrones:
        m = re.search(p, str(link or ''))
        if m:
            return m.group(1)
    return ""


# ─────────────────────────────────────────
#  NOMBRES DE MESES
# ─────────────────────────────────────────

_MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

def nombre_mes(num: int) -> str:
    return _MESES[num] if 1 <= num <= 12 else str(num)
