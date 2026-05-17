"""
WatermarkRemove - Módulo para eliminar marcas de agua de imágenes

Este módulo proporciona herramientas para detectar y eliminar marcas de agua
de imágenes de manhwa/manga.

Submódulos:
    - ui: Componentes de interfaz gráfica
    - wm_remove: Funciones de procesamiento de imágenes

Ejemplo:
    >>> from WatermarkRemove import load_positions, remove_watermark, align_watermark
    >>> pos = load_positions('newtoki', 'pos_4')
    >>> coords = align_watermark(img, watermark, **pos)
    >>> result = remove_watermark(img, watermark, *coords)
"""

from .wm_remove import (
    load_positions,
    load_images_cv2,
    align_watermark,
    remove_watermark,
    find_wm_color,
    generar_mascara_watermark,
    guardar,
    cargar_lotes_imagenes
)

__version__ = '4.0.0'
__author__ = 'Daylor'

__all__ = [
    'load_positions',
    'load_images_cv2',
    'align_watermark',
    'remove_watermark',
    'find_wm_color',
    'generar_mascara_watermark',
    'guardar',
    'cargar_lotes_imagenes'
]
