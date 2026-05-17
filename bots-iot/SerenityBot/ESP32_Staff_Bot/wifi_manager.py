try:
    import network
    _IS_MICROPYTHON = True
except ImportError:
    _IS_MICROPYTHON = False

import utime
import gc

_wlan = None


def connect(ssid: str, password: str, retries: int = 10, timeout_s: int = 20) -> bool:
    global _wlan
    gc.collect()

    if not _IS_MICROPYTHON:
        print(f"[WiFi Emulado] Conectando a '{ssid}'... OK (Emulación PC)")
        return True

    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)

    if _wlan.isconnected():
        print(f"[WiFi] Ya conectado: {_wlan.ifconfig()[0]}")
        return True

    print(f"[WiFi] Conectando a '{ssid}'...")
    _wlan.connect(ssid, password)

    t0 = utime.ticks_ms()
    while not _wlan.isconnected():
        if utime.ticks_diff(utime.ticks_ms(), t0) > timeout_s * 1000:
            print("[WiFi] Timeout de conexión.")
            return False
        utime.sleep(0.5)

    ip = _wlan.ifconfig()[0]
    print(f"[WiFi] Conectado. IP: {ip}")
    return True


def is_connected() -> bool:
    if not _IS_MICROPYTHON:
        return True
    return _wlan is not None and _wlan.isconnected()


def disconnect():
    global _wlan
    if not _IS_MICROPYTHON:
        return
    if _wlan:
        _wlan.disconnect()
        _wlan.active(False)


def ensure_connected(ssid: str, password: str) -> bool:
    """Reconecta si es necesario. Llama esto antes de cada request HTTP."""
    if is_connected():
        return True
    print("[WiFi] Reconectando...")
    return connect(ssid, password)
