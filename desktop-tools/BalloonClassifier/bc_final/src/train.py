# =============================================================================
# train.py — Bucle de entrenamiento con callbacks para la UI
# =============================================================================

import logging
import time
from pathlib import Path
from typing import Callable

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from utils.config import (
    EPOCHS, LEARNING_RATE, WEIGHT_DECAY,
    LR_PATIENCE, LR_FACTOR, LR_MIN,
    EARLY_STOP_PATIENCE, MODEL_FILE,
)
from src.model import build_model, save_model, get_device

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Callbacks del entrenamiento
# ---------------------------------------------------------------------------

class TrainingCallbacks:
    """
    Interfaz de callbacks para comunicar el progreso de entrenamiento
    a la UI sin acoplar el código de entrenamiento con PyQt.
    """
    def on_epoch_end(self, epoch: int, train_loss: float,
                     val_loss: float, val_acc: float) -> None: ...

    def on_batch_end(self, batch: int, total_batches: int,
                     loss: float) -> None: ...

    def on_training_end(self, best_val_acc: float, best_epoch: int) -> None: ...

    def on_error(self, error: str) -> None: ...

    def should_stop(self) -> bool:
        """La UI puede solicitar detención anticipada."""
        return False


# ---------------------------------------------------------------------------
# Bucle principal de entrenamiento
# ---------------------------------------------------------------------------

class Trainer:
    """
    Encapsula el ciclo completo de entrenamiento de PyTorch.

    Características:
        - Optimizador AdamW con scheduler ReduceLROnPlateau
        - Early stopping configurable
        - Guardado automático del mejor modelo
        - Callbacks para actualizar la UI en tiempo real
    """

    def __init__(self,
                 train_loader: DataLoader,
                 val_loader:   DataLoader,
                 epochs:        int   = EPOCHS,
                 learning_rate: float = LEARNING_RATE,
                 weight_decay:  float = WEIGHT_DECAY,
                 callbacks:     TrainingCallbacks | None = None,
                 save_path:     Path | str = MODEL_FILE):

        self.train_loader  = train_loader
        self.val_loader    = val_loader
        self.epochs        = epochs
        self.learning_rate = learning_rate
        self.weight_decay  = weight_decay
        self.callbacks     = callbacks or TrainingCallbacks()
        self.save_path     = Path(save_path)

        self.device = get_device()
        self.model  = build_model().to(self.device)

        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay,
        )
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode="max",
            patience=LR_PATIENCE, factor=LR_FACTOR, min_lr=LR_MIN,
        )
        self.criterion = nn.CrossEntropyLoss()

        # Histórico de métricas por epoch
        self.history = {
            "train_loss": [],
            "val_loss":   [],
            "val_acc":    [],
        }

        self._best_val_acc  = 0.0
        self._best_epoch    = 0
        self._no_improve    = 0

    # -----------------------------------------------------------------------

    def train(self) -> dict:
        """
        Ejecuta el entrenamiento completo.

        Returns:
            Diccionario con el historial de pérdidas y accuracy.
        """
        logger.info(f"Iniciando entrenamiento — {self.epochs} epochs")
        logger.info(f"Dispositivo: {self.device}")
        logger.info(f"LR: {self.learning_rate} | WD: {self.weight_decay}")

        for epoch in range(1, self.epochs + 1):

            # Verificar si la UI solicitó parar
            if self.callbacks.should_stop():
                logger.info("Entrenamiento detenido por el usuario.")
                break

            t0 = time.time()
            train_loss = self._train_epoch(epoch)
            val_loss, val_acc = self._validate_epoch()
            elapsed = time.time() - t0

            self.history["train_loss"].append(train_loss)
            self.history["val_loss"].append(val_loss)
            self.history["val_acc"].append(val_acc)

            self.scheduler.step(val_acc)

            logger.info(
                f"Epoch {epoch:3d}/{self.epochs} | "
                f"Loss train: {train_loss:.4f} | "
                f"Loss val: {val_loss:.4f} | "
                f"Acc val: {val_acc:.4f} | "
                f"LR: {self._current_lr():.2e} | "
                f"t: {elapsed:.1f}s"
            )

            # Callback a la UI
            self.callbacks.on_epoch_end(epoch, train_loss, val_loss, val_acc)

            # Guardar mejor modelo
            if val_acc > self._best_val_acc:
                self._best_val_acc = val_acc
                self._best_epoch   = epoch
                self._no_improve   = 0
                save_model(
                    self.model, self.save_path,
                    extra={
                        "best_epoch":   epoch,
                        "best_val_acc": val_acc,
                        "history":      self.history,
                    },
                )
                logger.info(f"  ✓ Nuevo mejor modelo guardado (acc={val_acc:.4f})")
            else:
                self._no_improve += 1

            # Early stopping
            if self._no_improve >= EARLY_STOP_PATIENCE:
                logger.info(
                    f"Early stopping: {EARLY_STOP_PATIENCE} epochs sin mejora."
                )
                break

        self.callbacks.on_training_end(self._best_val_acc, self._best_epoch)
        logger.info(
            f"Entrenamiento finalizado. "
            f"Mejor acc: {self._best_val_acc:.4f} (epoch {self._best_epoch})"
        )
        return self.history

    # -----------------------------------------------------------------------

    def _train_epoch(self, epoch: int) -> float:
        """Ejecuta una epoch de entrenamiento. Retorna la pérdida media."""
        self.model.train()
        total_loss = 0.0
        total_batches = len(self.train_loader)

        for batch_idx, (images, labels) in enumerate(self.train_loader, 1):
            images = images.to(self.device, non_blocking=True)
            labels = labels.to(self.device, non_blocking=True)

            self.optimizer.zero_grad(set_to_none=True)
            outputs = self.model(images)
            loss    = self.criterion(outputs, labels)
            loss.backward()

            # Gradient clipping para estabilidad
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            batch_loss  = loss.item()
            total_loss += batch_loss

            # Actualizar UI cada 5 batches o en el último
            if batch_idx % 5 == 0 or batch_idx == total_batches:
                self.callbacks.on_batch_end(batch_idx, total_batches, batch_loss)

        return total_loss / max(total_batches, 1)

    def _validate_epoch(self) -> tuple[float, float]:
        """Ejecuta validación. Retorna (val_loss, val_accuracy)."""
        self.model.eval()
        total_loss    = 0.0
        correct       = 0
        total_samples = 0

        with torch.no_grad():
            for images, labels in self.val_loader:
                images = images.to(self.device, non_blocking=True)
                labels = labels.to(self.device, non_blocking=True)

                outputs = self.model(images)
                loss    = self.criterion(outputs, labels)

                total_loss    += loss.item()
                preds          = outputs.argmax(dim=1)
                correct       += (preds == labels).sum().item()
                total_samples += labels.size(0)

        avg_loss = total_loss / max(len(self.val_loader), 1)
        accuracy = correct / max(total_samples, 1)
        return avg_loss, accuracy

    def _current_lr(self) -> float:
        """Retorna el learning rate actual del optimizador."""
        return self.optimizer.param_groups[0]["lr"]
