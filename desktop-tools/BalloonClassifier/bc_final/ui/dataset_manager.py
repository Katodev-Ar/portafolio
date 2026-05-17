# =============================================================================
# dataset_manager.py — Panel de gestión y estadísticas del dataset
# =============================================================================

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis

from utils.config import CLASSES, CLASS_COLORS
from src.dataset_loader import get_dataset_stats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker thread para escanear el dataset en segundo plano
# ---------------------------------------------------------------------------

class DatasetScanWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def run(self):
        try:
            stats = get_dataset_stats()
            self.finished.emit(stats)
        except Exception as e:
            logger.error(f"Error escaneando dataset: {e}")
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Panel del dataset
# ---------------------------------------------------------------------------

class DatasetManagerPanel(QWidget):
    """
    Panel que muestra estadísticas del dataset y permite actualizarlas.

    Secciones:
        - Tabla con número de imágenes por clase
        - Gráfico de barras
        - Total de imágenes
        - Botón de actualización
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._scan_worker = None

    # -----------------------------------------------------------------------
    # Construcción de la UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # ── Encabezado ──────────────────────────────────────────────────────
        header = QLabel("📊 Gestión del Dataset")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        main_layout.addWidget(header)

        # ── Fila superior: tabla + gráfico ──────────────────────────────────
        top_row = QHBoxLayout()

        # Tabla de estadísticas
        table_group = QGroupBox("Imágenes por categoría")
        table_layout = QVBoxLayout(table_group)
        self.table = QTableWidget(len(CLASSES), 2)
        self.table.setHorizontalHeaderLabels(["Categoría", "Imágenes"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setFixedHeight(220)
        self._populate_table_empty()
        table_layout.addWidget(self.table)
        top_row.addWidget(table_group)

        # Gráfico de barras
        chart_group = QGroupBox("Distribución de clases")
        chart_layout = QVBoxLayout(chart_group)
        self.chart_view = QChartView()
        self.chart_view.setMinimumHeight(200)
        self.chart_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        chart_layout.addWidget(self.chart_view)
        top_row.addWidget(chart_group)

        main_layout.addLayout(top_row)

        # ── Barra de estado ─────────────────────────────────────────────────
        status_layout = QHBoxLayout()
        self.lbl_total = QLabel("Total: —")
        self.lbl_total.setFont(QFont("Segoe UI", 11))
        status_layout.addWidget(self.lbl_total)
        status_layout.addStretch()

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)   # Modo indeterminado
        self.progress.setFixedWidth(120)
        status_layout.addWidget(self.progress)

        self.btn_refresh = QPushButton("🔄  Actualizar Dataset")
        self.btn_refresh.setFixedWidth(180)
        self.btn_refresh.clicked.connect(self.refresh)
        status_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(status_layout)

        # ── Advertencia de dataset vacío ────────────────────────────────────
        self.lbl_warning = QLabel(
            "⚠️  No se encontraron imágenes. Añade imágenes en las carpetas "
            "de cada categoría dentro de /dataset."
        )
        self.lbl_warning.setStyleSheet("color: #E67E22; font-size: 11px;")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setVisible(False)
        main_layout.addWidget(self.lbl_warning)

    # -----------------------------------------------------------------------
    # Lógica
    # -----------------------------------------------------------------------

    def refresh(self):
        """Escanea el dataset en segundo plano y actualiza la UI."""
        self.btn_refresh.setEnabled(False)
        self.progress.setVisible(True)

        self._scan_worker = DatasetScanWorker()
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_finished(self, stats: dict):
        self.progress.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self._update_table(stats)
        self._update_chart(stats)

        total = stats.get("__total__", 0)
        self.lbl_total.setText(f"Total: {total:,} imágenes")
        self.lbl_warning.setVisible(total == 0)

    def _on_scan_error(self, error: str):
        self.progress.setVisible(False)
        self.btn_refresh.setEnabled(True)
        self.lbl_total.setText(f"Error: {error}")

    def _populate_table_empty(self):
        for row, cls in enumerate(CLASSES):
            self.table.setItem(row, 0, QTableWidgetItem(cls))
            item = QTableWidgetItem("—")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, item)

    def _update_table(self, stats: dict):
        for row, cls in enumerate(CLASSES):
            count = stats.get(cls, 0)
            name_item = QTableWidgetItem(cls)
            color = QColor(CLASS_COLORS.get(cls, "#888888"))
            color.setAlpha(60)
            name_item.setBackground(color)
            self.table.setItem(row, 0, name_item)

            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if count == 0:
                count_item.setForeground(QColor("#E74C3C"))
            self.table.setItem(row, 1, count_item)

    def _update_chart(self, stats: dict):
        bar_set = QBarSet("Imágenes")
        bar_set.setColor(QColor("#4A90D9"))

        for cls in CLASSES:
            bar_set.append(stats.get(cls, 0))

        series = QBarSeries()
        series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("Imágenes por clase")
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

        axis_x = QBarCategoryAxis()
        axis_x.append(CLASSES)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        max_val = max((stats.get(c, 0) for c in CLASSES), default=1)
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val * 1.1 + 1)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)
        self.chart_view.setChart(chart)
