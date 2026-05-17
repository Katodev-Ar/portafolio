"""
main.py - Lanzador principal de WatermarkRemove
Autora: Daylor | Versión: 4.0.0

Ejecutar con:
    python main.py
"""
import sys
import os
from pathlib import Path

# Asegurar que el directorio raíz esté en el path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from WatermarkRemove.ui.watermark_tab import WatermarkTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WatermarkRemove v4.0.0")
        self.setMinimumSize(800, 600)
        self.resize(900, 700)
        self._apply_dark_theme()
        self._setup_ui()

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QGroupBox {
                border: 1px solid #555;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: bold;
                color: #cccccc;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #3c3f41;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4c5052;
            }
            QComboBox, QSpinBox {
                background-color: #3c3f41;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                border: 1px solid #555;
                font-family: Consolas, monospace;
            }
            QScrollBar:vertical {
                background: #2b2b2b;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 5px;
            }
        """)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QLabel("🖼️  WatermarkRemove")
        header.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #64b5f6; padding: 8px;")
        layout.addWidget(header)

        subtitle = QLabel("Eliminador de marcas de agua para manhwa/manga")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        # Pestaña principal
        self.watermark_tab = WatermarkTab(self)
        layout.addWidget(self.watermark_tab)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("WatermarkRemove")
    app.setApplicationVersion("4.0.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
