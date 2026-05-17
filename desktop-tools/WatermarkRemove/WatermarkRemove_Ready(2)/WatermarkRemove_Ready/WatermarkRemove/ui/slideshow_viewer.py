"""
Visor de imágenes tipo slideshow - MODIFICADO
- Corregida la lógica de "saltar imagen" (ahora copia el original).
- Eliminado el foco inicial del ComboBox para permitir atajos de teclado inmediatos.
"""
import os
import sys
import shutil
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QScrollArea, QComboBox, QGroupBox, QFormLayout, QSlider, QCheckBox,
    QGridLayout, QApplication, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer
from PyQt6.QtGui import QPixmap, QKeyEvent, QPainter, QPen, QColor, QMouseEvent

# Agregar el directorio raíz al path
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import UtilJson
from natsort import natsorted
from WatermarkRemove import align_watermark, remove_watermark
from WatermarkRemove.wm_remove import load_images_cv2, guardar

class SlideshowViewer(QDialog):
    review_completed = pyqtSignal(bool)
    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tga', '.psd', '.psb', '.jfif')

    def __init__(self, folder_path: str, parent=None, watermark_folder: str = None, watermark_name: str = None, watermark_tab=None):
        super().__init__(parent)
        self.folder_path = Path(folder_path) if folder_path else None
        self.image_files = []; self.current_index = 0; self.user_approved = False
        self.current_pixmap = None; self.zoom_level = 83
        self.watermark_tab = watermark_tab
        self.watermark_folder = Path(watermark_folder) if watermark_folder else None
        self.watermark_name = watermark_name
        self.watermark_positions = {}; self.watermark_files = []
        self.output_folder = None; self.processed_images = set()
        self.processed_positions = {}; self.watermark_rectangles = {}
        self.auto_wm_settings = {}; self.flashing_pos_name = None
        self.manual_override_active = False

        self._setup_ui()
        self._load_image_list()
        if self.watermark_folder and self.folder_path: self._create_output_folder()
        
        if self.watermark_folder:
            index = self.watermark_folder_combo.findData(str(self.watermark_folder))
            if index >= 0:
                self.watermark_folder_combo.setCurrentIndex(index)
                self._on_watermark_folder_changed(index) 
        
        if self.image_files: self._show_current_image()
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        
        # --- CORRECCIÓN: Establecer foco en la ventana principal ---
        self.setFocus()

    def _setup_ui(self):
        self.setWindowTitle("Revisión de Imágenes"); self.setModal(True); self.resize(1100, 1000)
        main_layout = QHBoxLayout(self); main_layout.setSpacing(15); main_layout.setContentsMargins(10, 10, 10, 10)
        left_panel = self._create_controls_panel(); main_layout.addWidget(left_panel)
        right_panel = self._create_image_panel(); main_layout.addWidget(right_panel, 1)

    def _create_controls_panel(self) -> QWidget:
        panel = QWidget(); panel.setFixedWidth(280); layout = QVBoxLayout(panel); layout.setSpacing(10); layout.setContentsMargins(0,0,0,0)
        info_group = QWidget(); info_layout = QVBoxLayout(info_group); info_layout.setSpacing(5)
        info_layout.addWidget(QLabel("📁 Carpeta:")); self.folder_label = QLabel(str(self.folder_path) if self.folder_path else "")
        self.folder_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 10px;"); self.folder_label.setWordWrap(True); info_layout.addWidget(self.folder_label); layout.addWidget(info_group)
        self.counter_label = QLabel("0 / 0"); self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.counter_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #2196F3; padding: 15px;"); layout.addWidget(self.counter_label)
        self.filename_label = QLabel("Sin archivo"); self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.filename_label.setStyleSheet("font-size: 12px; color: #888; padding: 10px; background-color: #1e1e1e; border-radius: 5px;"); self.filename_label.setWordWrap(True); layout.addWidget(self.filename_label)
        
        folders_group = QGroupBox("📁 Selección"); folders_layout = QFormLayout(); folders_layout.setSpacing(6)
        folders_layout.addRow(QLabel("Carpeta de Marcas:")); self.watermark_folder_combo = QComboBox(); self.watermark_folder_combo.currentIndexChanged.connect(self._on_watermark_folder_changed); folders_layout.addRow(self.watermark_folder_combo)
        folders_layout.addRow(QLabel("Marca específica:")); self.watermark_combo = QComboBox(); self.watermark_combo.currentIndexChanged.connect(self._on_watermark_changed); folders_layout.addRow(self.watermark_combo)
        
        auto_config_header_layout = QHBoxLayout(); self.enable_auto_config_checkbox = QCheckBox("Usar Config. Automática"); self.enable_auto_config_checkbox.toggled.connect(self._save_auto_config_state)
        self.toggle_options_btn = QPushButton("Opciones ▼"); self.toggle_options_btn.setCheckable(True); self.toggle_options_btn.toggled.connect(self._toggle_auto_config_visibility)
        auto_config_header_layout.addWidget(self.enable_auto_config_checkbox); auto_config_header_layout.addStretch(); auto_config_header_layout.addWidget(self.toggle_options_btn); folders_layout.addRow(auto_config_header_layout)
        self.auto_wm_options_widget = QWidget(); auto_wm_options_layout = QFormLayout(); auto_wm_options_layout.setSpacing(8)
        self.first_wm_combo=QComboBox(); self.middle_wm_combo=QComboBox(); self.last_wm_combo=QComboBox()
        self.btn_save_auto_config = QPushButton("💾 Guardar"); self.btn_save_auto_config.clicked.connect(self._save_auto_wm_config)
        auto_wm_options_layout.addRow("Primera:", self.first_wm_combo); auto_wm_options_layout.addRow("Intermedia:", self.middle_wm_combo); auto_wm_options_layout.addRow("Última:", self.last_wm_combo); auto_wm_options_layout.addRow(self.btn_save_auto_config)
        self.auto_wm_options_widget.setLayout(auto_wm_options_layout); folders_layout.addRow(self.auto_wm_options_widget); self.auto_wm_options_widget.hide()
        folders_group.setLayout(folders_layout); layout.addWidget(folders_group)

        # Fix: Load folders AFTER creating widgets to avoid AttributeError
        self._load_watermark_folders()

        keypad_group = QGroupBox("Atajos de Posición"); keypad_v_layout = QVBoxLayout(); keypad_v_layout.setSpacing(2); self.keypad_buttons = {}
        keypad_map = [(7,0,0), (8,0,1), (9,0,2), (4,1,0), (5,1,1), (6,1,2), (1,2,0), (2,2,1), (3,2,2)]
        keypad_layout = QGridLayout()
        for num, row, col in keypad_map:
            button = QPushButton(str(num)); button.setFixedSize(40, 40)
            button.clicked.connect(lambda c, n=num: self._on_keypad_button_clicked(n))
            if num in [4, 6]: button.setStyleSheet("background-color: #f44336; color: white;")
            self.keypad_buttons[num] = button; keypad_layout.addWidget(button, row, col)
        keypad_group.setLayout(keypad_layout); layout.addWidget(keypad_group)

        layout.addStretch()
        
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Anterior"); self.prev_btn.clicked.connect(self._previous_image); self.prev_btn.setStyleSheet("padding: 10px; font-size: 12px; background-color: #555; color: white;"); nav_layout.addWidget(self.prev_btn)
        self.next_btn = QPushButton("Siguiente"); self.next_btn.clicked.connect(self._next_image); self.next_btn.setStyleSheet("padding: 10px; font-size: 12px; background-color: #4CAF50; color: white; font-weight: bold;"); nav_layout.addWidget(self.next_btn)
        layout.addLayout(nav_layout)
        self.finish_btn = QPushButton("Finalizar y Procesar"); self.finish_btn.clicked.connect(self._finish_review); self.finish_btn.setStyleSheet("padding: 12px; font-size: 12px; background-color: #2196F3; color: white; font-weight: bold;"); layout.addWidget(self.finish_btn)
        self.cancel_btn = QPushButton("Cancelar"); self.cancel_btn.clicked.connect(self._cancel_review); self.cancel_btn.setStyleSheet("padding: 10px; font-size: 12px; background-color: #f44336; color: white;"); layout.addWidget(self.cancel_btn)
        return panel

    def _create_image_panel(self) -> QWidget:
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setSpacing(8); layout.setContentsMargins(0,0,0,0)
        zoom_container=QWidget(); zoom_layout=QHBoxLayout(zoom_container); zoom_layout.setContentsMargins(0,5,0,5)
        zoom_layout.addWidget(QLabel("Zoom:")); self.zoom_slider=QSlider(Qt.Orientation.Horizontal); self.zoom_slider.setRange(10, 200); self.zoom_slider.setValue(self.zoom_level); self.zoom_slider.valueChanged.connect(self._on_zoom_changed); zoom_layout.addWidget(self.zoom_slider, 1)
        self.zoom_label=QLabel(f"{self.zoom_level}%"); self.zoom_label.setFixedWidth(50); zoom_layout.addWidget(self.zoom_label); layout.addWidget(zoom_container)
        scroll = QScrollArea(); scroll.setWidgetResizable(False); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded); scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollBar:vertical { width: 9px; } QScrollBar:horizontal { height: 9px; } QScrollBar::handle { border-radius: 4px; background: #555; } QScrollBar::handle:vertical { min-height: 20px; } QScrollBar::handle:horizontal { min-width: 20px; }")
        self.image_label = QLabel(); self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter); scroll.setWidget(self.image_label); layout.addWidget(scroll, 1)
        self.scroll_area = scroll; return panel

    def _on_keypad_button_clicked(self, number):
        if number in [4, 6]:
            self._skip_and_copy_image()
            return

        num_to_alignment_map = {7: ('left', 'top'), 8: ('center', 'top'), 9: ('right', 'top'), 5: ('center', 'center'), 1: ('left', 'bottom'), 2: ('center', 'bottom'), 3: ('right', 'bottom')}
        target_alignment = num_to_alignment_map.get(number)
        if not target_alignment: return
        
        found_pos_name, found_rect_data = None, None
        for pos_name, rect_data in self.watermark_rectangles.items():
            if rect_data['side_x'] == target_alignment[0] and rect_data['side_y'] == target_alignment[1]:
                found_pos_name = pos_name; found_rect_data = rect_data; break
        
        if found_pos_name and found_rect_data:
            self.flashing_pos_name = found_pos_name
            self._apply_zoom()
            QTimer.singleShot(100, lambda: self._process_watermark_at_position(found_pos_name, found_rect_data, is_cumulative=False))
        else:
            self._log(f"Atajo {number} presionado, pero no hay marca de agua en esa posición.")
    
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        key_map = {Qt.Key.Key_1: 1, Qt.Key.Key_2: 2, Qt.Key.Key_3: 3, Qt.Key.Key_4: 4, Qt.Key.Key_5: 5, Qt.Key.Key_6: 6, Qt.Key.Key_7: 7, Qt.Key.Key_8: 8, Qt.Key.Key_9: 9}
        if key in key_map:
            number = key_map[key]; self._on_keypad_button_clicked(number); event.accept(); return
        
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal): self._on_zoom_changed(self.zoom_level + 10); event.accept(); return
            elif key == Qt.Key.Key_Minus: self._on_zoom_changed(self.zoom_level - 10); event.accept(); return
            elif key == Qt.Key.Key_0: self._on_zoom_changed(100); event.accept(); return
        if key == Qt.Key.Key_Space: self._next_image()
        elif key == Qt.Key.Key_Backspace: self._previous_image()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter): self._finish_review()
        elif key == Qt.Key.Key_Escape: self._cancel_review()
        else: super().keyPressEvent(event)

    def _draw_watermark_overlays(self, pixmap: QPixmap, scale_factor: float) -> QPixmap:
        result_pixmap = QPixmap(pixmap); painter = QPainter(result_pixmap); self.watermark_rectangles = {}; processed_positions_set = self.processed_positions.get(self.current_index, set())
        try:
            current_watermark_index = self.watermark_combo.currentIndex()
            if current_watermark_index < 0 or not self.watermark_files: painter.end(); return result_pixmap
            watermark_cv = load_images_cv2(self.watermark_files[current_watermark_index])
            if watermark_cv is None: painter.end(); return result_pixmap
            wm_h, wm_w = watermark_cv.shape[:2]; img_w, img_h = self.current_pixmap.width(), self.current_pixmap.height()
            for pos_name, pos_data in self.watermark_positions.items():
                off_x, off_y = pos_data.get('offset_x', 0), pos_data.get('offset_y', 0); side_x, side_y = pos_data.get('side_x', 'left'), pos_data.get('side_y', 'top')
                if side_x == 'left': x = off_x
                elif side_x == 'center': x = (img_w - wm_w) // 2 + off_x
                else: x = img_w - wm_w - off_x
                if side_y == 'top': y = off_y
                elif side_y == 'center': y = (img_h - wm_h) // 2 + off_y
                else: y = img_h - wm_h - off_y
                scaled_x, scaled_y = int(x * scale_factor), int(y * scale_factor); scaled_w, scaled_h = int(wm_w * scale_factor), int(wm_h * scale_factor)
                self.watermark_rectangles[pos_name] = {'rect': QRect(x, y, wm_w, wm_h), 'scaled_rect': QRect(scaled_x, scaled_y, scaled_w, scaled_h), 'offset_x': off_x, 'offset_y': off_y, 'side_x': side_x, 'side_y': side_y}
                if pos_name == self.flashing_pos_name: pen_color = QColor(255, 255, 0, 255); brush_color = QColor(255, 255, 0, 80)
                elif pos_name in processed_positions_set: pen_color = QColor(0, 255, 0, 200); brush_color = QColor(0, 255, 0, 25) 
                else: pen_color = QColor(255, 0, 0, 200); brush_color = QColor(255, 0, 0, 5)
                pen = QPen(pen_color); pen.setWidth(3); painter.setPen(pen); painter.setBrush(brush_color); painter.drawRect(scaled_x, scaled_y, scaled_w, scaled_h)
                painter.setPen(QPen(QColor(255, 255, 255, 255))); painter.drawText(scaled_x + 5, scaled_y + 15, pos_name)
        except Exception as e: self._log(f"⚠️ Error dibujando overlays: {e}")
        finally: painter.end()
        return result_pixmap
        
    def _process_watermark_at_position(self, pos_name: str, rect_data: dict, is_cumulative: bool = False):
        self.flashing_pos_name = None
        if not self.output_folder or not self.image_files: return
        try:
            current_file = self.image_files[self.current_index]; current_watermark_index = self.watermark_combo.currentIndex()
            if current_watermark_index < 0 or not self.watermark_files: return
            output_path = self.output_folder / current_file.name
            image = load_images_cv2(output_path) if is_cumulative and output_path.exists() else load_images_cv2(current_file)
            if not is_cumulative and self.current_index in self.processed_positions: self.processed_positions[self.current_index].clear()
            if image is None: self._log(f"❌ Error cargando imagen: {current_file.name}"); return
            watermark = load_images_cv2(self.watermark_files[current_watermark_index])
            if watermark is None: self._log(f"❌ Error cargando marca: {self.watermark_files[current_watermark_index].name}"); return
            x, y = align_watermark(image, watermark, offset_x=rect_data['offset_x'], offset_y=rect_data['offset_y'], side_x=rect_data['side_x'], side_y=rect_data['side_y'])
            result_image = remove_watermark(image, watermark, x, y); guardar(current_file, result_image, self.output_folder)
            self.processed_images.add(self.current_index)
            if self.current_index not in self.processed_positions: self.processed_positions[self.current_index] = set()
            self.processed_positions[self.current_index].add(pos_name)
            self._log(f"✅ Marca removida: {pos_name} en {current_file.name}")
            if not is_cumulative: self._next_image()
            else: self._show_current_image()
        except Exception as e: self._log(f"❌ Error procesando: {e}")
        

    # =========================
    # Auto-Proceso (sin clicks)
    # =========================
    def _start_auto_process(self):
        if self.auto_running:
            return
        if not self.image_files or not self.folder_path:
            self._log("⚠️ No hay imágenes cargadas.")
            return
        if not self.watermark_folder or not self.watermark_folder.exists():
            self._log("⚠️ Selecciona una carpeta de marcas primero.")
            return
        if not self.watermark_positions:
            self._log("⚠️ No hay posiciones cargadas para esta carpeta de marcas.")
            return
        if not self.output_folder:
            self._create_output_folder()

        self.auto_running = True
        if hasattr(self, "auto_start_btn"): self.auto_start_btn.setEnabled(False)
        if hasattr(self, "auto_stop_btn"): self.auto_stop_btn.setEnabled(True)
        self._log("⚡ Auto-Proceso iniciado.")
        self._auto_process_step()

    def _stop_auto_process(self):
        self.auto_running = False
        try:
            self.auto_timer.stop()
        except Exception:
            pass
        if hasattr(self, "auto_start_btn"): self.auto_start_btn.setEnabled(True)
        if hasattr(self, "auto_stop_btn"): self.auto_stop_btn.setEnabled(False)
        if hasattr(self, "auto_status_label"): self.auto_status_label.setText("Auto detenido.")
        self._log("⏹️ Auto-Proceso detenido.")

    def _auto_process_step(self):
        if not self.auto_running:
            return

        if not self.image_files or self.current_index >= len(self.image_files):
            self.auto_running = False
            if hasattr(self, "auto_start_btn"): self.auto_start_btn.setEnabled(True)
            if hasattr(self, "auto_stop_btn"): self.auto_stop_btn.setEnabled(False)
            if hasattr(self, "auto_status_label"): self.auto_status_label.setText("✅ Auto terminado.")
            self._log("✅ Auto-Proceso finalizado.")
            return

        current_file = self.image_files[self.current_index]
        if hasattr(self, "auto_status_label"):
            self.auto_status_label.setText(f"Procesando: {self.current_index + 1}/{len(self.image_files)} — {current_file.name}")

        try:
            # Si ya existe en salida, asumimos procesada y avanzamos
            if self.output_folder:
                out_path = self.output_folder / current_file.name
                if out_path.exists():
                    self._log(f"↪️ Ya existe en salida, salto: {current_file.name}")
                    self._next_image()
                    self.auto_timer.start(1)
                    return

            best = self._auto_detect_best_candidate(current_file)
            if best is None:
                # No detectó con confianza -> copiar original y avanzar
                self._log(f"⚠️ No se detectó marca con confianza, copio original: {current_file.name}")
                self._skip_and_copy_image()
                self.auto_timer.start(1)
                return

            best_pos, best_wm_index, best_score = best

            # Seleccionar watermark en el combo para reutilizar la función existente
            if best_wm_index is not None and 0 <= best_wm_index < self.watermark_combo.count():
                self.watermark_combo.setCurrentIndex(best_wm_index)

            if best_pos in self.watermark_positions:
                self.flashing_pos_name = best_pos
                self._process_watermark_at_position(best_pos, self.watermark_positions[best_pos], is_cumulative=False)
                self._log(f"⚡ Auto OK: {current_file.name} -> {best_pos} (score={best_score:.2f})")
            else:
                self._log(f"⚠️ Posición detectada no existe: {best_pos}. Copio original.")
                self._skip_and_copy_image()

        except Exception as e:
            self._log(f"❌ Error en Auto-Proceso: {e}")
            # En error, copiamos original para no detener el lote
            try:
                self._skip_and_copy_image()
            except Exception:
                pass

        # Programar siguiente paso sin bloquear la UI
        if self.auto_running:
            self.auto_timer.start(1)

    def _auto_detect_best_candidate(self, image_path: Path):
        """Devuelve (pos_name, wm_index, score) o None si es incierto."""
        try:
            image = load_images_cv2(image_path)
            if image is None:
                return None
        except Exception:
            return None

        # Posiciones únicas (evita duplicados en el JSON)
        pos_candidates = []
        seen = set()
        for pos_name, rd in (self.watermark_positions or {}).items():
            try:
                key = (rd.get('side_x'), rd.get('side_y'), int(rd.get('offset_x', 0)), int(rd.get('offset_y', 0)))
            except Exception:
                key = (rd.get('side_x'), rd.get('side_y'), rd.get('offset_x'), rd.get('offset_y'))
            if key in seen:
                continue
            seen.add(key)
            pos_candidates.append((pos_name, rd))

        if not pos_candidates or not self.watermark_files:
            return None

        # Watermarks candidatos: solo el seleccionado, o todos si está activo Auto-detectar variantes
        if hasattr(self, "auto_detect_checkbox") and self.auto_detect_checkbox.isChecked():
            wm_indices = list(range(len(self.watermark_files)))
        else:
            idx = self.watermark_combo.currentIndex()
            wm_indices = [idx] if idx >= 0 else list(range(len(self.watermark_files)))

        best = (None, None, float("inf"))
        second = float("inf")

        for wm_idx in wm_indices:
            wm_path = self.watermark_files[wm_idx]
            try:
                watermark = load_images_cv2(wm_path)
                if watermark is None or watermark.shape[2] < 4:
                    continue
            except Exception:
                continue

            for pos_name, rd in pos_candidates:
                score = self._score_candidate(image, watermark, rd)
                if score < best[2]:
                    second = best[2]
                    best = (pos_name, wm_idx, score)
                elif score < second:
                    second = score

        if best[0] is None or not np.isfinite(best[2]):
            return None

        # Heurística de confianza (conservadora)
        if best[2] > 110.0 and (second - best[2]) < 6.0:
            return None

        return best

    def _score_candidate(self, image: np.ndarray, watermark: np.ndarray, rd: dict) -> float:
        """Score menor = más probable que la marca esté ahí."""
        try:
            x, y = align_watermark(
                image, watermark,
                offset_x=int(rd.get('offset_x', 0)),
                offset_y=int(rd.get('offset_y', 0)),
                side_x=rd.get('side_x', 'left'),
                side_y=rd.get('side_y', 'top')
            )
        except Exception:
            return float("inf")

        x, y = int(x), int(y)
        h_img, w_img = image.shape[:2]
        h_wm, w_wm = watermark.shape[:2]

        # Overlap en imagen
        x_start_img = max(0, x)
        y_start_img = max(0, y)
        x_end_img = min(w_img, x + w_wm)
        y_end_img = min(h_img, y + h_wm)
        if x_start_img >= x_end_img or y_start_img >= y_end_img:
            return float("inf")

        # Overlap en watermark
        x_start_wm = max(0, -x)
        y_start_wm = max(0, -y)
        x_end_wm = x_start_wm + (x_end_img - x_start_img)
        y_end_wm = y_start_wm + (y_end_img - y_start_img)

        roi = image[y_start_img:y_end_img, x_start_img:x_end_img, :3].astype(np.float32)
        wm_crop = watermark[y_start_wm:y_end_wm, x_start_wm:x_end_wm, :3].astype(np.float32)
        alpha = (watermark[y_start_wm:y_end_wm, x_start_wm:x_end_wm, 3].astype(np.float32) / 255.0)
        if alpha.size == 0:
            return float("inf")

        # máscara: solo donde hay marca (alpha > ~4%)
        mask = alpha > 0.04
        if mask.sum() < 150:
            return float("inf")

        mask3 = mask[:, :, None]

        # 1) similitud con el template
        diff = np.abs(roi - wm_crop)
        diff_score = float(diff[mask3].mean())

        # 2) penalización por clipping al "desmezclar"
        alpha3 = alpha[:, :, None]
        alpha_safe = np.clip(1.0 - alpha3, 1e-5, 1.0)
        bg_raw = (roi / alpha_safe) - (wm_crop * (alpha3 / alpha_safe))

        clip = np.clip(bg_raw, 0.0, 255.0)
        clip_err = float(np.abs(bg_raw - clip)[mask3].mean())

        out_ratio = float(((bg_raw < 0.0) | (bg_raw > 255.0))[mask3].mean())

        return diff_score + (clip_err * 0.6) + (out_ratio * 350.0)

    def _on_zoom_changed(self, value): self.zoom_level = value; self.zoom_label.setText(f"{value}%"); self._apply_zoom()
    def _apply_zoom(self):
        if self.current_pixmap is None or self.current_pixmap.isNull(): return
        scale_factor = self.zoom_level / 100.0; new_size = self.current_pixmap.size() * scale_factor
        scaled_pixmap = self.current_pixmap.scaled(new_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if self.watermark_positions and self.watermark_files: scaled_pixmap = self._draw_watermark_overlays(scaled_pixmap, scale_factor)
        self.image_label.setPixmap(scaled_pixmap); self.image_label.resize(scaled_pixmap.size())
    def _toggle_auto_config_visibility(self, checked):
        if checked: self.auto_wm_options_widget.show(); self.toggle_options_btn.setText("Ocultar ▲")
        else: self.auto_wm_options_widget.hide(); self.toggle_options_btn.setText("Opciones ▼")
    
    def _update_and_save_preset_config(self, key: str, value):
        if not self.watermark_folder: return False
        folder_name = self.watermark_folder.name; json_path = Path(os.path.dirname(current_dir)) / 'wm_preset_offsets.json'
        json_file = UtilJson(json_path); all_presets = json_file.read() if json_path.exists() else {}
        if folder_name not in all_presets: all_presets[folder_name] = {}
        all_presets[folder_name][key] = value
        json_file.write(all_presets); return True

    def _save_auto_config_state(self, is_enabled):
        if self._update_and_save_preset_config("auto_config_enabled", is_enabled): self._apply_auto_watermark_selection()

    def _save_auto_wm_config(self):
        config_data = {"first": self.first_wm_combo.currentText(), "middle": self.middle_wm_combo.currentText(), "last": self.last_wm_combo.currentText()}
        if self._update_and_save_preset_config("auto_selection", config_data):
            self.auto_wm_settings[self.watermark_folder.name] = config_data
            QMessageBox.information(self, "Guardado", f"Configuración guardada para '{self.watermark_folder.name}'.")

    def _load_auto_wm_config(self):
        if not self.watermark_folder: return
        folder_name=self.watermark_folder.name; json_path=Path(os.path.dirname(current_dir))/'wm_preset_offsets.json'
        enabled_state = False; config = None
        if json_path.exists():
            json_file=UtilJson(json_path); all_presets=json_file.read(); folder_config=all_presets.get(folder_name,{})
            config=folder_config.get("auto_selection"); enabled_state=folder_config.get("auto_config_enabled", False)
        self.auto_wm_settings[folder_name] = config; self.enable_auto_config_checkbox.setChecked(enabled_state)
        if config: self.first_wm_combo.setCurrentText(config.get("first","")); self.middle_wm_combo.setCurrentText(config.get("middle","")); self.last_wm_combo.setCurrentText(config.get("last",""))
        else:
            if self.first_wm_combo.count() > 0: self.first_wm_combo.setCurrentIndex(0); self.middle_wm_combo.setCurrentIndex(0); self.last_wm_combo.setCurrentIndex(0)
    
    def _apply_auto_watermark_selection(self):
        if self.manual_override_active: return
        if not self.image_files or not self.watermark_folder or not self.enable_auto_config_checkbox.isChecked(): return
        folder_name=self.watermark_folder.name; config=self.auto_wm_settings.get(folder_name)
        if not config: return
        total_images=len(self.image_files); current_idx=self.current_index; target_wm_name=""
        if total_images == 1: target_wm_name=config.get("first")
        elif current_idx == 0: target_wm_name=config.get("first")
        elif current_idx == total_images-1: target_wm_name=config.get("last")
        else: target_wm_name=config.get("middle")
        if target_wm_name:
            # Desconectar temporalmente la señal para evitar el override
            self.watermark_combo.currentIndexChanged.disconnect(self._on_watermark_changed)
            index=self.watermark_combo.findText(target_wm_name)
            if index != -1: self.watermark_combo.setCurrentIndex(index)
            self.watermark_combo.currentIndexChanged.connect(self._on_watermark_changed)
            
    def _on_watermark_folder_changed(self, index):
        if index < 0: return
        folder_path = self.watermark_folder_combo.currentData()
        if folder_path: self.watermark_folder = Path(folder_path); self.watermark_name = self.watermark_folder_combo.currentText(); self._load_watermarks_into_combos(); self._load_watermark_positions(); self._load_auto_wm_config()
        if not self.output_folder and self.folder_path: self._create_output_folder()
        self._show_current_image()

    def _on_watermark_changed(self, index):
        if index >= 0 and self.watermark_combo.isVisible() and self.watermark_combo.isEnabled():
            self.manual_override_active = True
            self._show_current_image()
            
    def _show_current_image(self):
        if not self.image_files or self.current_index >= len(self.image_files): return
        current_file = self.image_files[self.current_index]; self.current_pixmap = QPixmap(str(current_file))
        if not self.current_pixmap.isNull(): self._apply_zoom()
        else: self.image_label.setText("Error cargando imagen")
        self.filename_label.setText(f"{current_file.name}"); self._update_counter()
        self.prev_btn.setEnabled(self.current_index > 0); self.next_btn.setEnabled(self.current_index < len(self.image_files) - 1)
        self._apply_auto_watermark_selection()
        
    def _next_image(self):
        if self.current_index < len(self.image_files) - 1:
            self.manual_override_active = False; self.current_index += 1; self._show_current_image()
        else: self._finish_review()
        
    def _previous_image(self):
        if self.current_index > 0:
            self.manual_override_active = False; self.current_index -= 1; self._show_current_image()

    def _skip_and_copy_image(self):
        """Copia la imagen original al destino y avanza a la siguiente."""
        if not self.output_folder or not self.image_files: return
        try:
            source_path = self.image_files[self.current_index]
            dest_path = self.output_folder / source_path.name
            shutil.copy2(source_path, dest_path)
            self._log(f"Imagen saltada (copiada): {source_path.name}")
            self._next_image()
        except Exception as e:
            self._log(f"❌ Error al copiar la imagen saltada: {e}")
            
    def _log(self, message: str):
        if self.watermark_tab and hasattr(self.watermark_tab, 'log'): self.watermark_tab.log(message)
        else: print(message)
    def _create_output_folder(self):
        if not self.folder_path: return
        folder_name = self.folder_path.name + " [sin marca]"; self.output_folder = self.folder_path.parent / folder_name; self.output_folder.mkdir(exist_ok=True)
    def _load_image_list(self):
        if not self.folder_path or not self.folder_path.exists(): return
        if self.folder_path.is_file(): self.folder_path = self.folder_path.parent
        for file in natsorted(self.folder_path.iterdir()):
            if file.is_file() and file.suffix.lower() in self.SUPPORTED_FORMATS: self.image_files.append(file)
        self._update_counter()
    def _load_watermark_folders(self):
        self.watermark_folder_combo.clear(); marcas_base_path = Path(os.path.dirname(current_dir)) / 'marcas'
        if not marcas_base_path.exists(): return
        folders = sorted([f for f in marcas_base_path.iterdir() if f.is_dir()], reverse=True)
        for folder in folders: self.watermark_folder_combo.addItem(folder.name, str(folder))
    def _load_watermarks_into_combos(self):
        for combo in [self.watermark_combo, self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]: combo.clear()
        self.watermark_files = []
        if not self.watermark_folder or not self.watermark_folder.exists(): return
        for file in natsorted(self.watermark_folder.iterdir()):
            if file.is_file() and file.suffix.lower() == '.png': self.watermark_files.append(file)
        for file in self.watermark_files:
            for combo in [self.watermark_combo, self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]: combo.addItem(file.name, str(file))
    def _load_watermark_positions(self):
        if not self.watermark_name: return
        try:
            positions_path = Path(os.path.dirname(current_dir)) / 'wm_positions.json'
            if not positions_path.exists(): self.watermark_positions = {}; return
            positions_file = UtilJson(positions_path); data = positions_file.read()
            self.watermark_positions = data.get(self.watermark_name, {})
        except Exception as e: self._log(f"⚠️ Error cargando posiciones: {e}"); self.watermark_positions = {}
    def _update_counter(self):
        if self.image_files: self.counter_label.setText(f"{self.current_index + 1} / {len(self.image_files)}")
        else: self.counter_label.setText("0 / 0")
    def _finish_review(self): self.user_approved = True; self.review_completed.emit(True); self.accept()
    def _cancel_review(self): self.user_approved = False; self.review_completed.emit(False); self.reject()
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton): super().mousePressEvent(event); return
        if not self.watermark_folder or not self.watermark_rectangles: super().mousePressEvent(event); return
        click_pos = self.scroll_area.mapFromGlobal(event.globalPosition().toPoint())
        image_x = click_pos.x() + self.scroll_area.horizontalScrollBar().value(); image_y = click_pos.y() + self.scroll_area.verticalScrollBar().value()
        for pos_name, rect_data in self.watermark_rectangles.items():
            if rect_data['scaled_rect'].contains(image_x, image_y):
                self._process_watermark_at_position(pos_name, rect_data, (event.button() == Qt.MouseButton.RightButton)); event.accept(); return
        super().mousePressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = SlideshowViewer(r"C:\Path\To\Your\Test\Images")
    viewer.exec()
    sys.exit(app.exec())