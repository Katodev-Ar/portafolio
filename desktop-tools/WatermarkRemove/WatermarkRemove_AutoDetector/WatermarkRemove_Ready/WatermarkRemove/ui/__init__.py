"""
WatermarkRemove.ui - Módulo de interfaz gráfica para Watermark Remover

Este módulo contiene todos los componentes de UI para el removedor de marcas de agua.
"""

from .watermark_tab import WatermarkTab
from .image_viewer import ImageViewer
from .slideshow_viewer import SlideshowViewer
from .position_editor import PositionEditor
from .auto_position_detector import AutoPositionDetector

__version__ = '1.0.0'
__all__ = ['WatermarkTab', 'ImageViewer', 'SlideshowViewer', 'PositionEditor', 'AutoPositionDetector']
