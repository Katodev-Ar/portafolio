"""
service.py — PrintBridge v5.5.0
Mejora 7 del Roadmap Técnico: modo servicio Windows sin GUI Tkinter.

Permite que PrintBridge corra como servicio del sistema operativo Windows,
arrancando automáticamente con el sistema sin necesidad de sesión de usuario
activa — requisito indispensable para entornos corporativos.

ARQUITECTURA DUAL:
    app.py      → modo GUI (Tkinter + tray icon)  — usuarios domésticos y PYME
    service.py  → modo servicio (sin GUI)          — IT corporativo

INSTALACIÓN Y GESTIÓN:
    printbridge.exe service install   → instala como servicio Windows
    printbridge.exe service start     → inicia el servicio
    printbridge.exe service stop      → detiene el servicio
    printbridge.exe service remove    → desinstala el servicio
    printbridge.exe service status    → muestra estado actual
    printbridge.exe service run       → modo foreground (debugging/Linux)

    O via Python directamente:
    python service.py install
    python service.py start
    python service.py stop
    python service.py remove

LOGGING EN MODO SERVICIO:
    Los logs se escriben en <BASE_DIR>/data/service.log
    y adicionalmente en el Event Log de Windows bajo "PrintBridge".

COMPATIBILIDAD:
    - Requiere pywin32 (win32service, win32serviceutil, win32event, servicemanager)
    - En Linux/macOS: modo foreground (run) disponible para desarrollo/testing
    - Compatible con PyInstaller --console (no --windowed) para el EXE de servicio
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
import time
from pathlib import Path
from multiprocessing import freeze_support

# ── Path setup ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_FILE = DATA_DIR / "service.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("PrintBridge.Service")

# ── Detección de disponibilidad de win32service ───────────────────────────────
try:
    import win32service
    import win32serviceutil
    import win32event
    import servicemanager
    WIN32SERVICE_AVAILABLE = True
except ImportError:
    WIN32SERVICE_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Core de inicialización (compartido entre modo servicio y modo foreground)
# ─────────────────────────────────────────────────────────────────────────────

def _initialize_components():
    """
    Inicializa DeviceManager, QueueManager y el servidor FastAPI.
    Retorna (device_mgr, queue_mgr) ya inyectados en server.py.
    Llamado tanto desde el servicio Windows como desde el modo foreground.
    """
    from cert_manager import ensure_certificate
    from config import load_config
    from device_manager import DeviceManager
    from queue_manager import QueueManager
    import printer
    import server as srv

    log.info("Inicializando componentes de PrintBridge…")

    # Mejora 2: garantizar certificado TLS antes de arrancar
    cert_ok = ensure_certificate(BASE_DIR)
    if cert_ok:
        log.info("Certificado TLS disponible — servidor arrancará en HTTPS")
    else:
        log.warning("Sin certificado TLS — servidor arrancará en HTTP")

    config     = load_config()
    device_mgr = DeviceManager()
    queue_mgr  = QueueManager(printer)

    # Inyectar dependencias en server.py (igual que app.py)
    srv.device_mgr = device_mgr
    srv.set_queue_manager(queue_mgr)

    port = int(config.get("port", 7878))
    srv.start_server(port)
    log.info(f"Servidor PrintBridge iniciado en puerto {port}")

    return device_mgr, queue_mgr


def _shutdown_components(device_mgr, queue_mgr):
    """Apagado limpio de todos los componentes."""
    import server as srv
    log.info("Deteniendo servidor…")
    try:
        srv.stop_server()
    except Exception as e:
        log.error(f"Error deteniendo servidor: {e}")

    log.info("Guardando estado de dispositivos…")
    try:
        device_mgr.flush()
    except Exception as e:
        log.error(f"Error en device_mgr.flush(): {e}")

    log.info("Cerrando executor de impresión…")
    try:
        queue_mgr.shutdown(wait=False)
    except Exception as e:
        log.error(f"Error en queue_mgr.shutdown(): {e}")

    log.info("PrintBridge detenido correctamente.")


# ─────────────────────────────────────────────────────────────────────────────
# Windows Service
# ─────────────────────────────────────────────────────────────────────────────

if WIN32SERVICE_AVAILABLE:

    class PrintBridgeService(win32serviceutil.ServiceFramework):
        """
        Servicio Windows para PrintBridge.

        El SCM (Service Control Manager) de Windows llama:
          SvcDoRun()  → cuando el servicio arranca
          SvcStop()   → cuando el SCM pide detener el servicio
        """

        _svc_name_         = "PrintBridge"
        _svc_display_name_ = "PrintBridge Print Server"
        _svc_description_  = (
            "Servidor de impresión en red local. "
            "Permite imprimir desde cualquier dispositivo de la red. "
            "Administrar en: https://localhost:7878"
        )

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            # Evento de parada — WaitForSingleObject espera este evento
            self._stop_event  = win32event.CreateEvent(None, 0, 0, None)
            self._device_mgr  = None
            self._queue_mgr   = None

        def SvcStop(self):
            """Llamado por el SCM cuando se pide detener el servicio."""
            log.info("SCM solicitó detener el servicio PrintBridge")
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            """Cuerpo principal del servicio. Bloquea hasta que SvcStop() sea llamado."""
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            log.info("Servicio PrintBridge iniciando…")

            try:
                self._device_mgr, self._queue_mgr = _initialize_components()
            except Exception as e:
                log.critical(f"Error al inicializar PrintBridge: {e}", exc_info=True)
                servicemanager.LogErrorMsg(f"PrintBridge: error de inicialización: {e}")
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                return

            log.info("Servicio PrintBridge activo. Esperando señal de parada…")
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)

            # Esperar indefinidamente hasta que SvcStop() dispare el evento
            win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)

            log.info("Señal de parada recibida — cerrando servicio…")
            _shutdown_components(self._device_mgr, self._queue_mgr)

            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, ""),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Modo foreground (sin GUI, para Linux/macOS o debugging Windows)
# ─────────────────────────────────────────────────────────────────────────────

def run_foreground():
    """
    Arranca PrintBridge en modo foreground (sin GUI, sin servicio Windows).
    Útil para:
      - Desarrollo en Linux/macOS
      - Debugging del modo servicio en Windows
      - Contenedores Docker
      - Sistemas sin Tkinter

    Ctrl+C detiene el servidor limpiamente.
    """
    import signal

    log.info("Iniciando PrintBridge en modo foreground (sin GUI)…")

    device_mgr, queue_mgr = _initialize_components()
    stop_event = threading.Event()

    def _handle_signal(sig, frame):
        log.info(f"Señal {sig} recibida — deteniendo PrintBridge…")
        stop_event.set()

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log.info("PrintBridge activo. Presiona Ctrl+C para detener.")
    try:
        while not stop_event.wait(timeout=1.0):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        _shutdown_components(device_mgr, queue_mgr)


# ─────────────────────────────────────────────────────────────────────────────
# CLI — gestión del servicio
# ─────────────────────────────────────────────────────────────────────────────

def _print_usage():
    print("""
PrintBridge — Gestión del servicio Windows

Uso:
  python service.py <comando>

Comandos:
  install   Instala PrintBridge como servicio de Windows
  start     Inicia el servicio (debe estar instalado)
  stop      Detiene el servicio en ejecución
  restart   Detiene e inicia el servicio
  remove    Desinstala el servicio de Windows
  status    Muestra el estado actual del servicio
  run       Modo foreground sin GUI (útil para testing/Linux)

Ejemplos:
  python service.py install
  python service.py start
  python service.py status
  python service.py stop
  python service.py remove
    """)


def _get_service_status() -> str:
    """Retorna el estado del servicio como string legible."""
    if not WIN32SERVICE_AVAILABLE:
        return "N/A (win32service no disponible)"
    try:
        status = win32serviceutil.QueryServiceStatus("PrintBridge")[1]
        states = {
            win32service.SERVICE_STOPPED:          "Detenido",
            win32service.SERVICE_START_PENDING:    "Iniciando…",
            win32service.SERVICE_STOP_PENDING:     "Deteniendo…",
            win32service.SERVICE_RUNNING:          "En ejecución ✓",
            win32service.SERVICE_CONTINUE_PENDING: "Reanudando…",
            win32service.SERVICE_PAUSE_PENDING:    "Pausando…",
            win32service.SERVICE_PAUSED:           "Pausado",
        }
        return states.get(status, f"Estado desconocido ({status})")
    except Exception as e:
        return f"No instalado ({e})"


def _cli_main(argv: list[str]) -> int:
    """
    Punto de entrada CLI para gestión del servicio.
    Retorna el código de salida (0 = éxito, 1 = error).
    """
    cmd = argv[0].lower() if argv else "help"

    if cmd in ("help", "--help", "-h"):
        _print_usage()
        return 0

    if cmd == "run":
        run_foreground()
        return 0

    if cmd == "status":
        status = _get_service_status()
        print(f"PrintBridge Service: {status}")
        return 0

    if not WIN32SERVICE_AVAILABLE:
        print("ERROR: win32service no está disponible en este sistema.")
        print("       Instalar con: pip install pywin32")
        print("       Alternativa:  python service.py run  (modo foreground)")
        return 1

    # Comandos que delegan a win32serviceutil
    try:
        if cmd == "install":
            win32serviceutil.InstallService(
                pythonClassString=f"{Path(__file__).stem}.PrintBridgeService",
                serviceName="PrintBridge",
                displayName="PrintBridge Print Server",
                description=(
                    "Servidor de impresión en red local PrintBridge. "
                    "Administrar en https://localhost:7878"
                ),
                startType=win32service.SERVICE_AUTO_START,
            )
            print("✅ Servicio PrintBridge instalado correctamente.")
            print("   Iniciar con: python service.py start")
            print("   O desde Servicios de Windows (services.msc)")

        elif cmd == "start":
            win32serviceutil.StartService("PrintBridge")
            print("✅ Servicio PrintBridge iniciado.")

        elif cmd == "stop":
            win32serviceutil.StopService("PrintBridge")
            print("✅ Servicio PrintBridge detenido.")

        elif cmd == "restart":
            win32serviceutil.RestartService("PrintBridge")
            print("✅ Servicio PrintBridge reiniciado.")

        elif cmd == "remove":
            # Detener primero si está corriendo
            try:
                win32serviceutil.StopService("PrintBridge")
                time.sleep(2)
            except Exception:
                pass
            win32serviceutil.RemoveService("PrintBridge")
            print("✅ Servicio PrintBridge desinstalado.")

        else:
            print(f"Comando desconocido: '{cmd}'")
            _print_usage()
            return 1

    except Exception as e:
        print(f"ERROR: {e}")
        log.error(f"Error en comando '{cmd}': {e}", exc_info=True)
        return 1

    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    freeze_support()   # Requerido para ProcessPoolExecutor con spawn en Windows

    args = sys.argv[1:]

    # Si no hay argumentos y estamos en Windows con win32service disponible,
    # intentar correr como servicio Windows (llamada desde SCM)
    if not args and WIN32SERVICE_AVAILABLE:
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(PrintBridgeService)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception:
            # Falló el dispatcher — probablemente ejecutado manualmente
            _print_usage()
        sys.exit(0)

    # CLI explícito
    exit_code = _cli_main(args)
    sys.exit(exit_code)
