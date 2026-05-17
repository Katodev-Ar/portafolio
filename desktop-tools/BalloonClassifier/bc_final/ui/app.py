# =============================================================================
# app.py — Ventana principal de la aplicación
# =============================================================================

import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QTabWidget, QStatusBar, QLabel,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon

from ui.dataset_manager import DatasetManagerPanel
from ui.training_panel   import TrainingPanel
from ui.inference_panel  import InferencePanel
from utils.config import MODEL_FILE

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Ventana principal con tres pestañas:
        1. Dataset    — gestión y estadísticas
        2. Entrenamiento — configuración, gráficos y log
        3. Predicción  — inferencia sobre imágenes nuevas
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎌 Balloon Classifier — Manga/Manhwa/Manhua")
        self.setMinimumSize(1100, 700)
        self._build_ui()
        self._setup_logging_handler()
        # Escanear dataset automáticamente al arrancar
        QTimer.singleShot(300, self.panel_dataset.refresh)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(0)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setFont(QFont("Segoe UI", 10))

        self.panel_dataset = DatasetManagerPanel()
        self.panel_train   = TrainingPanel()
        self.panel_infer   = InferencePanel()

        self.tabs.addTab(self.panel_dataset, "📊  Dataset")
        self.tabs.addTab(self.panel_train,   "🏋️  Entrenamiento")
        self.tabs.addTab(self.panel_infer,   "🔍  Predicción")

        layout.addWidget(self.tabs)

        # Conectar evento de fin de entrenamiento para recargar modelo en Inferencia
        # Las señales están dentro del panel de entrenamiento; usamos QTimer como proxy
        self.panel_train.btn_train.clicked.connect(self._on_train_started)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.lbl_status = QLabel("Listo")
        self.status.addPermanentWidget(self.lbl_status)
        self._update_model_status()

    def _update_model_status(self):
        if MODEL_FILE.exists():
            self.lbl_status.setText(f"✅ Modelo: {MODEL_FILE.name}")
            self.lbl_status.setStyleSheet("color: #27AE60;")
        else:
            self.lbl_status.setText("⚠️ Sin modelo — entrena primero")
            self.lbl_status.setStyleSheet("color: #E67E22;")

    def _on_train_started(self):
        """Conecta fin de entrenamiento para recargar modelo en Inferencia."""
        # Buscamos la señal train_end dentro del worker cuando exista
        def _watch():
            if self.panel_train._worker:
                self.panel_train._worker.finished.connect(self._on_train_finished)
        QTimer.singleShot(500, _watch)

    def _on_train_finished(self):
        self._update_model_status()
        self.panel_infer.reload_model()

    def _setup_logging_handler(self):
        """Redirige logs de Python al log del panel de entrenamiento."""
        class QtLogHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self._cb = callback

            def emit(self, record):
                msg = self.format(record)
                self._cb(msg)

        handler = QtLogHandler(self.panel_train._append_log)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def run_app():
    """Lanza la aplicación Qt."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("BalloonClassifier")

    # Tema oscuro
    palette = app.palette()
    from PyQt6.QtGui import QPalette, QColor
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window,          QColor(30, 30, 46))
    dark.setColor(QPalette.ColorRole.WindowText,      QColor(205, 214, 244))
    dark.setColor(QPalette.ColorRole.Base,            QColor(24, 24, 37))
    dark.setColor(QPalette.ColorRole.AlternateBase,   QColor(49, 50, 68))
    dark.setColor(QPalette.ColorRole.ToolTipBase,     QColor(30, 30, 46))
    dark.setColor(QPalette.ColorRole.ToolTipText,     QColor(205, 214, 244))
    dark.setColor(QPalette.ColorRole.Text,            QColor(205, 214, 244))
    dark.setColor(QPalette.ColorRole.Button,          QColor(49, 50, 68))
    dark.setColor(QPalette.ColorRole.ButtonText,      QColor(205, 214, 244))
    dark.setColor(QPalette.ColorRole.Highlight,       QColor(137, 180, 250))
    dark.setColor(QPalette.ColorRole.HighlightedText, QColor(30, 30, 46))
    app.setPalette(dark)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
