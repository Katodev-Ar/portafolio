"""
Pestaña UI para Watermark Remover
"""
import os
import sys
import threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QTextEdit, QPushButton, QMessageBox, QFileDialog, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

# Agregar el directorio raíz al path
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .image_viewer import ImageViewer
from .position_editor import PositionEditor
from .auto_position_detector import AutoPositionDetector
from .slideshow_viewer import SlideshowViewer
from .stitcher_dialog import StitcherDialog

# Importar lógica de eliminación
# Nota: load_positions no estaba en tu código original explícito, pero asumimos que existía o no la usamos aquí directamemte
# Usaremos nuestra propia lógica de lectura de JSON para ser seguros
from WatermarkRemove.wm_remove import load_images_cv2, remove_watermark, align_watermark
import cv2

class WorkerSignals(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

class WatermarkTab(QWidget):
    """
    Pestaña de Quita Marcas - Widget independiente para eliminar marcas de agua
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_folder = None
        self._setup_ui()
        self.is_processing = False

    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # GroupBox de configuración
        settings_group = QGroupBox("Quita Marcas Settings")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(4)
        settings_layout.setContentsMargins(6, 6, 6, 6)

        # Botón principal: Ejecutar Proceso
        self.run_process_btn = QPushButton("Ejecutar Proceso")
        self.run_process_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_process_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff; 
                color: white; 
                padding: 12px; 
                font-size: 14px; 
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #444;
                color: #888;
            }
        """)
        self.run_process_btn.clicked.connect(self._on_run_process_click)
        settings_layout.addWidget(self.run_process_btn)

        # Botones secundarios (Ocultos por petición usuario)
        # self.view_images_btn = QPushButton("Ver Imágenes de Input")
        # self.view_images_btn.clicked.connect(self._open_image_viewer)
        # settings_layout.addWidget(self.view_images_btn)

        # self.edit_positions_btn = QPushButton("⚙️ Editor de Posiciones de Marcas")
        # self.edit_positions_btn.clicked.connect(self._open_position_editor)
        # settings_layout.addWidget(self.edit_positions_btn)

        # Botón Smart Stitcher (Unir RAW)
        self.btn_stitcher = QPushButton("🔗 Unir RAW (Smart Stitch)")
        self.btn_stitcher.setStyleSheet("""
            QPushButton {
                background-color: #673AB7; 
                color: white; 
                padding: 10px; 
                border-radius: 5px; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5E35B1; }
        """)
        self.btn_stitcher.clicked.connect(self._open_stitcher_dialog)
        settings_layout.addWidget(self.btn_stitcher)

        # Botón Auto Detector de Posiciones
        self.btn_auto_detector = QPushButton("🔍 Auto Detectar Posiciones de Marca")
        self.btn_auto_detector.setStyleSheet("""
            QPushButton {
                background-color: #00695C;
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #004D40; }
        """)
        self.btn_auto_detector.clicked.connect(self._open_auto_detector)
        settings_layout.addWidget(self.btn_auto_detector)

        # Layout horizontal (placeholder para futuros controles) - Este ya no es necesario aquí
        # post_process_layout = QHBoxLayout()
        # settings_layout.addLayout(post_process_layout)

        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)

        # TextEdit: Consola de proceso
        self.process_console = QTextEdit()
        self.process_console.setEnabled(True)
        self.process_console.setReadOnly(True)
        self.process_console.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        main_layout.addWidget(self.process_console)

        # Signals
        self.signals = WorkerSignals()
        self.signals.log.connect(self.log)
        self.signals.finished.connect(self._on_process_finished)
        self.signals.error.connect(self._on_process_error)

    def set_input_path(self, path):
        """Define la carpeta de trabajo externa"""
        if path and os.path.exists(path):
            self.current_folder = Path(path)
            self.log(f"📂 Carpeta seleccionada: {self.current_folder}")
        else:
            self.log("⚠ Ruta inválida proporcionada.")

    def _open_image_viewer(self):
        """Abre el visor de imágenes"""
        folder = self.current_folder
        if not folder or not folder.exists():
            # Intentar fallback tradicional o pedir carpeta
            folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
            if folder:
                self.set_input_path(folder)
            else:
                self.log("⚠ Debes seleccionar una carpeta primero (usa 'Abrir' en la app principal o selecciona aquí).")
                return

        try:
            self.log(f"Abriendo visor para: {folder}")
            viewer = ImageViewer(str(folder), self)
            viewer.exec()
        except Exception as e:
            self.log(f"Error al abrir visor: {str(e)}")

    def _open_auto_detector(self):
        """Abre el Auto Detector de Posiciones de Marca de Agua"""
        try:
            self.log("Abriendo Auto Detector de Posiciones...")
            dlg = AutoPositionDetector(self)
            dlg.exec()
            self.log("Auto Detector cerrado.")
        except Exception as e:
            self.log(f"Error al abrir Auto Detector: {str(e)}")

    def _open_position_editor(self):
        """Abre el editor de posiciones de marcas de agua"""
        try:
            self.log("Abriendo editor de posiciones...")
            editor = PositionEditor(self)
            
            # Si tenemos carpeta, intentamos pre-cargarla en el editor
            if self.current_folder and self.current_folder.exists():
                editor.images_folder = self.current_folder
                editor.images_label.setText(self.current_folder.name)
                editor._load_images()
                editor._check_ready()

            result = editor.exec()
            if result:
                self.log("Editor cerrado correctamente")
            else:
                self.log("Editor cancelado")

        except Exception as e:
            self.log(f"Error al abrir editor: {str(e)}")

    def _open_stitcher_dialog(self, initial_folder=None):
        """Abre el diálogo de Smart Stitcher"""
        # Si initial_folder es None, usa el texto del input o guardado
        # Convertir a str si es Path
        dialog = StitcherDialog(self, str(initial_folder) if initial_folder else None)
        dialog.exec()

    def log(self, message: str):
        """Agrega un mensaje a la consola de proceso"""
        self.process_console.append(message)
        # Scroll al final
        sb = self.process_console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_run_process_click(self):
        """Se activa al hacer click en Ejecutar Proceso"""
        if self.is_processing: return

        # Solicitar carpeta
        folder_path = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta para Procesar")
        if not folder_path:
            self.log("⏹ Operación cancelada por el usuario.")
            return

        self.set_input_path(folder_path)
        
        # Lanzar el panel Pro (SlideshowViewer)
        try:
            self.log(f"🚀 Iniciando Panel de Revisión para: {self.current_folder.name}")
            viewer = SlideshowViewer(
                folder_path=str(self.current_folder),
                parent=self,
                watermark_tab=self
            )
            result = viewer.exec()
            
            if result == QDialog.DialogCode.Accepted:
                self.log("✅ Revisión finalizada y aprobada.")
                # El visor ya procesó las imágenes, pasamos directo a preguntar por Stitch
                output_folder = viewer.output_folder
                self._on_process_finished(str(output_folder) if output_folder else None)
            else:
                self.log("⚠️ Revisión cancelada o cerrada sin confirmar.")
            
        except Exception as e:
            self.log(f"❌ Error al abrir el panel de revisión: {e}")
            import traceback
            traceback.print_exc()

    def _start_processing_thread(self):
        if self.is_processing: return
        self.is_processing = True
        self.log("🚀 Iniciando proceso de eliminación de marcas...")
        
        # Ejecutar en hilo para no congelar la UI
        t = threading.Thread(target=self._run_processing_logic)
        t.daemon = True
        t.start()

    def _run_processing_logic(self):
        try:
            folder = self.current_folder
            
            # 1. Cargar posiciones guardadas (Manuales / Offsets)
            json_pos_path = Path(parent_dir) / 'wm_preset_offsets.json'
            json_manual_pos_path = Path(parent_dir) / 'wm_positions.json'
            
            # Prioridad: 
            # 1. wm_positions.json (offsets manuales pos_1, pos_2...)
            # 2. wm_preset_offsets.json (config auto First/Middle/Last + offsets base)
            
            positions_map = {}
            auto_config = None
            
            # Cargar mapa manual si existe
            if json_manual_pos_path.exists():
                all_manual = UtilJson(json_manual_pos_path).read()
                positions_map = all_manual.get(folder.name, {})

            # Cargar config auto si existe
            if json_pos_path.exists():
                all_presets = UtilJson(json_pos_path).read()
                auto_config = all_presets.get(folder.name, {}).get("auto_selection", {})

            # Validar si tenemos ALGO
            if not positions_map and not auto_config:
                 # Esto no debería pasar si _check_config_exists funcionó, pero por seguridad
                 self.signals.error.emit(f"Error interno: Configuración no encontrada tras validación.")
                 return

            # 2. Cargar imágenes
            valid_exts = ('.png', '.jpg', '.jpeg', '.webp')
            images = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in valid_exts])
            
            if not images:
                self.signals.error.emit("Calculando... 0 imágenes en la carpeta.")
                return

            # Crear carpeta de salida
            output_dir = folder / "cleaned"
            output_dir.mkdir(exist_ok=True)
            self.signals.log.emit(f"📂 Guardando resultados en: {output_dir}")

            # 3. Preparar Marcas de Agua (Cache)
            marcas_dir = Path(parent_dir) / 'marcas'
            wm_cache = {}

            def get_wm_image(idx, total):
                # Determinar nombre de marca según auto_config
                wm_name = None
                if auto_config:
                    if idx == 0: wm_name = auto_config.get("first")
                    elif idx == total - 1: wm_name = auto_config.get("last")
                    else: wm_name = auto_config.get("middle")
                
                # Cargar imagen
                if wm_name:
                    if wm_name in wm_cache: return wm_cache[wm_name]
                    
                    # Buscar fichero
                    found = list(marcas_dir.rglob(wm_name))
                    if found:
                        img = load_images_cv2(str(found[0]))
                        if img is not None:
                            wm_cache[wm_name] = img
                            return img
                
                # Fallback: Primera marca encontrada en carpeta
                if "default" in wm_cache: return wm_cache["default"]
                
                found_any = list(marcas_dir.rglob("*.png"))
                if found_any:
                    img = load_images_cv2(str(found_any[0]))
                    wm_cache["default"] = img
                    return img
                
                return None

            processed_count = 0

            for i, img_path in enumerate(images):
                idx_key = f"pos_{i+1}"
                
                # Obtenemos offsets (Manual > Auto o Default 0)
                offset_x, offset_y, side_x, side_y = 0, 0, "right", "bottom"
                
                if idx_key in positions_map:
                    d = positions_map[idx_key]
                    offset_x = d.get('offset_x', 0)
                    offset_y = d.get('offset_y', 0)
                    side_x = d.get('side_x', 'right')
                    side_y = d.get('side_y', 'bottom')
                elif auto_config:
                    # Si no hay manual, usamos 0,0 pero intentamos limpiar con la marca auto
                    pass
                else:
                    # Sin info para esta imagen
                    self.signals.log.emit(f"🔸 Saltando {img_path.name} (Sin datos)")
                    continue

                # Cargar imagen
                img = load_images_cv2(str(img_path))
                if img is None: continue

                # Obtener marca correspondiente
                wm_img = get_wm_image(i, len(images))
                if wm_img is None:
                    self.signals.log.emit(f"❌ Error: No se encontró imagen de marca de agua para {img_path.name}")
                    continue

                self.signals.log.emit(f"🔹 Procesando: {img_path.name}...")
                
                # Alinear
                x, y = align_watermark(img, wm_img, offset_x, offset_y, side_x, side_y)
                
                # Remover
                res = remove_watermark(img, wm_img, x, y)
                
                # Guardar
                save_p = output_dir / img_path.name
                cv2.imwrite(str(save_p), res, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                
                processed_count += 1

            self.signals.log.emit(f"✅ Proceso terminado. {processed_count} imágenes limpiadas.")
            self.signals.finished.emit(str(output_dir))

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(f"Error crítico en proceso: {e}")

    def _on_process_finished(self, output_path=None):
        self.is_processing = False
        self.run_process_btn.setEnabled(True)
        self.run_process_btn.setText("Ejecutar Proceso")
        
        # Preguntar automáticamente si quiere Unir
        # Usar instancia para asegurar modalidad y visibilidad
        msg_box = QMessageBox(self.window()) # Usar la ventana principal como padre
        msg_box.setWindowTitle("Proceso Finalizado")
        msg_box.setText("La limpieza de marcas ha terminado.\n\n¿Desea unir las imágenes limpias ahora (Smart Stitcher)?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        # Forzar que esté encima
        msg_box.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        reply = msg_box.exec()
        
        if reply == QMessageBox.StandardButton.Yes:
            # Si output_path es válido, lo usamos. Si no, abrimos el stitcher igual (usará último o pedirá)
            # Pero la lógica original requería output_path para ser útil.
            target_path = output_path if output_path else None
            self._open_stitcher_dialog(target_path)

    def _on_process_error(self, err_msg):
        self.is_processing = False
        self.run_process_btn.setEnabled(True)
        self.run_process_btn.setText("Ejecutar Proceso")
        self.log(f"❌ ERROR: {err_msg}")
        QMessageBox.warning(self, "Error", err_msg)
