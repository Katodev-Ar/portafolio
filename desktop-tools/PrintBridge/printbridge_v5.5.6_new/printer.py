"""
PrintBridge printer module.
Uses PyMuPDF (fitz) for PDF rendering/preview - NO LibreOffice needed for PDFs.
LibreOffice still used ONLY for Office format conversion (DOCX→PDF etc).
Images printed directly via win32 GDI.
"""
import os, io, subprocess, tempfile, shutil, logging, base64
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    import win32ui as _win32ui_type
from pathlib import Path

log = logging.getLogger("PrintBridge.Printer")

try:
    import win32print, win32ui, win32con
    from PIL import Image as PILImage, ImageWin
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False
    log.warning("PyMuPDF not installed. PDF preview disabled.")

# Fix Mejora #2: import numpy al inicio con flag de disponibilidad
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

from config import load_config

OFFICE_EXTENSIONS = {"doc","docx","xls","xlsx","ppt","pptx","odt","ods","odp","rtf","txt"}
IMAGE_EXTENSIONS  = {"jpg","jpeg","png","bmp","tiff","tif","webp","gif"}


def get_available_printers() -> list[str]:
    if not WIN32_AVAILABLE:
        return ["(Simulado) Impresora de prueba"]
    try:
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return [p[2] for p in printers]
    except Exception:
        return []


def get_default_printer() -> str:
    if not WIN32_AVAILABLE:
        return ""
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


# ─── OFFICE → PDF (Native Python, no LibreOffice needed) ─────────────────────

def _convert_office_to_pdf(filepath: str, temp_dir: str, orientation: str = "portrait", paper: str = "a4") -> str:
    """Convert Office/text document to PDF using native Python libraries."""
    import converter as _conv
    return _conv.convert_to_pdf(filepath, temp_dir,
                                 orientation=orientation, page_size=paper)


# ─── PDF → IMAGES via PyMuPDF (no LibreOffice needed) ────────────────────────

def pdf_to_preview_images(filepath: str, max_pages: int = 50, dpi: int = 120) -> list[str]:
    """
    Convert PDF pages to base64 PNG using PyMuPDF.
    Fast, accurate, no external dependencies.
    Returns list of data:image/png;base64,... strings.
    """
    if not FITZ_AVAILABLE:
        log.error("PyMuPDF (fitz) no está instalado. Instala con: pip install PyMuPDF")
        return []

    results = []
    doc = None
    try:
        doc = fitz.open(filepath)
        total = min(len(doc), max_pages)
        mat = fitz.Matrix(dpi/72, dpi/72)  # scale factor

        for i in range(total):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("png")
            b64 = base64.b64encode(img_bytes).decode()
            results.append(f"data:image/png;base64,{b64}")
    except Exception as e:
        log.error(f"PyMuPDF preview error: {e}")
    finally:
        # Fix ALTO: cerrar siempre el documento para evitar fuga de recursos
        if doc is not None:
            doc.close()

    return results


def txt_to_preview(filepath: str, max_lines_per_page: int = 60, dpi: int = 96) -> list[str]:
    """
    Render a plain text file as preview image(s) using PIL.
    No external tools needed.
    Returns list of data:image/png;base64,... strings.
    """
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()

        if not lines:
            lines = ["(archivo vacío)"]

        # Split into pages
        pages_lines = [lines[i:i+max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)]

        # Page size: A4 at 96dpi approx
        W, H = 794, 1123
        MARGIN = 40
        LINE_H = 16
        FONT_SIZE = 13

        # Try to use a monospace font, fall back to default
        try:
            font = ImageFont.truetype("cour.ttf", FONT_SIZE)   # Windows Courier
        except Exception:
            try:
                font = ImageFont.truetype("DejaVuSansMono.ttf", FONT_SIZE)
            except Exception:
                font = ImageFont.load_default()

        results = []
        for page_lines in pages_lines[:20]:
            img = PILImage.new("RGB", (W, H), "white")
            draw = ImageDraw.Draw(img)
            y = MARGIN
            for line in page_lines:
                # Truncate long lines
                if len(line) > 100:
                    line = line[:97] + "..."
                draw.text((MARGIN, y), line, fill="black", font=font)
                y += LINE_H
                if y > H - MARGIN:
                    break
            buf = io.BytesIO()  # io importado al inicio del módulo
            img.save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            results.append(f"data:image/png;base64,{b64}")

        return results
    except Exception as e:
        log.error(f"txt_to_preview error: {e}")
        return []



# ─── PRINTING ─────────────────────────────────────────────────────────────────

# ─── DEVMODE helpers ──────────────────────────────────────────────────────────

_MEDIA_TYPES = {
    # media_type_name: (dmMediaType, dmPrintQuality)
    "normal":       (1,  -3),   # DMMEDIA_STANDARD,  DMRES_MEDIUM
    "glossy":       (3,  -4),   # DMMEDIA_GLOSSY,    DMRES_HIGH
    "glossy_ultra": (3,  -4),
    "semi_gloss":   (3,  -3),
    "matte":        (1,  -4),   # Standard media, high quality
    "photo":        (3,  -4),
    "transparency": (2,  -4),   # DMMEDIA_TRANSPARENCY
    "envelope":     (1,  -2),
    "labels":       (1,  -3),
    "draft":        (1,  -1),   # DMRES_DRAFT
}

def _apply_devmode(printer_name: str, options: dict) -> Any:  # win32ui.CDC | None at runtime
    """
    Apply DEVMODE settings (quality, media type) to printer.
    Returns a DEVMODE-based printer DC or None if unavailable.
    Uses win32print.OpenPrinter + DocumentProperties.
    """
    if not WIN32_AVAILABLE:
        return None
    try:
        import pywintypes
        quality   = options.get("quality", "standard")
        media_key = options.get("media_type", "normal")
        dm_media, dm_quality = _MEDIA_TYPES.get(media_key, (1, -3))

        # Map quality override
        if quality == "high":   dm_quality = -4  # DMRES_HIGH
        elif quality == "draft": dm_quality = -1  # DMRES_DRAFT
        elif quality == "standard": pass         # keep media default

        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            dm = win32print.GetPrinter(hPrinter, 2)["pDevMode"]
            dm.PrintQuality = dm_quality
            dm.MediaType    = dm_media
            # F1 Fix: aplicar DEVMODE al driver ANTES de crear el DC
            # Sin esta llamada, CreatePrinterDC usa la configuración por defecto
            # DM_IN_BUFFER|DM_OUT_BUFFER = 8
            win32print.DocumentProperties(0, hPrinter, printer_name, dm, dm, 8)
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            return hDC
        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        log.debug(f"DEVMODE setup failed (using default): {e}")
        return None


def _print_image_direct(filepath: str, printer_name: str, copies: int, options: dict) -> None:
    """Print image via win32 GDI — no external tools."""
    img = PILImage.open(filepath)
    if img.mode in ("RGBA","P","LA"):
        img = img.convert("RGB")
    if options.get("mirror"):
        img = img.transpose(PILImage.FLIP_LEFT_RIGHT)
    if options.get("rotate"):
        img = img.rotate(-int(options["rotate"]), expand=True)
    if options.get("color") in ("grayscale", "bw"):
        img = img.convert("L").convert("RGB")

    hDC = _apply_devmode(printer_name, options)
    if hDC is None:
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
    pw = hDC.GetDeviceCaps(win32con.HORZRES)
    ph = hDC.GetDeviceCaps(win32con.VERTRES)
    iw, ih = img.size
    scale = min(pw/iw, ph/ih)
    nw, nh = int(iw*scale), int(ih*scale)
    img = img.resize((nw,nh), PILImage.LANCZOS)
    x=(pw-nw)//2; y=(ph-nh)//2

    # PR-01: try/finally garantiza que el DC se cierre aunque haya excepción
    try:
        for _ in range(copies):
            hDC.StartDoc(Path(filepath).name)
            hDC.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hDC.GetHandleOutput(), (x,y,x+nw,y+nh))
            hDC.EndPage()
            hDC.EndDoc()
    finally:
        hDC.DeleteDC()


def _print_pdf_direct(pdf_path: str, printer_name: str, copies: int, options: dict) -> None:
    """
    Print PDF via GDI (PyMuPDF for rendering).
    Supports: grayscale, page range, copies, orientation, duplex (manual odd/even).
    """
    if not FITZ_AVAILABLE or not WIN32_AVAILABLE:
        raise RuntimeError("PyMuPDF y pywin32 son necesarios para imprimir. Instálalos con: pip install PyMuPDF pywin32")

    grayscale       = options.get("color") in ("grayscale", "bw")
    page_range_str  = options.get("page_range", "").strip()
    orientation     = options.get("orientation", "portrait")
    duplex          = options.get("duplex", "off")

    doc = fitz.open(pdf_path)
    try:
        total = len(doc)
        try:
            all_pages = _parse_page_range(page_range_str, total)
        except ValueError as e:
            # N-05 Fix: convertir a RuntimeError para que queue_manager lo registre
            # con un mensaje claro en job.error, distinguible de fallos de impresión
            raise RuntimeError(f"Rango de páginas inválido: {e}") from e

        # Manual duplex: JS sends two separate jobs (odd pass, then even pass)
        # each with page_range='odd' or 'even' and duplex='off'
        # So here we just print whatever pages were requested in a single pass.
        page_passes = [("all", all_pages)]

        def render_page(page_num, hDC, pw, ph, render_dpi):
            page = doc.load_page(page_num)
            # Auto-rotate page to match printer orientation
            page_w = page.rect.width
            page_h = page.rect.height
            page_landscape = page_w > page_h
            printer_landscape = pw > ph

            mat = fitz.Matrix(render_dpi/72, render_dpi/72)
            if page_landscape != printer_landscape:
                # Rotate 90 degrees to match
                mat = fitz.Matrix(render_dpi/72, render_dpi/72).prerotate(90)

            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("ppm")
            img = PILImage.open(io.BytesIO(img_data))

            if grayscale:
                img = img.convert("L").convert("RGB")

            iw, ih = img.size
            scale = min(pw/iw, ph/ih)
            nw, nh = int(iw*scale), int(ih*scale)
            if nw < 1: nw = 1
            if nh < 1: nh = 1
            img = img.resize((nw, nh), PILImage.LANCZOS)
            x = (pw - nw) // 2
            y = (ph - nh) // 2
            return img, x, y, nw, nh

        for copy_num in range(copies):
            for pass_name, pages_in_pass in page_passes:
                if not pages_in_pass:
                    continue

                # Fix Bug #2: usar el DC de _apply_devmode para que calidad/papel se apliquen
                hDC = _apply_devmode(printer_name, options)
                if hDC is None:
                    hDC = win32ui.CreateDC()
                    hDC.CreatePrinterDC(printer_name)
                pw = hDC.GetDeviceCaps(win32con.HORZRES)
                ph = hDC.GetDeviceCaps(win32con.VERTRES)
                printer_dpi_x = hDC.GetDeviceCaps(win32con.LOGPIXELSX)
                # High quality = render at higher DPI
                quality = options.get("quality", "standard")
                render_dpi = {"high": min(printer_dpi_x, 600),
                              "draft": min(printer_dpi_x, 150),
                              "standard": min(printer_dpi_x, 300)}.get(quality, 300)

                doc_title = Path(pdf_path).name
                if duplex != "off":
                    doc_title += f" [{pass_name}]"

                hDC.StartDoc(doc_title)
                for page_num in pages_in_pass:
                    if page_num >= total:
                        continue
                    img, x, y, nw, nh = render_page(page_num, hDC, pw, ph, render_dpi)
                    hDC.StartPage()
                    dib = ImageWin.Dib(img)
                    dib.draw(hDC.GetHandleOutput(), (x, y, x+nw, y+nh))
                    hDC.EndPage()
                    # Liberar memoria de la imagen inmediatamente tras enviarla al DC
                    # para no acumular todas las páginas en RAM (PDFs grandes a 600 DPI
                    # pueden usar 50-200 MB por página)
                    del dib, img
                hDC.EndDoc()
                hDC.DeleteDC()

    finally:
        # Fix ALTO: cerrar siempre el documento
        doc.close()


def _parse_page_range(range_str: str, total: int) -> list[int]:
    """Parse '1-3,5,7', 'odd', or 'even' into list of 0-indexed page numbers."""
    if not range_str or range_str.lower() in ("all","todos",""):
        return list(range(total))
    low = range_str.strip().lower()
    if low == "odd":
        return [p for p in range(total) if p % 2 == 0]   # 0-indexed: 0=page1, 2=page3...
    if low == "even":
        return [p for p in range(total) if p % 2 == 1]   # 0-indexed: 1=page2, 3=page4...
    pages = []
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                pages.extend(range(int(a)-1, int(b)))
            except ValueError:
                pass
        else:
            try:
                pages.append(int(part)-1)
            except ValueError:
                pass
    # M-06 Fix: deduplicar y ordenar — page_range='1,1,2,1-3' no debe imprimir
    # páginas duplicadas desperdiciando papel
    valid = sorted(set(p for p in pages if 0 <= p < total))
    if not valid and range_str.strip():
        # El input no estaba vacío pero no produjo ninguna página válida.
        raise ValueError(
            f"page_range '{range_str}' no contiene páginas válidas "
            f"para un documento de {total} página(s)."
        )
    return valid


def print_file(filepath: str, copies: int = 1, options: dict | None = None) -> None:
    options = options or {}
    config  = load_config()
    printer_name = config.get("printer") or get_default_printer()
    if not printer_name:
        raise RuntimeError("No hay impresora configurada.")

    ext = Path(filepath).suffix.lower().lstrip(".")
    temp_dir = tempfile.mkdtemp()
    try:
        if ext in IMAGE_EXTENSIONS:
            if WIN32_AVAILABLE:
                _print_image_direct(filepath, printer_name, copies, options)
        elif ext == "pdf":
            _print_pdf_direct(filepath, printer_name, copies, options)
        elif ext in OFFICE_EXTENSIONS:
            pdf_path = _convert_office_to_pdf(filepath, temp_dir)
            _print_pdf_direct(pdf_path, printer_name, copies, options)
        else:
            raise RuntimeError(f"Formato no soportado: .{ext}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ─── Scanner ──────────────────────────────────────────────────────────────────

def get_available_scanners() -> list[dict]:
    try:
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        mgr = win32com.client.Dispatch("WIA.DeviceManager")
        result = []
        for info in mgr.DeviceInfos:
            try:
                if info.Type == 1:
                    result.append({"id":info.DeviceID,"name":info.Properties["Name"].Value})
            except Exception: pass
        return result
    except Exception as e:
        log.warning(f"WIA: {e}"); return []


def scan_document(device_id: str, output_path: str, color: str = "color", dpi: int = 200, source: str = "flatbed", options: dict | None = None) -> str:
    """
    Scan via WIA with full Pillow post-processing.
    options keys: brightness(-127..127), contrast(-127..127), gamma(float),
                  unsharp(bool), descreen(bool), img_option(str), border_fill(str)
    Retries 3x if device is busy (WIA_ERROR_BUSY).
    """
    import time
    opts = options or {}
    last_err = None

    # CoInitialize/CoUninitialize fuera del loop — inicializar el COM apartment
    # una sola vez evita comportamiento indefinido si quedan referencias COM
    # activas entre reintentos (objetos WIA parcialmente construidos).
    import pythoncom, win32com.client
    pythoncom.CoInitialize()
    try:
        for attempt in range(3):
            try:
                mgr = win32com.client.Dispatch("WIA.DeviceManager")
                device = None
                for info in mgr.DeviceInfos:
                    if info.DeviceID == device_id:
                        device = info.Connect()
                        break
                if not device:
                    raise RuntimeError("Escáner no encontrado. Verificá que esté encendido y conectado.")
                item = device.Items[1]

                # DPI (horizontal and vertical)
                for pid in (6147, 6148):
                    try:
                        prop = item.Properties[pid]
                        try:
                            vals = list(prop.SubTypeValues)
                            dpi_clamped = min(vals, key=lambda x: abs(x - dpi)) if vals else dpi
                        except Exception:
                            dpi_clamped = dpi
                        prop.Value = dpi_clamped
                    except Exception:
                        pass

                # Color mode: 4=color, 2=grayscale, 1=b&w
                try:
                    item.Properties[6146].Value = {"color": 4, "grayscale": 2, "bw": 1}.get(color, 4)
                except Exception:
                    pass

                # Paper source: 1=flatbed, 2=ADF, 4=ADF duplex
                try:
                    item.Properties[6149].Value = {"flatbed": 1, "adf": 2, "adf_duplex": 4}.get(source, 1)
                except Exception:
                    pass

                # Hardware brightness / contrast (WIA range -1000..1000)
                try:
                    item.Properties[6154].Value = max(-1000, min(1000, int(opts.get("brightness", 0)) * 8))
                except Exception:
                    pass
                try:
                    item.Properties[6155].Value = max(-1000, min(1000, int(opts.get("contrast", 0)) * 8))
                except Exception:
                    pass

                image = item.Transfer()
                raw = bytes(image.FileData.BinaryData)
                pil_img = PILImage.open(io.BytesIO(raw))
                if pil_img.mode in ("RGBA", "P", "LA"):
                    pil_img = pil_img.convert("RGB")

                # ── Pillow post-processing ──────────────────────────────────
                from PIL import ImageEnhance, ImageFilter

                # Gamma correction
                gamma_val = float(opts.get("gamma", 2.2))
                if NUMPY_AVAILABLE and abs(gamma_val - 1.0) > 0.05:
                    arr = np.array(pil_img, dtype=np.float32) / 255.0
                    arr = np.power(arr, 1.0 / gamma_val)
                    pil_img = PILImage.fromarray((arr * 255).clip(0, 255).astype(np.uint8))

                if opts.get("unsharp"):
                    pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))

                if opts.get("descreen"):
                    pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=0.8))

                img_opt = opts.get("img_option", "none")
                if img_opt == "enhance_text":
                    pil_img = pil_img.convert("L")
                    pil_img = ImageEnhance.Contrast(pil_img).enhance(2.0)
                    pil_img = pil_img.convert("RGB")
                elif img_opt == "remove_bg":
                    pil_img = pil_img.convert("L")
                    pil_img = pil_img.point(lambda x: 255 if x > 200 else x)
                    pil_img = pil_img.convert("RGB")

                border = opts.get("border_fill", "none")
                if border in ("white", "black"):
                    fill_c = (255, 255, 255) if border == "white" else (0, 0, 0)
                    bw, bh = pil_img.size
                    m = max(4, int(min(bw, bh) * 0.005))
                    from PIL import ImageDraw as _ID
                    drw = _ID.Draw(pil_img)
                    drw.rectangle([0, 0, bw-1, m], fill=fill_c)
                    drw.rectangle([0, bh-m-1, bw-1, bh-1], fill=fill_c)
                    drw.rectangle([0, 0, m, bh-1], fill=fill_c)
                    drw.rectangle([bw-m-1, 0, bw-1, bh-1], fill=fill_c)

                pil_img.save(output_path, "PNG", optimize=False)
                return output_path

            except RuntimeError:
                raise
            except Exception as e:
                last_err = e
                err_str = str(e)
                if "-2145320954" in err_str or "ocupado" in err_str.lower() or "busy" in err_str.lower():
                    if attempt < 2:
                        log.warning(f"Scanner busy (attempt {attempt+1}), retrying in 2s...")
                        time.sleep(2)
                        continue
                    raise RuntimeError(
                        "El escáner está ocupado.\n"
                        "Cerrá Epson Scan 2 o cualquier otra aplicación que use el escáner, "
                        "luego volvé a intentarlo."
                    )
                raise RuntimeError(f"Error al escanear: {e}")
        raise RuntimeError(f"Error al escanear después de 3 intentos: {last_err}")
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
