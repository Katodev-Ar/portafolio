# gas_client.py — Cliente HTTP para Google Apps Script (GAS)
# Compatible con MicroPython (urequests / ujson)
# ============================================================
# Todas las operaciones de Sheets y Drive se delegan al GAS.
# El ESP32 sólo necesita hacer requests HTTP; no necesita OAuth.
# ============================================================

import ujson
import gc
try:
    import urequests as requests
except ImportError:
    import requests  # fallback para pruebas en CPython

from config import GAS_URL
from cache import cache

# Tiempo máximo de espera por request (segundos)
_TIMEOUT = 20


def _post(payload: dict) -> dict:
    """
    Envía un POST JSON al Apps Script y retorna la respuesta parseada.
    El GAS debe responder siempre con {"ok": true/false, ...}.
    """
    gc.collect()
    body = ujson.dumps(payload)
    try:
        resp = requests.post(
            GAS_URL,
            headers={"Content-Type": "application/json"},
            data=body,
            timeout=_TIMEOUT,
        )
        data = ujson.loads(resp.text)
        resp.close()
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get(params: dict) -> dict:
    """
    Envía un GET con query-string al Apps Script.
    """
    gc.collect()
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{GAS_URL}?{qs}"
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        data = ujson.loads(resp.text)
        resp.close()
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────
#  SERIES
# ─────────────────────────────────────────

def get_series() -> list:
    """Retorna todas las filas de la hoja 'Series'. Usando caché."""
    cached = cache.get("series")
    if cached is not None:
        return cached
    r = _get({"action": "getSeries"})
    data = r.get("data", []) if r.get("ok") else []
    if data:
        cache.set("series", data, ttl_s=60)
    return data


def upsert_serie(serie: dict) -> bool:
    """Inserta o actualiza una serie en la hoja 'Series'."""
    cache.invalidate("series")
    r = _post({"action": "upsertSerie", "serie": serie})
    return bool(r.get("ok"))


def get_serie_by_name(nombre: str) -> dict:
    """Retorna la info de una serie por nombre."""
    series = get_series()
    nombre_low = str(nombre).strip().lower()
    for s in series:
        if str(s.get("Nombre", "")).strip().lower() == nombre_low:
            return s
    return {}


def get_serie_by_channel(canal_id: str) -> dict:
    """Retorna la info de una serie por Canal_ID."""
    series = get_series()
    for s in series:
        if str(s.get("Canal_ID", "")).strip() == str(canal_id).strip():
            return s
    return {}


# ─────────────────────────────────────────
#  ASIGNACIONES
# ─────────────────────────────────────────

def get_asignaciones() -> list:
    """Retorna todas las asignaciones activas."""
    cached = cache.get("asignaciones")
    if cached is not None:
        return cached
    r = _get({"action": "getAsignaciones"})
    data = r.get("data", []) if r.get("ok") else []
    if data:
        cache.set("asignaciones", data, ttl_s=15)
    return data


def add_asignacion(proyecto, capitulo, tarea, usuario, estado, id_usuario) -> bool:
    """Agrega una nueva asignación."""
    r = _post({
        "action": "addAsignacion",
        "row": {
            "Proyecto": proyecto,
            "Capitulo": capitulo,
            "Tarea": tarea,
            "Usuario": usuario,
            "Estado": estado,
            "ID_Usuario": str(id_usuario),
        }
    })
    cache.invalidate("asignaciones")
    return bool(r.get("ok"))


def add_asignaciones_batch(rows: list) -> bool:
    """Agrega múltiples asignaciones de una vez."""
    r = _post({
        "action": "addAsignacionesBatch",
        "rows": rows
    })
    cache.invalidate("asignaciones")
    return bool(r.get("ok"))


def update_asignacion_estado(row_id, estado: str) -> bool:
    """Actualiza el estado de una asignación por ID de fila."""
    r = _post({
        "action": "updateAsignacionEstado",
        "rowId": row_id,
        "estado": estado,
    })
    cache.invalidate("asignaciones")
    return bool(r.get("ok"))


def delete_asignacion(row_id) -> bool:
    """Elimina una asignación por ID de fila."""
    cache.invalidate("asignaciones")
    r = _post({"action": "deleteAsignacion", "rowId": row_id})
    return bool(r.get("ok"))


def sync_asignaciones(filas: list) -> bool:
    """Reemplaza toda la hoja Asignaciones con la lista dada."""
    r = _post({"action": "syncAsignaciones", "filas": filas})
    return bool(r.get("ok"))


# ─────────────────────────────────────────
#  REGISTROS
# ─────────────────────────────────────────

def get_registros() -> list:
    """Retorna todos los registros históricos."""
    cached = cache.get("registros")
    if cached is not None:
        return cached
    r = _get({"action": "getRegistros"})
    data = r.get("data", []) if r.get("ok") else []
    if data:
        cache.set("registros", data, ttl_s=30)
    return data


def add_registro(fecha, usuario, proyecto, capitulo, tarea, id_usuario) -> bool:
    """Appends una nueva fila en la hoja 'Registro'."""
    r = _post({
        "action": "addRegistro",
        "row": {
            "Fecha": fecha,
            "Usuario": usuario,
            "Proyecto": proyecto,
            "Capitulo": capitulo,
            "Tarea": tarea,
            "ID_Usuario": str(id_usuario),
        }
    })
    cache.invalidate("registros")
    return bool(r.get("ok"))


def replace_registros(filas: list) -> bool:
    """Reemplaza la hoja Registro completa (para finalizar mes)."""
    cache.invalidate("registros")
    r = _post({"action": "replaceRegistros", "filas": filas})
    return bool(r.get("ok"))


# ─────────────────────────────────────────
#  TABLA DE SERIE (hojas por responsable)
# ─────────────────────────────────────────

def get_tabla_serie(nombre_serie: str, hoja_responsable: str) -> list:
    """Lee el bloque de capítulos de una serie en la hoja del responsable."""
    r = _get({
        "action": "getTablaSerie",
        "serie": nombre_serie,
        "hoja": hoja_responsable,
    })
    return r.get("data", []) if r.get("ok") else []


def write_tabla_serie(nombre_serie: str, hoja_responsable: str, filas: list) -> bool:
    """Escribe (sobrescribe) el bloque de una serie en la hoja del responsable."""
    r = _post({
        "action": "writeTablaSerie",
        "serie": nombre_serie,
        "hoja": hoja_responsable,
        "filas": filas,
    })
    return bool(r.get("ok"))


def update_estado_tarea_serie(nombre_serie: str, hoja_responsable: str,
                               capitulo: str, columna: str, valor: str) -> bool:
    """Actualiza una celda de estado (✅/⏳/❌) en la tabla de una serie."""
    r = _post({
        "action": "updateEstadoTareaSerie",
        "serie": nombre_serie,
        "hoja": hoja_responsable,
        "capitulo": capitulo,
        "columna": columna,
        "valor": valor,
    })
    return bool(r.get("ok"))


def update_estado_tarea_serie_batch(nombre_serie: str, hoja_responsable: str,
                               capitulos: list, columna: str, valor: str) -> bool:
    """Actualiza el estado de múltiples capítulos a la vez."""
    r = _post({
        "action": "updateEstadoTareaSerieBatch",
        "serie": nombre_serie,
        "hoja": hoja_responsable,
        "capitulos": capitulos,
        "columna": columna,
        "valor": valor,
    })
    return bool(r.get("ok"))


# ─────────────────────────────────────────
#  DRIVE (vía GAS, sin OAuth directo)
# ─────────────────────────────────────────

def listar_drive(folder_id: str, solo_carpetas: bool = True) -> list:
    """
    Devuelve los archivos/carpetas dentro de folder_id.
    El GAS hace la llamada a Drive API con sus propios permisos.
    """
    r = _get({
        "action": "listarDrive",
        "folderId": folder_id,
        "soloCarpetas": "1" if solo_carpetas else "0",
    })
    return r.get("data", []) if r.get("ok") else []


# ─────────────────────────────────────────
#  USUARIOS / AUSENCIAS (cache en Sheets)
# ─────────────────────────────────────────

def get_usuario(user_id: str) -> dict:
    r = _get({"action": "getUsuario", "userId": str(user_id)})
    return r.get("data", {}) if r.get("ok") else {}


def set_actividad(user_id: str, timestamp_iso: str) -> bool:
    r = _post({"action": "setActividad", "userId": str(user_id), "ts": timestamp_iso})
    return bool(r.get("ok"))


def set_ausencia(user_id: str, fecha_fin_iso: str) -> bool:
    r = _post({"action": "setAusencia", "userId": str(user_id), "fechaFin": fecha_fin_iso})
    return bool(r.get("ok"))


def clear_ausencia(user_id: str) -> bool:
    r = _post({"action": "clearAusencia", "userId": str(user_id)})
    return bool(r.get("ok"))


# ─────────────────────────────────────────
#  APODOS / CRÉDITOS
# ─────────────────────────────────────────

def get_apodo(user_id: str) -> str:
    r = _get({"action": "getApodo", "userId": str(user_id)})
    return r.get("apodo", "") if r.get("ok") else ""


def set_apodo(user_id: str, apodo: str):
    return _post({"action": "setApodo", "userId": str(user_id), "apodo": apodo})

def set_correo(user_id: str, email: str):
    return _post({"action": "setCorreo", "userId": str(user_id), "email": email})

def quitar_staff(user_id: str):
    return _post({"action": "quitarStaff", "userId": str(user_id)})


# ─────────────────────────────────────────
#  TICKET COUNTER
# ─────────────────────────────────────────

def siguiente_ticket() -> int:
    r = _post({"action": "siguienteTicket"})
    return int(r.get("ticketNum", 0)) if r.get("ok") else 0


# ─────────────────────────────────────────
#  BACKUP / DUPLICAR HOJA (finalizar mes)
# ─────────────────────────────────────────

def duplicar_hoja_registro(nombre_backup: str, filas_mes: list) -> bool:
    r = _post({
        "action": "duplicarHojaRegistro",
        "nombre": nombre_backup,
        "filas": filas_mes,
    })
    return bool(r.get("ok"))
