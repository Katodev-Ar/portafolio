"""
Editor de posiciones de marcas de agua
NUEVO: Clic en imagen para posición aproximada → refinamiento automático con template matching
"""
import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QFileDialog, QWidget, QMessageBox,
    QScrollArea, QSlider, QSpinBox, QGridLayout, QFormLayout, QCheckBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QKeyEvent, QImage, QPainter, QPen, QColor, QCursor
import cv2
import numpy as np

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import UtilJson
from WatermarkRemove import load_images_cv2, align_watermark, remove_watermark
from natsort import natsorted


# ─────────────────────────────────────────────
# Widget de imagen con clic
# ─────────────────────────────────────────────
class ClickableImageLabel(QLabel):
    """
    Imagen interactiva: el usuario hace clic para indicar dónde está la marca.
    Emite clicked(x, y) en coordenadas de la imagen original.
    Muestra un rectángulo overlay con el resultado (rojo=aprox, verde=refinado).
    """
    clicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_level = 60
        self.original_pixmap = None
        self.overlay_rect = None        # (x, y, w, h) coords imagen original
        self.overlay_refined = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1e1e1e;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def set_image(self, pixmap: QPixmap):
        self.original_pixmap = pixmap
        self.overlay_rect = None
        self.update_display()

    def set_overlay(self, x, y, w, h, refined=False):
        self.overlay_rect = (x, y, w, h)
        self.overlay_refined = refined
        self.update_display()

    def clear_overlay(self):
        self.overlay_rect = None
        self.update_display()

    def update_display(self):
        if self.original_pixmap is None:
            return
        scale = self.zoom_level / 100.0
        scaled = self.original_pixmap.scaled(
            self.original_pixmap.size() * scale,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        if self.overlay_rect:
            x, y, w, h = self.overlay_rect
            sx, sy = int(x * scale), int(y * scale)
            sw, sh = int(w * scale), int(h * scale)
            painter = QPainter(scaled)
            if self.overlay_refined:
                pen_color = QColor(0, 220, 80, 220)
                fill_color = QColor(0, 220, 80, 35)
                label_txt = "✓ Refinado"
            else:
                pen_color = QColor(255, 80, 60, 220)
                fill_color = QColor(255, 80, 60, 30)
                label_txt = "≈ Aproximado"
            pen = QPen(pen_color)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(fill_color)
            painter.drawRect(sx, sy, sw, sh)
            painter.setPen(QPen(QColor(255, 255, 255, 230)))
            lx = sx + 4
            ly = sy - 8 if sy > 20 else sy + sh + 16
            painter.drawText(lx, ly, label_txt)
            painter.end()
        self.setPixmap(scaled)
        self.resize(scaled.size())

    def set_zoom(self, zoom: int):
        self.zoom_level = max(10, min(200, zoom))
        self.update_display()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.original_pixmap:
            scale = self.zoom_level / 100.0
            img_x = int(event.position().x() / scale)
            img_y = int(event.position().y() / scale)
            img_x = max(0, min(self.original_pixmap.width() - 1, img_x))
            img_y = max(0, min(self.original_pixmap.height() - 1, img_y))
            self.clicked.emit(img_x, img_y)
        super().mousePressEvent(event)


# ─────────────────────────────────────────────
# Editor principal
# ─────────────────────────────────────────────
class PositionEditor(QDialog):
    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tga', '.jfif')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.images_folder = None
        self.watermarks_folder = None
        self.image_files = []
        self.watermark_files = []
        self.current_image_index = 0
        self.current_image = None
        self.current_watermark = None
        self.marcas_base_path = Path(os.path.dirname(current_dir)) / 'marcas'

        self.offset_x = 0
        self.offset_y = 0
        self.side_x = "left"
        self.side_y = "top"
        self.current_selected_position = None
        self.saved_positions = []
        self.auto_wm_settings = {}
        self.zoom_level = 60
        self._click_x = None
        self._click_y = None

        self._setup_ui()
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

    # ── UI ──────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("Editor de Posiciones — Clic para colocar marca")
        self.setModal(True)
        self.resize(1200, 900)
        main = QHBoxLayout(self)
        main.setSpacing(10)
        main.setContentsMargins(8, 8, 8, 8)
        main.addWidget(self._create_controls_panel())
        main.addWidget(self._create_image_panel(), 1)

    def _create_controls_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(275)
        layout = QVBoxLayout(panel)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # Selección
        fg = QGroupBox("📁 Selección")
        fl = QVBoxLayout()
        fl.setSpacing(5)
        btn_img = QPushButton("📂 Carpeta de Imágenes")
        btn_img.clicked.connect(self._select_images_folder)
        btn_img.setStyleSheet("padding: 6px;")
        fl.addWidget(btn_img)
        self.images_label = QLabel("No seleccionada")
        self.images_label.setStyleSheet("color: #888; font-size: 10px; padding-left: 8px;")
        self.images_label.setWordWrap(True)
        fl.addWidget(self.images_label)
        fl.addWidget(QLabel("Carpeta de Marcas:"))
        self.watermark_folder_combo = QComboBox()
        self.watermark_folder_combo.currentIndexChanged.connect(self._on_watermark_folder_changed)
        fl.addWidget(self.watermark_folder_combo)
        fl.addWidget(QLabel("Marca específica:"))
        self.watermark_combo = QComboBox()
        self.watermark_combo.currentIndexChanged.connect(self._on_watermark_changed)
        fl.addWidget(self.watermark_combo)
        ach = QHBoxLayout()
        self.enable_auto_config_checkbox = QCheckBox("Config. Automática")
        self.enable_auto_config_checkbox.toggled.connect(self._save_auto_config_state)
        self.toggle_options_btn = QPushButton("Mostrar ▼")
        self.toggle_options_btn.setCheckable(True)
        self.toggle_options_btn.toggled.connect(self._toggle_auto_config_visibility)
        ach.addWidget(self.enable_auto_config_checkbox)
        ach.addStretch()
        ach.addWidget(self.toggle_options_btn)
        fl.addLayout(ach)
        self.auto_wm_options_widget = QWidget()
        awl = QFormLayout()
        self.first_wm_combo = QComboBox()
        self.middle_wm_combo = QComboBox()
        self.last_wm_combo = QComboBox()
        btn_save_auto = QPushButton("💾 Guardar Config. Auto")
        btn_save_auto.clicked.connect(self._save_auto_wm_config)
        awl.addRow("Primera:", self.first_wm_combo)
        awl.addRow("Intermedia:", self.middle_wm_combo)
        awl.addRow("Última:", self.last_wm_combo)
        awl.addRow(btn_save_auto)
        self.auto_wm_options_widget.setLayout(awl)
        self.auto_wm_options_widget.hide()
        fl.addWidget(self.auto_wm_options_widget)
        self._load_watermark_folders()
        fg.setLayout(fl)
        layout.addWidget(fg)

        # Clic para colocar
        cg = QGroupBox("🖱️ Clic en imagen para colocar")
        cl = QVBoxLayout()
        cl.setSpacing(6)
        hint = QLabel("1. Haz clic donde está la marca\n2. Se refina automáticamente\n3. Ajusta fino con las flechas")
        hint.setStyleSheet("color: #aaa; font-size: 10px; padding: 4px;")
        cl.addWidget(hint)
        self.click_status_label = QLabel("Sin posición")
        self.click_status_label.setStyleSheet(
            "color: #ff9800; font-size: 11px; font-weight: bold; padding: 5px;"
            "background: #2a2a2a; border-radius: 4px;"
        )
        self.click_status_label.setWordWrap(True)
        self.click_status_label.setMinimumHeight(55)
        cl.addWidget(self.click_status_label)
        btn_refine = QPushButton("🔍 Refinar posición ahora")
        btn_refine.setStyleSheet(
            "background:#1565C0; color:white; padding:8px; font-weight:bold; border-radius:4px;"
        )
        btn_refine.clicked.connect(self._refine_from_click)
        cl.addWidget(btn_refine)
        btn_clear = QPushButton("✕ Limpiar clic")
        btn_clear.setStyleSheet("color: #888; padding: 4px;")
        btn_clear.clicked.connect(self._clear_click)
        cl.addWidget(btn_clear)
        cg.setLayout(cl)
        layout.addWidget(cg)

        # Posición manual
        pg = QGroupBox("🎮 Ancla manual (alternativa)")
        pl = QVBoxLayout()
        pl.setSpacing(5)
        gc = QWidget()
        self.position_grid = QGridLayout(gc)
        self.position_grid.setSpacing(4)
        self.position_buttons = {}
        for row_idx, row in enumerate([[7, 8, 9], [4, 5, 6], [1, 2, 3]]):
            for col_idx, num in enumerate(row):
                btn = QPushButton(str(num))
                btn.setFixedSize(38, 38)
                btn.setCheckable(True)
                btn.clicked.connect(lambda c, n=num: self._on_grid_button_clicked(n))
                self.position_grid.addWidget(btn, row_idx, col_idx)
                self.position_buttons[num] = btn
        pl.addWidget(gc)
        pl.addWidget(QLabel("Ajuste fino (px):"))
        ox = QHBoxLayout()
        ox.addWidget(QLabel("X:"))
        self.offset_x_spin = QSpinBox()
        self.offset_x_spin.setRange(-9999, 9999)
        self.offset_x_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_x_spin.valueChanged.connect(lambda v: self._on_offset_spin_changed('x', v))
        ox.addWidget(self.offset_x_spin, 1)
        pl.addLayout(ox)
        oy = QHBoxLayout()
        oy.addWidget(QLabel("Y:"))
        self.offset_y_spin = QSpinBox()
        self.offset_y_spin.setRange(-9999, 9999)
        self.offset_y_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.offset_y_spin.valueChanged.connect(lambda v: self._on_offset_spin_changed('y', v))
        oy.addWidget(self.offset_y_spin, 1)
        pl.addLayout(oy)
        btn_sc = QPushButton("💾 Guardar Coordenadas")
        btn_sc.clicked.connect(self._save_preset_offsets)
        btn_sc.setStyleSheet("padding: 5px; margin-top: 4px;")
        pl.addWidget(btn_sc)
        pg.setLayout(pl)
        layout.addWidget(pg)

        # Contador + acciones
        self.counter_label = QLabel("0 / 0")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3; padding: 8px;")
        layout.addWidget(self.counter_label)

        self.btn_save = QPushButton("💾 Guardar y Siguiente  [Enter]")
        self.btn_save.clicked.connect(self._save_and_next)
        self.btn_save.setStyleSheet(
            "padding: 12px; background:#388E3C; color:white; font-weight:bold; border-radius:4px;"
        )
        self.btn_save.setEnabled(False)
        layout.addWidget(self.btn_save)

        btn_close = QPushButton("❌ Cerrar")
        btn_close.clicked.connect(self.close)
        btn_close.setStyleSheet("padding: 10px; background:#c62828; color:white; border-radius:4px;")
        layout.addWidget(btn_close)

        layout.addStretch()
        return panel

    def _create_image_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        zc = QWidget()
        zl = QHBoxLayout(zc)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        zl.addWidget(self.zoom_slider, 1)
        self.zoom_label = QLabel(f"{self.zoom_level}%")
        self.zoom_label.setFixedWidth(45)
        self.zoom_label.setStyleSheet("font-weight: bold;")
        zl.addWidget(self.zoom_label)
        layout.addWidget(zc)

        hint2 = QLabel("👆 Haz clic en la imagen donde aparece la marca de agua — se ajustará automáticamente")
        hint2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint2.setStyleSheet(
            "background:#1a3a5c; color:#64b5f6; padding:6px; font-size:11px; border-radius:4px;"
        )
        layout.addWidget(hint2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setStyleSheet("border: 2px solid #444;")
        self.image_label = ClickableImageLabel()
        self.image_label.clicked.connect(self._on_image_clicked)
        scroll.setWidget(self.image_label)
        layout.addWidget(scroll, 1)
        return panel

    # ── Clic + refinamiento ────────────────────────────

    def _on_image_clicked(self, img_x: int, img_y: int):
        self._click_x = img_x
        self._click_y = img_y
        self.click_status_label.setText(f"Clic en ({img_x}, {img_y}) — refinando...")
        self.click_status_label.setStyleSheet(
            "color:#ff9800; font-size:11px; font-weight:bold; padding:5px;"
            "background:#2a2a2a; border-radius:4px;"
        )
        if self.current_watermark is not None:
            wm_h, wm_w = self.current_watermark.shape[:2]
            self.image_label.set_overlay(
                max(0, img_x - wm_w // 2), max(0, img_y - wm_h // 2),
                wm_w, wm_h, refined=False
            )
        self._refine_from_click()

    def _refine_from_click(self):
        if self._click_x is None or self._click_y is None:
            self.click_status_label.setText("⚠ Haz clic en la imagen primero")
            return
        if self.current_image is None or self.current_watermark is None:
            self.click_status_label.setText("⚠ Carga imagen y marca primero")
            return

        img = self.current_image
        wm = self.current_watermark
        wm_h, wm_w = wm.shape[:2]
        h_img, w_img = img.shape[:2]

        # Template: marca sobre fondo blanco
        wm_color = wm[:, :, :3]
        alpha = wm[:, :, 3:4].astype(np.float32) / 255.0
        template = (wm_color.astype(np.float32) * alpha +
                    np.ones_like(wm_color, dtype=np.float32) * 255 * (1 - alpha)).astype(np.uint8)
        tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        # Ventana de búsqueda alrededor del clic
        cx, cy = self._click_x, self._click_y
        ax = cx - wm_w // 2
        ay = cy - wm_h // 2
        margin_x = max(120, wm_w)
        margin_y = max(120, wm_h)

        sx1 = max(0, ax - margin_x)
        sy1 = max(0, ay - margin_y)
        sx2 = min(w_img - wm_w, ax + margin_x)
        sy2 = min(h_img - wm_h, ay + margin_y)

        if sx2 < sx1 or sy2 < sy1 or (sx2 - sx1) < 1 or (sy2 - sy1) < 1:
            self._apply_position(ax, ay, wm_w, wm_h, 0.0)
            return

        region = img[sy1:sy2 + wm_h, sx1:sx2 + wm_w]
        if region.shape[0] < wm_h or region.shape[1] < wm_w:
            self._apply_position(ax, ay, wm_w, wm_h, 0.0)
            return

        try:
            result = cv2.matchTemplate(
                cv2.cvtColor(region, cv2.COLOR_BGR2GRAY),
                tpl_gray,
                cv2.TM_CCOEFF_NORMED
            )
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            refined_x = sx1 + max_loc[0]
            refined_y = sy1 + max_loc[1]
        except Exception:
            self._apply_position(ax, ay, wm_w, wm_h, 0.0)
            return

        self._apply_position(refined_x, refined_y, wm_w, wm_h, max_val)

    def _apply_position(self, rx: int, ry: int, wm_w: int, wm_h: int, score: float):
        """Aplica posición refinada (o aproximada si score=0) al editor."""
        h_img, w_img = self.current_image.shape[:2]
        cx = rx + wm_w // 2
        cy = ry + wm_h // 2

        if cx / w_img < 0.33:
            side_x = "left";   off_x = rx
        elif cx / w_img > 0.67:
            side_x = "right";  off_x = w_img - wm_w - rx
        else:
            side_x = "center"; off_x = rx - (w_img - wm_w) // 2

        if cy / h_img < 0.33:
            side_y = "top";    off_y = ry
        elif cy / h_img > 0.67:
            side_y = "bottom"; off_y = h_img - wm_h - ry
        else:
            side_y = "center"; off_y = ry - (h_img - wm_h) // 2

        self.side_x = side_x
        self.side_y = side_y
        self.offset_x = off_x
        self.offset_y = off_y

        self.offset_x_spin.blockSignals(True)
        self.offset_y_spin.blockSignals(True)
        self.offset_x_spin.setValue(off_x)
        self.offset_y_spin.setValue(off_y)
        self.offset_x_spin.blockSignals(False)
        self.offset_y_spin.blockSignals(False)

        num_map = {
            ("left","top"):7, ("center","top"):8, ("right","top"):9,
            ("left","center"):4, ("center","center"):5, ("right","center"):6,
            ("left","bottom"):1, ("center","bottom"):2, ("right","bottom"):3,
        }
        num = num_map.get((side_x, side_y))
        if num:
            for n, btn in self.position_buttons.items():
                btn.setChecked(n == num)
            self.current_selected_position = num

        refined = score > 0.1
        self.image_label.set_overlay(rx, ry, wm_w, wm_h, refined=refined)

        if refined:
            self.click_status_label.setText(
                f"✓ Refinado: ({rx}, {ry})\n"
                f"  {side_x}/{side_y}  off=({off_x}, {off_y})\n"
                f"  Confianza: {int(score*100)}%"
            )
            self.click_status_label.setStyleSheet(
                "color:#66bb6a; font-size:11px; font-weight:bold; padding:5px;"
                "background:#1a2e1a; border-radius:4px;"
            )
        else:
            self.click_status_label.setText(
                f"⚠ Aproximado: ({rx}, {ry})\n"
                f"  {side_x}/{side_y}  off=({off_x}, {off_y})\n"
                f"  Ajusta manualmente si hace falta"
            )
            self.click_status_label.setStyleSheet(
                "color:#ffb74d; font-size:11px; font-weight:bold; padding:5px;"
                "background:#2a2200; border-radius:4px;"
            )

        self._update_preview()

    def _clear_click(self):
        self._click_x = None
        self._click_y = None
        self.image_label.clear_overlay()
        self.click_status_label.setText("Sin posición")
        self.click_status_label.setStyleSheet(
            "color:#ff9800; font-size:11px; font-weight:bold; padding:5px;"
            "background:#2a2a2a; border-radius:4px;"
        )

    # ── Posición manual ────────────────────────────────

    def _on_grid_button_clicked(self, n):
        for num, btn in self.position_buttons.items():
            btn.setChecked(num == n)
        pos_map = {
            1:("left","bottom"), 2:("center","bottom"), 3:("right","bottom"),
            4:("left","center"), 5:("center","center"), 6:("right","center"),
            7:("left","top"),    8:("center","top"),    9:("right","top"),
        }
        s = pos_map[n]
        self.side_x, self.side_y = s
        self.current_selected_position = n
        self._load_preset_offsets_for_position(n)
        self._update_preview()
        self.setFocus()

    def _load_preset_offsets_for_position(self, n):
        if not self.watermarks_folder:
            self.offset_x_spin.setValue(0); self.offset_y_spin.setValue(0); return
        jp = Path(os.path.dirname(current_dir)) / 'wm_preset_offsets.json'
        if not jp.exists():
            self.offset_x_spin.setValue(0); self.offset_y_spin.setValue(0); return
        coords = UtilJson(jp).read().get(self.watermarks_folder.name, {}).get(str(n))
        if coords:
            self.offset_x_spin.setValue(coords.get('offset_x', 0))
            self.offset_y_spin.setValue(coords.get('offset_y', 0))
        else:
            self.offset_x_spin.setValue(0); self.offset_y_spin.setValue(0)

    def _save_preset_offsets(self):
        if self.current_selected_position is None or not self.watermarks_folder:
            QMessageBox.warning(self, "Atención", "Selecciona carpeta y posición primero."); return
        coords = {'offset_x': self.offset_x_spin.value(), 'offset_y': self.offset_y_spin.value()}
        if self._update_preset_config(str(self.current_selected_position), coords):
            QMessageBox.information(self, "Guardado",
                f"Coordenadas para posición {self.current_selected_position} guardadas.")

    def _on_offset_spin_changed(self, axis, v):
        if axis == 'x': self.offset_x = v
        else:           self.offset_y = v
        self._update_preview()

    # ── Preview ────────────────────────────────────────

    def _update_preview(self):
        if self.current_image is None or self.current_watermark is None: return
        try:
            img = self.current_image.copy()
            wm = self.current_watermark
            x, y = align_watermark(img, wm, self.offset_x, self.offset_y, self.side_x, self.side_y)
            res = remove_watermark(img, wm, x, y)
            rgb = cv2.cvtColor(res, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            q = QImage(rgb.data, w, h, 3*w, QImage.Format.Format_RGB888)
            self.image_label.original_pixmap = QPixmap.fromImage(q)
            self.image_label.update_display()
        except Exception as e:
            self.image_label.setText(f"❌ Error: {e}")

    # ── Carpetas / archivos ─────────────────────────────

    def _select_images_folder(self):
        f = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Imágenes")
        if f:
            self.images_folder = Path(f)
            self.images_label.setText(self.images_folder.name)
            self._load_images(); self._check_ready()

    def _load_watermark_folders(self):
        self.watermark_folder_combo.clear()
        if not self.marcas_base_path.exists(): return
        for folder in sorted([f for f in self.marcas_base_path.iterdir() if f.is_dir()], reverse=True):
            self.watermark_folder_combo.addItem(folder.name, str(folder))

    def _on_watermark_folder_changed(self, i):
        if i < 0: return
        p = self.watermark_folder_combo.currentData()
        if p:
            self.watermarks_folder = Path(p)
            self._load_watermarks_into_combos()
            self._load_auto_wm_config()
            self._check_ready()

    def _load_images(self):
        if not self.images_folder or not self.images_folder.exists(): return
        self.image_files = [
            f for f in natsorted(self.images_folder.iterdir())
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_FORMATS
        ]
        self.current_image_index = 0
        self._update_counter()

    def _load_watermarks_into_combos(self):
        for c in [self.watermark_combo, self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]:
            c.clear()
        self.watermark_files = []
        if not self.watermarks_folder or not self.watermarks_folder.exists(): return
        for f in natsorted(self.watermarks_folder.iterdir()):
            if f.is_file() and f.suffix.lower() == '.png':
                self.watermark_files.append(f)
        for f in self.watermark_files:
            for c in [self.watermark_combo, self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]:
                c.addItem(f.name, str(f))

    def _check_ready(self):
        ready = bool(self.images_folder and self.watermarks_folder and self.image_files and self.watermark_files)
        self.btn_save.setEnabled(ready)
        if ready:
            self._load_current_image()
            self._apply_auto_watermark_selection()
            self._load_current_watermark()
            self._update_preview()

    def _load_current_image(self):
        if self.image_files and self.current_image_index < len(self.image_files):
            self.current_image = load_images_cv2(str(self.image_files[self.current_image_index]))
            self._clear_click()

    def _load_current_watermark(self):
        p = self.watermark_combo.currentData()
        if p: self.current_watermark = load_images_cv2(str(p))

    def _on_watermark_changed(self, i):
        if i >= 0: self._load_current_watermark(); self._update_preview()

    # ── Guardar ────────────────────────────────────────

    def _save_and_next(self):
        if self.current_selected_position is None:
            if self._click_x is not None:
                self._refine_from_click()
            if self.current_selected_position is None:
                QMessageBox.warning(self, "Sin posición",
                    "Haz clic en la imagen donde está la marca, o selecciona un ancla 1-9.")
                return

        self.saved_positions.append({
            'offset_x': self.offset_x, 'offset_y': self.offset_y,
            'side_x': self.side_x, 'side_y': self.side_y
        })

        if self.current_image_index < len(self.image_files) - 1:
            self.current_image_index += 1
            self._load_current_image()
            self._update_counter()
            self._apply_auto_watermark_selection()
            self._load_current_watermark()
            self._update_preview()
        else:
            self._save_to_json()
            QMessageBox.information(self, "Completado",
                f"Se guardaron {len(self.saved_positions)} posiciones.")
            self.accept()

    def _save_to_json(self):
        if not self.watermarks_folder or not self.saved_positions: return
        try:
            fn = self.watermarks_folder.name
            jp = Path(os.path.dirname(current_dir)) / 'wm_positions.json'
            jf = UtilJson(jp)
            jf.set(fn, {f'pos_{i}': d for i, d in enumerate(self.saved_positions, 1)})
            print(f"✓ Guardadas {len(self.saved_positions)} posiciones en '{fn}'")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar:\n{e}")

    # ── Auto-config ────────────────────────────────────

    def _toggle_auto_config_visibility(self, checked):
        self.auto_wm_options_widget.setVisible(checked)
        self.toggle_options_btn.setText("Ocultar ▲" if checked else "Mostrar ▼")

    def _save_auto_config_state(self, v):
        self._update_preset_config("auto_config_enabled", v)

    def _save_auto_wm_config(self):
        if not self.watermarks_folder:
            QMessageBox.warning(self, "Atención", "Selecciona una Carpeta de Marcas primero."); return
        cfg = {"first": self.first_wm_combo.currentText(),
               "middle": self.middle_wm_combo.currentText(),
               "last": self.last_wm_combo.currentText()}
        if self._update_preset_config("auto_selection", cfg):
            self.auto_wm_settings[self.watermarks_folder.name] = cfg
            QMessageBox.information(self, "Guardado",
                f"Config automática guardada para '{self.watermarks_folder.name}'.")

    def _load_auto_wm_config(self):
        if not self.watermarks_folder: return
        fn = self.watermarks_folder.name
        jp = Path(os.path.dirname(current_dir)) / 'wm_preset_offsets.json'
        enabled = False; cfg = None
        if jp.exists():
            fc = UtilJson(jp).read().get(fn, {})
            cfg = fc.get("auto_selection"); enabled = fc.get("auto_config_enabled", False)
        self.auto_wm_settings[fn] = cfg
        self.enable_auto_config_checkbox.setChecked(enabled)
        if cfg:
            self.first_wm_combo.setCurrentText(cfg.get("first", ""))
            self.middle_wm_combo.setCurrentText(cfg.get("middle", ""))
            self.last_wm_combo.setCurrentText(cfg.get("last", ""))
        elif self.first_wm_combo.count() > 0:
            for c in [self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]:
                c.setCurrentIndex(0)

    def _apply_auto_watermark_selection(self):
        if not self.image_files or not self.watermarks_folder: return
        if not self.enable_auto_config_checkbox.isChecked(): return
        cfg = self.auto_wm_settings.get(self.watermarks_folder.name)
        if not cfg: return
        total = len(self.image_files); idx = self.current_image_index
        target = cfg.get("first") if (idx == 0 or total == 1) else \
                 cfg.get("last") if idx == total - 1 else cfg.get("middle")
        if target:
            i = self.watermark_combo.findText(target)
            if i != -1: self.watermark_combo.setCurrentIndex(i)

    def _update_preset_config(self, key: str, value, is_coord=False) -> bool:
        if not self.watermarks_folder: return False
        fn = self.watermarks_folder.name
        jp = Path(os.path.dirname(current_dir)) / 'wm_preset_offsets.json'
        jf = UtilJson(jp)
        data = jf.read() if jp.exists() else {}
        if fn not in data: data[fn] = {}
        data[fn][key] = value
        jf.write(data)
        return True

    # Alias para compatibilidad con watermark_tab
    def _update_and_save_preset_config(self, key, value, is_coord=False):
        return self._update_preset_config(key, value, is_coord)

    # ── Utilidades ─────────────────────────────────────

    def _on_zoom_changed(self, v):
        self.zoom_level = v
        self.zoom_label.setText(f"{v}%")
        self.image_label.set_zoom(v)

    def _update_counter(self):
        self.counter_label.setText(
            f"{self.current_image_index + 1} / {len(self.image_files)}"
            if self.image_files else "0 / 0"
        )

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.btn_save.isEnabled(): self._save_and_next()
        elif e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    editor = PositionEditor()
    editor.show()
    sys.exit(app.exec())
