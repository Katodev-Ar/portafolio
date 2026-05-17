# =============================================================================
# metrics.py — Cálculo y guardado de métricas de evaluación
# =============================================================================

import json
import logging
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    classification_report,
    precision_recall_fscore_support,
)

logger = logging.getLogger(__name__)


def compute_metrics(y_true: list[int], y_pred: list[int],
                    class_names: list[str]) -> dict:
    """
    Calcula métricas completas de clasificación.

    Args:
        y_true:       Etiquetas reales (índices de clase).
        y_pred:       Predicciones del modelo (índices de clase).
        class_names:  Nombres de las clases en orden de índice.

    Returns:
        Diccionario con accuracy, matriz de confusión, precision, recall y F1
        por clase.
    """
    acc = accuracy_score(y_true, y_pred)
    cm  = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred,
        labels=list(range(len(class_names))),
        zero_division=0,
    )

    per_class = {}
    for i, cls in enumerate(class_names):
        per_class[cls] = {
            "precision": float(precision[i]),
            "recall":    float(recall[i]),
            "f1":        float(f1[i]),
            "support":   int(support[i]),
        }

    metrics = {
        "accuracy":         float(acc),
        "confusion_matrix": cm.tolist(),
        "per_class":        per_class,
        "class_names":      class_names,
    }

    logger.info(f"Accuracy global: {acc:.4f}")
    logger.info("\n" + classification_report(
        y_true, y_pred, target_names=class_names, zero_division=0
    ))

    return metrics


def save_metrics(metrics: dict, path: str | Path) -> None:
    """Guarda las métricas en formato JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    logger.info(f"Métricas guardadas en: {path}")


def load_metrics(path: str | Path) -> dict | None:
    """Carga métricas desde un archivo JSON. Retorna None si no existe."""
    path = Path(path)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_metrics_summary(metrics: dict) -> str:
    """Retorna un resumen legible de las métricas."""
    lines = [
        f"Accuracy global: {metrics['accuracy']:.4f}",
        "",
        f"{'Clase':<15} {'Precisión':>10} {'Recall':>8} {'F1':>8} {'Muestras':>10}",
        "-" * 55,
    ]
    for cls, vals in metrics["per_class"].items():
        lines.append(
            f"{cls:<15} {vals['precision']:>10.4f} {vals['recall']:>8.4f} "
            f"{vals['f1']:>8.4f} {vals['support']:>10}"
        )
    return "\n".join(lines)
