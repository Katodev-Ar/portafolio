# =============================================================================
# dataset_loader.py — Carga y escaneo del dataset
# =============================================================================

import logging
from pathlib import Path
from typing import Tuple

import torch
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torchvision import transforms
from PIL import Image

from utils.config import (
    CLASSES, CLASS_TO_IDX, DATASET_PATH,
    IMAGE_SIZE, BATCH_SIZE, VAL_SPLIT, RANDOM_SEED,
)
from utils.image_utils import get_image_paths, is_valid_image
from src.preprocessing import build_transform
from src.augmentation import build_augmentation_transform

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataset personalizado
# ---------------------------------------------------------------------------

class BalloonDataset(Dataset):
    """
    Dataset de globos de manga organizado en subcarpetas por clase.

    Estructura esperada:
        dataset/
            dialogo/   ← imagen_001.png, ...
            grito/
            ...
    """

    def __init__(self, samples: list[Tuple[Path, int]],
                 transform=None):
        self.samples   = samples   # Lista de (ruta_imagen, idx_clase)
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        img_path, label = self.samples[idx]
        try:
            img = Image.open(img_path).convert("RGB")
        except Exception as e:
            logger.warning(f"Error abriendo {img_path}: {e}. Usando imagen negra.")
            img = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (0, 0, 0))

        if self.transform:
            img = self.transform(img)

        return img, label


# ---------------------------------------------------------------------------
# Escáner de dataset
# ---------------------------------------------------------------------------

def scan_dataset(dataset_path: Path | None = None) -> dict[str, list[Path]]:
    """
    Escanea el directorio del dataset y retorna un dict:
        { nombre_clase: [lista de rutas de imágenes válidas] }

    Solo incluye clases definidas en config.CLASSES.
    """
    dataset_path = dataset_path or DATASET_PATH
    result: dict[str, list[Path]] = {}

    for cls in CLASSES:
        cls_dir = dataset_path / cls
        if cls_dir.exists() and cls_dir.is_dir():
            paths = [
                p for p in get_image_paths(cls_dir)
                if is_valid_image(p)
            ]
            result[cls] = paths
            logger.info(f"  [{cls}] → {len(paths)} imágenes")
        else:
            result[cls] = []
            logger.warning(f"  [{cls}] → carpeta no encontrada: {cls_dir}")

    total = sum(len(v) for v in result.values())
    logger.info(f"Total imágenes en dataset: {total}")
    return result


def get_dataset_stats(dataset_path: Path | None = None) -> dict:
    """Retorna estadísticas del dataset para mostrar en la UI."""
    scanned = scan_dataset(dataset_path)
    total   = sum(len(v) for v in scanned.values())
    stats   = {cls: len(paths) for cls, paths in scanned.items()}
    stats["__total__"] = total
    return stats


# ---------------------------------------------------------------------------
# Construcción de splits train / val
# ---------------------------------------------------------------------------

def build_splits(dataset_path: Path | None = None,
                 val_split: float = VAL_SPLIT,
                 seed: int = RANDOM_SEED
                 ) -> Tuple[list, list]:
    """
    Divide el dataset en train y validación de forma estratificada.

    Returns:
        (train_samples, val_samples) — listas de (Path, int)
    """
    import random
    random.seed(seed)

    scanned  = scan_dataset(dataset_path)
    train_s, val_s = [], []

    for cls, paths in scanned.items():
        if not paths:
            continue
        label = CLASS_TO_IDX[cls]
        random.shuffle(paths)
        n_val = max(1, int(len(paths) * val_split))
        val_s.extend(  [(p, label) for p in paths[:n_val]])
        train_s.extend([(p, label) for p in paths[n_val:]])

    logger.info(f"Split — Train: {len(train_s)} | Val: {len(val_s)}")
    return train_s, val_s


# ---------------------------------------------------------------------------
# DataLoaders listos para entrenar
# ---------------------------------------------------------------------------

def build_dataloaders(dataset_path: Path | None = None,
                      batch_size: int = BATCH_SIZE,
                      num_workers: int = 0,
                      use_weighted_sampler: bool = True
                      ) -> Tuple[DataLoader, DataLoader]:
    """
    Construye DataLoaders de entrenamiento y validación.

    Args:
        use_weighted_sampler: Balancea clases desiguales automáticamente.

    Returns:
        (train_loader, val_loader)
    """
    train_samples, val_samples = build_splits(dataset_path)

    train_transform = build_augmentation_transform()
    val_transform   = build_transform()

    train_ds = BalloonDataset(train_samples, transform=train_transform)
    val_ds   = BalloonDataset(val_samples,   transform=val_transform)

    # Sampler ponderado para balancear clases en train
    train_loader_kwargs = dict(
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )

    if use_weighted_sampler and train_samples:
        labels  = [s[1] for s in train_samples]
        counts  = torch.bincount(torch.tensor(labels), minlength=len(CLASSES))
        weights = 1.0 / counts.float().clamp(min=1)
        sample_weights = torch.tensor([weights[l] for l in labels])
        sampler = WeightedRandomSampler(sample_weights, len(sample_weights))
        train_loader_kwargs["sampler"] = sampler
    else:
        train_loader_kwargs["shuffle"] = True

    train_loader = DataLoader(train_ds, **train_loader_kwargs)
    val_loader   = DataLoader(val_ds,
                              batch_size=batch_size,
                              shuffle=False,
                              num_workers=num_workers,
                              pin_memory=torch.cuda.is_available())

    return train_loader, val_loader
