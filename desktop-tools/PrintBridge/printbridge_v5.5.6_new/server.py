import os
import re
import shutil
import socket
import tempfile
import threading
import logging
import uuid
import base64
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

import printer
from queue_manager import QueueManager, PrintJob
from device_manager import DeviceManager
from config import load_config, save_config

log = logging.getLogger("PrintBridge.Server")

BASE_DIR  = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR   = BASE_DIR / "web"

app = FastAPI(title="PrintBridge")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

device_mgr: DeviceManager = None
queue_mgr:  QueueManager  = None


def set_queue_manager(qm):
    global queue_mgr
    queue_mgr = qm


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _has_pin() -> bool:
    """Returns True if a PIN is configured (non-empty)."""
    return bool(load_config().get("pin", "").strip())

def _check_auth(request: Request):
    if not _has_pin():
        return  # Sin contraseña: acceso libre
    token = request.headers.get("X-Device-Token") or request.cookies.get("pb_token")
    if not token or not device_mgr.is_authorized(token):
        raise HTTPException(status_code=401, detail="No autorizado.")


# ── Web UI ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        content = index_file.read_text(encoding="utf-8")
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    return HTMLResponse("<h1>PrintBridge</h1><p>Archivos web no encontrados.</p>")


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(request: Request, pin: str = Form(""), device_name: str = Form("")):
    ip = request.client.host
    if _has_pin() and not device_mgr.verify_pin(pin):
        raise HTTPException(status_code=403, detail="PIN incorrecto.")
    token = device_mgr.generate_token(device_name or f"Dispositivo ({ip})", ip)
    response = JSONResponse({"token": token, "ok": True})
    response.set_cookie("pb_token", token, max_age=60*60*24*365, httponly=True)
    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    token = request.headers.get("X-Device-Token") or request.cookies.get("pb_token")
    if token:
        device_mgr.remove_device(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("pb_token")
    return response


@app.get("/api/auth/check")
async def auth_check(request: Request):
    pin_required = _has_pin()
    if not pin_required:
        return {"authorized": True, "pin_required": False}
    token = request.headers.get("X-Device-Token") or request.cookies.get("pb_token")
    if token and device_mgr.is_authorized(token):
        return {"authorized": True, "pin_required": True}
    return {"authorized": False, "pin_required": True}


# ── Server info ───────────────────────────────────────────────────────────────

@app.get("/api/info")
async def server_info(request: Request):
    _check_auth(request)
    config = load_config()
    return {
        "name":               config.get("server_name", "PrintBridge"),
        "ip":                 get_local_ip(),
        "port":               config.get("port", 7878),
        "printer":            config.get("printer", ""),
        "available_printers": printer.get_available_printers(),
        "version":            "1.0.0",
    }


# ── Print ─────────────────────────────────────────────────────────────────────

@app.post("/api/print")
async def print_file(
    request:        Request,
    file:           UploadFile = File(...),
    copies:         int  = Form(1),
    mirror:         bool = Form(False),
    rotate:         int  = Form(0),
    color:          str  = Form("color"),
    orientation:    str  = Form("portrait"),
    paper:          str  = Form("a4"),
    page_range:     str  = Form(""),
    pages_per_sheet:int  = Form(1),
    scale:          str  = Form("fit"),
    duplex:         str  = Form("off"),
    quality:        str  = Form("standard"),
    media_type:     str  = Form("normal"),
):
    _check_auth(request)
    config  = load_config()
    allowed = config.get("allowed_extensions", [])
    ext     = Path(file.filename).suffix.lower().lstrip(".")

    if allowed and ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Formato .{ext} no permitido.")

    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    token       = request.headers.get("X-Device-Token") or request.cookies.get("pb_token")
    device_info = device_mgr.devices.get(token, {})

    job = PrintJob(
        filename    = file.filename,
        filepath    = str(dest),
        device_name = device_info.get("name", "Desconocido"),
        ip          = request.client.host,
        copies      = copies,
        options     = {
            "mirror": mirror,
            "rotate": rotate,
            "color": color,
            "orientation": orientation,
            "paper": paper,
            "page_range": page_range,
            "pages_per_sheet": pages_per_sheet,
            "scale": scale,
            "duplex": duplex,
            "quality": quality,
            "media_type": media_type,
        },
    )

    job_id = queue_mgr.add_job(job)
    if not job_id:
        raise HTTPException(status_code=503, detail="Cola llena.")

    return {"ok": True, "job_id": job_id}


@app.get("/api/queue")
async def get_queue(request: Request):
    _check_auth(request)
    return {"queue": queue_mgr.get_queue()}


@app.delete("/api/queue/{job_id}")
async def cancel_job(job_id: str, request: Request):
    _check_auth(request)
    return {"ok": queue_mgr.cancel_job(job_id)}


@app.get("/api/history")
async def get_history(request: Request):
    _check_auth(request)
    return {"history": queue_mgr.get_history()}


# ── Devices ───────────────────────────────────────────────────────────────────

@app.get("/api/devices")
async def list_devices(request: Request):
    _check_auth(request)
    return {"devices": device_mgr.get_all_devices()}


@app.delete("/api/devices/{token}")
async def remove_device(token: str, request: Request):
    _check_auth(request)
    return {"ok": device_mgr.remove_device(token)}


# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config(request: Request):
    _check_auth(request)
    config = load_config()
    return {k: v for k, v in config.items() if k != "pin"}


@app.post("/api/config/printer")
async def set_printer(request: Request, printer_name: str = Form(...)):
    _check_auth(request)
    config = load_config()
    config["printer"] = printer_name
    save_config(config)
    return {"ok": True}

@app.post("/api/config/pin")
async def set_pin(request: Request, pin: str = Form("")):
    _check_auth(request)
    config = load_config()
    config["pin"] = pin.strip()
    save_config(config)
    return {"ok": True}


# ── Scanner ───────────────────────────────────────────────────────────────────

# In-memory scan sessions: session_id → list of scanned page paths
_scan_sessions: dict = {}

@app.get("/api/scanners")
async def list_scanners(request: Request):
    _check_auth(request)
    return {"scanners": printer.get_available_scanners()}


@app.post("/api/scan")
async def scan_document(
    request:     Request,
    device_id:   str   = Form(...),
    color:       str   = Form("color"),
    dpi:         int   = Form(200),
    source:      str   = Form("flatbed"),
    session_id:  str   = Form(""),
    brightness:  int   = Form(0),
    contrast:    int   = Form(0),
    gamma:       float = Form(2.2),
    img_option:  str   = Form("none"),
    unsharp:     str   = Form("0"),
    descreen:    str   = Form("0"),
    border_fill: str   = Form("none"),
):
    """Scan one page and add it to a session. Returns preview URL + session state."""
    _check_auth(request)

    filename = f"scan_{uuid.uuid4().hex[:8]}.png"
    out_path = str(UPLOAD_DIR / filename)

    scan_opts = {
        "brightness": brightness,
        "contrast":   contrast,
        "gamma":      gamma,
        "img_option": img_option,
        "unsharp":    unsharp == "1",
        "descreen":   descreen == "1",
        "border_fill": border_fill,
    }

    try:
        printer.scan_document(device_id, out_path, color=color, dpi=dpi,
                               source=source, options=scan_opts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Add to session
    sid = session_id or uuid.uuid4().hex
    if sid not in _scan_sessions:
        _scan_sessions[sid] = []
    _scan_sessions[sid].append(out_path)

    page_num = len(_scan_sessions[sid])

    return {
        "ok": True,
        "session_id": sid,
        "page": page_num,
        "total_pages": page_num,
        "filename": filename,
        "url": f"/api/scan/download/{filename}",
    }


@app.delete("/api/scan/session/{session_id}/page/{page_index}")
async def delete_scan_page(session_id: str, page_index: int, request: Request):
    """Remove a specific page from the session (0-indexed)."""
    _check_auth(request)
    pages = _scan_sessions.get(session_id, [])
    if 0 <= page_index < len(pages):
        removed = pages.pop(page_index)
        try:
            Path(removed).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True, "total_pages": len(_scan_sessions.get(session_id, []))}


@app.post("/api/scan/session/{session_id}/reorder")
async def reorder_scan_pages(session_id: str, request: Request, order: str = Form(...)):
    """Reorder pages. order = comma-separated 0-indexed positions e.g. '2,0,1'"""
    _check_auth(request)
    pages = _scan_sessions.get(session_id, [])
    try:
        indices = [int(i) for i in order.split(",")]
        if set(indices) == set(range(len(pages))):
            _scan_sessions[session_id] = [pages[i] for i in indices]
    except Exception:
        pass
    return {"ok": True, "total_pages": len(_scan_sessions.get(session_id, []))}


@app.post("/api/scan/session/{session_id}/merge")
async def merge_scan_session(
    session_id: str,
    request: Request,
    filename: str = Form("documento_escaneado"),
):
    """Merge all scanned pages into a single PDF and return it."""
    _check_auth(request)
    pages = _scan_sessions.get(session_id, [])
    if not pages:
        raise HTTPException(status_code=400, detail="No hay páginas escaneadas en esta sesión.")

    # Filter existing files
    pages = [p for p in pages if Path(p).exists()]
    if not pages:
        raise HTTPException(status_code=400, detail="Las páginas escaneadas ya no existen.")

    try:
        import img2pdf
        from PIL import Image as PILImage
        import io as _io

        img_bytes_list = []
        for p in pages:
            img = PILImage.open(p)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = _io.BytesIO()
            img.save(buf, "JPEG", quality=95)
            img_bytes_list.append(buf.getvalue())

        pdf_bytes = img2pdf.convert(img_bytes_list)

        safe_name = re.sub(r'[^\w\-.]', '_', filename)
        if not safe_name.endswith(".pdf"):
            safe_name += ".pdf"
        out_pdf = UPLOAD_DIR / safe_name
        with open(out_pdf, "wb") as f:
            f.write(pdf_bytes)

        # Clean up session images
        for p in pages:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        del _scan_sessions[session_id]

        return {"ok": True, "filename": safe_name, "url": f"/api/scan/download/{safe_name}", "pages": len(img_bytes_list)}
    except Exception as e:
        log.exception("merge_scan_session error")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/scan/session/{session_id}")
async def cancel_scan_session(session_id: str, request: Request):
    """Cancel and clean up a scan session."""
    _check_auth(request)
    pages = _scan_sessions.pop(session_id, [])
    for p in pages:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True}


@app.get("/api/scan/download/{filename}")
async def download_scan(filename: str, request: Request):
    _check_auth(request)
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(str(path), filename=filename)


# ── Runner ────────────────────────────────────────────────────────────────────

_server_instance = None


def start_server(port: int = 7878):
    global _server_instance
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    _server_instance = uvicorn.Server(config)
    t = threading.Thread(target=_server_instance.run, daemon=True)
    t.start()
    log.info(f"Servidor iniciado en http://0.0.0.0:{port}")


def stop_server():
    global _server_instance
    if _server_instance:
        _server_instance.should_exit = True


# ── Document preview ──────────────────────────────────────────────────────────

@app.post("/api/preview")
async def generate_preview(
    request: Request,
    file: UploadFile = File(...),
    orientation: str = Form("portrait"),
    paper: str = Form("a4"),
):
    _check_auth(request)
    ext = Path(file.filename).suffix.lower().lstrip(".")

    safe_name = f"prev_{uuid.uuid4().hex[:8]}_{file.filename}"
    dest = UPLOAD_DIR / safe_name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    temp_dir = tempfile.mkdtemp()
    try:
        pdf_path = None

        # Images: return directly as base64 (no conversion needed)
        if ext in {"jpg","jpeg","png","bmp","tiff","tif","webp","gif"}:
            with open(dest, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            mime = "image/jpeg" if ext in ("jpg","jpeg") else f"image/{ext}"
            if ext == "tif": mime = "image/tiff"
            return {"ok": True, "pages": [f"data:{mime};base64,{b64}"], "total": 1}

        # TXT: render as plain text preview image
        elif ext == "txt":
            pages = printer.txt_to_preview(str(dest))
            return {"ok": True, "pages": pages, "total": len(pages)}

        # Office documents: convert to PDF first
        elif ext in {"doc","docx","xls","xlsx","ppt","pptx","odt","ods","odp","rtf"}:
            pdf_path = printer._convert_office_to_pdf(str(dest), temp_dir,
                                                       orientation=orientation, paper=paper)

        # PDF: use directly
        elif ext == "pdf":
            pdf_path = str(dest)

        pages = []
        if pdf_path:
            pages = printer.pdf_to_preview_images(pdf_path, max_pages=20)

        return {"ok": True, "pages": pages, "total": len(pages)}
    except Exception as e:
        log.error(f"Preview error: {e}")
        return {"ok": False, "pages": [], "error": str(e)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
