# =============================================================================
# config.py — Configuración global del clasificador de globos
# =============================================================================
# Todos los parámetros ajustables del sistema están centralizados aquí.
# Para futura integración con sistema OCR externo, los parámetros de API
# también se añadirán en esta sección.

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# RUTAS DEL PROYECTO
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH  = ROOT_DIR / "dataset"
MODEL_PATH    = ROOT_DIR / "models"
LOG_PATH      = ROOT_DIR / "logs"
METRICS_PATH  = ROOT_DIR / "models" / "metrics.json"
MODEL_FILE    = ROOT_DIR / "models" / "balloon_classifier.pt"

# Crear directorios si no existen
for _dir in [DATASET_PATH, MODEL_PATH, LOG_PATH]:
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# CLASES DE GLOBOS
# ---------------------------------------------------------------------------
CLASSES = [
    "dialogo",       # Globo de conversación estándar
    "pensamiento",   # Globo con bordes tipo nube
    "grito",         # Globo dentado / explosivo
    "narracion",     # Caja rectangular de narrador
    "texto_libre",   # Texto sin globo contenedor
    "sfx",           # Onomatopeya / efecto de sonido
]

NUM_CLASSES = len(CLASSES)

# Mapas de índice ↔ nombre de clase
CLASS_TO_IDX = {cls: idx for idx, cls in enumerate(CLASSES)}
IDX_TO_CLASS = {idx: cls for cls, idx in CLASS_TO_IDX.items()}

# Colores para visualización (R, G, B)
CLASS_COLORS = {
    "dialogo":     "#4A90D9",
    "pensamiento": "#7B68EE",
    "grito":       "#E74C3C",
    "narracion":   "#2ECC71",
    "texto_libre": "#F39C12",
    "sfx":         "#E91E63",
}

# ---------------------------------------------------------------------------
# IMAGEN Y PREPROCESAMIENTO
# ---------------------------------------------------------------------------
IMAGE_SIZE    = 224          # Tamaño de entrada del modelo (px)
MEAN_RGB      = [0.485, 0.456, 0.406]   # Media ImageNet
STD_RGB       = [0.229, 0.224, 0.225]   # Desviación estándar ImageNet
USE_GRAYSCALE = False        # Convertir a escala de grises antes de entrenar

# ---------------------------------------------------------------------------
# DATA AUGMENTATION
# ---------------------------------------------------------------------------
AUG_ROTATION      = 5      # Grados máximos de rotación (±)
AUG_ZOOM_MIN      = 0.9    # Factor mínimo de zoom
AUG_ZOOM_MAX      = 1.1    # Factor máximo de zoom
AUG_BRIGHTNESS    = 0.2    # Variación máxima de brillo
AUG_CONTRAST      = 0.2    # Variación máxima de contraste
AUG_NOISE_STDDEV  = 0.01   # Desviación estándar del ruido gaussiano

# ---------------------------------------------------------------------------
# ENTRENAMIENTO
# ---------------------------------------------------------------------------
BATCH_SIZE     = 32
EPOCHS         = 30
LEARNING_RATE  = 0.0003
WEIGHT_DECAY   = 1e-4      # Regularización L2 en AdamW
VAL_SPLIT      = 0.2       # Fracción del dataset para validación
RANDOM_SEED    = 42

# Scheduler: ReduceLROnPlateau
LR_PATIENCE    = 5
LR_FACTOR      = 0.5
LR_MIN         = 1e-6

# Early stopping
EARLY_STOP_PATIENCE = 10

# ---------------------------------------------------------------------------
# MODELO
# ---------------------------------------------------------------------------
BACKBONE       = "mobilenet_v3_small"   # Backbone preentrenado
PRETRAINED     = True                   # Usar pesos ImageNet
DROPOUT_RATE   = 0.3                    # Dropout en cabeza clasificadora
FREEZE_BACKBONE = False                 # Si True, solo entrena la cabeza

# ---------------------------------------------------------------------------
# INFERENCIA
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 0.5  # Confianza mínima para aceptar predicción

# ---------------------------------------------------------------------------
# FUTURA INTEGRACIÓN EXTERNA (OCR / Traductor)
# ---------------------------------------------------------------------------
# Formato esperado desde el sistema externo:
# {
#   "image": "recorte_globo.png",   ← ruta o base64
#   "ocr_text": "...",              ← texto reconocido
#   "bounding_box": [x, y, w, h]   ← posición en la página
# }
EXTERNAL_API_URL   = "http://localhost:5000/classify"
EXTERNAL_API_TOKEN = ""     # Token de autenticación (vacío por ahora)
