# =============================================================================
# model.py — Definición del modelo clasificador de globos
# =============================================================================

import logging
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models
from torchvision.models import MobileNet_V3_Small_Weights

from utils.config import (
    NUM_CLASSES, BACKBONE, PRETRAINED,
    DROPOUT_RATE, FREEZE_BACKBONE, MODEL_FILE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constructor del modelo
# ---------------------------------------------------------------------------

def build_model(num_classes: int = NUM_CLASSES,
                pretrained:  bool  = PRETRAINED,
                dropout:     float = DROPOUT_RATE,
                freeze_backbone: bool = FREEZE_BACKBONE) -> nn.Module:
    """
    Construye MobileNetV3-Small con cabeza clasificadora personalizada.

    Arquitectura:
        Input [3, 224, 224]
            ↓
        MobileNetV3-Small backbone (pretrained ImageNet)
            ↓
        AdaptiveAvgPool2d  →  [576, 1, 1]
            ↓
        Flatten
            ↓
        Linear(576 → 1024) + Hardswish + Dropout
            ↓
        Linear(1024 → num_classes)
            ↓
        (Softmax aplicada durante inferencia, no en training)

    Args:
        num_classes:     Número de categorías de globos.
        pretrained:      Usar pesos preentrenados en ImageNet.
        dropout:         Tasa de dropout en la cabeza clasificadora.
        freeze_backbone: Si True, congela pesos del backbone.

    Returns:
        nn.Module listo para entrenar.
    """
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1 if pretrained else None
    model   = models.mobilenet_v3_small(weights=weights)

    # Congelar backbone si se solicita (útil con datasets pequeños)
    if freeze_backbone:
        for param in model.features.parameters():
            param.requires_grad = False
        logger.info("Backbone congelado — solo se entrenará la cabeza.")

    # Reemplazar la cabeza clasificadora original
    in_features = model.classifier[0].in_features   # 576
    model.classifier = nn.Sequential(
        nn.Linear(in_features, 1024),
        nn.Hardswish(inplace=True),
        nn.Dropout(p=dropout),
        nn.Linear(1024, num_classes),
    )

    _log_model_info(model)
    return model


# ---------------------------------------------------------------------------
# Guardado y carga del modelo
# ---------------------------------------------------------------------------

def save_model(model: nn.Module,
               path: Path | str = MODEL_FILE,
               extra: dict | None = None) -> None:
    """
    Guarda el modelo completo y metadatos opcionales.

    El archivo guardado incluye:
        - state_dict:  Pesos del modelo
        - config:      Parámetros de construcción
        - extra:       Información adicional (epoch, métricas, etc.)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "state_dict": model.state_dict(),
        "config": {
            "num_classes": NUM_CLASSES,
            "dropout":     DROPOUT_RATE,
            "backbone":    BACKBONE,
        },
    }
    if extra:
        checkpoint.update(extra)

    torch.save(checkpoint, path)
    logger.info(f"Modelo guardado en: {path}")


def load_model(path: Path | str = MODEL_FILE,
               device: torch.device | None = None) -> tuple[nn.Module, dict]:
    """
    Carga un modelo desde un checkpoint guardado.

    Returns:
        (model, extra_info)
    """
    path   = Path(path)
    device = device or get_device()

    if not path.exists():
        raise FileNotFoundError(f"No se encontró el modelo en: {path}")

    checkpoint = torch.load(path, map_location=device, weights_only=False)

    cfg   = checkpoint.get("config", {})
    model = build_model(
        num_classes=cfg.get("num_classes", NUM_CLASSES),
        pretrained=False,   # No cargar ImageNet otra vez
        dropout=cfg.get("dropout", DROPOUT_RATE),
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device)
    model.eval()

    extra = {k: v for k, v in checkpoint.items()
             if k not in ("state_dict", "config")}
    logger.info(f"Modelo cargado desde: {path}")
    return model, extra


def model_exists(path: Path | str = MODEL_FILE) -> bool:
    """Verifica si existe un modelo guardado."""
    return Path(path).exists()


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def get_device() -> torch.device:
    """Retorna el dispositivo disponible (CUDA > MPS > CPU)."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    logger.info(f"Dispositivo seleccionado: {device}")
    return device


def _log_model_info(model: nn.Module) -> None:
    """Loguea el número de parámetros del modelo."""
    total     = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(
        f"Modelo: MobileNetV3-Small | "
        f"Parámetros totales: {total:,} | "
        f"Entrenables: {trainable:,}"
    )
