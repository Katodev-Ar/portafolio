# 🎌 BalloonClassifier

Aplicación de escritorio en Python para **entrenar, evaluar y usar** un modelo de IA que clasifica globos de diálogo en manga/manhwa/manhua.

---

## Categorías de globos

| Clase | Descripción |
|-------|-------------|
| `dialogo` | Globo de conversación estándar |
| `pensamiento` | Globo con bordes tipo nube |
| `grito` | Globo dentado / explosivo |
| `narracion` | Caja rectangular de narrador |
| `texto_libre` | Texto sin globo contenedor |
| `sfx` | Onomatopeya / efecto de sonido |

---

## Instalación

```bash
# 1. Clonar o extraer el proyecto
cd balloon_classifier

# 2. Crear entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

### Requisitos del sistema
- Python 3.10+
- Para aceleración GPU: instalar PyTorch con CUDA según https://pytorch.org

---

## Estructura del proyecto

```
balloon_classifier/
├── dataset/
│   ├── dialogo/          ← tus imágenes .png/.jpg
│   ├── pensamiento/
│   ├── grito/
│   ├── narracion/
│   ├── texto_libre/
│   └── sfx/
├── models/
│   └── balloon_classifier.pt   ← guardado automáticamente
├── logs/
│   └── balloon_classifier.log
├── src/
│   ├── dataset_loader.py       # Carga y splits del dataset
│   ├── preprocessing.py        # Pipeline de preprocesamiento
│   ├── augmentation.py         # Data augmentation configurable
│   ├── model.py                # MobileNetV3-Small + cabeza custom
│   ├── train.py                # Bucle de entrenamiento con callbacks
│   ├── evaluate.py             # Métricas de evaluación
│   └── predict.py              # Inferencia en producción
├── ui/
│   ├── app.py                  # Ventana principal (tabs)
│   ├── dataset_manager.py      # Panel de estadísticas del dataset
│   ├── training_panel.py       # Panel de entrenamiento con gráficos
│   └── inference_panel.py      # Panel de predicción
├── utils/
│   ├── config.py               # Todos los parámetros configurables
│   ├── image_utils.py          # Utilidades de imagen (PIL/OpenCV)
│   └── metrics.py              # Cálculo y guardado de métricas
├── main.py                     # Punto de entrada
└── requirements.txt
```

---

## Uso

### 1. Preparar el dataset

Coloca tus imágenes recortadas de globos en las carpetas correspondientes:

```
dataset/dialogo/dialogo_001.png
dataset/dialogo/dialogo_002.jpg
dataset/grito/grito_001.png
...
```

> Recomendado: **mínimo 50–100 imágenes por clase** para resultados razonables.

### 2. Lanzar la aplicación

```bash
python main.py
```

### 3. Flujo de trabajo en la UI

```
Tab "Dataset"        → Verifica conteo de imágenes por clase
Tab "Entrenamiento"  → Ajusta epochs/batch/lr → Inicia entrenamiento
                       Observa gráficos de pérdida y accuracy en tiempo real
Tab "Predicción"     → Carga una imagen de globo → Clasifica
```

---

## Configuración

Todos los parámetros están en `utils/config.py`:

```python
IMAGE_SIZE     = 224
BATCH_SIZE     = 32
EPOCHS         = 30
LEARNING_RATE  = 0.0003
VAL_SPLIT      = 0.2       # 20% para validación
```

---

## Integración futura (OCR / Traductor externo)

El sistema está preparado para recibir payloads del sistema externo:

```python
from src.predict import BalloonPredictor

predictor = BalloonPredictor()
predictor.load()

payload = {
    "image": "ruta/globo.png",   # o base64
    "ocr_text": "...",
    "bounding_box": [x, y, w, h]
}
result = predictor.predict_from_payload(payload)
# result["class"]       → "dialogo"
# result["confidence"]  → 0.93
```

---

## Modelo

- **Backbone:** MobileNetV3-Small (preentrenado ImageNet)
- **Entrada:** 224×224 px, RGB
- **Cabeza:** Linear(576→1024) + Hardswish + Dropout + Linear(1024→6)
- **Guardado automático** del mejor modelo en `models/balloon_classifier.pt`
- **Métricas** guardadas en `models/metrics.json`

---

## Extensiones futuras previstas

- [ ] Detección automática de globos en páginas completas
- [ ] Análisis de forma del globo (contorno, dentado, nube...)
- [ ] Cálculo del centro visual para typesetting
- [ ] Tipografía automática según clase de globo
- [ ] API REST para integración con otros servicios
