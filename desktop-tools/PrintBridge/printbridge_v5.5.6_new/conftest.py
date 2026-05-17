"""
conftest.py — Configuración raíz de pytest para PrintBridge
Mejora 8 del Roadmap Técnico: CI Pipeline

Este archivo es cargado automáticamente por pytest antes de cualquier test.
Provee:
  - Detección de plataforma (WIN32_AVAILABLE)
  - Skip automático de tests marcados @win32_only en Linux/macOS
  - Fixtures compartidas reutilizables por todos los test files
  - Configuración de paths para imports
"""
from __future__ import annotations

import sys
import os
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Configuración de path ──────────────────────────────────────────────────
# Asegurar que la raíz del proyecto esté en sys.path para todos los tests,
# independientemente del directorio desde el que se ejecute pytest.
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Detección de plataforma ────────────────────────────────────────────────
try:
    import win32print  # noqa: F401
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

IS_WINDOWS = sys.platform == "win32"

# ── Skip automático para tests win32_only ──────────────────────────────────
def pytest_collection_modifyitems(config, items):
    """
    Hook de pytest: salta automáticamente los tests marcados @win32_only
    cuando no estamos en Windows o cuando win32print no está disponible.

    Esto permite que el runner de Ubuntu ejecute `pytest` sin flags
    adicionales y los tests de plataforma se saltan solos — sin necesidad
    de recordar `-m "not win32_only"`.
    """
    if WIN32_AVAILABLE:
        return  # En Windows con win32print: ejecutar todo

    skip_win32 = pytest.mark.skip(
        reason="Requiere Windows + win32print/win32ui (marcado win32_only)"
    )
    for item in items:
        if "win32_only" in item.keywords:
            item.add_marker(skip_win32)


# ── Fixture: directorio de datos aislado ──────────────────────────────────
@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """
    Directorio temporal con estructura de datos de PrintBridge.
    Útil para tests que necesitan crear archivos de config/devices/uploads.
    """
    (tmp_path / "data" / "uploads").mkdir(parents=True)
    (tmp_path / "data").joinpath("config.json").write_text(
        json.dumps({
            "port": 7878,
            "pin": "",
            "printer": "",
            "server_name": "PrintBridge-Test",
            "start_minimized": False,
            "max_history": 100,
            "max_queue_size": 20,
            "token_expiry_days": 90,
            "allowed_extensions": ["pdf", "docx", "xlsx", "jpg", "png"],
        }),
        encoding="utf-8",
    )
    (tmp_path / "data").joinpath("devices.json").write_text("{}", encoding="utf-8")
    (tmp_path / "data").joinpath("history.json").write_text("[]", encoding="utf-8")
    return tmp_path


# ── Fixture: mock de printer module ───────────────────────────────────────
@pytest.fixture()
def mock_printer() -> MagicMock:
    """
    Mock del módulo printer.py para tests que no necesitan hardware real.
    Simula todas las funciones públicas con respuestas vacías correctas.
    """
    p = MagicMock()
    p.print_file.return_value = None
    p.get_available_printers.return_value = ["FakePrinter-A4", "FakePrinter-Letter"]
    p.get_default_printer.return_value = "FakePrinter-A4"
    p.get_available_scanners.return_value = ["FakeScanner-Flatbed"]
    p.scan_document.return_value = None
    p.preview_file.return_value = b""   # bytes vacíos de preview PNG
    return p


# ── Fixture: QueueManager aislado ─────────────────────────────────────────
@pytest.fixture()
def queue_manager(mock_printer, monkeypatch, tmp_path):
    """
    QueueManager con printer mock y archivos de datos en tmp_path.
    El worker thread arranca pero nunca llama hardware real.
    """
    import config as cfg
    monkeypatch.setattr(cfg, "CONFIG_FILE",  tmp_path / "config.json")
    monkeypatch.setattr(cfg, "DEVICES_FILE", tmp_path / "devices.json")
    monkeypatch.setattr(cfg, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(cfg, "_config_cache", None)
    monkeypatch.setattr(cfg, "_pin_configured", None)

    from queue_manager import QueueManager, PrintJob
    mgr = QueueManager(mock_printer)
    yield mgr, PrintJob
    # Detener el worker al final del test
    mgr._stop_event.set() if hasattr(mgr, "_stop_event") else None


# ── Fixture: DeviceManager aislado ────────────────────────────────────────
@pytest.fixture()
def device_manager(monkeypatch, tmp_path):
    """
    DeviceManager con archivos de datos en tmp_path.
    Detiene el hilo de guardado periódico al finalizar el test.
    """
    import json as _json
    import config as cfg

    tmp_cfg  = tmp_path / "config.json"
    tmp_dev  = tmp_path / "devices.json"
    tmp_hist = tmp_path / "history.json"

    tmp_cfg.write_text(_json.dumps({"pin": "", "token_expiry_days": 90}), encoding="utf-8")
    tmp_dev.write_text("{}", encoding="utf-8")
    tmp_hist.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(cfg, "CONFIG_FILE",  tmp_cfg)
    monkeypatch.setattr(cfg, "DEVICES_FILE", tmp_dev)
    monkeypatch.setattr(cfg, "HISTORY_FILE", tmp_hist)
    monkeypatch.setattr(cfg, "_config_cache", None)
    monkeypatch.setattr(cfg, "_pin_configured", None)

    from device_manager import DeviceManager
    dm = DeviceManager()
    yield dm
    dm.flush()   # detiene _stop_event + persiste cambios pendientes


# ── Fixture: upload dir temporal ──────────────────────────────────────────
@pytest.fixture()
def upload_dir(tmp_path: Path, monkeypatch) -> Path:
    """
    Directorio de uploads temporal. Parchea server.UPLOAD_DIR para que
    los tests de /api/print y /api/scan no escriban en el directorio real.
    """
    udir = tmp_path / "uploads"
    udir.mkdir()
    try:
        import server as srv
        monkeypatch.setattr(srv, "UPLOAD_DIR", udir)
    except Exception:
        pass
    return udir


# ── Fixture: FastAPI TestClient ────────────────────────────────────────────
@pytest.fixture()
def api_client(mock_printer, monkeypatch, tmp_path):
    """
    httpx.AsyncClient / starlette TestClient apuntando a la app FastAPI.
    Inyecta mocks de device_mgr y queue_mgr para no necesitar hardware.

    Uso:
        def test_something(api_client):
            client, dm, qm = api_client
            r = client.get("/api/version")
            assert r.status_code == 200
    """
    try:
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("starlette no disponible")

    import json as _json
    import config as cfg

    tmp_cfg  = tmp_path / "config.json"
    tmp_dev  = tmp_path / "devices.json"
    tmp_hist = tmp_path / "history.json"
    tmp_uploads = tmp_path / "uploads"
    tmp_uploads.mkdir()

    tmp_cfg.write_text(_json.dumps({
        "pin": "", "port": 7878, "printer": "FakePrinter-A4",
        "server_name": "TestBridge", "max_history": 100,
        "max_queue_size": 20, "token_expiry_days": 90,
        "allowed_extensions": ["pdf", "jpg", "png"],
    }), encoding="utf-8")
    tmp_dev.write_text("{}", encoding="utf-8")
    tmp_hist.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(cfg, "CONFIG_FILE",  tmp_cfg)
    monkeypatch.setattr(cfg, "DEVICES_FILE", tmp_dev)
    monkeypatch.setattr(cfg, "HISTORY_FILE", tmp_hist)
    monkeypatch.setattr(cfg, "_config_cache", None)
    monkeypatch.setattr(cfg, "_pin_configured", None)

    import server as srv
    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_uploads)
    monkeypatch.setattr(srv, "printer", mock_printer)

    from device_manager import DeviceManager
    from queue_manager import QueueManager

    dm = DeviceManager()
    qm = QueueManager(mock_printer)

    monkeypatch.setattr(srv, "device_mgr", dm)
    monkeypatch.setattr(srv, "queue_mgr", qm)

    client = TestClient(srv.app, raise_server_exceptions=True)
    yield client, dm, qm

    dm.flush()


# ── Fixture: token de admin autenticado ────────────────────────────────────
@pytest.fixture()
def admin_token(api_client):
    """
    Realiza login en la API y devuelve el token de admin.
    Útil para tests que necesitan autenticación sin repetir el flujo.
    """
    client, dm, qm = api_client
    # Sin PIN: el primer login genera admin automáticamente
    r = client.post("/api/auth/login", data={"pin": "", "device_name": "TestAdmin"})
    assert r.status_code == 200, f"Login falló: {r.text}"
    token = r.cookies.get("pb_token") or r.headers.get("pb_token")
    return client, dm, qm, token


# ── Helpers de test expuestos como fixtures ────────────────────────────────
@pytest.fixture()
def make_pdf_bytes() -> bytes:
    """Retorna bytes mínimos de un PDF válido para tests de upload."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
