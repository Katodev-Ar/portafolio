
import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QLineEdit, QSpinBox, QFileDialog, QProgressBar, QMessageBox, QGroupBox, QFormLayout,
    QTabWidget, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings

# Importar lógica
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from smart_stitch_logic import SmartStitcher

class StitcherWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, folder, width, height, sensitivity, post_process_config=None):
        super().__init__()
        self.folder = folder
        self.width = width
        self.height = height
        self.sensitivity = sensitivity
        self.post_process_config = post_process_config
        self.stitcher = SmartStitcher(console_callback=self.emit_log)

    def emit_log(self, text):
        self.progress.emit(text)

    def run(self):
        try:
            # 1. Stitch & Post Process (handled internally)
            self.stitcher.process_folder(
                self.folder, 
                self.width, 
                self.height, 
                sensitivity=self.sensitivity,
                post_process_config=self.post_process_config
            )
            
            self.finished.emit(True, "Proceso completado.")
        except Exception as e:
            self.finished.emit(False, str(e))

class StitcherDialog(QDialog):
    def __init__(self, parent=None, initial_folder=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Stitcher - Unir y Cortar")
        self.resize(500, 400)
        self.settings = QSettings("VisualFluent", "SmartStitcher")
        self._setup_ui()
        self._load_settings()
        
        # Si se pasa una carpeta específica, tiene prioridad sobre la guardada
        if initial_folder and os.path.exists(initial_folder):
            self.folder_input.setText(str(initial_folder))

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 1. Selección de Carpeta
        folder_group = QGroupBox("Carpeta de Origen")
        folder_layout = QHBoxLayout()
        self.folder_input = QLineEdit()
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.browse_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        # 2. Tabs de Configuración
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- TAB 1: Básico ---
        tab_basic = QWidget()
        basic_layout = QVBoxLayout(tab_basic)
        
        settings_group = QGroupBox("Configuración de Corte")
        form_layout = QFormLayout()

        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 5000)
        self.width_spin.setValue(720)
        self.width_spin.setSuffix(" px")
        form_layout.addRow("Ancho Objetivo:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1000, 50000)
        self.height_spin.setValue(15000) # Altura típica de webtoon cap
        self.height_spin.setSuffix(" px")
        form_layout.addRow("Altura Máxima (aprox):", self.height_spin)
        
        self.sensitivity_spin = QSpinBox()
        self.sensitivity_spin.setRange(1, 100)
        self.sensitivity_spin.setValue(90)
        self.sensitivity_spin.setSuffix("%")
        form_layout.addRow("Sensibilidad de Corte:", self.sensitivity_spin)

        settings_group.setLayout(form_layout)
        basic_layout.addWidget(settings_group)
        basic_layout.addStretch()
        self.tabs.addTab(tab_basic, "Básico")

        # --- TAB 2: Post Process ---
        tab_pp = QWidget()
        pp_layout = QVBoxLayout(tab_pp)
        
        self.pp_group = QGroupBox("Post Process Settings")
        self.pp_group.setCheckable(True)
        self.pp_group.setChecked(False)
        pp_form = QFormLayout()
        
        self.pp_app_path = QLineEdit()
        self.pp_app_path.setPlaceholderText("Ruta al ejecutable (ej: waifu2x-ncnn-vulkan.exe)")
        browse_pp_btn = QPushButton("Browse")
        browse_pp_btn.clicked.connect(self._browse_pp_app)
        pp_app_layout = QHBoxLayout()
        pp_app_layout.addWidget(self.pp_app_path)
        pp_app_layout.addWidget(browse_pp_btn)
        
        self.pp_args = QLineEdit()
        self.pp_args.setText("-i [stitched] -o [processed] -n 3 -s 1 -f jpg")
        self.pp_args.setPlaceholderText("Argumentos")
        
        pp_form.addRow("Aplicación:", pp_app_layout)
        pp_form.addRow("Argumentos:", self.pp_args)
        pp_form.addRow(QLabel("<small>Use <b>[stitched]</b> como placeholder de entrada y <b>[processed]</b> para salida.</small>"))
        
        self.pp_group.setLayout(pp_form)
        pp_layout.addWidget(self.pp_group)
        pp_layout.addStretch()
        self.tabs.addTab(tab_pp, "Post Process")

        # 3. Log y Progreso
        self.log_output = QLabel("Listo para iniciar...")
        self.log_output.setWordWrap(True)
        self.log_output.setStyleSheet("color: #666; font-size: 11px; border: 1px solid #ccc; padding: 5px;")
        layout.addWidget(self.log_output)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminado
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # 4. Botones
        btn_layout = QHBoxLayout()
        self.btn_run = QPushButton("🚀 Iniciar Stitch")
        self.btn_run.clicked.connect(self._run_process)
        self.btn_run.setStyleSheet("background-color: #2196F3; color: white; padding: 10px; font-weight: bold;")
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_run)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
        if folder:
            self.folder_input.setText(folder)

    def _browse_pp_app(self):
        f, _ = QFileDialog.getOpenFileName(self, "Ejecutable", "", "Executables (*.exe);;All Files (*.*)")
        if f:
            self.pp_app_path.setText(f)

    def _run_process(self):
        folder = self.folder_input.text()
        if not folder or not os.path.exists(folder):
            QMessageBox.warning(self, "Error", "Seleccione una carpeta válida.")
            return

        self.btn_run.setEnabled(False)
        self.progress_bar.show()
        self.log_output.setText("Iniciando...")
        
        # Configuración Post Process
        pp_config = {
            "enabled": self.pp_group.isChecked(),
            "app_path": self.pp_app_path.text(),
            "args": self.pp_args.text()
        }

        self._save_settings()

        # Iniciar Worker Thread
        self.worker = StitcherWorker(
            folder, 
            self.width_spin.value(), 
            self.height_spin.value(),
            self.sensitivity_spin.value(),
            post_process_config=pp_config
        )
        self.worker.progress.connect(self.log_output.setText)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, success, message):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        if success:
            QMessageBox.information(self, "Éxito", message)
            self.log_output.setText("✅ " + message)
        else:
            QMessageBox.critical(self, "Error", message)
            self.log_output.setText("❌ " + message)

    def _save_settings(self):
        """Guarda la configuración actual"""
        self.settings.setValue("width", self.width_spin.value())
        self.settings.setValue("height", self.height_spin.value())
        self.settings.setValue("sensitivity", self.sensitivity_spin.value())
        self.settings.setValue("folder", self.folder_input.text())
        
        # Post Process
        self.settings.setValue("pp_enabled", self.pp_group.isChecked())
        self.settings.setValue("pp_app_path", self.pp_app_path.text())
        self.settings.setValue("pp_args", self.pp_args.text())

    def _load_settings(self):
        """Carga la configuración guardada con valores por defecto seguros"""
        # Cargar valores con tipo explícito y default
        width = self.settings.value("width", 720, type=int)
        self.width_spin.setValue(width)
        
        height = self.settings.value("height", 15000, type=int)
        self.height_spin.setValue(height)
        
        sensitivity = self.settings.value("sensitivity", 90, type=int)
        self.sensitivity_spin.setValue(sensitivity)
        
        folder = self.settings.value("folder", "", type=str)
        if folder:
            self.folder_input.setText(folder)

        # Post Process
        pp_enabled = self.settings.value("pp_enabled", False, type=bool)
        self.pp_group.setChecked(pp_enabled)
        
        pp_path = self.settings.value("pp_app_path", "", type=str)
        if pp_path:
            self.pp_app_path.setText(pp_path)
            
        pp_args = self.settings.value("pp_args", "", type=str)
        if pp_args:
            self.pp_args.setText(pp_args)
