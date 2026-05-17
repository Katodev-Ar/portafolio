# =============================================================================
# training_panel.py — Panel de entrenamiento con gráficos en tiempo real
# =============================================================================

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QSpinBox, QDoubleSpinBox,
    QProgressBar, QTextEdit, QSplitter,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCharts import (
    QChart, QChartView, QLineSeries, QValueAxis, QLegend,
)

from utils.config import EPOCHS, BATCH_SIZE, LEARNING_RATE
from src.train import Trainer, TrainingCallbacks
from src.dataset_loader import build_dataloaders

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Señales del entrenador → UI
# ---------------------------------------------------------------------------

class TrainerSignals(QObject):
    epoch_done  = pyqtSignal(int, float, float, float)   # epoch, t_loss, v_loss, v_acc
    batch_done  = pyqtSignal(int, int, float)            # batch, total, loss
    train_end   = pyqtSignal(float, int)                 # best_acc, best_epoch
    error       = pyqtSignal(str)
    log         = pyqtSignal(str)


class UICallbacks(TrainingCallbacks):
    """Puente entre el Trainer y las señales Qt."""

    def __init__(self, signals: TrainerSignals):
        self.signals = signals
        self._stop   = False

    def on_epoch_end(self, epoch, train_loss, val_loss, val_acc):
        self.signals.epoch_done.emit(epoch, train_loss, val_loss, val_acc)
        self.signals.log.emit(
            f"[Epoch {epoch}]  loss={train_loss:.4f}  "
            f"val_loss={val_loss:.4f}  acc={val_acc:.4f}"
        )

    def on_batch_end(self, batch, total_batches, loss):
        self.signals.batch_done.emit(batch, total_batches, loss)

    def on_training_end(self, best_val_acc, best_epoch):
        self.signals.train_end.emit(best_val_acc, best_epoch)

    def on_error(self, error):
        self.signals.error.emit(error)

    def should_stop(self):
        return self._stop


# ---------------------------------------------------------------------------
# Worker thread para el entrenamiento
# ---------------------------------------------------------------------------

class TrainWorker(QThread):
    def __init__(self, epochs, batch_size, lr, signals):
        super().__init__()
        self.epochs     = epochs
        self.batch_size = batch_size
        self.lr         = lr
        self.signals    = signals
        self.callbacks  = UICallbacks(signals)
        self._trainer   = None

    def run(self):
        try:
            self.signals.log.emit("Cargando dataset...")
            train_loader, val_loader = build_dataloaders(batch_size=self.batch_size)

            if len(train_loader.dataset) == 0:
                self.signals.error.emit("Dataset vacío. Añade imágenes al dataset.")
                return

            self.signals.log.emit(
                f"Dataset listo — Train: {len(train_loader.dataset)} "
                f"| Val: {len(val_loader.dataset)}"
            )

            self._trainer = Trainer(
                train_loader=train_loader,
                val_loader=val_loader,
                epochs=self.epochs,
                learning_rate=self.lr,
                callbacks=self.callbacks,
            )
            self._trainer.train()

        except Exception as e:
            logger.exception("Error en el entrenamiento")
            self.signals.error.emit(str(e))

    def stop(self):
        if self.callbacks:
            self.callbacks._stop = True


# ---------------------------------------------------------------------------
# Panel de entrenamiento
# ---------------------------------------------------------------------------

class TrainingPanel(QWidget):
    """
    Panel completo de entrenamiento con:
        - Configuración de hiperparámetros
        - Botón de inicio/parada
        - Gráficos en tiempo real de pérdida y accuracy
        - Log de texto
        - Barra de progreso por batch
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker  = None
        self._epochs_done = 0
        self._build_ui()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(10)

        header = QLabel("🏋️  Entrenamiento del Modelo")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        main.addWidget(header)

        # ── Controles ────────────────────────────────────────────────────────
        ctrl_group = QGroupBox("Hiperparámetros")
        ctrl_row   = QHBoxLayout(ctrl_group)

        ctrl_row.addWidget(QLabel("Epochs:"))
        self.spin_epochs = QSpinBox()
        self.spin_epochs.setRange(1, 500)
        self.spin_epochs.setValue(EPOCHS)
        ctrl_row.addWidget(self.spin_epochs)

        ctrl_row.addWidget(QLabel("Batch size:"))
        self.spin_batch = QSpinBox()
        self.spin_batch.setRange(1, 256)
        self.spin_batch.setSingleStep(8)
        self.spin_batch.setValue(BATCH_SIZE)
        ctrl_row.addWidget(self.spin_batch)

        ctrl_row.addWidget(QLabel("Learning rate:"))
        self.spin_lr = QDoubleSpinBox()
        self.spin_lr.setDecimals(6)
        self.spin_lr.setRange(1e-6, 0.1)
        self.spin_lr.setSingleStep(0.00001)
        self.spin_lr.setValue(LEARNING_RATE)
        ctrl_row.addWidget(self.spin_lr)

        ctrl_row.addStretch()

        self.btn_train = QPushButton("▶  Iniciar Entrenamiento")
        self.btn_train.setFixedWidth(200)
        self.btn_train.clicked.connect(self._start_training)
        ctrl_row.addWidget(self.btn_train)

        self.btn_stop = QPushButton("⏹  Detener")
        self.btn_stop.setFixedWidth(100)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_training)
        ctrl_row.addWidget(self.btn_stop)

        main.addWidget(ctrl_group)

        # ── Progreso ─────────────────────────────────────────────────────────
        prog_layout = QHBoxLayout()
        self.lbl_epoch_prog = QLabel("Epoch: —")
        prog_layout.addWidget(self.lbl_epoch_prog)
        self.progress_epoch = QProgressBar()
        self.progress_epoch.setRange(0, 100)
        self.progress_epoch.setValue(0)
        prog_layout.addWidget(self.progress_epoch)
        self.progress_batch = QProgressBar()
        self.progress_batch.setRange(0, 100)
        self.progress_batch.setValue(0)
        self.progress_batch.setFixedWidth(200)
        self.progress_batch.setToolTip("Progreso del batch actual")
        prog_layout.addWidget(self.progress_batch)
        main.addLayout(prog_layout)

        # ── Splitter: gráficos + log ──────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Gráficos
        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.setSpacing(6)

        self.chart_loss = self._build_chart("Pérdida", ["Train loss", "Val loss"],
                                            ["#E74C3C", "#3498DB"])
        self.chart_acc  = self._build_chart("Accuracy", ["Val accuracy"], ["#2ECC71"])

        charts_layout.addWidget(self.chart_loss["view"])
        charts_layout.addWidget(self.chart_acc["view"])
        splitter.addWidget(charts_widget)

        # Log de entrenamiento
        log_group  = QGroupBox("Log de entrenamiento")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier New", 9))
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_group)

        splitter.setSizes([600, 300])
        main.addWidget(splitter)

        # ── Estado final ─────────────────────────────────────────────────────
        self.lbl_result = QLabel("")
        self.lbl_result.setFont(QFont("Segoe UI", 11))
        main.addWidget(self.lbl_result)

    def _build_chart(self, title: str, series_names: list,
                     colors: list) -> dict:
        """Crea un QChart con las series dadas. Retorna dict con chart, view y series."""
        chart   = QChart()
        chart.setTitle(title)
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)

        series_list = []
        for name, color in zip(series_names, colors):
            s = QLineSeries()
            s.setName(name)
            pen = s.pen()
            pen.setColor(QColor(color))
            pen.setWidth(2)
            s.setPen(pen)
            chart.addSeries(s)
            series_list.append(s)

        axis_x = QValueAxis()
        axis_x.setTitleText("Epoch")
        axis_x.setLabelFormat("%d")
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        for s in series_list:
            s.attachAxis(axis_x)

        axis_y = QValueAxis()
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        for s in series_list:
            s.attachAxis(axis_y)

        view = QChartView(chart)
        view.setMinimumHeight(180)

        return {"chart": chart, "view": view, "series": series_list,
                "axis_x": axis_x, "axis_y": axis_y}

    # -----------------------------------------------------------------------
    # Lógica
    # -----------------------------------------------------------------------

    def _start_training(self):
        self._epochs_done = 0
        self._clear_charts()
        self.log_text.clear()
        self.lbl_result.setText("")

        epochs     = self.spin_epochs.value()
        batch_size = self.spin_batch.value()
        lr         = self.spin_lr.value()

        self.progress_epoch.setRange(0, epochs)
        self.progress_epoch.setValue(0)

        signals = TrainerSignals()
        signals.epoch_done.connect(self._on_epoch_done)
        signals.batch_done.connect(self._on_batch_done)
        signals.train_end.connect(self._on_train_end)
        signals.error.connect(self._on_error)
        signals.log.connect(self._append_log)

        self._worker = TrainWorker(epochs, batch_size, lr, signals)
        self._worker.finished.connect(self._on_thread_finished)
        self._worker.start()

        self.btn_train.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _stop_training(self):
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)
        self._append_log("⏹ Solicitud de parada enviada...")

    def _on_epoch_done(self, epoch, train_loss, val_loss, val_acc):
        self._epochs_done = epoch
        self.lbl_epoch_prog.setText(f"Epoch: {epoch}")
        self.progress_epoch.setValue(epoch)

        # Actualizar gráfico de pérdida
        self.chart_loss["series"][0].append(epoch, train_loss)
        self.chart_loss["series"][1].append(epoch, val_loss)
        self._auto_range(self.chart_loss)

        # Actualizar gráfico de accuracy
        self.chart_acc["series"][0].append(epoch, val_acc)
        self._auto_range(self.chart_acc)

    def _on_batch_done(self, batch, total, loss):
        pct = int(batch / max(total, 1) * 100)
        self.progress_batch.setValue(pct)

    def _on_train_end(self, best_acc, best_epoch):
        self.lbl_result.setText(
            f"✅  Entrenamiento finalizado — Mejor accuracy: "
            f"{best_acc:.4f} (epoch {best_epoch})"
        )
        self.lbl_result.setStyleSheet("color: #27AE60;")

    def _on_error(self, error):
        self._append_log(f"❌  Error: {error}")
        self.lbl_result.setText(f"Error: {error}")
        self.lbl_result.setStyleSheet("color: #E74C3C;")

    def _on_thread_finished(self):
        self.btn_train.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_batch.setValue(0)

    def _append_log(self, text: str):
        self.log_text.append(text)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def _clear_charts(self):
        for chart_dict in [self.chart_loss, self.chart_acc]:
            for s in chart_dict["series"]:
                s.clear()

    def _auto_range(self, chart_dict: dict):
        """Ajusta los ejes automáticamente al rango de datos."""
        all_points = [
            (p.x(), p.y())
            for s in chart_dict["series"]
            for p in s.points()
        ]
        if not all_points:
            return
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        chart_dict["axis_x"].setRange(min(xs), max(xs) + 0.5)
        margin = (max(ys) - min(ys)) * 0.1 + 1e-6
        chart_dict["axis_y"].setRange(max(0, min(ys) - margin), max(ys) + margin)
