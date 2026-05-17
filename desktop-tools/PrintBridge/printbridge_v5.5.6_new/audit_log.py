"""
audit_log.py — PrintBridge v5.0.1
Módulo de auditoría de eventos de seguridad (E-09).
Registra en JSON estructurado con retención de 90 días (E-18).
"""
import json
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).parent
_AUDIT_FILE = BASE_DIR / "data" / "audit.log"
_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

_alog = logging.getLogger("PrintBridge.Audit")

if not _alog.handlers:
    _handler = TimedRotatingFileHandler(
        str(_AUDIT_FILE),
        when="midnight",
        backupCount=90,          # E-18: 90 días de retención
        encoding="utf-8",
    )
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _alog.addHandler(_handler)
    _alog.setLevel(logging.INFO)
    _alog.propagate = False  # no duplicar en root logger


def log_event(
    event: str,
    ip: str,
    device: str,
    outcome: str,
    details: dict | None = None,
) -> None:
    """
    Registra un evento de seguridad estructurado.

    Eventos estándar:
      LOGIN_OK, LOGIN_FAIL, LOGOUT,
      PIN_CHANGE, PRINTER_CHANGE,
      DEVICE_REVOKED, DEVICE_ADDED,
      PRINT, SCAN,
      BACKUP_EXPORT, BACKUP_IMPORT
    """
    record = {
        "ts":      datetime.utcnow().isoformat() + "Z",
        "event":   event,
        "ip":      ip,
        "device":  device,
        "outcome": outcome,   # ok | denied | error
    }
    if details:
        # AU-01: sub-key en lugar de update() — evita sobrescribir campos estándar
        # R-01 Fix: sanitizar valores no serializables antes de json.dumps para
        # evitar que un TypeError silencioso pierda el evento de auditoría.
        # Las claves también se normalizan a str para evitar keys inesperadas
        # como '0' o 'None' cuando el caller pasa claves de tipo no-str.
        _RESERVED = {"ts", "event", "ip", "device", "outcome"}
        safe_details: dict = {}
        for k, v in details.items():
            sk = str(k)
            if sk in _RESERVED:
                continue
            try:
                json.dumps(v)          # verificar serializabilidad sin efectos
                safe_details[sk] = v
            except (TypeError, ValueError):
                safe_details[sk] = str(v)   # fallback seguro: representación textual
        record["details"] = safe_details
    _alog.info(json.dumps(record, ensure_ascii=False))
