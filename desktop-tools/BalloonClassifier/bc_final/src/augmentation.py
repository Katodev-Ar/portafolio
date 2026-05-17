# =============================================================================
# augmentation.py — Transformaciones de data augmentation
# =============================================================================
# Todas las transformaciones aleatorias usadas durante el entrenamiento
# están aquí. Son configurables desde utils/config.py.

import random
import numpy as np
from PIL import Image
import torchvision.transforms as T

from utils.config import (
    IMAGE_SIZE, MEAN_RGB, STD_RGB, USE_GRAYSCALE,
    AUG_ROTATION, AUG_ZOOM_MIN, AUG_ZOOM_MAX,
    AUG_BRIGHTNESS, AUG_CONTRAST, AUG_NOISE_STDDEV,
)
from src.preprocessing import EnhanceContrastIfFlat, ToGrayscaleRGB


# ---------------------------------------------------------------------------
# Transformación personalizada: ruido gaussiano
# ---------------------------------------------------------------------------

class AddGaussianNoise:
    """
    Añade ruido gaussiano leve a un tensor de imagen.
    Debe aplicarse DESPUÉS de T.ToTensor().
    """
    def __init__(self, std: float = AUG_NOISE_STDDEV):
        self.std = std

    def __call__(self, tensor: "torch.Tensor") -> "torch.Tensor":
        import torch
        noise = torch.randn_like(tensor) * self.std
        return (tensor + noise).clamp(0.0, 1.0)

    def __repr__(self) -> str:
        return f"AddGaussianNoise(std={self.std})"


# ---------------------------------------------------------------------------
# Constructor del pipeline de augmentation para entrenamiento
# ---------------------------------------------------------------------------

def build_augmentation_transform(
    image_size:    int   = IMAGE_SIZE,
    rotation:      float = AUG_ROTATION,
    zoom_min:      float = AUG_ZOOM_MIN,
    zoom_max:      float = AUG_ZOOM_MAX,
    brightness:    float = AUG_BRIGHTNESS,
    contrast:      float = AUG_CONTRAST,
    noise_std:     float = AUG_NOISE_STDDEV,
    use_grayscale: bool  = USE_GRAYSCALE,
) -> T.Compose:
    """
    Construye el pipeline de augmentation para entrenamiento.

    Transformaciones aplicadas (todas probabilísticas):
        1. Mejora de contraste si imagen muy plana
        2. Conversión a grises (opcional)
        3. Rotación aleatoria leve
        4. Zoom / recorte aleatorio
        5. Flip horizontal (útil para mangá asiático)
        6. Ajuste de brillo y contraste
        7. Conversión a tensor
        8. Ruido gaussiano leve
        9. Normalización

    Returns:
        torchvision.transforms.Compose configurado.
    """
    # Tamaño para escala antes del crop
    scale_size = int(image_size * zoom_max * 1.1)

    steps = [
        EnhanceContrastIfFlat(threshold=0.08),
    ]

    if use_grayscale:
        steps.append(ToGrayscaleRGB())

    steps += [
        # Rotación leve (globos raramente están muy inclinados)
        T.RandomRotation(degrees=rotation, fill=255),

        # Zoom: resize + crop aleatorio
        T.Resize(scale_size, interpolation=T.InterpolationMode.LANCZOS),
        T.RandomResizedCrop(
            size=image_size,
            scale=(zoom_min, zoom_max),
            ratio=(0.85, 1.15),
            interpolation=T.InterpolationMode.LANCZOS,
        ),

        # Flip horizontal — globos son simétricos horizontalmente
        T.RandomHorizontalFlip(p=0.5),

        # Color jitter (brillo + contraste)
        T.ColorJitter(brightness=brightness, contrast=contrast),

        # Conversión a tensor [0, 1]
        T.ToTensor(),

        # Ruido gaussiano
        AddGaussianNoise(std=noise_std),

        # Normalización ImageNet
        T.Normalize(mean=MEAN_RGB, std=STD_RGB),
    ]

    return T.Compose(steps)
