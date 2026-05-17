#!/usr/bin/env python3
# =============================================================================
# main.py — Punto de entrada de BalloonClassifier
# =============================================================================

import sys
import os
import traceback
from pathlib import Path

# ── Asegurar que el directorio raíz esté en sys.path ───────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Archivo de error de emergencia (siempre accesible) ─────────────────────
ERROR_LOG = ROOT / "logs" / "startup_error.txt"


def _fatal(msg: str):
    """Muestra un error crítico de forma visible y lo guarda en disco."""
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    ERROR_LOG.write_text(msg, encoding="utf-8")

    # Intentar mostrar ventana de error Qt si está disponible
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox()
        box.setWindowTitle("BalloonClassifier — Error de inicio")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText("La aplicación no pudo iniciarse.\n\nRevisa el archivo:\n"
                    f"{ERROR_LOG}\n\n{msg[:800]}")
        box.exec()
    except Exception:
        pass  # Si Qt tampoco está, el archivo de log es suficiente

    print("\n" + "=" * 60)
    print("ERROR FATAL — BalloonClassifier no pudo iniciar")
    print("=" * 60)
    print(msg)
    print(f"\nError guardado en: {ERROR_LOG}")
    print("=" * 60)
    input("\nPresiona ENTER para cerrar...")
    sys.exit(1)


# ── Verificación de dependencias ───────────────────────────────────────────

def check_dependencies():
    missing = []
    deps = [
        ("torch",        "torch"),
        ("torchvision",  "torchvision"),
        ("cv2",          "opencv-python"),
        ("PIL",          "Pillow"),
        ("numpy",        "numpy"),
        ("sklearn",      "scikit-learn"),
        ("PyQt6",        "PyQt6"),
        ("PyQt6.QtCharts","PyQt6-Charts"),
    ]
    for module, pkg in deps:
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)
    return missing


# ── Logging ────────────────────────────────────────────────────────────────

def setup_logging():
    import logging
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "balloon_classifier.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # 1. Verificar dependencias ANTES de importar nada más
    missing = check_dependencies()
    if missing:
        _fatal(
            "Faltan las siguientes dependencias. Ejecuta en la terminal:\n\n"
            f"  pip install {' '.join(missing)}\n\n"
            "Dependencias faltantes:\n  - " + "\n  - ".join(missing)
        )

    # 2. Logging
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("  BalloonClassifier — iniciando")
    logger.info(f"  Python {sys.version}")
    logger.info(f"  Directorio: {ROOT}")
    logger.info("=" * 60)

    # 3. Variables de entorno Qt
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    # 4. Lanzar la app con captura total de errores
    try:
        from ui.app import run_app
        run_app()
    except Exception:
        tb = traceback.format_exc()
        logger.critical(f"Error no manejado:\n{tb}")
        _fatal(tb)
