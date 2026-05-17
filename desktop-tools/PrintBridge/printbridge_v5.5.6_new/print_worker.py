"""
print_worker.py — PrintBridge v5.5.0
Mejora 1 del Roadmap Técnico: lógica de impresión en proceso separado.

Este módulo define la función `run_print_job()` que se ejecuta en un proceso
hijo aislado via `concurrent.futures.ProcessPoolExecutor`.

POR QUÉ MÓDULO SEPARADO (no función dentro de queue_manager.py):
  - ProcessPoolExecutor requiere que la función worker sea importable desde
    el proceso hijo. Las funciones definidas dentro de métodos o closures
    no son picklables en Windows.
  - Al ser un módulo de nivel raíz, funciona correctamente con PyInstaller
    (que congela el árbol de importaciones en el .exe).
  - Mantiene printer.py completamente separado del código de concurrencia.

TIMEOUT:
  El timeout por defecto es 120 segundos. Se puede configurar por tipo de
  documento en config.json bajo la clave "print_timeouts":
    {
      "print_timeouts": {
        "pdf":   60,   // PDF directo via PyMuPDF, rápido
        "docx": 180,   // Conversión LibreOffice puede tardar más
        "xlsx": 180,
        "pptx": 180,
        "jpg":   30,
        "png":   30,
        "default": 120
      }
    }

AISLAMIENTO:
  El proceso hijo no tiene acceso a la memoria del servidor principal.
  Si un driver de impresora cuelga, el proceso hijo muere sin afectar
  al servidor. El proceso padre detecta el TimeoutError y marca el job
  como error con mensaje descriptivo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Agregar el directorio raíz al path para que el proceso hijo pueda importar
# los módulos del proyecto (necesario cuando se lanza con multiprocessing)
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("PrintBridge.PrintWorker")


def run_print_job(filepath: str, copies: int, options: dict) -> None:
    """
    Ejecuta un job de impresión de forma completamente síncrona.

    Esta función corre en un proceso hijo aislado. Cualquier excepción
    se propaga de vuelta al proceso padre a través del Future.

    Args:
        filepath: Ruta absoluta al archivo a imprimir.
        copies:   Número de copias.
        options:  Diccionario de opciones de impresión (color, paper, etc.).

    Raises:
        RuntimeError: Si la impresora no está configurada, el formato no
                      está soportado, o el driver falla.
        FileNotFoundError: Si el archivo no existe en el momento de imprimir.
    """
    # Importar printer aquí (dentro del proceso hijo) para que los globals
    # win32print se inicialicen en el contexto del proceso hijo, no del padre.
    import printer as _printer

    if not Path(filepath).exists():
        raise FileNotFoundError(f"Archivo no encontrado al intentar imprimir: {filepath}")

    _printer.print_file(filepath, copies, options)


def get_timeout_for_ext(ext: str) -> int:
    """
    Retorna el timeout en segundos para el tipo de archivo dado.
    Lee la configuración desde config.json si está disponible.
    """
    DEFAULT_TIMEOUTS = {
        "pdf":     60,
        "jpg":     30,
        "jpeg":    30,
        "png":     30,
        "bmp":     30,
        "gif":     30,
        "tiff":    30,
        "tif":     30,
        "docx":   180,
        "doc":    180,
        "xlsx":   180,
        "xls":    180,
        "pptx":   180,
        "ppt":    180,
        "odt":    180,
        "ods":    180,
        "odp":    180,
        "rtf":    120,
        "default": 120,
    }
    try:
        from config import load_config
        cfg = load_config()
        custom = cfg.get("print_timeouts", {})
        if custom:
            return int(custom.get(ext.lower(), custom.get("default", DEFAULT_TIMEOUTS["default"])))
    except Exception:
        pass
    return DEFAULT_TIMEOUTS.get(ext.lower(), DEFAULT_TIMEOUTS["default"])


# Guard requerido para ProcessPoolExecutor en Windows (freeze_support).
# Sin esto, PyInstaller y el modo "spawn" de multiprocessing en Windows
# crean procesos hijos que reintentan ejecutar el módulo completo,
# causando un loop infinito de creación de procesos.
if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
