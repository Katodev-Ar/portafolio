import json
import logging
import os
import socket
from pathlib import Path
from typing import Optional

log = logging.getLogger("PrintBridge.Config")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
DEVICES_FILE = DATA_DIR / "devices.json"
HISTORY_FILE = DATA_DIR / "history.json"

DEFAULT_CONFIG = {
    "port": 7878,
    "pin": "",  # Vacío = sin contraseña por defecto
    "printer": "",
    "server_name": "PrintBridge",
    "start_minimized": False,
    "max_history": 100,
    "max_queue_size": 20,  # Fix: límite de cola separado del historial
    "allowed_extensions": [
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
        "txt", "odt", "ods", "odp", "rtf",
        "jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp", "gif"
    ]
}


# Fix: función centralizada — única definición compartida por app.py y server.py
def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# Fix ALTO: caché con lock para thread-safety bajo concurrencia de uvicorn
# Fix MEDIO: escritura atómica — evita archivo corrupto si el proceso muere mid-write
import threading as _threading
_config_cache: dict | None = None
_config_lock  = _threading.Lock()
_config_mtime: float = 0.0   # P-01: mtime del archivo para detectar cambios externos

def load_config(force: bool = False) -> dict:
    """P-01: caché con invalidación basada en mtime del archivo.
    Detecta cambios externos (restauración manual, otro proceso)
    comparando el mtime actual contra el registrado al cargar.
    """
    global _config_cache, _config_mtime
    with _config_lock:
        # Verificar si el archivo fue modificado externamente
        if _config_cache is not None and not force:
            try:
                current_mtime = CONFIG_FILE.stat().st_mtime if CONFIG_FILE.exists() else 0.0
                if current_mtime <= _config_mtime:
                    return dict(_config_cache)  # caché válido
                # mtime cambió → recargar
                log.info("config.json modificado externamente — recargando caché")
            except OSError:
                return dict(_config_cache)  # error de stat → usar caché
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            _config_cache = data
            try:
                _config_mtime = CONFIG_FILE.stat().st_mtime
            except OSError:
                _config_mtime = 0.0
            return dict(_config_cache)
        _config_cache = DEFAULT_CONFIG.copy()
        _config_mtime = 0.0
        return dict(_config_cache)


# A-02 Fix: flag cacheado — evita copiar el dict completo en cada request autenticado
_pin_configured = None  # bool | None

def has_pin() -> bool:
    # N-02 Fix: leer y escribir _pin_configured siempre dentro del lock.
    # El double-checked locking sin barrera de memoria es seguro en CPython
    # (GIL) pero riesgoso en implementaciones sin GIL (PyPy, Jython, etc.).
    global _pin_configured
    with _config_lock:
        if _pin_configured is not None:
            return _pin_configured
        _pin_configured = bool((_config_cache or {}).get("pin", "").strip())
        return _pin_configured


def save_config(config: dict) -> None:
    global _config_cache, _pin_configured
    # B-03: toda la operación (write + rename + cache update) dentro del lock
    # para evitar la ventana donde otro thread lee _config_cache actualizado
    # mientras el archivo en disco todavía tiene la versión anterior.
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with _config_lock:
        tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CONFIG_FILE)
        _config_cache = dict(config)
        _pin_configured = None  # invalidar al guardar nueva config
        try:
            _config_mtime = CONFIG_FILE.stat().st_mtime  # P-01: actualizar mtime registrado
        except OSError:
            _config_mtime = 0.0


def load_devices() -> dict:
    if DEVICES_FILE.exists():
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_devices(devices: dict) -> None:
    # Escritura atómica — igual que save_config
    tmp = DEVICES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)
    tmp.replace(DEVICES_FILE)


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list[dict]) -> None:
    # Escritura atómica — igual que save_config
    tmp = HISTORY_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    tmp.replace(HISTORY_FILE)
