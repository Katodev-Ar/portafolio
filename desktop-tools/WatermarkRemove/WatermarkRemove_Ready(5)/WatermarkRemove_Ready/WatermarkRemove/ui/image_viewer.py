"""
Visor de imágenes para mostrar todas las imágenes de una carpeta
"""
import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QWidget, QGridLayout, QApplication
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from natsort import natsorted
# Agregar el directorio raíz al path
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


class ImageViewer(QDialog):
    """
    Ventana para visualizar todas las imágenes de una carpeta en una cuadrícula
    """

    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tga', '.psd', '.psb', '.jfif')
    THUMBNAIL_SIZE = 200  # Tamaño de las miniaturas

    def __init__(self, folder_path: str, parent=None):
        super().__init__(parent)
        self.folder_path = Path(folder_path) if folder_path else None
        self.image_labels = []

        self._setup_ui()
        if self.folder_path and self.folder_path.exists():
            self._load_images()

    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        self.setWindowTitle("Visor de Imágenes")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)

        # Layout principal
        main_layout = QVBoxLayout(self)

        # Header con información
        header_layout = QHBoxLayout()
        self.path_label = QLabel()
        self.path_label.setStyleSheet("font-weight: bold; padding: 5px;")
        self.image_count_label = QLabel("0 imágenes")
        self.image_count_label.setStyleSheet("padding: 5px;")

        header_layout.addWidget(QLabel("Carpeta:"))
        header_layout.addWidget(self.path_label, 1)
        header_layout.addWidget(self.image_count_label)

        main_layout.addLayout(header_layout)

        # Área de scroll para las imágenes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Widget contenedor para la cuadrícula
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll_area.setWidget(self.grid_widget)
        main_layout.addWidget(scroll_area)

        # Botón de cerrar
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.close)
        main_layout.addWidget(close_button)

        if self.folder_path:
            self.path_label.setText(str(self.folder_path))

    def _load_images(self):
        """Carga y muestra todas las imágenes de la carpeta"""
        if not self.folder_path or not self.folder_path.exists():
            self.path_label.setText("Carpeta no válida")
            return

        # Limpiar grid anterior
        self._clear_grid()

        # Buscar todas las imágenes
        image_files = []
        if self.folder_path.is_file():
            # Si es un archivo, usar su directorio padre
            self.folder_path = self.folder_path.parent

        for file in natsorted(self.folder_path.iterdir()):
            if file.is_file() and file.suffix.lower() in self.SUPPORTED_FORMATS:
                image_files.append(file)

        # Actualizar contador
        self.image_count_label.setText(f"{len(image_files)} imagen{'es' if len(image_files) != 1 else ''}")

        if not image_files:
            no_images_label = QLabel("No se encontraron imágenes en esta carpeta")
            no_images_label.setStyleSheet("color: gray; font-size: 14px; padding: 20px;")
            no_images_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(no_images_label, 0, 0)
            return

        # Mostrar imágenes en cuadrícula (3 columnas)
        columns = 3
        for index, image_file in enumerate(image_files):
            row = index // columns
            col = index % columns
            image_widget = self._create_image_widget(image_file)
            self.grid_layout.addWidget(image_widget, row, col)

    def _create_image_widget(self, image_path: Path) -> QWidget:
        """
        Crea un widget que contiene una imagen miniatura y su nombre

        Args:
            image_path: Ruta al archivo de imagen

        Returns:
            QWidget con la imagen y su información
        """
        container = QWidget()
        container.setMaximumWidth(self.THUMBNAIL_SIZE + 20)
        layout = QVBoxLayout(container)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        # Label para la imagen
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setFixedSize(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE)
        image_label.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")

        # Cargar y escalar imagen
        try:
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    self.THUMBNAIL_SIZE,
                    self.THUMBNAIL_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                image_label.setPixmap(scaled_pixmap)
            else:
                image_label.setText("Error\ncargando\nimagen")
                image_label.setStyleSheet("border: 1px solid #f00; background-color: #fee;")
        except Exception as e:
            image_label.setText(f"Error:\n{str(e)[:20]}")
            image_label.setStyleSheet("border: 1px solid #f00; background-color: #fee;")

        layout.addWidget(image_label)

        # Label para el nombre del archivo
        name_label = QLabel(image_path.name)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("font-size: 10px; color: #666;")
        name_label.setMaximumWidth(self.THUMBNAIL_SIZE)
        layout.addWidget(name_label)

        # Hacer clickeable para ver en tamaño completo
        image_label.mousePressEvent = lambda event: self._show_full_image(image_path)
        image_label.setCursor(Qt.CursorShape.PointingHandCursor)

        self.image_labels.append(image_label)
        return container

    def _show_full_image(self, image_path: Path):
        """
        Muestra la imagen en tamaño completo en una nueva ventana

        Args:
            image_path: Ruta a la imagen
        """
        full_image_dialog = QDialog(self)
        full_image_dialog.setWindowTitle(image_path.name)
        full_image_dialog.resize(800, 600)

        layout = QVBoxLayout(full_image_dialog)

        # Scroll area para imagen grande
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap(str(image_path))
        if not pixmap.isNull():
            # Escalar a un tamaño razonable si es muy grande
            if pixmap.width() > 1600 or pixmap.height() > 1200:
                pixmap = pixmap.scaled(
                    1600, 1200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            image_label.setPixmap(pixmap)
        else:
            image_label.setText("Error cargando imagen")

        scroll.setWidget(image_label)
        layout.addWidget(scroll)

        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(full_image_dialog.close)
        layout.addWidget(close_btn)

        full_image_dialog.exec()

    def _clear_grid(self):
        """Limpia todos los widgets del grid"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.image_labels.clear()

    def set_folder(self, folder_path: str):
        """
        Cambia la carpeta y recarga las imágenes

        Args:
            folder_path: Nueva ruta de carpeta
        """
        self.folder_path = Path(folder_path) if folder_path else None
        self.path_label.setText(str(self.folder_path) if self.folder_path else "")
        self._load_images()


# Para pruebas independientes
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Usar carpeta de prueba
    test_folder = r"C:\Users\Felix\Downloads\Image Picka\32 urek"
    viewer = ImageViewer(test_folder)
    viewer.show()

    sys.exit(app.exec())
