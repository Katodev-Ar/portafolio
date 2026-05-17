import os
import sys
import cv2
import numpy as np
from pathlib import Path
from typing import List, Union, Literal
from natsort import natsorted

# Agregar el directorio padre al path para poder importar utils
current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils import UtilJson


def cargar_lotes_imagenes(carpeta: str, subcarpetas=True) -> List[Path]:
    """Retorna una lista con las rutas completas de todos los archivos dentro de una carpeta."""
    directorio = Path(carpeta)
    archivos = []

    if subcarpetas:    
        archivos = natsorted(
            directorio.iterdir() 
            )
    else:
        archivos = natsorted(
            [f for f in directorio.iterdir() if f.is_file()]
            )
    return archivos


def load_images_cv2(image_path: Union[str, Path]) -> np.ndarray:
    """Carga la imagen principal y la marca de agua."""
    if isinstance(image_path, Path):
        image_path = str(image_path)
    img_array = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen: {image_path}")

    return img


def align_watermark(
    image: np.ndarray,
    watermark: np.ndarray,
    offset_x: int=0,
    offset_y: int=0,
    side_x: str=Literal['left', 'center', 'right'],
    side_y: str=Literal['top', 'center', 'bottom']
):
    """
    Alinea la marca de agua en la imagen con un offset dado.

    Ahora soporta posiciones parcialmente fuera de la imagen.
    La función siempre retorna coordenadas, incluso si están fuera de los bordes.

    Args:
        image (np.ndarray): Imagen original.
        watermark (np.ndarray): Marca de agua (debe incluir canal alfa).
        offset_x (int): Desplazamiento horizontal en píxeles.
        offset_y (int): Desplazamiento vertical en píxeles.
        side_x (str): 'left', 'center' o 'right' para alinear horizontalmente.
        side_y (str): 'top', 'center' o 'bottom' para alinear verticalmente.

    Returns:
        tuple[int, int]: Coordenadas (x, y) donde posicionar la marca de agua.
        Las coordenadas pueden ser negativas o fuera de la imagen.
    """
    h_img, w_img, _ = image.shape
    h_wm, w_wm, _ = watermark.shape

    # Coordenadas X (pueden ser negativas o mayores que el ancho)
    if side_x == 'left':
        x = offset_x
    elif side_x == 'center':
        x = (w_img - w_wm) // 2 + offset_x
    elif side_x == 'right':
        x = w_img - w_wm - offset_x

    # Coordenadas Y (pueden ser negativas o mayores que el alto)
    if side_y == 'top':
        y = offset_y
    elif side_y == 'center':
        y = (h_img - h_wm) // 2 + offset_y
    elif side_y == 'bottom':
        y = h_img - h_wm - offset_y

    return x, y


def find_wm_color(
    image:np.ndarray, 
    watermark:np.ndarray,
    radio=140, 
    rango=70
    ):
    """Encuentra la mejor alineación de la marca de agua minimizando la diferencia absoluta."""
    h_img, w_img, _ = image.shape
    h_wm, w_wm, _ = watermark.shape

    best_x, best_y = 0, 0
    min_diff = float("inf")

    alpha_wm = watermark[:, :, 3] / 255.0  
    centro_x = w_img // 2
    centro_y = h_img // 2
    rango_x = [centro_x-radio, centro_x-rango]
    rango_y = [centro_y-radio, centro_y-rango]

    for y in range(*rango_y):  
        for x in range(*rango_x):  
            roi = image[y:y+h_wm, x:x+w_wm, :3]  
            visible_mask = alpha_wm > 0.1  
            if np.sum(visible_mask) < (0.05 * visible_mask.size):  
                continue  

            diff = np.abs(roi.astype(np.int16) - watermark[:, :, :3].astype(np.int16))
            total_diff = np.sum(diff[visible_mask])  

            if total_diff < min_diff:
                min_diff = total_diff
                best_x, best_y = x, y

    return best_x, best_y


def generar_mascara_watermark(watermark: np.ndarray) -> np.ndarray:
    """Genera una máscara binaria de la marca de agua usando su canal alfa."""
    alpha = watermark[:, :, 3]
    mask = np.where(alpha > 10, 255, 0).astype(np.uint8)
    return mask


def remove_watermark(
    image:np.ndarray,
    watermark:np.ndarray,
    x:int,
    y:int
)-> np.ndarray:
    """
    Elimina la marca de agua de la imagen usando la ecuación de canal alfa.

    Soporta marcas de agua parcialmente fuera de los bordes de la imagen.
    Solo procesa la parte de la marca que está dentro de la imagen.
    """
    x, y = int(x), int(y)
    h_img, w_img = image.shape[:2]
    h_wm, w_wm, _ = watermark.shape

    # Calcular la región de superposición (clipping)
    # Coordenadas en la imagen
    x_start_img = max(0, x)
    y_start_img = max(0, y)
    x_end_img = min(w_img, x + w_wm)
    y_end_img = min(h_img, y + h_wm)

    # Coordenadas en la marca de agua (qué parte usar)
    x_start_wm = max(0, -x)
    y_start_wm = max(0, -y)
    x_end_wm = x_start_wm + (x_end_img - x_start_img)
    y_end_wm = y_start_wm + (y_end_img - y_start_img)

    # Si no hay superposición, no hacer nada
    if x_start_img >= x_end_img or y_start_img >= y_end_img:
        return image

    # Extraer solo la parte que se superpone
    roi = image[y_start_img:y_end_img, x_start_img:x_end_img].astype(np.float32)
    wm_cropped = watermark[y_start_wm:y_end_wm, x_start_wm:x_end_wm].astype(np.float32)

    # Aplicar la ecuación de eliminación de marca de agua
    alpha = wm_cropped[:, :, 3] / 255.0
    alpha = alpha[:, :, np.newaxis]
    alpha_safe = np.clip(1 - alpha, 1e-5, 1)
    new_region = (roi / alpha_safe) - (wm_cropped[:, :, :3] * (alpha / alpha_safe))
    new_region = np.clip(new_region, 0, 255).astype(np.uint8)

    # Escribir de vuelta solo la región procesada
    image[y_start_img:y_end_img, x_start_img:x_end_img, :3] = new_region
    return image


def guardar(image_path: Path, result: np.ndarray, output_folder: Path):
    """Guarda la imagen procesada en la misma estructura dentro la carpeta de salida."""
    if not isinstance(image_path, Path):
        image_path = Path(image_path)
    output_folder.mkdir(parents=True, exist_ok=True)

    output_image = output_folder / image_path.name
    
    # Codificar la imagen en memoria
    ext = output_image.suffix  # Obtener la extensión del archivo (.png, .jpg, etc.)
    success, encoded_image = cv2.imencode(ext, result)

    if not success:
        raise ValueError(f"No se pudo codificar la imagen para guardarla en: {output_image}")

    # Guardar usando numpy para evitar problemas con caracteres especiales
    output_image.with_suffix(ext).write_bytes(encoded_image.tobytes())

    return output_image


def load_positions(site_name: str = 'newtoki', position: str = 'pos_1') -> dict:
    """
    Carga las posiciones de marcas de agua desde el archivo JSON.

    Args:
        site_name: Nombre del sitio web (ej: 'newtoki', 'manganelo')
        position: Nombre de la posición (ej: 'pos_1', 'pos_2', etc.)

    Returns:
        dict: Diccionario con los parámetros de posición (offset_x, offset_y, side_x, side_y)

    Ejemplo:
        >>> pos = load_positions('newtoki', 'pos_4')
        >>> coords = align_watermark(img, wm, **pos)
    """
    positions_path = Path(current_dir) / 'wm_positions.json'
    positions_file = UtilJson(positions_path)

    site_positions = positions_file.get(site_name, {})
    if not site_positions:
        raise ValueError(f"No se encontraron posiciones para el sitio: {site_name}")

    position_data = site_positions.get(position)
    if not position_data:
        raise ValueError(f"No se encontró la posición '{position}' para el sitio '{site_name}'")

    return position_data


if __name__ == "__main__":
    def mostrar(img):
        cv2.imshow('Mi Imagen', img)
        cv2.waitKey(0)  # Espera hasta que presiones una tecla
        cv2.destroyAllWindows()


    img = load_images_cv2(r'c:\Users\Felix\Downloads\Image Picka\32 urek\1 - CiEhJNkTQMXF.jpg')
    wm = load_images_cv2(r'c:\Users\Felix\Desktop\Python\watermark\SmartStitch\marcas\468 V2\color.png')

    # Cargar posiciones usando la función helper
    pos = load_positions('newtoki', 'pos_4')
    coor = align_watermark(img, wm, **pos)
    img_wmr = remove_watermark(img, wm, *coor)

    mostrar(img_wmr)