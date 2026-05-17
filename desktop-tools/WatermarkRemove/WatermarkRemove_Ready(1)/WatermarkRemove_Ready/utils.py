"""
utils.py - Utilidades generales para WatermarkRemove
Incluye UtilJson: clase para leer/escribir archivos JSON fácilmente.
"""
import json
from pathlib import Path


class UtilJson:
    """
    Clase para manejar archivos JSON de configuración.
    Soporta lectura, escritura, y operaciones de get/set sobre claves.
    """

    def __init__(self, path):
        self.path = Path(path)

    def read(self) -> dict:
        """Lee y retorna el contenido del archivo JSON. Si no existe, retorna {}."""
        if not self.path.exists():
            return {}
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def write(self, data: dict):
        """Escribe el diccionario completo en el archivo JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get(self, key: str, default=None):
        """Retorna el valor de una clave del JSON."""
        data = self.read()
        return data.get(key, default)

    def set(self, key: str, value):
        """Establece el valor de una clave y guarda el archivo."""
        data = self.read()
        data[key] = value
        self.write(data)

    def delete(self, key: str):
        """Elimina una clave del JSON y guarda el archivo."""
        data = self.read()
        if key in data:
            del data[key]
            self.write(data)
