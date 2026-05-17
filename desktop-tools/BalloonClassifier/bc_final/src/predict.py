# =============================================================================
# predict.py — Inferencia sobre imágenes individuales
# =============================================================================
# Este módulo es el punto de entrada para la predicción en producción.
# Está diseñado para integrarse con el sistema externo OCR/Traductor.

import logging
from pathlib import Path
from typing import Union

import torch
from PIL import Image

from utils.config import (
    CLASSES, IDX_TO_CLASS, MODEL_FILE,
    CONFIDENCE_THRESHOLD,
)
from src.model import load_model, get_device
from src.preprocessing import preprocess_single

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predictor reutilizable (mantiene el modelo en memoria)
# ---------------------------------------------------------------------------

class BalloonPredictor:
    """
    Predictor de globos de manga. Mantiene el modelo cargado en memoria
    para inferencia rápida y repetida.

    Uso básico:
        predictor = BalloonPredictor()
        result = predictor.predict("ruta/imagen.png")
        print(result["class"], result["confidence"])

    Integración futura con sistema externo:
        payload = {
            "image": "ruta/globo.png",
            "ocr_text": "...",
            "bounding_box": [x, y, w, h]
        }
        result = predictor.predict_from_payload(payload)
    """

    def __init__(self, model_path: Path | None = None,
                 device: "torch.device | None" = None):
        self.model_path = Path(model_path or MODEL_FILE)
        self.device     = device or get_device()
        self.model      = None
        self._loaded    = False

    def load(self) -> bool:
        """Carga el modelo en memoria. Retorna True si fue exitoso."""
        try:
            self.model, _ = load_model(self.model_path, self.device)
            self._loaded  = True
            logger.info("Predictor listo.")
            return True
        except FileNotFoundError:
            logger.error(f"Modelo no encontrado: {self.model_path}")
            return False
        except Exception as e:
            logger.error(f"Error cargando modelo: {e}")
            return False

    @property
    def is_ready(self) -> bool:
        return self._loaded and self.model is not None

    # -----------------------------------------------------------------------

    def predict(self, image: Union[str, Path, Image.Image]) -> dict:
        """
        Predice la clase de un globo a partir de una imagen.

        Args:
            image: Ruta a la imagen o PIL Image ya cargada.

        Returns:
            {
                "class":       str,           # nombre de la clase predicha
                "confidence":  float,         # confianza [0, 1]
                "probabilities": {cls: prob}, # prob de todas las clases
                "is_confident":bool,          # si supera el umbral
            }
        """
        if not self.is_ready:
            raise RuntimeError("Modelo no cargado. Llama a .load() primero.")

        # Cargar imagen si se pasó como ruta
        if isinstance(image, (str, Path)):
            img = Image.open(image).convert("RGB")
        else:
            img = image.convert("RGB")

        # Preprocesar
        tensor = preprocess_single(img).to(self.device)

        # Inferencia
        self.model.eval()
        with torch.no_grad():
            logits = self.model(tensor)          # [1, num_classes]
            probs  = torch.softmax(logits, dim=1).squeeze(0)  # [num_classes]

        probs_np = probs.cpu().numpy()
        pred_idx  = int(probs_np.argmax())
        pred_cls  = IDX_TO_CLASS[pred_idx]
        confidence= float(probs_np[pred_idx])

        probabilities = {cls: float(probs_np[i]) for i, cls in IDX_TO_CLASS.items()}

        result = {
            "class":         pred_cls,
            "confidence":    confidence,
            "probabilities": probabilities,
            "is_confident":  confidence >= CONFIDENCE_THRESHOLD,
        }

        logger.debug(
            f"Predicción: {pred_cls} ({confidence:.2%}) | "
            f"Confiante: {result['is_confident']}"
        )
        return result

    # -----------------------------------------------------------------------
    # Integración futura con sistema externo OCR/Traductor
    # -----------------------------------------------------------------------

    def predict_from_payload(self, payload: dict) -> dict:
        """
        Procesa un payload del sistema externo de traducción OCR.

        El sistema externo enviará:
            {
                "image":        "ruta/globo.png",  ← o base64
                "ocr_text":     "...",
                "bounding_box": [x, y, w, h]
            }

        Retorna el resultado de predicción enriquecido con
        los metadatos del payload.

        (Implementación completa pendiente en futura versión)
        """
        import base64, io

        img_data = payload.get("image", "")
        ocr_text = payload.get("ocr_text", "")
        bbox     = payload.get("bounding_box", [])

        # Soporte para base64 o ruta de archivo
        if img_data.startswith("data:image") or _is_base64(img_data):
            # Decodificar base64
            b64 = img_data.split(",")[-1]
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        else:
            img = Image.open(img_data).convert("RGB")

        result = self.predict(img)
        result["ocr_text"]     = ocr_text
        result["bounding_box"] = bbox
        return result


def _is_base64(s: str) -> bool:
    """Comprueba heurísticamente si un string parece base64."""
    import re
    return bool(re.match(r'^[A-Za-z0-9+/=]{20,}$', s.strip()))


# ---------------------------------------------------------------------------
# Función de conveniencia para uso directo
# ---------------------------------------------------------------------------

_default_predictor: BalloonPredictor | None = None


def predict_image(image: Union[str, Path, Image.Image],
                  model_path: Path | None = None) -> dict:
    """
    Función de alto nivel para predecir una imagen.
    Reutiliza el predictor global si ya está cargado.
    """
    global _default_predictor
    if _default_predictor is None or not _default_predictor.is_ready:
        _default_predictor = BalloonPredictor(model_path)
        if not _default_predictor.load():
            raise RuntimeError("No se pudo cargar el modelo de clasificación.")
    return _default_predictor.predict(image)
