"""
Editor de posiciones de marcas de agua - Version reorganizada
CORREGIDO: Sincronizada la lógica del numpad con su nueva disposición visual.
"""
import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QFileDialog, QWidget, QMessageBox,
    QScrollArea, QSlider, QSpinBox, QGridLayout, QFormLayout, QCheckBox,
    QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QKeyEvent, QImage
import cv2

# Agregar el directorio raíz al path
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import UtilJson
from WatermarkRemove import load_images_cv2, align_watermark, remove_watermark
from natsort import natsorted

class ZoomableImageLabel(QLabel):
    def __init__(self, parent=None): super().__init__(parent); self.zoom_level=80; self.original_pixmap=None; self.setAlignment(Qt.AlignmentFlag.AlignCenter); self.setStyleSheet("background-color: #2b2b2b;"); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    def set_image(self, pixmap: QPixmap): self.original_pixmap=pixmap; self.update_display()
    def update_display(self):
        if self.original_pixmap is None: return
        scale_factor = self.zoom_level / 100.0; new_size = self.original_pixmap.size() * scale_factor
        scaled_pixmap = self.original_pixmap.scaled(new_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled_pixmap); self.resize(scaled_pixmap.size())
    def set_zoom(self, zoom: int): self.zoom_level=max(10, min(200, zoom)); self.update_display()

class PositionEditor(QDialog):
    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tga', '.jfif')
    def __init__(self, parent=None):
        super().__init__(parent)
        self.images_folder=None; self.watermarks_folder=None; self.image_files=[]; self.watermark_files=[]
        self.current_image_index=0; self.current_image=None; self.current_watermark=None
        self.marcas_base_path = Path(os.path.dirname(current_dir)) / 'marcas'
        self.offset_x=0; self.offset_y=0; self.side_x="left"; self.side_y="top"
        self.current_selected_position=None; self.saved_positions=[]; self.auto_wm_settings={}
        self.zoom_level = 80
        self._setup_ui()
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

    def _setup_ui(self):
        self.setWindowTitle("Editor de Posiciones de Marca de Agua"); self.setModal(True)
        self.resize(1000, 950)
        main_layout = QHBoxLayout(self); main_layout.setSpacing(15); main_layout.setContentsMargins(10, 10, 10, 10)
        left_panel = self._create_controls_panel(); main_layout.addWidget(left_panel)
        right_panel = self._create_image_panel(); main_layout.addWidget(right_panel, 1)

    def _create_controls_panel(self) -> QWidget:
        panel=QWidget(); self.controls_panel_width=250; panel.setFixedWidth(self.controls_panel_width)
        layout=QVBoxLayout(panel); layout.setSpacing(10); layout.setContentsMargins(0, 0, 0, 0)
        folders_group=QGroupBox("📁 Selección"); folders_layout=QVBoxLayout(); folders_layout.setSpacing(6)
        btn_images=QPushButton("📂 Carpeta de Imágenes"); btn_images.clicked.connect(self._select_images_folder); btn_images.setStyleSheet("padding: 6px;"); folders_layout.addWidget(btn_images)
        self.images_label=QLabel("No seleccionada"); self.images_label.setStyleSheet("color: #666; font-size: 10px; padding-left: 10px;"); self.images_label.setWordWrap(True); folders_layout.addWidget(self.images_label)
        folders_layout.addWidget(QLabel("Carpeta de Marcas:")); self.watermark_folder_combo=QComboBox(); self.watermark_folder_combo.currentIndexChanged.connect(self._on_watermark_folder_changed); folders_layout.addWidget(self.watermark_folder_combo)
        folders_layout.addWidget(QLabel("Marca específica:")); self.watermark_combo=QComboBox(); self.watermark_combo.currentIndexChanged.connect(self._on_watermark_changed); folders_layout.addWidget(self.watermark_combo)

        auto_config_header_layout = QHBoxLayout()
        self.enable_auto_config_checkbox = QCheckBox("Usar Configuración Automática")
        self.enable_auto_config_checkbox.toggled.connect(self._save_auto_config_state)
        self.toggle_options_btn = QPushButton("Mostrar ▼")
        self.toggle_options_btn.setCheckable(True)
        self.toggle_options_btn.toggled.connect(self._toggle_auto_config_visibility)
        auto_config_header_layout.addWidget(self.enable_auto_config_checkbox)
        auto_config_header_layout.addStretch()
        auto_config_header_layout.addWidget(self.toggle_options_btn)
        folders_layout.addLayout(auto_config_header_layout)

        self.auto_wm_options_widget = QWidget()
        auto_wm_layout = QFormLayout()
        auto_wm_layout.setSpacing(8)
        self.first_wm_combo=QComboBox(); self.middle_wm_combo=QComboBox(); self.last_wm_combo=QComboBox()
        self.btn_save_auto_config = QPushButton("💾 Guardar Config. Automática")
        self.btn_save_auto_config.clicked.connect(self._save_auto_wm_config)
        auto_wm_layout.addRow("Primera:", self.first_wm_combo); auto_wm_layout.addRow("Intermedia:", self.middle_wm_combo); auto_wm_layout.addRow("Última:", self.last_wm_combo); auto_wm_layout.addRow(self.btn_save_auto_config)
        self.auto_wm_options_widget.setLayout(auto_wm_layout)
        folders_layout.addWidget(self.auto_wm_options_widget)
        self.auto_wm_options_widget.hide()

        self._load_watermark_folders(); folders_group.setLayout(folders_layout); layout.addWidget(folders_group)
        position_group=QGroupBox("🎮 Posición"); position_layout=QVBoxLayout(); position_layout.setSpacing(8)
        position_layout.addWidget(QLabel("Posición:")); grid_container=QWidget(); self.position_grid=QGridLayout(grid_container); self.position_grid.setSpacing(5); self.position_buttons={}
        
        keypad_layout = [[7, 8, 9], [4, 5, 6], [1, 2, 3]]
        for row_idx, row_list in enumerate(keypad_layout):
            for col_idx, num in enumerate(row_list):
                button = QPushButton(str(num))
                button.setFixedSize(40, 40)
                button.setCheckable(True)
                button.clicked.connect(lambda c, n=num: self._on_grid_button_clicked(n))
                self.position_grid.addWidget(button, row_idx, col_idx)
                self.position_buttons[num] = button

        position_layout.addWidget(grid_container)
        position_layout.addWidget(QLabel("Ajuste Fino (pixel):")); offset_x_container=QWidget(); offset_x_layout=QHBoxLayout(offset_x_container); offset_x_layout.setContentsMargins(0,0,0,0); offset_x_layout.setSpacing(5); offset_x_layout.addWidget(QLabel("Horizontal:\t")); self.offset_x_spin=QSpinBox(); self.offset_x_spin.setRange(-9999, 9999); self.offset_x_spin.setAlignment(Qt.AlignmentFlag.AlignCenter); self.offset_x_spin.valueChanged.connect(lambda v: self._on_offset_spin_changed('x',v)); offset_x_layout.addWidget(self.offset_x_spin, 1); position_layout.addWidget(offset_x_container)
        offset_y_container=QWidget(); offset_y_layout=QHBoxLayout(offset_y_container); offset_y_layout.setContentsMargins(0,0,0,0); offset_y_layout.setSpacing(5); offset_y_layout.addWidget(QLabel("Vertical:\t\t")); self.offset_y_spin=QSpinBox(); self.offset_y_spin.setRange(-9999, 9999); self.offset_y_spin.setAlignment(Qt.AlignmentFlag.AlignCenter); self.offset_y_spin.valueChanged.connect(lambda v: self._on_offset_spin_changed('y',v)); offset_y_layout.addWidget(self.offset_y_spin, 1); position_layout.addWidget(offset_y_container)
        btn_save_coords=QPushButton("💾 Guardar Coordenadas"); btn_save_coords.setToolTip("Guarda los valores de Ajuste Fino para la posición numérica seleccionada."); btn_save_coords.clicked.connect(self._save_preset_offsets); btn_save_coords.setStyleSheet("padding: 6px; margin-top: 5px;"); position_layout.addWidget(btn_save_coords)
        position_group.setLayout(position_layout); layout.addWidget(position_group)
        self.counter_label=QLabel("0 / 0"); self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.counter_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3; padding: 10px;"); layout.addWidget(self.counter_label)
        self.btn_save=QPushButton("💾 Guardar y Siguiente"); self.btn_save.clicked.connect(self._save_and_next); self.btn_save.setStyleSheet("padding: 12px; background-color: #4CAF50; color: white; font-weight: bold;"); self.btn_save.setEnabled(False); layout.addWidget(self.btn_save)
        btn_close=QPushButton("❌ Cerrar"); btn_close.clicked.connect(self.close); btn_close.setStyleSheet("padding: 10px; background-color: #f44336; color: white;"); layout.addWidget(btn_close)
        layout.addStretch(); return panel

    def _create_image_panel(self) -> QWidget:
        panel=QWidget(); layout=QVBoxLayout(panel); layout.setSpacing(8); layout.setContentsMargins(0,0,0,0)
        zoom_container=QWidget(); zoom_layout=QHBoxLayout(zoom_container); zoom_layout.setContentsMargins(0,0,0,0)
        zoom_layout.addWidget(QLabel("Zoom:")); self.zoom_slider=QSlider(Qt.Orientation.Horizontal); self.zoom_slider.setRange(10, 200)
        self.zoom_slider.setValue(self.zoom_level)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed); zoom_layout.addWidget(self.zoom_slider, 1)
        self.zoom_label=QLabel(f"{self.zoom_level}%"); self.zoom_label.setFixedWidth(50); self.zoom_label.setStyleSheet("font-weight: bold;"); zoom_layout.addWidget(self.zoom_label)
        layout.addWidget(zoom_container)
        scroll=QScrollArea(); scroll.setWidgetResizable(False)
        scroll.setStyleSheet("""
            border: 2px solid #444;
            QScrollBar:vertical { width: 9px; } QScrollBar:horizontal { height: 9px; }
            QScrollBar::handle { border-radius: 4px; background: #555; }
            QScrollBar::handle:vertical { min-height: 20px; } QScrollBar::handle:horizontal { min-width: 20px; }
        """)
        self.image_label=ZoomableImageLabel(); scroll.setWidget(self.image_label); layout.addWidget(scroll, 1); return panel
    
    def _update_and_save_preset_config(self, key_to_update: str, value_to_update, is_coord=False):
        if not self.watermarks_folder: return False
        folder_name = self.watermarks_folder.name
        json_path = Path(os.path.dirname(current_dir)) / 'wm_preset_offsets.json'
        json_file = UtilJson(json_path)
        all_presets = json_file.read() if json_path.exists() else {}

        if folder_name not in all_presets: all_presets[folder_name] = {}
        
        if is_coord: all_presets[folder_name][key_to_update] = value_to_update
        else:
            if 'auto_selection' not in all_presets[folder_name] and key_to_update != 'auto_selection': all_presets[folder_name]['auto_selection'] = {}
            all_presets[folder_name][key_to_update] = value_to_update

        json_file.write(all_presets)
        return True

    def _toggle_auto_config_visibility(self, checked):
        if checked: self.auto_wm_options_widget.show(); self.toggle_options_btn.setText("Ocultar ▲")
        else: self.auto_wm_options_widget.hide(); self.toggle_options_btn.setText("Mostrar ▼")

    def _save_auto_config_state(self, is_enabled):
        self._update_and_save_preset_config("auto_config_enabled", is_enabled)

    def _save_auto_wm_config(self):
        if not self.watermarks_folder: QMessageBox.warning(self, "Atención", "Selecciona una Carpeta de Marcas primero."); return
        config_data = {"first": self.first_wm_combo.currentText(), "middle": self.middle_wm_combo.currentText(), "last": self.last_wm_combo.currentText()}
        if self._update_and_save_preset_config("auto_selection", config_data):
            self.auto_wm_settings[self.watermarks_folder.name] = config_data
            QMessageBox.information(self, "Guardado", f"Configuración automática guardada para '{self.watermarks_folder.name}'.")

    def _load_auto_wm_config(self):
        if not self.watermarks_folder: return
        folder_name = self.watermarks_folder.name; json_path = Path(os.path.dirname(current_dir)) / 'wm_preset_offsets.json'
        enabled_state = False; config = None
        if json_path.exists():
            json_file=UtilJson(json_path); all_presets=json_file.read()
            folder_config = all_presets.get(folder_name, {}); config = folder_config.get("auto_selection"); enabled_state = folder_config.get("auto_config_enabled", False)
        self.auto_wm_settings[folder_name] = config; self.enable_auto_config_checkbox.setChecked(enabled_state)
        if config: self.first_wm_combo.setCurrentText(config.get("first","")); self.middle_wm_combo.setCurrentText(config.get("middle","")); self.last_wm_combo.setCurrentText(config.get("last",""))
        else:
            if self.first_wm_combo.count() > 0: self.first_wm_combo.setCurrentIndex(0); self.middle_wm_combo.setCurrentIndex(0); self.last_wm_combo.setCurrentIndex(0)

    def _apply_auto_watermark_selection(self):
        if not self.image_files or not self.watermarks_folder or not self.enable_auto_config_checkbox.isChecked(): return
        folder_name=self.watermarks_folder.name; config=self.auto_wm_settings.get(folder_name);
        if not config: return
        total_images=len(self.image_files); current_idx=self.current_image_index; target_wm_name=""
        if total_images == 1: target_wm_name = config.get("first")
        elif current_idx == 0: target_wm_name = config.get("first")
        elif current_idx == total_images - 1: target_wm_name = config.get("last")
        else: target_wm_name = config.get("middle")
        if target_wm_name:
            index=self.watermark_combo.findText(target_wm_name)
            if index != -1: self.watermark_combo.setCurrentIndex(index)
    
    def _on_grid_button_clicked(self, n):
        for num, btn in self.position_buttons.items(): btn.setChecked(num==n)
        # --- MODIFICACIÓN: Mapa de posiciones corregido ---
        pos_map = {
            1:("left","bottom"), 2:("center","bottom"), 3:("right","bottom"),
            4:("left","center"), 5:("center","center"), 6:("right","center"),
            7:("left","top"), 8:("center","top"), 9:("right","top")
        }
        s=pos_map.get(n); self.side_x, self.side_y = s[0], s[1]; self.current_selected_position=n
        self._load_preset_offsets_for_position(n); self._update_preview(); self.setFocus()
        
    def _load_preset_offsets_for_position(self, n):
        if not self.watermarks_folder: self.offset_x_spin.setValue(0); self.offset_y_spin.setValue(0); return
        fn=self.watermarks_folder.name; pk=str(n); jp=Path(os.path.dirname(current_dir))/'wm_preset_offsets.json'
        if not jp.exists(): self.offset_x_spin.setValue(0); self.offset_y_spin.setValue(0); return
        jf=UtilJson(jp); presets=jf.read(); coords=presets.get(fn,{}).get(pk)
        if coords: self.offset_x_spin.setValue(coords.get('offset_x',0)); self.offset_y_spin.setValue(coords.get('offset_y',0))
        else: self.offset_x_spin.setValue(0); self.offset_y_spin.setValue(0)
    def _save_preset_offsets(self):
        if self.current_selected_position is None or not self.watermarks_folder: QMessageBox.warning(self, "Atención", "Selecciona una carpeta y una posición (1-9) primero."); return
        pos_key = str(self.current_selected_position)
        coords = {'offset_x': self.offset_x_spin.value(), 'offset_y': self.offset_y_spin.value()}
        if self._update_and_save_preset_config(pos_key, coords, is_coord=True):
            QMessageBox.information(self, "Guardado", f"Coordenadas para la posición {pos_key} guardadas para '{self.watermarks_folder.name}'.")

    def _on_zoom_changed(self, v): self.zoom_label.setText(f"{v}%"); self.image_label.set_zoom(v)
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.btn_save.isEnabled(): self._save_and_next()
        elif e.key() == Qt.Key.Key_Escape: self.close()
        else: super().keyPressEvent(e)
    
    def _on_offset_spin_changed(self, axis, v):
        if axis == 'x': self.offset_x=v;
        elif axis == 'y': self.offset_y=v
        self._update_preview()
    def _select_images_folder(self):
        f=QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Imágenes")
        if f: self.images_folder=Path(f); self.images_label.setText(self.images_folder.name); self._load_images(); self._check_ready()
    def _load_watermark_folders(self):
        self.watermark_folder_combo.clear()
        if not self.marcas_base_path.exists(): return
        folders = sorted([f for f in self.marcas_base_path.iterdir() if f.is_dir()], reverse=True)
        for folder in folders: self.watermark_folder_combo.addItem(folder.name, str(folder))
    def _on_watermark_folder_changed(self, i):
        if i < 0: return
        p=self.watermark_folder_combo.currentData()
        if p: self.watermarks_folder=Path(p); self._load_watermarks_into_combos(); self._load_auto_wm_config(); self._check_ready()
    def _load_images(self):
        if not self.images_folder or not self.images_folder.exists(): return
        self.image_files = [f for f in natsorted(self.images_folder.iterdir()) if f.is_file() and f.suffix.lower() in self.SUPPORTED_FORMATS]
        self.current_image_index=0; self._update_counter()
    def _load_watermarks_into_combos(self):
        for combo in [self.watermark_combo, self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]: combo.clear()
        self.watermark_files = []
        if not self.watermarks_folder or not self.watermarks_folder.exists(): return
        for file in natsorted(self.watermarks_folder.iterdir()):
            if file.is_file() and file.suffix.lower() == '.png': self.watermark_files.append(file)
        for file in self.watermark_files:
            for combo in [self.watermark_combo, self.first_wm_combo, self.middle_wm_combo, self.last_wm_combo]: combo.addItem(file.name, str(file))
    def _check_ready(self):
        ready = self.images_folder and self.watermarks_folder and self.image_files and self.watermark_files
        if ready:
            self.btn_save.setEnabled(True); self._load_current_image()
            self._apply_auto_watermark_selection(); self._load_current_watermark(); self._update_preview()
    def _load_current_image(self):
        if self.image_files and self.current_image_index < len(self.image_files): self.current_image=load_images_cv2(str(self.image_files[self.current_image_index]))
    def _load_current_watermark(self):
        watermark_path=self.watermark_combo.currentData();
        if watermark_path: self.current_watermark=load_images_cv2(str(watermark_path))
    def _on_watermark_changed(self, i):
        if i >= 0: self._load_current_watermark(); self._update_preview()
    def _update_preview(self):
        if self.current_image is None or self.current_watermark is None: return
        try:
            img, wm = self.current_image.copy(), self.current_watermark
            x, y = align_watermark(img, wm, self.offset_x, self.offset_y, self.side_x, self.side_y)
            res=remove_watermark(img, wm, x, y); rgb=cv2.cvtColor(res, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape; q_img=QImage(rgb.data, w, h, 3*w, QImage.Format.Format_RGB888)
            self.image_label.set_image(QPixmap.fromImage(q_img)); self._adjust_window_size(w,h)
        except Exception as e: self.image_label.setText(f"❌ Error: {str(e)}")
    def _adjust_window_size(self, w, h): S,M,B,P=15,20,4,20; nw=self.controls_panel_width+S+w+B+M+P; self.resize(nw, self.height())
    def _update_counter(self): self.counter_label.setText(f"{self.current_image_index + 1} / {len(self.image_files)}" if self.image_files else "0 / 0")
    def _save_and_next(self):
        if self.current_selected_position is None: QMessageBox.warning(self, "Posición no seleccionada", "Selecciona una posición (1-9) antes de guardar."); return
        pos_data = {'offset_x': self.offset_x, 'offset_y': self.offset_y, 'side_x': self.side_x, 'side_y': self.side_y}
        self.saved_positions.append(pos_data)
        if self.current_image_index < len(self.image_files) - 1:
            self.current_image_index += 1; self._load_current_image(); self._update_counter()
            self._apply_auto_watermark_selection(); self._update_preview()
        else:
            self._save_to_json(); QMessageBox.information(self, "Completado", f"Se guardaron {len(self.saved_positions)} posiciones"); self.accept()
    def _save_to_json(self):
        if not self.watermarks_folder or not self.saved_positions: return
        try:
            fn=self.watermarks_folder.name; jp=Path(os.path.dirname(current_dir))/'wm_positions.json'; jf=UtilJson(jp)
            pos_dict = {f'pos_{i}': d for i, d in enumerate(self.saved_positions, 1)}; jf.set(fn, pos_dict)
            print(f"✓ Guardadas {len(self.saved_positions)} posiciones en '{fn}'")
        except Exception as e: QMessageBox.critical(self, "Error al guardar", f"No se pudieron guardar las posiciones:\n{str(e)}")

if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    app=QApplication(sys.argv); editor=PositionEditor(); editor.show(); sys.exit(app.exec())