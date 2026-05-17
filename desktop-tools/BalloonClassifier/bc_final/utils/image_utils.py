# =============================================================================
# image_utils.py — Utilidades de imagen
# =============================================================================

import cv2
import numpy as np
from PIL import Image
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"}


def load_image_pil(path: str | Path) -> Image.Image | None:
    """Carga una imagen como PIL Image. Retorna None si falla."""
    try:
        img = Image.open(path)
        return img.convert("RGB")
    except Exception as e:
        logger.error(f"Error cargando imagen {path}: {e}")
        return None


def load_image_cv2(path: str | Path) -> np.ndarray | None:
    """Carga una imagen como array NumPy BGR (OpenCV). Retorna None si falla."""
    try:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError("cv2.imread retornó None")
        return img
    except Exception as e:
        logger.error(f"Error cargando imagen {path}: {e}")
        return None


def pil_to_cv2(img: Image.Image) -> np.ndarray:
    """Convierte PIL Image (RGB) a NumPy array BGR."""
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def cv2_to_pil(img: np.ndarray) -> Image.Image:
    """Convierte NumPy array BGR a PIL Image RGB."""
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def is_valid_image(path: str | Path) -> bool:
    """Verifica que el archivo sea una imagen válida y soportada."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTS:
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def get_image_paths(folder: str | Path) -> list[Path]:
    """Retorna todas las rutas de imágenes válidas dentro de una carpeta."""
    folder = Path(folder)
    paths = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    return sorted(paths)


def resize_image(img: Image.Image, size: int) -> Image.Image:
    """Redimensiona una imagen PIL a (size, size) manteniendo calidad."""
    return img.resize((size, size), Image.LANCZOS)


def enhance_contrast(img: Image.Image, threshold: float = 0.1) -> Image.Image:
    """
    Mejora el contraste de imágenes muy planas (baja desviación estándar).
    Se aplica CLAHE sobre la imagen para preservar detalles locales.
    """
    img_cv = pil_to_cv2(img)
    gray   = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
    std    = gray.std() / 255.0

    if std < threshold:
        lab   = cv2.cvtColor(img_cv, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l     = clahe.apply(l)
        lab   = cv2.merge([l, a, b])
        img_cv = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        logger.debug(f"CLAHE aplicado (std={std:.3f})")

    return cv2_to_pil(img_cv)


def visualize_prediction(img: Image.Image, class_name: str,
                         confidence: float, probs: dict[str, float]) -> Image.Image:
    """
    Dibuja la predicción sobre la imagen usando OpenCV.
    Retorna una PIL Image con el overlay.
    """
    img_cv = pil_to_cv2(img)
    h, w   = img_cv.shape[:2]

    # Fondo semitransparente para el texto
    overlay = img_cv.copy()
    cv2.rectangle(overlay, (0, 0), (w, 50), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, img_cv, 0.4, 0, img_cv)

    text = f"{class_name.upper()}  {confidence:.1%}"
    cv2.putText(img_cv, text, (10, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

    return cv2_to_pil(img_cv)
