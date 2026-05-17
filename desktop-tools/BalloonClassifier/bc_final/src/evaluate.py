# =============================================================================
# evaluate.py — Evaluación completa del modelo entrenado
# =============================================================================

import logging
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from utils.config import CLASSES, IDX_TO_CLASS, METRICS_PATH
from utils.metrics import compute_metrics, save_metrics, format_metrics_summary
from src.model import load_model, get_device

logger = logging.getLogger(__name__)


def evaluate_model(model: "torch.nn.Module | None" = None,
                   val_loader: DataLoader | None = None,
                   model_path: Path | None = None,
                   save_path:  Path | None = None,
                   device: "torch.device | None" = None) -> dict:
    """
    Evalúa el modelo sobre el conjunto de validación.

    Puede recibir el modelo ya en memoria o cargarlo desde disco.

    Args:
        model:      Modelo ya cargado (opcional).
        val_loader: DataLoader de validación.
        model_path: Ruta al checkpoint si model es None.
        save_path:  Dónde guardar metrics.json (None = usar config).
        device:     Dispositivo de cómputo.

    Returns:
        Diccionario de métricas con accuracy, confusion_matrix, per_class.
    """
    device = device or get_device()

    # Cargar modelo si no se pasó en memoria
    if model is None:
        if model_path is None:
            from utils.config import MODEL_FILE
            model_path = MODEL_FILE
        model, _ = load_model(model_path, device=device)

    model.eval()
    model.to(device)

    if val_loader is None:
        raise ValueError("Se requiere un DataLoader de validación para evaluar.")

    y_true, y_pred = [], []

    with torch.no_grad():
        for images, labels in val_loader:
            images = images.to(device, non_blocking=True)
            outputs = model(images)
            preds   = outputs.argmax(dim=1).cpu().tolist()
            y_pred.extend(preds)
            y_true.extend(labels.tolist())

    metrics = compute_metrics(y_true, y_pred, CLASSES)

    # Guardar métricas
    save_path = Path(save_path) if save_path else METRICS_PATH
    save_metrics(metrics, save_path)

    # Log del resumen
    logger.info("\n" + format_metrics_summary(metrics))

    return metrics


def predict_batch(model: "torch.nn.Module",
                  images: "torch.Tensor",
                  device: "torch.device | None" = None
                  ) -> tuple[list[str], list[float]]:
    """
    Corre inferencia sobre un batch de imágenes.

    Returns:
        (class_names, confidences) — listas paralelas.
    """
    device = device or get_device()
    model.eval()

    with torch.no_grad():
        images  = images.to(device)
        logits  = model(images)
        probs   = torch.softmax(logits, dim=1)
        confs, idxs = probs.max(dim=1)

    class_names  = [IDX_TO_CLASS[i.item()] for i in idxs]
    confidences  = [c.item() for c in confs]
    return class_names, confidences
