import secrets
import hashlib
import hmac
import os
import threading
from datetime import datetime, timedelta
import logging
from typing import TypedDict, Optional
from config import load_devices, save_devices, load_config, save_config

log = logging.getLogger("PrintBridge.DeviceManager")


class DeviceInfo(TypedDict):
    """TypedDict para registros de dispositivo."""
    name:       str
    ip:         str
    added_at:   str
    last_seen:  str
    role:       str   # E-06: 'admin' | 'user'
    expires_at: str   # E-08: ISO datetime de expiración


def _hash_pin(pin: str) -> str:
    """Hashea el PIN con PBKDF2-SHA256 + salt aleatorio."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 260_000)
    return salt.hex() + ":" + key.hex()


def _verify_pin_hash(pin: str, stored: str) -> bool:
    """Verifica el PIN contra el hash almacenado, resistente a timing attacks."""
    try:
        salt_hex, key_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 260_000)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False


class DeviceManager:
    def __init__(self):
        self.devices: dict[str, DeviceInfo] = load_devices()  # B-04: tipo explícito
        self._lock = threading.RLock()   # R-03 Fix: RLock permite re-adquisición desde
                                          # el mismo thread — previene deadlock latente si
                                          # is_authorized() es llamado desde un contexto que
                                          # ya posee el lock (e.g. generate_token()).
        # Persistir last_seen a disco cada 60 segundos, no en cada request.
        # D-02 Fix: reemplazar threading.Timer recursivo (que se reprogramaba en
        # su propio callback y acumulaba threads con uptime alto) por un hilo
        # dedicado con threading.Event. El Event permite cancelación limpia en
        # flush()/remove_all() sin esperar el próximo intervalo.
        self._dirty = False
        self._stop_event = threading.Event()
        self._save_thread = threading.Thread(
            target=self._periodic_save_loop, daemon=True, name="DevMgr-PeriodicSave"
        )
        self._save_thread.start()

    def _periodic_save_loop(self) -> None:
        """D-02 Fix: loop de guardado periódico con Event.
        Duerme 60 s (interruptible por _stop_event.set()) y persiste si hay cambios.
        A diferencia del Timer recursivo, este hilo vive exactamente una vez durante
        toda la vida del DeviceManager — sin acumulación de threads."""
        while not self._stop_event.wait(timeout=60):
            with self._lock:
                if self._dirty:
                    try:
                        save_devices(self.devices)
                    except Exception as e:
                        log.warning(f"Error en guardado periódico de dispositivos: {e}")
                    self._dirty = False

    def flush(self):
        """Forzar escritura inmediata a disco y detener el hilo de guardado periódico.
        Llamar en app._quit() para garantizar que los cambios en memoria se persistan
        antes de cerrar el proceso. Es el único mecanismo fiable de guardado al cierre
        — __del__ NO es confiable en Python (no se garantiza su ejecución en referencias
        circulares, shutdown del intérprete o SIGKILL).
        D-02 Fix: señalizar _stop_event para que el hilo dedicado termine limpiamente."""
        self._stop_event.set()   # detener el loop de guardado periódico
        with self._lock:
            if self._dirty:
                save_devices(self.devices)
                self._dirty = False

    def reload(self):
        with self._lock:
            self.devices = load_devices()

    def _hash_pin_public(self, pin: str) -> str:
        """Expuesto para que server.py pueda hashear el PIN al guardarlo."""
        return _hash_pin(pin)

    def verify_pin(self, pin: str) -> bool:
        config = load_config()
        stored = config.get("pin", "").strip()
        if not stored:
            return True  # Sin contraseña configurada
        # Fix Seg #1+#2: comparar contra hash, resistente a timing attacks
        if ":" in stored:
            return _verify_pin_hash(pin, stored)
        # Migración: PIN en texto plano → hashear y guardar
        # M-04 Fix: envolver en try/except sin propagar el valor del PIN en logs
        match = hmac.compare_digest(pin.encode(), stored.encode())
        if match:
            try:
                config["pin"] = _hash_pin(pin)
                save_config(config)
            except Exception:
                pass  # no loguear — contiene PIN en texto plano
        return match

    def generate_token(self, device_name: str, ip: str) -> str:
        token = secrets.token_hex(32)
        with self._lock:
            # E-06: primer dispositivo = admin (bootstrap)
            # S-05: localhost YA NO otorga admin automático después del bootstrap
            # — previene escalada de privilegios vía SSRF o servidor compartido
            is_first = len(self.devices) == 0
            role     = "admin" if is_first else "user"
            # E-08: expiración configurable (default 90 días)
            expiry_days = load_config().get("token_expiry_days", 90)
            expires_at  = (datetime.now() + timedelta(days=expiry_days)).isoformat()
            self.devices[token] = {
                "name":       device_name or f"Dispositivo ({ip})",
                "ip":         ip,
                "added_at":   datetime.now().isoformat(),
                "last_seen":  datetime.now().isoformat(),
                "role":       role,
                "expires_at": expires_at,
            }
            # A-03 Fix: retry con backoff exponencial para dar tiempo al FS
            # a liberar el lock (antivirus, otro proceso en Windows)
            import time as _time
            for attempt in range(3):
                try:
                    save_devices(self.devices)
                    break
                except OSError as e:
                    log.error(f"Error guardando dispositivo (intento {attempt+1}/3): {e}")
                    if attempt < 2:
                        _time.sleep(0.1 * (2 ** attempt))  # N-04 Fix: 100ms, 200ms
        return token

    def is_authorized(self, token: str) -> bool:
        expired = False
        with self._lock:
            if token in self.devices:
                # E-08: verificar expiración
                exp = self.devices[token].get("expires_at")
                if exp:
                    try:
                        if datetime.fromisoformat(exp) < datetime.now():
                            del self.devices[token]
                            # D-01 Fix: tomar snapshot DENTRO del mismo bloque with
                            # donde ocurre el del — elimina la ventana TOCTOU en la
                            # que otro thread podía modificar self.devices entre la
                            # liberación del primer lock y la re-adquisición del segundo.
                            snapshot = dict(self.devices)
                            expired = True
                    except Exception:
                        pass
                if not expired:
                    self.devices[token]["last_seen"] = datetime.now().isoformat()
                    self._dirty = True
                    return True
        # NEW-03 / D-01: persistir inmediatamente fuera del lock
        if expired:
            try:
                save_devices(snapshot)
            except Exception as e:
                log.warning(f"No se pudo persistir token expirado: {e}")
            return False
        return False

    def get_device(self, token: str) -> DeviceInfo:
        """Acceso thread-safe al dict de un dispositivo."""
        with self._lock:
            return dict(self.devices.get(token, {}))

    def get_all_devices(self) -> list[dict]:
        with self._lock:
            # Fix ALTO: full_token solo para uso interno (revocar desde la UI local)
            # Se incluye para que la UI local pueda revocar, pero el endpoint /api/devices
            # del servidor NO debe exponerlo hacia clientes web
            return [
                {"token": t[:8] + "...", "full_token": t, **d}
                for t, d in self.devices.items()
            ]

    def remove_device(self, token: str) -> bool:
        with self._lock:
            if token in self.devices:
                del self.devices[token]
                save_devices(self.devices)
                return True
        return False

    def remove_all(self):
        with self._lock:
            self.devices = {}
            save_devices(self.devices)
