"""
Auto Detector de Posiciones de Marca de Agua
=============================================
Detecta automáticamente la ubicación de una marca de agua en una imagen
usando template matching de OpenCV y convierte las coordenadas a la
representación (side_x, side_y, offset_x, offset_y) del sistema.

Flujo:
  1. El usuario selecciona la carpeta de marca (ej: "468") y una carpeta
     con imágenes de muestra (una imagen por posición a registrar).
  2. Por cada imagen, se ejecuta template matching para encontrar la ubicación.
  3. La detección se convierte al sistema de coordenadas relativas.
  4. El usuario puede revisar cada resultado y confirmar o ajustar.
  5. Se guardan todas las posiciones en wm_positions.json.
"""

import os
import sys
from pathlib import Path
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QFileDialog, QWidget, QMessageBox,
    QScrollArea, QSpinBox, QFormLayout, QSizePolicy, QProgressBar,
    QListWidget, QListWidgetItem, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QColor, QFont

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import UtilJson
from WatermarkRemove import load_images_cv2, align_watermark, remove_watermark
from natsort import natsorted

SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tga', '.jfif')


# ---------------------------------------------------------------------------
# Lógica de detección (sin UI)
# ---------------------------------------------------------------------------

def _coords_to_relative(x_det: int, y_det: int,
                         w_img: int, h_img: int,
                         w_wm: int, h_wm: int):
    """
    Convierte coordenadas absolutas (x, y) de la esquina superior-izquierda
    de la marca de agua al sistema (side_x, side_y, offset_x, offset_y).

    Estrategia: evalúa las 9 posiciones base y elige la que minimiza el
    offset resultante (distancia mínima al borde de referencia).
    """
    candidates = []

    sides_x = {
        'left':   x_det,
        'center': x_det - (w_img - w_wm) // 2,
        'right':  (w_img - w_wm) - x_det,
    }
    sides_y = {
        'top':    y_det,
        'center': y_det - (h_img - h_wm) // 2,
        'bottom': (h_img - h_wm) - y_det,
    }

    for sy, oy in sides_y.items():
        for sx, ox in sides_x.items():
            dist = abs(ox) + abs(oy)
            candidates.append((dist, sx, sy, ox, oy))

    candidates.sort(key=lambda c: c[0])
    _, best_sx, best_sy, best_ox, best_oy = candidates[0]
    return best_sx, best_sy, int(best_ox), int(best_oy)


def detect_watermark_position(image: np.ndarray, watermark: np.ndarray,
                               threshold: float = 0.4) -> tuple | None:
    """
    Usa template matching multi-escala y multi-canal para detectar la
    ubicación de la marca de agua en la imagen.

    Devuelve (x, y, confidence) o None si no se detecta con suficiente
    confianza.
    """
    h_img, w_img = image.shape[:2]
    h_wm, w_wm = watermark.shape[:2]

    if h_wm > h_img or w_wm > w_img:
        return None

    # Construir versiones de búsqueda
    # 1) Imagen base en escala de grises
    img_gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float32)

    # 2) Template: usar solo píxeles opacos de la marca (alpha > 30)
    if watermark.shape[2] == 4:
        alpha = watermark[:, :, 3]
        mask = (alpha > 30).astype(np.uint8)
        wm_gray = cv2.cvtColor(watermark[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float32)
    else:
        mask = None
        wm_gray = cv2.cvtColor(watermark[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float32)

    best_val = -1.0
    best_loc = (0, 0)

    # Template matching con máscara (TM_CCORR_NORMED admite mask en OpenCV)
    try:
        if mask is not None:
            result = cv2.matchTemplate(img_gray, wm_gray, cv2.TM_CCORR_NORMED, mask=mask)
        else:
            result = cv2.matchTemplate(img_gray, wm_gray, cv2.TM_CCORR_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
    except Exception:
        pass

    if best_val < threshold:
        return None

    x, y = best_loc
    return x, y, float(best_val)


def detect_and_convert(image: np.ndarray, watermark: np.ndarray,
                        threshold: float = 0.4):
    """
    Detecta la posición y la convierte al sistema relativo.
    Devuelve dict con todos los datos o None.
    """
    result = detect_watermark_position(image, watermark, threshold)
    if result is None:
        return None
    x, y, confidence = result
    h_img, w_img = image.shape[:2]
    h_wm, w_wm = watermark.shape[:2]
    side_x, side_y, offset_x, offset_y = _coords_to_relative(
        x, y, w_img, h_img, w_wm, h_wm
    )
    return {
        'abs_x': x, 'abs_y': y,
        'confidence': confidence,
        'side_x': side_x, 'side_y': side_y,
        'offset_x': offset_x, 'offset_y': offset_y,
    }


def draw_detection_preview(image: np.ndarray, watermark: np.ndarray,
                            x: int, y: int) -> np.ndarray:
    """
    Dibuja un rectángulo sobre la imagen mostrando dónde se detectó la marca.
    Devuelve imagen BGR sin canal alfa.
    """
    vis = image[:, :, :3].copy()
    h_wm, w_wm = watermark.shape[:2]
    cv2.rectangle(vis, (x, y), (x + w_wm, y + h_wm), (0, 255, 0), 3)
    # Semitransparente sobre la región
    overlay = vis.copy()
    cv2.rectangle(overlay, (x, y), (x + w_wm, y + h_wm), (0, 255, 0), -1)
    cv2.addWeighted(overlay, 0.15, vis, 0.85, 0, vis)
    cv2.putText(vis, "DETECTADO", (x, max(y - 8, 15)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return vis


# ---------------------------------------------------------------------------
# Worker thread para no bloquear la UI
# ---------------------------------------------------------------------------

class DetectionWorker(QThread):
    result_ready = pyqtSignal(int, object)   # (index, result_dict or None)
    finished_all = pyqtSignal()

    def __init__(self, image_files, watermark_path, threshold, parent=None):
        super().__init__(parent)
        self.image_files = image_files
        self.watermark_path = watermark_path
        self.threshold = threshold

    def run(self):
        wm = load_images_cv2(str(self.watermark_path))
        for i, img_path in enumerate(self.image_files):
            try:
                img = load_images_cv2(str(img_path))
                res = detect_and_convert(img, wm, self.threshold)
                self.result_ready.emit(i, res)
            except Exception as e:
                self.result_ready.emit(i, None)
        self.finished_all.emit()


# ---------------------------------------------------------------------------
# Widget de previsualización
# ---------------------------------------------------------------------------

class PreviewLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)

    def show_cv2(self, img_bgr: np.ndarray, max_w=700, max_h=500):
        h, w = img_bgr.shape[:2]
        scale = min(max_w / w, max_h / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, nw, nh, 3 * nw, QImage.Format.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(qimg))

    def clear_preview(self):
        self.clear()
        self.setText("Sin previsualización")


# ---------------------------------------------------------------------------
# Diálogo principal
# ---------------------------------------------------------------------------

class AutoPositionDetector(QDialog):
    """
    Diálogo que detecta automáticamente las posiciones de la marca de agua
    en un lote de imágenes y genera las entradas para wm_positions.json.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Auto Detector de Posiciones")
        self.setModal(True)
        self.resize(1100, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        self.marcas_base_path = Path(os.path.dirname(current_dir)) / 'marcas'
        self.images_folder: Path | None = None
        self.image_files: list[Path] = []
        self.watermark_path: Path | None = None
        self.watermark_img: np.ndarray | None = None

        # Resultados: lista de dicts (uno por imagen)
        self.detections: list[dict | None] = []
        self.worker: DetectionWorker | None = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(10, 10, 10, 10)

        # Panel izquierdo: controles
        left = self._build_left_panel()
        root.addWidget(left)

        # Panel derecho: lista de imágenes + previsualización
        right = self._build_right_panel()
        root.addWidget(right, 1)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(270)
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # -- Selección de carpetas --
        sel_group = QGroupBox("📁 Selección")
        sel_lay = QVBoxLayout()
        sel_lay.setSpacing(6)

        btn_imgs = QPushButton("📂 Carpeta de Imágenes de Muestra")
        btn_imgs.clicked.connect(self._select_images_folder)
        btn_imgs.setStyleSheet("padding:6px;")
        sel_lay.addWidget(btn_imgs)

        self.imgs_label = QLabel("No seleccionada")
        self.imgs_label.setStyleSheet("color:#888; font-size:10px; padding-left:8px;")
        self.imgs_label.setWordWrap(True)
        sel_lay.addWidget(self.imgs_label)

        sel_lay.addWidget(QLabel("Carpeta de Marca (source):"))
        self.wm_folder_combo = QComboBox()
        self.wm_folder_combo.currentIndexChanged.connect(self._on_wm_folder_changed)
        sel_lay.addWidget(self.wm_folder_combo)

        sel_lay.addWidget(QLabel("Archivo de marca (.png):"))
        self.wm_file_combo = QComboBox()
        self.wm_file_combo.currentIndexChanged.connect(self._on_wm_file_changed)
        sel_lay.addWidget(self.wm_file_combo)

        sel_group.setLayout(sel_lay)
        layout.addWidget(sel_group)

        # -- Umbral de confianza --
        cfg_group = QGroupBox("⚙️ Configuración")
        cfg_lay = QFormLayout()
        cfg_lay.setSpacing(6)

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(10, 99)
        self.threshold_spin.setValue(40)
        self.threshold_spin.setSuffix(" %")
        self.threshold_spin.setToolTip(
            "Confianza mínima para aceptar una detección.\n"
            "Bájalo si no detecta. Súbelo para menos falsos positivos."
        )
        cfg_lay.addRow("Umbral de confianza:", self.threshold_spin)
        cfg_group.setLayout(cfg_lay)
        layout.addWidget(cfg_group)

        # -- Botón Detectar --
        self.btn_detect = QPushButton("🔍 Detectar Posiciones")
        self.btn_detect.setEnabled(False)
        self.btn_detect.setStyleSheet(
            "padding:10px; background:#1565C0; color:white; font-weight:bold; border-radius:5px;"
        )
        self.btn_detect.clicked.connect(self._run_detection)
        layout.addWidget(self.btn_detect)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # -- Ajuste manual de la selección actual --
        adj_group = QGroupBox("✏️ Ajuste Manual (imagen seleccionada)")
        adj_lay = QFormLayout()
        adj_lay.setSpacing(6)

        self.adj_side_x = QComboBox()
        self.adj_side_x.addItems(["left", "center", "right"])
        self.adj_side_x.currentTextChanged.connect(self._on_manual_adjust)
        adj_lay.addRow("Lado X:", self.adj_side_x)

        self.adj_side_y = QComboBox()
        self.adj_side_y.addItems(["top", "center", "bottom"])
        self.adj_side_y.currentTextChanged.connect(self._on_manual_adjust)
        adj_lay.addRow("Lado Y:", self.adj_side_y)

        self.adj_offset_x = QSpinBox()
        self.adj_offset_x.setRange(-9999, 9999)
        self.adj_offset_x.valueChanged.connect(self._on_manual_adjust)
        adj_lay.addRow("Offset X:", self.adj_offset_x)

        self.adj_offset_y = QSpinBox()
        self.adj_offset_y.setRange(-9999, 9999)
        self.adj_offset_y.valueChanged.connect(self._on_manual_adjust)
        adj_lay.addRow("Offset Y:", self.adj_offset_y)

        adj_group.setLayout(adj_lay)
        layout.addWidget(adj_group)

        self._manual_updating = False  # flag para evitar loops

        # -- Guardar --
        self.btn_save = QPushButton("💾 Guardar en wm_positions.json")
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(
            "padding:10px; background:#2E7D32; color:white; font-weight:bold; border-radius:5px;"
        )
        self.btn_save.clicked.connect(self._save_positions)
        layout.addWidget(self.btn_save)

        btn_close = QPushButton("❌ Cerrar")
        btn_close.setStyleSheet(
            "padding:8px; background:#c62828; color:white; border-radius:5px;"
        )
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        layout.addStretch()

        self._load_wm_folders()
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setSpacing(8)
        lay.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Lista de imágenes
        list_container = QWidget()
        list_lay = QVBoxLayout(list_container)
        list_lay.setContentsMargins(0, 0, 0, 0)
        list_lay.addWidget(QLabel("Imágenes de muestra:"))
        self.img_list = QListWidget()
        self.img_list.setMaximumWidth(220)
        self.img_list.currentRowChanged.connect(self._on_list_selection_changed)
        list_lay.addWidget(self.img_list)
        splitter.addWidget(list_container)

        # Previsualización
        preview_container = QWidget()
        preview_lay = QVBoxLayout(preview_container)
        preview_lay.setContentsMargins(0, 0, 0, 0)

        self.info_label = QLabel("Selecciona una imagen de la lista para ver la detección.")
        self.info_label.setStyleSheet("color:#aaa; padding:4px;")
        self.info_label.setWordWrap(True)
        preview_lay.addWidget(self.info_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: 2px solid #444;")
        self.preview = PreviewLabel()
        scroll.setWidget(self.preview)
        preview_lay.addWidget(scroll, 1)

        splitter.addWidget(preview_container)
        splitter.setSizes([220, 800])

        lay.addWidget(splitter, 1)
        return panel

    # ------------------------------------------------------------------
    # Lógica de carga de combos
    # ------------------------------------------------------------------

    def _load_wm_folders(self):
        self.wm_folder_combo.clear()
        if not self.marcas_base_path.exists():
            return
        folders = sorted(
            [f for f in self.marcas_base_path.iterdir() if f.is_dir()],
            reverse=True
        )
        for folder in folders:
            self.wm_folder_combo.addItem(folder.name, str(folder))

    def _on_wm_folder_changed(self, i):
        self.wm_file_combo.clear()
        if i < 0:
            return
        folder = Path(self.wm_folder_combo.currentData())
        pngs = [f for f in natsorted(folder.iterdir())
                if f.is_file() and f.suffix.lower() == '.png']
        for f in pngs:
            self.wm_file_combo.addItem(f.name, str(f))

    def _on_wm_file_changed(self, i):
        if i < 0:
            return
        path = self.wm_file_combo.currentData()
        if path:
            try:
                self.watermark_path = Path(path)
                self.watermark_img = load_images_cv2(path)
            except Exception:
                self.watermark_img = None
        self._check_ready()

    # ------------------------------------------------------------------
    # Selección de carpeta de imágenes
    # ------------------------------------------------------------------

    def _select_images_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de imágenes de muestra")
        if not folder:
            return
        self.images_folder = Path(folder)
        self.imgs_label.setText(self.images_folder.name)
        self.image_files = [
            f for f in natsorted(self.images_folder.iterdir())
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS
        ]
        self._populate_list()
        self._check_ready()

    def _populate_list(self):
        self.img_list.clear()
        self.detections = [None] * len(self.image_files)
        for f in self.image_files:
            item = QListWidgetItem(f"⬜ {f.name}")
            self.img_list.addItem(item)

    # ------------------------------------------------------------------
    # Habilitar botón detectar
    # ------------------------------------------------------------------

    def _check_ready(self):
        ready = (
            self.image_files
            and self.watermark_img is not None
        )
        self.btn_detect.setEnabled(bool(ready))

    # ------------------------------------------------------------------
    # Detección
    # ------------------------------------------------------------------

    def _run_detection(self):
        if self.worker and self.worker.isRunning():
            return

        self.detections = [None] * len(self.image_files)
        self.progress.setVisible(True)
        self.progress.setMaximum(len(self.image_files))
        self.progress.setValue(0)
        self.btn_detect.setEnabled(False)
        self.btn_save.setEnabled(False)

        # Reset iconos lista
        for i in range(self.img_list.count()):
            item = self.img_list.item(i)
            name = self.image_files[i].name
            item.setText(f"⏳ {name}")
            item.setForeground(QColor("#888"))

        threshold = self.threshold_spin.value() / 100.0

        self.worker = DetectionWorker(
            self.image_files,
            self.watermark_path,
            threshold,
            self
        )
        self.worker.result_ready.connect(self._on_result)
        self.worker.finished_all.connect(self._on_detection_done)
        self.worker.start()

    def _on_result(self, index: int, result):
        self.detections[index] = result
        self.progress.setValue(index + 1)
        item = self.img_list.item(index)
        name = self.image_files[index].name
        if result is not None:
            conf = int(result['confidence'] * 100)
            item.setText(f"✅ {name}  [{conf}%]")
            item.setForeground(QColor("#81C784"))
        else:
            item.setText(f"❌ {name}  [no detectado]")
            item.setForeground(QColor("#EF5350"))

    def _on_detection_done(self):
        self.progress.setVisible(False)
        self.btn_detect.setEnabled(True)

        detected = sum(1 for d in self.detections if d is not None)
        total = len(self.detections)

        if detected > 0:
            self.btn_save.setEnabled(True)

        QMessageBox.information(
            self,
            "Detección completada",
            f"Detectadas: {detected} / {total} imágenes.\n\n"
            f"{'Puedes guardar las posiciones.' if detected > 0 else 'Baja el umbral de confianza e intenta de nuevo.'}"
        )

        # Mostrar primera detección exitosa
        for i, d in enumerate(self.detections):
            if d is not None:
                self.img_list.setCurrentRow(i)
                break

    # ------------------------------------------------------------------
    # Selección en lista → previsualización
    # ------------------------------------------------------------------

    def _on_list_selection_changed(self, row: int):
        if row < 0 or row >= len(self.image_files):
            return

        result = self.detections[row] if row < len(self.detections) else None

        # Actualizar controles de ajuste manual sin disparar eventos
        self._manual_updating = True
        if result:
            self.adj_side_x.setCurrentText(result['side_x'])
            self.adj_side_y.setCurrentText(result['side_y'])
            self.adj_offset_x.setValue(result['offset_x'])
            self.adj_offset_y.setValue(result['offset_y'])
        self._manual_updating = False

        self._refresh_preview(row)

    def _refresh_preview(self, row: int):
        if row < 0 or row >= len(self.image_files):
            return

        try:
            img = load_images_cv2(str(self.image_files[row]))
        except Exception:
            self.preview.clear_preview()
            return

        result = self.detections[row] if row < len(self.detections) else None

        if result is None:
            # Solo mostrar imagen sin detección
            vis = img[:, :, :3].copy()
            self.info_label.setText("❌ No se detectó la marca en esta imagen.")
            self.info_label.setStyleSheet("color:#EF5350; padding:4px;")
        else:
            x, y = result['abs_x'], result['abs_y']
            vis = draw_detection_preview(img, self.watermark_img, x, y)
            conf = int(result['confidence'] * 100)
            self.info_label.setText(
                f"✅ Confianza: {conf}%  |  "
                f"Pos: ({x}, {y})  |  "
                f"side_x={result['side_x']}  side_y={result['side_y']}  "
                f"offset_x={result['offset_x']}  offset_y={result['offset_y']}"
            )
            self.info_label.setStyleSheet("color:#81C784; padding:4px;")

        self.preview.show_cv2(vis)

    # ------------------------------------------------------------------
    # Ajuste manual
    # ------------------------------------------------------------------

    def _on_manual_adjust(self):
        if self._manual_updating:
            return
        row = self.img_list.currentRow()
        if row < 0 or row >= len(self.detections):
            return

        side_x = self.adj_side_x.currentText()
        side_y = self.adj_side_y.currentText()
        offset_x = self.adj_offset_x.value()
        offset_y = self.adj_offset_y.value()

        if self.watermark_img is None:
            return

        try:
            img = load_images_cv2(str(self.image_files[row]))
        except Exception:
            return

        # Recalcular abs_x, abs_y desde los ajustes manuales
        x, y = align_watermark(img, self.watermark_img, offset_x, offset_y, side_x, side_y)

        # Actualizar o crear la detección para esta imagen
        existing = self.detections[row]
        confidence = existing['confidence'] if existing else 1.0

        self.detections[row] = {
            'abs_x': x, 'abs_y': y,
            'confidence': confidence,
            'side_x': side_x, 'side_y': side_y,
            'offset_x': offset_x, 'offset_y': offset_y,
        }

        # Actualizar ícono en lista
        item = self.img_list.item(row)
        name = self.image_files[row].name
        item.setText(f"✏️ {name}  [manual]")
        item.setForeground(QColor("#FFD54F"))

        self._refresh_preview(row)
        self.btn_save.setEnabled(True)

    # ------------------------------------------------------------------
    # Guardar
    # ------------------------------------------------------------------

    def _save_positions(self):
        # Nombre de la carpeta de marca = key en JSON
        folder_name = self.wm_folder_combo.currentText()
        if not folder_name:
            QMessageBox.warning(self, "Error", "Selecciona una carpeta de marca.")
            return

        valid = [(i, d) for i, d in enumerate(self.detections) if d is not None]
        if not valid:
            QMessageBox.warning(self, "Sin datos", "No hay detecciones válidas para guardar.")
            return

        # Construir dict de posiciones
        pos_dict = {}
        for pos_num, (i, d) in enumerate(valid, 1):
            pos_dict[f"pos_{pos_num}"] = {
                "offset_x": d['offset_x'],
                "offset_y": d['offset_y'],
                "side_x":   d['side_x'],
                "side_y":   d['side_y'],
            }

        json_path = Path(os.path.dirname(current_dir)) / 'wm_positions.json'
        jf = UtilJson(json_path)

        # Verificar si ya existe y preguntar
        existing = jf.read() if json_path.exists() else {}
        if folder_name in existing:
            reply = QMessageBox.question(
                self,
                "Sobrescribir",
                f"Ya existen posiciones para '{folder_name}'.\n¿Deseas sobrescribirlas?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        jf.set(folder_name, pos_dict)

        QMessageBox.information(
            self,
            "Guardado",
            f"✅ Se guardaron {len(pos_dict)} posiciones para '{folder_name}' en wm_positions.json."
        )
        print(f"✓ {len(pos_dict)} posiciones guardadas para '{folder_name}'")


# ---------------------------------------------------------------------------
# Standalone
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    dlg = AutoPositionDetector()
    dlg.show()
    sys.exit(app.exec())
