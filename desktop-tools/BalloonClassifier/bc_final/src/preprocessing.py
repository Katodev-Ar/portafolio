# =============================================================================
# preprocessing.py — Pipeline de preprocesamiento de imágenes
# =============================================================================

import logging
import numpy as np
from PIL import Image
import torchvision.transforms as T

from utils.config import IMAGE_SIZE, MEAN_RGB, STD_RGB, USE_GRAYSCALE
from utils.image_utils import enhance_contrast

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transformación personalizada: mejora de contraste
# ---------------------------------------------------------------------------

class EnhanceContrastIfFlat:
    """
    Transformación personalizada que aplica CLAHE cuando la imagen
    tiene poca variación de contraste (imagen muy plana).
    """
    def __init__(self, threshold: float = 0.1):
        self.threshold = threshold

    def __call__(self, img: Image.Image) -> Image.Image:
        return enhance_contrast(img, self.threshold)

    def __repr__(self) -> str:
        return f"EnhanceContrastIfFlat(threshold={self.threshold})"


# ---------------------------------------------------------------------------
# Transformaciones de conversión a escala de grises
# ---------------------------------------------------------------------------

class ToGrayscaleRGB:
    """
    Convierte a escala de grises pero mantiene 3 canales RGB
    (requerido por MobileNetV3).
    """
    def __call__(self, img: Image.Image) -> Image.Image:
        gray = img.convert("L")
        return Image.merge("RGB", [gray, gray, gray])


# ---------------------------------------------------------------------------
# Constructor del pipeline de preprocesamiento estándar (sin augmentation)
# ---------------------------------------------------------------------------

def build_transform(image_size: int = IMAGE_SIZE,
                    use_grayscale: bool = USE_GRAYSCALE) -> T.Compose:
    """
    Construye el pipeline de preprocesamiento para inferencia y validación.

    Pasos:
        1. Mejora de contraste si la imagen es muy plana
        2. Conversión a escala de grises (opcional)
        3. Redimensionado a image_size × image_size
        4. Conversión a tensor (normaliza a [0, 1])
        5. Normalización con media/std de ImageNet

    Returns:
        torchvision.transforms.Compose listo para usar.
    """
    steps = [
        EnhanceContrastIfFlat(threshold=0.08),
    ]

    if use_grayscale:
        steps.append(ToGrayscaleRGB())

    steps += [
        T.Resize((image_size, image_size), interpolation=T.InterpolationMode.LANCZOS),
        T.ToTensor(),
        T.Normalize(mean=MEAN_RGB, std=STD_RGB),
    ]

    transform = T.Compose(steps)
    logger.debug(f"Transform construido: {transform}")
    return transform


# ---------------------------------------------------------------------------
# Utilidad: preprocesar una sola imagen PIL para inferencia
# ---------------------------------------------------------------------------

def preprocess_single(img: Image.Image,
                      image_size: int = IMAGE_SIZE) -> "torch.Tensor":
    """
    Preprocesa una única imagen PIL y retorna un tensor listo para el modelo.
    El tensor tendrá forma [1, 3, image_size, image_size].
    """
    import torch
    transform = build_transform(image_size=image_size)
    tensor    = transform(img.convert("RGB"))
    return tensor.unsqueeze(0)   # Añade dimensión de batch


# ---------------------------------------------------------------------------
# Utilidad: desnormalizar tensor para visualización
# ---------------------------------------------------------------------------

def denormalize(tensor: "torch.Tensor") -> np.ndarray:
    """
    Desnormaliza un tensor [3, H, W] para visualizarlo como imagen.
    Retorna un array uint8 de forma [H, W, 3].
    """
    import torch
    mean = torch.tensor(MEAN_RGB).view(3, 1, 1)
    std  = torch.tensor(STD_RGB).view(3, 1, 1)
    img  = tensor * std + mean
    img  = img.clamp(0, 1)
    return (img.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
