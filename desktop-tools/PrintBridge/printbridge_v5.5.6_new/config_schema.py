"""
config_schema.py — PrintBridge v5.5.0
Mejora 5 del Roadmap Técnico: Configuración tipada con Pydantic BaseModel.

Ventajas sobre el dict genérico anterior:
  - Tipos validados en carga: port="siete-mil" → ValidationError con mensaje claro
  - Valores por defecto centralizados y documentados en un solo lugar
  - Autocompletado en IDEs para todos los campos de configuración
  - Validadores custom (server_name sin HTML, extensiones en minúsculas)
  - Retrocompatibilidad total: AppConfig.to_dict() devuelve el mismo dict
    que load_config() — el resto del código no necesita cambios

INTEGRACIÓN:
    La carga tipada se usa en load_config() de config.py cuando Pydantic
    está disponible. Si no está instalado, load_config() sigue funcionando
    con el dict genérico anterior (degradación graciosa).

    Para acceso tipado explícito desde cualquier módulo:
        from config_schema import AppConfig, load_typed_config
        cfg = load_typed_config()
        print(cfg.port)          # int, nunca str
        print(cfg.server_name)   # str validado sin caracteres HTML
"""

from __future__ import annotations

import re
from typing import List, Optional

try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    try:
        # Pydantic v1 fallback
        from pydantic import BaseModel, Field, validator as field_validator  # type: ignore
        PYDANTIC_AVAILABLE = True
    except ImportError:
        PYDANTIC_AVAILABLE = False


# ── Modelo tipado ────────────────────────────────────────────────────────────

if PYDANTIC_AVAILABLE:

    class AppConfig(BaseModel):
        """
        Configuración completa de PrintBridge con tipos validados.

        Todos los campos tienen valores por defecto seguros.
        La validación ocurre en la construcción — un config.json corrupto
        lanza ValidationError con un mensaje descriptivo en lugar de un
        KeyError/TypeError críptico en algún punto aleatorio del código.
        """

        # ── Servidor ──────────────────────────────────────────────────────
        port: int = Field(
            default=7878,
            ge=1, le=65535,
            description="Puerto TCP del servidor HTTP/HTTPS",
        )
        server_name: str = Field(
            default="PrintBridge",
            max_length=64,
            description="Nombre visible en la UI web y en el tray icon",
        )
        start_minimized: bool = Field(
            default=False,
            description="Iniciar con la ventana principal oculta (solo tray)",
        )

        # ── Seguridad ─────────────────────────────────────────────────────
        pin: str = Field(
            default="",
            description="Hash PBKDF2 del PIN, o '' para acceso sin contraseña",
        )

        # ── Impresión ─────────────────────────────────────────────────────
        printer: str = Field(
            default="",
            description="Nombre de la impresora por defecto ('' = impresora del sistema)",
        )
        allowed_extensions: List[str] = Field(
            default_factory=lambda: [
                "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
                "txt", "odt", "ods", "odp", "rtf",
                "jpg", "jpeg", "png", "bmp", "tiff", "tif", "webp", "gif",
            ],
            description="Extensiones de archivo permitidas para impresión",
        )
        print_timeouts: dict = Field(
            default_factory=dict,
            description="Timeouts por extensión en segundos (Mejora 1). "
                        "Vacío = usar defaults de print_worker.py",
        )

        # ── Cola e historial ──────────────────────────────────────────────
        max_queue_size: int = Field(
            default=20,
            ge=1, le=200,
            description="Máximo de trabajos en cola simultáneos",
        )
        max_history: int = Field(
            default=100,
            ge=10, le=10_000,
            description="Máximo de entradas en el historial de impresión",
        )

        # ── Tokens ────────────────────────────────────────────────────────
        token_expiry_days: int = Field(
            default=90,
            ge=1, le=3650,
            description="Días hasta que un token de dispositivo expira",
        )

        # ── Clave interna de compatibilidad ───────────────────────────────
        _test_key_v510: Optional[str] = None

        # ── Validadores ───────────────────────────────────────────────────

        @field_validator("server_name")
        @classmethod
        def name_no_html(cls, v: str) -> str:
            """A-02 + S-01: server_name no puede contener caracteres HTML peligrosos."""
            v = v.strip()
            if not v:
                return "PrintBridge"
            if len(v) > 64:
                raise ValueError(f"server_name demasiado largo ({len(v)} chars, máx 64)")
            if not re.fullmatch(r"[\w\s\-\.]+", v):
                raise ValueError(
                    "server_name contiene caracteres no permitidos. "
                    "Usar solo letras, números, espacios, guiones y puntos."
                )
            return v

        @field_validator("allowed_extensions")
        @classmethod
        def extensions_lowercase(cls, v: List[str]) -> List[str]:
            """Normalizar extensiones a minúsculas y eliminar duplicados."""
            seen = set()
            result = []
            for ext in v:
                ext_lower = ext.lower().lstrip(".")
                if ext_lower not in seen:
                    seen.add(ext_lower)
                    result.append(ext_lower)
            return result

        @field_validator("port")
        @classmethod
        def port_not_reserved(cls, v: int) -> int:
            """Advertir si el puerto está en el rango reservado (< 1024)."""
            if v < 1024:
                import warnings
                warnings.warn(
                    f"Puerto {v} está en el rango reservado (<1024). "
                    "Puede requerir privilegios de administrador.",
                    UserWarning,
                    stacklevel=2,
                )
            return v

        # ── Serialización ─────────────────────────────────────────────────

        def to_dict(self) -> dict:
            """
            Serializa a dict compatible con el formato de config.json anterior.
            Mantiene retrocompatibilidad: el dict resultante es idéntico al que
            producía load_config() antes de la Mejora 5.
            """
            d = self.model_dump(exclude_none=True)
            # Eliminar campo interno de Pydantic
            d.pop("_test_key_v510", None)
            return d

        model_config = {"extra": "allow"}   # tolerar claves futuras/desconocidas

else:
    # Stub cuando Pydantic no está instalado — mantiene la interfaz pública
    class AppConfig:  # type: ignore
        """Stub de AppConfig cuando Pydantic no está disponible."""

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def to_dict(self) -> dict:
            return {k: v for k, v in self.__dict__.items()
                    if not k.startswith("_")}


# ── Función de carga tipada ──────────────────────────────────────────────────

def load_typed_config() -> "AppConfig":
    """
    Carga config.json y retorna un AppConfig validado.

    En caso de error de validación (tipos incorrectos en config.json),
    loga el error y retorna un AppConfig con valores por defecto —
    comportamiento seguro "fail-open" para no romper el servidor al arrancar.

    Ejemplo:
        cfg = load_typed_config()
        port = cfg.port          # int garantizado
        name = cfg.server_name   # str validado
    """
    from config import load_config
    import logging
    _log = logging.getLogger("PrintBridge.Config")

    raw = load_config()

    if not PYDANTIC_AVAILABLE:
        _log.debug("Pydantic no disponible — usando config sin validación de tipos")
        obj = AppConfig(**raw)
        return obj

    try:
        return AppConfig(**raw)
    except Exception as e:
        _log.warning(
            f"config.json tiene valores inválidos: {e}. "
            "Usando configuración por defecto para los campos afectados."
        )
        # Intentar con solo los campos válidos
        safe = {}
        for field_name, field_info in AppConfig.model_fields.items():
            if field_name in raw:
                try:
                    AppConfig(**{field_name: raw[field_name]})
                    safe[field_name] = raw[field_name]
                except Exception:
                    _log.warning(f"Campo '{field_name}' ignorado por valor inválido: {raw[field_name]!r}")
        try:
            return AppConfig(**safe)
        except Exception:
            return AppConfig()
