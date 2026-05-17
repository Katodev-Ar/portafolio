# =============================================================================
# inference_panel.py — Panel de predicción / inferencia
# =============================================================================

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFileDialog,
    QProgressBar, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QColor, QPainter, QPen, QImage
from PyQt6.QtCharts import QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis, QValueAxis

from utils.config import CLASSES, CLASS_COLORS, MODEL_FILE
from src.predict import BalloonPredictor
from utils.image_utils import load_image_pil

logger = logging.getLogger(__name__)

PREVIEW_SIZE = 300


# ---------------------------------------------------------------------------
# Worker de predicción
# ---------------------------------------------------------------------------

class PredictWorker(QThread):
    result  = pyqtSignal(dict)
    error   = pyqtSignal(str)

    def __init__(self, image_path: str, predictor: BalloonPredictor):
        super().__init__()
        self.image_path = image_path
        self.predictor  = predictor

    def run(self):
        try:
            res = self.predictor.predict(self.image_path)
            self.result.emit(res)
        except Exception as e:
            logger.exception("Error en predicción")
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Panel de inferencia
# ---------------------------------------------------------------------------

class InferencePanel(QWidget):
    """
    Panel que permite:
        - Cargar una imagen de globo
        - Visualizar la imagen
        - Ejecutar el modelo y mostrar predicción
        - Ver probabilidades de todas las clases
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._predictor  = BalloonPredictor()
        self._pred_worker = None
        self._current_image_path = None
        self._build_ui()
        self._try_load_model()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(10)

        header = QLabel("🔍  Predicción de Globos")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        main.addWidget(header)

        # ── Fila principal ───────────────────────────────────────────────────
        row = QHBoxLayout()

        # Columna izquierda: imagen + controles
        left = QVBoxLayout()

        # Preview de imagen
        img_group = QGroupBox("Imagen del globo")
        img_layout = QVBoxLayout(img_group)
        self.lbl_image = QLabel()
        self.lbl_image.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet(
            "background: #1e1e2e; border: 2px dashed #444; border-radius: 8px;"
        )
        self.lbl_image.setText("Sin imagen")
        self.lbl_image.setFont(QFont("Segoe UI", 10))
        img_layout.addWidget(self.lbl_image, alignment=Qt.AlignmentFlag.AlignCenter)
        left.addWidget(img_group)

        # Botones
        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("📂  Cargar Imagen")
        self.btn_load.clicked.connect(self._load_image)
        btn_row.addWidget(self.btn_load)

        self.btn_predict = QPushButton("🧠  Clasificar")
        self.btn_predict.clicked.connect(self._run_prediction)
        self.btn_predict.setEnabled(False)
        btn_row.addWidget(self.btn_predict)

        left.addLayout(btn_row)
        left.addStretch()

        row.addLayout(left)

        # Columna derecha: resultado + gráfico de probabilidades
        right = QVBoxLayout()

        # Resultado principal
        result_group = QGroupBox("Resultado")
        result_layout = QVBoxLayout(result_group)

        self.lbl_class = QLabel("—")
        self.lbl_class.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.lbl_class.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(self.lbl_class)

        self.lbl_confidence = QLabel("Confianza: —")
        self.lbl_confidence.setFont(QFont("Segoe UI", 16))
        self.lbl_confidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(self.lbl_confidence)

        self.lbl_warning = QLabel("⚠️ Confianza baja — resultado incierto")
        self.lbl_warning.setStyleSheet("color: #E67E22;")
        self.lbl_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warning.setVisible(False)
        result_layout.addWidget(self.lbl_warning)

        right.addWidget(result_group)

        # Gráfico de barras de probabilidades
        prob_group = QGroupBox("Probabilidades por clase")
        prob_layout = QVBoxLayout(prob_group)
        self.chart_view = QChartView()
        self.chart_view.setMinimumHeight(220)
        self.chart_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        prob_layout.addWidget(self.chart_view)
        right.addWidget(prob_group)

        row.addLayout(right)
        main.addLayout(row)

        # ── Estado del modelo ────────────────────────────────────────────────
        self.lbl_model_status = QLabel("⏳ Cargando modelo...")
        self.lbl_model_status.setFont(QFont("Segoe UI", 10))
        main.addWidget(self.lbl_model_status)

        # ── Progreso ─────────────────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        main.addWidget(self.progress)

    # -----------------------------------------------------------------------
    # Lógica
    # -----------------------------------------------------------------------

    def _try_load_model(self):
        """Intenta cargar el modelo al iniciar el panel."""
        if self._predictor.load():
            self.lbl_model_status.setText("✅  Modelo listo para clasificar")
            self.lbl_model_status.setStyleSheet("color: #27AE60;")
        else:
            self.lbl_model_status.setText(
                "⚠️  Modelo no encontrado. Entrena primero el modelo."
            )
            self.lbl_model_status.setStyleSheet("color: #E67E22;")

    def reload_model(self):
        """Recarga el modelo (llamado tras terminar entrenamiento)."""
        self._predictor = BalloonPredictor()
        self._try_load_model()

    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen de globo", "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return

        self._current_image_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                PREVIEW_SIZE, PREVIEW_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.lbl_image.setPixmap(pixmap)
        else:
            self.lbl_image.setText("Error al cargar imagen")

        # Limpiar resultado anterior
        self.lbl_class.setText("—")
        self.lbl_confidence.setText("Confianza: —")
        self.lbl_class.setStyleSheet("")
        self.lbl_warning.setVisible(False)

        can_predict = self._predictor.is_ready
        self.btn_predict.setEnabled(can_predict)

    def _run_prediction(self):
        if not self._current_image_path:
            return
        if not self._predictor.is_ready:
            self.reload_model()
            if not self._predictor.is_ready:
                return

        self.btn_predict.setEnabled(False)
        self.progress.setVisible(True)

        self._pred_worker = PredictWorker(self._current_image_path, self._predictor)
        self._pred_worker.result.connect(self._on_result)
        self._pred_worker.error.connect(self._on_error)
        self._pred_worker.finished.connect(self._on_worker_done)
        self._pred_worker.start()

    def _on_result(self, result: dict):
        cls_name   = result["class"]
        confidence = result["confidence"]
        probs      = result["probabilities"]
        confident  = result["is_confident"]

        # Mostrar clase predicha
        self.lbl_class.setText(cls_name.upper())
        color = CLASS_COLORS.get(cls_name, "#FFFFFF")
        self.lbl_class.setStyleSheet(f"color: {color};")

        self.lbl_confidence.setText(f"Confianza: {confidence:.1%}")
        self.lbl_warning.setVisible(not confident)

        # Gráfico de probabilidades
        self._update_prob_chart(probs, cls_name)

    def _on_error(self, error: str):
        self.lbl_class.setText("Error")
        self.lbl_confidence.setText(error)
        self.lbl_class.setStyleSheet("color: #E74C3C;")

    def _on_worker_done(self):
        self.btn_predict.setEnabled(True)
        self.progress.setVisible(False)

    def _update_prob_chart(self, probs: dict, predicted_cls: str):
        bar_set = QBarSet("Probabilidad")

        pred_color = QColor(CLASS_COLORS.get(predicted_cls, "#4A90D9"))
        bar_set.setColor(pred_color)

        ordered = [probs.get(cls, 0.0) for cls in CLASSES]
        for v in ordered:
            bar_set.append(v)

        series = QBarSeries()
        series.append(bar_set)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("Probabilidades por clase")
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

        axis_x = QBarCategoryAxis()
        axis_x.append(CLASSES)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0.0, 1.0)
        axis_y.setLabelFormat("%.2f")
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(False)
        self.chart_view.setChart(chart)
