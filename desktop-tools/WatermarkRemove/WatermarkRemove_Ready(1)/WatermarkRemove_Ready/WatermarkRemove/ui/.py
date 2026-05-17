"""
Editor interactivo de posiciones de marcas de agua
"""
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QFileDialog, QWidget, QMessageBox,
    QScrollArea, QSlider
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QKeyEvent, QImage
from PySide6.QtCore import QRect
import numpy as np
import cv2

# Agregar el directorio raíz al path
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import UtilJson
from WatermarkRemove import load_images_cv2, align_watermark, remove_watermark


class PositionEditor(QDialog):
    """
    Editor interactivo para ajustar posiciones de marcas de agua

    Controles:
        - Flechas: Ajustar offset_x y offset_y (pixel a pixel)
        - Enter: Guardar posición actual y pasar a siguiente imagen
        - Escape: Cerrar sin guardar
    """

    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tga', '.jfif')

    def __init__(self, parent=None):
        super().__init__(parent)

        # Datos
        self.images_folder = None
        self.watermarks_folder = None
        self.image_files = []
        self.watermark_files = []
        self.current_image_index = 0
        self.current_image = None
        self.current_watermark = None

        # Posición actual
        self.offset_x = 0
        self.offset_y = 0
        self.side_x = "left"
        self.side_y = "top"

        # Posiciones guardadas
        self.saved_positions = []

        # Zoom
        self.zoom_level = 100  # Porcentaje
        self.current_pixmap = None  # Pixmap actual sin escalar

        self._setup_ui()

        # Instalar event filter para capturar teclas globalmente
        self.installEventFilter(self)

    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        self.setWindowTitle("Editor de Posiciones de Marca de Agua")
        self.setModal(True)
        self.resize(1200, 700)
        self.setMinimumSize(900, 600)

        # Layout principal HORIZONTAL (controles | imagen)
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === PANEL IZQUIERDO: Controles ===
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_panel.setMinimumWidth(350)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # === SECCIÓN: Selección de carpetas ===
        folders_group = QGroupBox("📁 Carpetas")
        folders_layout = QVBoxLayout()

        # Carpeta de imágenes
        images_folder_layout = QHBoxLayout()
        self.images_folder_label = QLabel("No seleccionada")
        self.images_folder_label.setStyleSheet("color: #666; padding: 5px;")
        btn_select_images = QPushButton("Seleccionar Carpeta de Imágenes")
        btn_select_images.clicked.connect(self._select_images_folder)
        images_folder_layout.addWidget(QLabel("Imágenes:"))
        images_folder_layout.addWidget(self.images_folder_label, 1)
        images_folder_layout.addWidget(btn_select_images)
        folders_layout.addLayout(images_folder_layout)

        # Carpeta de marcas de agua
        watermarks_folder_layout = QHBoxLayout()
        self.watermarks_folder_label = QLabel("No seleccionada")
        self.watermarks_folder_label.setStyleSheet("color: #666; padding: 5px;")
        btn_select_watermarks = QPushButton("Seleccionar Carpeta de Marcas")
        btn_select_watermarks.clicked.connect(self._select_watermarks_folder)
        watermarks_folder_layout.addWidget(QLabel("Marcas:"))
        watermarks_folder_layout.addWidget(self.watermarks_folder_label, 1)
        watermarks_folder_layout.addWidget(btn_select_watermarks)
        folders_layout.addLayout(watermarks_folder_layout)

        # Selector de marca de agua
        watermark_select_layout = QHBoxLayout()
        self.watermark_combo = QComboBox()
        self.watermark_combo.currentIndexChanged.connect(self._on_watermark_changed)
        # Desactivar navegación con teclado
        self.watermark_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        watermark_select_layout.addWidget(QLabel("Marca actual:"))
        watermark_select_layout.addWidget(self.watermark_combo, 1)
        folders_layout.addLayout(watermark_select_layout)

        folders_group.setLayout(folders_layout)
        main_layout.addWidget(folders_group)

        # === SECCIÓN: Vista de imagen ===
        image_group = QGroupBox("🖼️ Vista de Imagen")
        image_layout = QVBoxLayout()

        # Contador de imagen
        self.image_counter_label = QLabel("0 / 0")
        self.image_counter_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2196F3;")
        self.image_counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_counter_label)

        # Label para mostrar imagen con marca
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #2b2b2b; border: 2px solid #444;")
        self.image_label.setMinimumSize(800, 500)
        image_layout.addWidget(self.image_label, 1)

        image_group.setLayout(image_layout)
        main_layout.addWidget(image_group, 1)

        # === SECCIÓN: Controles de posición ===
        controls_group = QGroupBox("🎮 Controles de Posición")
        controls_layout = QHBoxLayout()

        # Side X
        side_x_layout = QVBoxLayout()
        side_x_layout.addWidget(QLabel("Posición Horizontal:"))
        self.side_x_combo = QComboBox()
        self.side_x_combo.addItem("Izquierda", "left")
        self.side_x_combo.addItem("Centro", "center")
        self.side_x_combo.addItem("Derecha", "right")
        self.side_x_combo.currentIndexChanged.connect(self._on_position_changed)
        # Desactivar navegación con teclado en el combo
        self.side_x_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        side_x_layout.addWidget(self.side_x_combo)
        controls_layout.addLayout(side_x_layout)

        # Side Y
        side_y_layout = QVBoxLayout()
        side_y_layout.addWidget(QLabel("Posición Vertical:"))
        self.side_y_combo = QComboBox()
        self.side_y_combo.addItem("Arriba", "top")
        self.side_y_combo.addItem("Centro", "center")
        self.side_y_combo.addItem("Abajo", "bottom")
        self.side_y_combo.currentIndexChanged.connect(self._on_position_changed)
        # Desactivar navegación con teclado en el combo
        self.side_y_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        side_y_layout.addWidget(self.side_y_combo)
        controls_layout.addLayout(side_y_layout)

        # Offsets
        offsets_layout = QVBoxLayout()
        self.offset_x_label = QLabel("Offset X: 0")
        self.offset_y_label = QLabel("Offset Y: 0")
        self.offset_x_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.offset_y_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        offsets_layout.addWidget(self.offset_x_label)
        offsets_layout.addWidget(self.offset_y_label)
        controls_layout.addLayout(offsets_layout)

        controls_group.setLayout(controls_layout)
        main_layout.addWidget(controls_group)

        # === SECCIÓN: Instrucciones ===
        instructions = QLabel(
            "⌨️ Controles: [FLECHAS] Ajustar offset  |  [ENTER] Guardar y Siguiente  |  [ESC] Cerrar"
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet(
            "background-color: #f0f0f0; padding: 10px; "
            "border-radius: 5px; font-weight: bold; color: #333;"
        )
        main_layout.addWidget(instructions)

        # === SECCIÓN: Botones de acción ===
        buttons_layout = QHBoxLayout()

        self.btn_save = QPushButton("💾 Guardar Posición y Siguiente (Enter)")
        self.btn_save.clicked.connect(self._save_and_next)
        self.btn_save.setStyleSheet("padding: 10px; background-color: #4CAF50; color: white;")
        self.btn_save.setEnabled(False)

        self.btn_close = QPushButton("❌ Cerrar (Esc)")
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setStyleSheet("padding: 10px; background-color: #f44336; color: white;")

        buttons_layout.addWidget(self.btn_save)
        buttons_layout.addWidget(self.btn_close)

        main_layout.addLayout(buttons_layout)

    def _select_images_folder(self):
        """Abre diálogo para seleccionar carpeta de imágenes"""
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Imágenes")
        if folder:
            self.images_folder = Path(folder)
            self.images_folder_label.setText(str(self.images_folder))
            self._load_images()
            self._check_ready()

    def _select_watermarks_folder(self):
        """Abre diálogo para seleccionar carpeta de marcas de agua"""
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta de Marcas de Agua")
        if folder:
            self.watermarks_folder = Path(folder)
            self.watermarks_folder_label.setText(str(self.watermarks_folder))
            self._load_watermarks()
            self._check_ready()

    def _load_images(self):
        """Carga la lista de imágenes desde la carpeta seleccionada"""
        if not self.images_folder or not self.images_folder.exists():
            return

        self.image_files = []
        for file in sorted(self.images_folder.iterdir()):
            if file.is_file() and file.suffix.lower() in self.SUPPORTED_FORMATS:
                self.image_files.append(file)

        self.current_image_index = 0
        self._update_image_counter()

    def _load_watermarks(self):
        """Carga la lista de marcas de agua y actualiza el combo"""
        if not self.watermarks_folder or not self.watermarks_folder.exists():
            return

        self.watermark_files = []
        self.watermark_combo.clear()

        for file in sorted(self.watermarks_folder.iterdir()):
            if file.is_file() and file.suffix.lower() == '.png':
                self.watermark_files.append(file)
                self.watermark_combo.addItem(file.name)

    def _check_ready(self):
        """Verifica si está todo listo para empezar a editar"""
        ready = (
            self.images_folder is not None and
            self.watermarks_folder is not None and
            len(self.image_files) > 0 and
            len(self.watermark_files) > 0
        )

        self.btn_save.setEnabled(ready)

        if ready:
            self._load_current_image()
            self._load_current_watermark()
            self._update_preview()

    def _load_current_image(self):
        """Carga la imagen actual en memoria"""
        if not self.image_files or self.current_image_index >= len(self.image_files):
            return

        image_path = self.image_files[self.current_image_index]
        self.current_image = load_images_cv2(str(image_path))

    def _load_current_watermark(self):
        """Carga la marca de agua actual"""
        if not self.watermark_files or self.watermark_combo.currentIndex() < 0:
            return

        watermark_path = self.watermark_files[self.watermark_combo.currentIndex()]
        self.current_watermark = load_images_cv2(str(watermark_path))

    def _on_watermark_changed(self, index):
        """Callback cuando cambia la marca de agua seleccionada"""
        if index >= 0:
            self._load_current_watermark()
            self._update_preview()

    def _on_position_changed(self):
        """Callback cuando cambian los controles de posición"""
        self.side_x = self.side_x_combo.currentData()
        self.side_y = self.side_y_combo.currentData()
        self._update_preview()

    def _update_preview(self):
        """Actualiza el preview de la imagen con la marca de agua y el resultado de remove_watermark"""
        if self.current_image is None or self.current_watermark is None:
            return

        try:
            # Hacer copia de la imagen para no modificar la original
            img_copy = self.current_image.copy()

            # Calcular coordenadas de la marca usando align_watermark
            # Ahora soporta posiciones fuera de los bordes
            x, y = align_watermark(
                img_copy,
                self.current_watermark,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                side_x=self.side_x,
                side_y=self.side_y
            )

            # Aplicar remove_watermark para obtener el resultado
            result_img = remove_watermark(img_copy, self.current_watermark, x, y)

            # Convertir de BGR (OpenCV) a RGB para Qt
            result_rgb = cv2.cvtColor(result_img, cv2.COLOR_BGR2RGB)

            # Convertir numpy array a QImage
            height, width, channel = result_rgb.shape
            bytes_per_line = 3 * width
            q_image = QImage(
                result_rgb.data,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )

            # Convertir a QPixmap
            pixmap = QPixmap.fromImage(q_image)

            # Escalar para que quepa en el label manteniendo aspecto
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # Mostrar
            self.image_label.setPixmap(scaled_pixmap)

        except Exception as e:
            self.image_label.setText(f"❌ Error: {str(e)}")

    def _update_image_counter(self):
        """Actualiza el contador de imágenes"""
        if self.image_files:
            self.image_counter_label.setText(
                f"{self.current_image_index + 1} / {len(self.image_files)}"
            )
        else:
            self.image_counter_label.setText("0 / 0")

    def _update_offset_labels(self):
        """Actualiza las etiquetas de offset"""
        self.offset_x_label.setText(f"Offset X: {self.offset_x}")
        self.offset_y_label.setText(f"Offset Y: {self.offset_y}")

    def _save_and_next(self):
        """Guarda la posición actual y pasa a la siguiente imagen"""
        # Guardar posición actual
        position_data = {
            'offset_x': self.offset_x,
            'offset_y': self.offset_y,
            'side_x': self.side_x,
            'side_y': self.side_y
        }
        self.saved_positions.append(position_data)

        # Pasar a siguiente imagen
        if self.current_image_index < len(self.image_files) - 1:
            self.current_image_index += 1
            self._load_current_image()
            self._update_image_counter()
            self._update_preview()
        else:
            # Última imagen, guardar todo y cerrar
            self._save_to_json()
            QMessageBox.information(
                self,
                "Completado",
                f"Se guardaron {len(self.saved_positions)} posiciones correctamente"
            )
            self.accept()

    def _save_to_json(self):
        """Guarda todas las posiciones en el archivo JSON"""
        if not self.watermarks_folder or not self.saved_positions:
            return

        try:
            # Obtener el nombre de la carpeta de marcas de agua (será el nombre del dict)
            watermark_folder_name = self.watermarks_folder.name

            # Ruta al archivo JSON
            wm_dir = os.path.dirname(current_dir)
            json_path = Path(wm_dir) / 'wm_poscition.json'

            # Cargar JSON existente o crear uno nuevo
            json_file = UtilJson(json_path)

            # Crear estructura de posiciones
            positions_dict = {}
            for i, pos_data in enumerate(self.saved_positions, start=1):
                positions_dict[f'pos_{i}'] = pos_data

            # Guardar bajo el nombre de la carpeta de marcas
            json_file.set(watermark_folder_name, positions_dict)

            print(f"✓ Guardadas {len(self.saved_positions)} posiciones en '{watermark_folder_name}'")

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al guardar",
                f"No se pudieron guardar las posiciones:\n{str(e)}"
            )

    def keyPressEvent(self, event: QKeyEvent):
        """Maneja los eventos de teclado"""
        key = event.key()

        # Ajustar offsets con flechas
        if key == Qt.Key.Key_Left:
            self.offset_x -= 1
            self._update_offset_labels()
            self._update_preview()
        elif key == Qt.Key.Key_Right:
            self.offset_x += 1
            self._update_offset_labels()
            self._update_preview()
        elif key == Qt.Key.Key_Up:
            self.offset_y -= 1
            self._update_offset_labels()
            self._update_preview()
        elif key == Qt.Key.Key_Down:
            self.offset_y += 1
            self._update_offset_labels()
            self._update_preview()
        # Guardar y siguiente
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if self.btn_save.isEnabled():
                self._save_and_next()
        # Cerrar
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# Para pruebas independientes
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    editor = PositionEditor()
    editor.show()
    sys.exit(app.exec())
