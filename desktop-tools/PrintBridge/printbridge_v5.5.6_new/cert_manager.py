"""
cert_manager.py — PrintBridge v5.5.0
Mejora 2 del Roadmap Técnico: HTTPS automático en el primer arranque.

Genera un certificado TLS autofirmado (RSA-2048, SHA-256, 10 años) en el
primer arranque sin intervención del usuario, usando la librería `cryptography`
que ya es una dependencia transitiva de varios paquetes del proyecto.

La generación ocurre en un thread background para no bloquear la splash screen.
El certificado se guarda en:
    <BASE_DIR>/data/cert.pem  — certificado público
    <BASE_DIR>/data/key.pem   — clave privada (permisos 600 en Linux/macOS)

Integración con el Trust Store del sistema (Windows):
    - Si el certificado ya está instalado en CurrentUser\\Root, no hace nada.
    - Si no está instalado, ofrece instalarlo con un diálogo de un click.
    - La instalación es silenciosa en Windows (sin UAC) para CurrentUser.

Uso desde app.py:
    from cert_manager import ensure_certificate, is_cert_trusted_windows

    # En __init__, antes de _start_server():
    cert_ready = ensure_certificate(BASE_DIR)
    if cert_ready and not is_cert_trusted_windows(BASE_DIR):
        _offer_trust_dialog()
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("PrintBridge.CertManager")

# ── Constantes ──────────────────────────────────────────────────────────────
CERT_FILENAME = "cert.pem"
KEY_FILENAME  = "key.pem"
CERT_DAYS     = 3650      # 10 años — evita expiración durante la vida del producto
KEY_SIZE      = 2048      # RSA-2048: balance entre compatibilidad y seguridad
CERT_CN       = "PrintBridge"
CERT_ORG      = "PrintBridge Local Server"


def _data_dir(base_dir: Path) -> Path:
    d = base_dir / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cert_exists(base_dir: Path) -> bool:
    """Retorna True si ambos archivos cert.pem y key.pem existen."""
    d = _data_dir(base_dir)
    return (d / CERT_FILENAME).exists() and (d / KEY_FILENAME).exists()


def _generate_certificate(base_dir: Path) -> bool:
    """
    Genera un certificado TLS autofirmado RSA-2048 / SHA-256.

    Retorna True si la generación fue exitosa, False si falló
    (por ejemplo, si `cryptography` no está instalado).

    El certificado incluye Subject Alternative Names (SANs) para:
    - localhost
    - 127.0.0.1
    - La IP local detectada (para acceso desde otros dispositivos de la red)
    Esta combinación cubre todos los escenarios de acceso típicos de PrintBridge.
    """
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import ipaddress
    except ImportError:
        log.warning(
            "Mejora 2: 'cryptography' no instalado. "
            "El servidor usará HTTP. "
            "Instalar con: pip install cryptography"
        )
        return False

    try:
        log.info("Generando certificado TLS autofirmado (primera ejecución)…")

        # ── Clave privada ──────────────────────────────────────────────────
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=KEY_SIZE,
        )

        # ── Nombre del sujeto ──────────────────────────────────────────────
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME,         CERT_CN),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME,   CERT_ORG),
        ])

        # ── Subject Alternative Names ──────────────────────────────────────
        # Detectar IP local para incluirla en las SANs. Si falla, solo localhost.
        san_ips: list[x509.GeneralName] = [
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
        try:
            from config import get_local_ip
            local_ip = get_local_ip()
            if local_ip and local_ip != "127.0.0.1":
                san_ips.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
        except Exception:
            pass

        san = x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("printbridge.local"),
            *san_ips,
        ])

        # ── Construir certificado ──────────────────────────────────────────
        now_utc = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now_utc)
            .not_valid_after(now_utc + timedelta(days=CERT_DAYS))
            .add_extension(san, critical=False)
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # ── Persistir ──────────────────────────────────────────────────────
        data = _data_dir(base_dir)
        cert_path = data / CERT_FILENAME
        key_path  = data / KEY_FILENAME

        cert_path.write_bytes(
            cert.public_bytes(serialization.Encoding.PEM)
        )
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

        # Proteger la clave privada en sistemas Unix (chmod 600)
        if platform.system() != "Windows":
            os.chmod(key_path, 0o600)

        log.info(f"Certificado TLS generado: {cert_path}")
        return True

    except Exception as e:
        log.error(f"Error generando certificado TLS: {e}", exc_info=True)
        return False


def ensure_certificate(base_dir: Path) -> bool:
    """
    Punto de entrada principal de la Mejora 2.

    Verifica si el certificado existe; si no, lo genera.
    Esta función es segura para llamar múltiples veces (idempotente).

    Retorna True si el certificado está disponible al finalizar.
    """
    if cert_exists(base_dir):
        return True
    return _generate_certificate(base_dir)


def ensure_certificate_async(
    base_dir: Path,
    on_complete: Optional[callable] = None,
) -> threading.Thread:
    """
    Versión asíncrona de ensure_certificate para no bloquear el hilo de GUI.
    Ejecuta la generación en un thread background.

    Args:
        base_dir:    Directorio base del proyecto.
        on_complete: Callback opcional llamado con el resultado (bool) cuando
                     la generación termina. Se llama desde el thread background
                     — usar .after() de Tkinter si necesita actualizar la GUI.

    Retorna el thread iniciado (útil para join() si se necesita esperar).
    """
    def _worker():
        result = ensure_certificate(base_dir)
        if on_complete:
            try:
                on_complete(result)
            except Exception as e:
                log.warning(f"Error en callback de cert_complete: {e}")

    t = threading.Thread(target=_worker, daemon=True, name="CertGen")
    t.start()
    return t


# ── Trust Store de Windows ────────────────────────────────────────────────────

def is_cert_trusted_windows(base_dir: Path) -> bool:
    """
    Verifica si el certificado de PrintBridge está instalado en el Trust Store
    de Windows (CurrentUser\\Root).

    Retorna False en plataformas no-Windows o si el certificado no existe.
    Usa certutil.exe que está presente en todas las versiones de Windows.
    """
    if platform.system() != "Windows":
        return False

    cert_path = _data_dir(base_dir) / CERT_FILENAME
    if not cert_path.exists():
        return False

    try:
        # certutil -verify comprueba si el certificado es de confianza
        # para el usuario actual sin necesitar admin
        result = subprocess.run(
            ["certutil", "-verify", str(cert_path)],
            capture_output=True, text=True, timeout=10
        )
        # Si no lanza error y no menciona "untrusted root", está instalado
        return result.returncode == 0 and "untrusted" not in result.stdout.lower()
    except Exception:
        return False


def install_cert_trust_store_windows(base_dir: Path) -> bool:
    """
    Instala el certificado en el Trust Store de Windows (CurrentUser\\Root).
    No requiere UAC — CurrentUser no necesita privilegios de administrador.

    Retorna True si la instalación fue exitosa.
    Solo tiene efecto en Windows; en otras plataformas retorna False.
    """
    if platform.system() != "Windows":
        return False

    cert_path = _data_dir(base_dir) / CERT_FILENAME
    if not cert_path.exists():
        return False

    try:
        result = subprocess.run(
            ["certutil", "-addstore", "-user", "Root", str(cert_path)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            log.info("Certificado instalado en Trust Store de Windows (CurrentUser\\Root)")
            return True
        else:
            log.warning(f"certutil falló: {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        log.warning("certutil.exe no encontrado — no se pudo instalar el certificado")
        return False
    except Exception as e:
        log.error(f"Error instalando certificado en Trust Store: {e}")
        return False


def get_cert_info(base_dir: Path) -> dict:
    """
    Retorna información sobre el certificado actual para mostrar en la UI.
    Útil para el panel de configuración de la GUI.
    """
    cert_path = _data_dir(base_dir) / CERT_FILENAME
    if not cert_path.exists():
        return {"exists": False}

    try:
        from cryptography import x509 as _x509
        from cryptography.hazmat.primitives.serialization import Encoding
        cert = _x509.load_pem_x509_certificate(cert_path.read_bytes())
        return {
            "exists":      True,
            "subject":     cert.subject.get_attributes_for_oid(
                               _x509.oid.NameOID.COMMON_NAME)[0].value,
            "not_before":  cert.not_valid_before_utc.strftime("%Y-%m-%d"),
            "not_after":   cert.not_valid_after_utc.strftime("%Y-%m-%d"),
            "serial":      hex(cert.serial_number),
            "trusted_win": is_cert_trusted_windows(base_dir),
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}
