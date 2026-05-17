# cache.py — Caché en RAM con TTL para reducir llamadas HTTP
# Compatible con MicroPython (ESP32-S3)
# ============================================================
#
# El mayor cuello de botella del bot NO es el CPU, sino la espera
# de respuestas HTTP (~1.5s por cada llamada a GAS).
# Este caché almacena datos que se usan frecuentemente para que
# no se tengan que pedir cada vez.
#
# Ejemplo: si llegan 3 comandos /asignar seguidos, los 3 necesitan
# gas.get_asignaciones() y gas.get_series(). Sin caché son 6 llamadas
# HTTP (9 segundos de espera). Con caché son 2 (3 segundos).

try:
    import utime
    _ticks = utime.ticks_ms
    _diff = utime.ticks_diff
except ImportError:
    import time
    _ticks = lambda: int(time.time() * 1000)
    _diff = lambda a, b: a - b

import gc


class TTLCache:
    """Caché simple clave-valor con expiración por tiempo (TTL en segundos)."""

    def __init__(self, default_ttl=30):
        self._store = {}       # {key: (valor, timestamp_ms)}
        self._ttl_ms = default_ttl * 1000

    def get(self, key):
        """Retorna el valor cacheado o None si expiró/no existe."""
        entry = self._store.get(key)
        if entry is None:
            return None
        valor, ts = entry
        if _diff(_ticks(), ts) > self._ttl_ms:
            # Expirado
            del self._store[key]
            return None
        return valor

    def set(self, key, valor, ttl_s=None):
        """Guarda un valor en caché con TTL opcional (en segundos)."""
        self._store[key] = (valor, _ticks())

    def invalidate(self, key):
        """Borra una clave específica."""
        self._store.pop(key, None)

    def clear(self):
        """Borra todo el caché."""
        self._store.clear()
        gc.collect()

    def invalidate_prefix(self, prefix):
        """Borra todas las claves que empiecen con un prefijo."""
        keys_to_del = [k for k in self._store if str(k).startswith(prefix)]
        for k in keys_to_del:
            del self._store[k]


# ── Instancia global ──
# TTL de 30 segundos: si llegan varios comandos en ráfaga,
# reutilizan los datos. Pero si pasa medio minuto, se refrescan.
cache = TTLCache(default_ttl=30)
