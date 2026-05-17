"""
smart_stitch_logic.py - Lógica de Smart Stitcher para WatermarkRemove

Combina múltiples imágenes de una carpeta en una sola imagen larga (stitch),
luego la corta inteligentemente en partes de altura aproximada buscando
líneas blancas/en blanco para hacer cortes limpios.
"""
import os
import sys
import subprocess
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from natsort import natsorted


class SmartStitcher:
    """
    Une imágenes de una carpeta y las corta en páginas de altura aproximada,
    buscando cortes en zonas blancas para no cortar en medio del contenido.
    """

    SUPPORTED_FORMATS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.jfif')

    def __init__(self, console_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            console_callback: función para emitir mensajes de log (ej: print o señal Qt)
        """
        self.log = console_callback or print

    # ------------------------------------------------------------------
    # Entrada principal
    # ------------------------------------------------------------------

    def process_folder(
        self,
        folder: str,
        target_width: int = 720,
        target_height: int = 15000,
        sensitivity: int = 90,
        post_process_config: Optional[dict] = None,
    ):
        """
        Procesa todas las imágenes de una carpeta:
        1. Las une en una tira larga.
        2. Las recorta en páginas inteligentes.
        3. (Opcional) Ejecuta post-proceso externo.

        Args:
            folder: Ruta a la carpeta con imágenes.
            target_width: Ancho al que redimensionar las imágenes (px).
            target_height: Altura máxima aproximada de cada página de salida (px).
            sensitivity: 1-100, qué tan estricto es el buscador de líneas blancas.
            post_process_config: dict con {'enabled', 'app_path', 'args'} para post-proceso.
        """
        folder = Path(folder)
        if not folder.exists():
            raise FileNotFoundError(f"La carpeta no existe: {folder}")

        # 1. Cargar imágenes
        image_files = self._load_image_list(folder)
        if not image_files:
            raise ValueError("No se encontraron imágenes en la carpeta.")

        self.log(f"📂 Carpeta: {folder.name}")
        self.log(f"🖼️  Imágenes encontradas: {len(image_files)}")

        # 2. Stitch (unir)
        self.log("⏳ Uniendo imágenes...")
        stitched = self._stitch_images(image_files, target_width)
        self.log(f"✅ Tira unida: {stitched.shape[1]}x{stitched.shape[0]} px")

        # 3. Carpeta de salida: stitched
        stitched_dir = folder / "stitched"
        stitched_dir.mkdir(exist_ok=True)
        stitched_path = stitched_dir / "stitched_full.jpg"
        self._save_image(stitched, stitched_path)
        self.log(f"💾 Tira completa guardada en: {stitched_path.name}")

        # 4. Cortar en páginas
        self.log(f"✂️  Cortando en páginas (~{target_height}px, sensibilidad={sensitivity}%)...")
        pages = self._smart_cut(stitched, target_height, sensitivity)
        self.log(f"📄 Páginas generadas: {len(pages)}")

        # 5. Guardar páginas cortadas
        output_dir = folder / "output"
        output_dir.mkdir(exist_ok=True)
        for i, page in enumerate(pages, 1):
            out_path = output_dir / f"page_{i:03d}.jpg"
            self._save_image(page, out_path)
            self.log(f"   Guardada: {out_path.name} ({page.shape[1]}x{page.shape[0]}px)")

        self.log(f"\n✅ Proceso completado. {len(pages)} páginas en: {output_dir}")

        # 6. Post-proceso opcional
        if post_process_config and post_process_config.get("enabled"):
            self._run_post_process(post_process_config, stitched_dir, output_dir)

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _load_image_list(self, folder: Path):
        """Retorna lista ordenada de archivos de imagen en la carpeta."""
        files = [
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_FORMATS
        ]
        return natsorted(files, key=lambda f: f.name)

    def _load_image(self, path: Path) -> np.ndarray:
        """Carga una imagen con soporte para rutas con caracteres especiales."""
        img_array = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"No se pudo cargar: {path}")
        return img

    def _save_image(self, img: np.ndarray, path: Path, quality: int = 95):
        """Guarda una imagen con soporte para rutas con caracteres especiales."""
        ext = path.suffix.lower()
        params = [cv2.IMWRITE_JPEG_QUALITY, quality] if ext in ('.jpg', '.jpeg') else []
        success, encoded = cv2.imencode(ext, img, params)
        if not success:
            raise IOError(f"No se pudo codificar la imagen: {path}")
        path.write_bytes(encoded.tobytes())

    def _stitch_images(self, image_files: list, target_width: int) -> np.ndarray:
        """Une todas las imágenes verticalmente, redimensionando al ancho objetivo."""
        strips = []
        for f in image_files:
            try:
                img = self._load_image(f)
                # Redimensionar al ancho objetivo manteniendo proporción
                h, w = img.shape[:2]
                if w != target_width:
                    new_h = int(h * target_width / w)
                    img = cv2.resize(img, (target_width, new_h), interpolation=cv2.INTER_LANCZOS4)
                strips.append(img)
            except Exception as e:
                self.log(f"⚠️ Saltando {f.name}: {e}")

        if not strips:
            raise ValueError("No se pudieron cargar imágenes válidas.")

        return np.vstack(strips)

    def _smart_cut(self, image: np.ndarray, target_height: int, sensitivity: int) -> list:
        """
        Corta la imagen larga en páginas de ~target_height px.
        Busca filas blancas/claras cerca del punto de corte para hacer
        cortes limpios entre viñetas.

        sensitivity: 1-100 (100 = solo corta en filas completamente blancas,
                             1  = acepta casi cualquier fila clara)
        """
        total_h = image.shape[0]
        pages = []
        y_start = 0

        # Umbral de blancura: qué tan clara debe ser una fila para ser candidata a corte
        # sensitivity=90 → umbral=230, sensitivity=50 → umbral=200, sensitivity=10 → umbral=160
        brightness_threshold = int(160 + (sensitivity / 100) * 90)

        # Margen de búsqueda: buscar corte dentro del ±15% de target_height
        search_margin = int(target_height * 0.15)

        while y_start < total_h:
            ideal_cut = y_start + target_height

            if ideal_cut >= total_h:
                # Última página: tomar lo que queda
                pages.append(image[y_start:total_h])
                break

            # Buscar la mejor línea de corte en el rango [ideal_cut - margin, ideal_cut + margin]
            search_start = max(y_start + 100, ideal_cut - search_margin)
            search_end = min(total_h - 1, ideal_cut + search_margin)

            best_y = self._find_best_cut(image, search_start, search_end, brightness_threshold)

            if best_y is None:
                # No se encontró línea limpia: cortar en el punto ideal
                best_y = ideal_cut

            pages.append(image[y_start:best_y])
            y_start = best_y

        return pages

    def _find_best_cut(
        self,
        image: np.ndarray,
        y_start: int,
        y_end: int,
        brightness_threshold: int,
    ) -> Optional[int]:
        """
        Busca la fila más blanca/clara en el rango [y_start, y_end].
        Retorna el índice de fila óptimo, o None si no hay candidato claro.
        """
        region = image[y_start:y_end]
        if region.shape[0] == 0:
            return None

        # Calcular el brillo medio de cada fila (en escala de grises)
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        row_means = gray.mean(axis=1)  # Media de brillo por fila

        # Buscar filas que superen el umbral de brillo
        bright_rows = np.where(row_means >= brightness_threshold)[0]

        if len(bright_rows) == 0:
            # Ninguna fila supera el umbral: usar la más clara
            best_local = int(np.argmax(row_means))
        else:
            # Preferir la fila brillante más cercana al centro del rango de búsqueda
            center = (y_end - y_start) // 2
            best_local = int(bright_rows[np.argmin(np.abs(bright_rows - center))])

        return y_start + best_local

    def _run_post_process(self, config: dict, stitched_dir: Path, output_dir: Path):
        """Ejecuta una aplicación externa de post-proceso (ej: waifu2x)."""
        app_path = config.get("app_path", "").strip()
        args_template = config.get("args", "").strip()

        if not app_path or not Path(app_path).exists():
            self.log("⚠️ Post-proceso: ejecutable no encontrado, omitiendo.")
            return

        processed_dir = output_dir.parent / "processed"
        processed_dir.mkdir(exist_ok=True)

        args = args_template.replace("[stitched]", str(output_dir))
        args = args.replace("[processed]", str(processed_dir))

        cmd = f'"{app_path}" {args}'
        self.log(f"🔧 Post-proceso: {cmd}")

        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                self.log("✅ Post-proceso completado.")
            else:
                self.log(f"⚠️ Post-proceso terminó con código {result.returncode}")
                if result.stderr:
                    self.log(f"   stderr: {result.stderr[:300]}")
        except subprocess.TimeoutExpired:
            self.log("❌ Post-proceso: timeout excedido (10 min).")
        except Exception as e:
            self.log(f"❌ Post-proceso error: {e}")
