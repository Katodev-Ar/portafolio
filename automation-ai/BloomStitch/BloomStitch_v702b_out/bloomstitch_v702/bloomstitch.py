"""
BloomStitch v7.2 - by BloomScans
· v6.0: Árbol batch expandible — muestra archivos dentro de carpeta/zip/psd
· v6.0: Editor de nombre de capítulos con plantilla {n}
· v6.0: Formato de exportación en modo simple
· v6.0: Procesamiento paralelo (ThreadPoolExecutor) — más velocidad
· v6.0: Stitch optimizado con BILINEAR para resize y menos copies en RAM
· v6.7: Carpeta de salida por defecto al lado de la carpeta original
· v6.7: Ordenamiento de archivos al agregar (menú de métodos)
· v6.7: Sonido de inicio corregido
· v6.8: Botón "Abrir carpeta" al finalizar
· v6.8: Selección múltiple de carpetas en modo simple
· v6.8: Sonido de inicio mejorado con fallbacks
· v6.9: Botón abrir carpeta corregido en batch
· v6.9: Selector múltiple de carpetas con diálogo propio
· v6.9: PSD habilitado como entrada
· v7.0: Integración con Google Drive  (PSD → WEBP directo desde la nube)
· v7.1: Client secret embebido — sin archivo externo
· v7.1: Detección de carpeta fuente flexible (cualquier patrón de nombre)
· v7.1: EXE más liviano — assets van al lado del ejecutable
· v7.2: Detección difusa de carpetas (fuzzy match)
· v7.2: Cache local del escaneo Drive
· v7.2: Descarga paralela de PSDs
· v7.2: Thumbnail de PSD en tabla
· v7.2: Indicador verde/naranja de estado de procesamiento
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading, os, sys, zipfile, subprocess, json, math, shutil, tempfile, re, struct, multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_OK = True
except ImportError:
    DND_OK = False
# ── Google Drive (auto-instala si faltan)
def _ensure_gdrive_deps():
    """Instala google-auth-oauthlib y google-api-python-client si no están presentes.
    NOTA: cuando el programa está compilado como .exe (frozen), las librerías ya vienen
    embebidas por PyInstaller — no se intenta instalar nada para evitar spawn infinito.
    """
    if getattr(sys, "frozen", False):
        return  # En .exe las libs van embebidas; pip con sys.executable causaría spawn infinito
    needed = []
    try:
        import google.oauth2.credentials  # noqa
    except ImportError:
        needed.append("google-auth-oauthlib")
    try:
        import googleapiclient.discovery  # noqa
    except ImportError:
        needed.append("google-api-python-client")
    if needed:
        import subprocess
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet"] + needed,
            capture_output=True,
            timeout=120,
        )

_ensure_gdrive_deps()

GDRIVE_LIBS_OK = False
GDRIVE_IMPORT_ERROR = ""
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request as GRequest
    from googleapiclient.discovery import build as gdrive_build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
    import io as _io
    GDRIVE_LIBS_OK = True
except ImportError as _e:
    GDRIVE_IMPORT_ERROR = str(_e)

GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Client secret embebido — no se necesita credentials.json externo
# (generado desde Google Cloud Console, proyecto stitch-488305)
GDRIVE_CLIENT_SECRET_EMBEDDED = {
    "installed": {
        "client_id":     "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com.apps.googleusercontent.com",
        "project_id":    "stitch-488305",
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "YOUR_GOOGLE_CLIENT_SECRET",
        "redirect_uris": ["http://localhost"]
    }
}
GDRIVE_TOKEN  = None   # se asigna en _setup_window
GDRIVE_CACHE  = None   # se asigna en _setup_window — cache del escaneo

# ─── RUTAS
if getattr(sys, 'frozen', False):
    APP_DIR  = Path(sys._MEIPASS)
    WORK_DIR = Path(sys.executable).parent
else:
    APP_DIR  = Path(__file__).parent
    WORK_DIR = APP_DIR

CONFIG_FILE = WORK_DIR / "bloomstitch_config.json"
ICON_FILE   = APP_DIR  / "icon.png"       # logo BloomScan con texto (448×289)
ICON_ALT    = APP_DIR  / "icon_alt.png"   # conejito azul solo (151×257)
ICON_ICO    = APP_DIR  / "icon.ico"
# bloom_upscaler.exe es el exe renombrado de waifu2x-ncnn-vulkan
UPSCALER_EXE = WORK_DIR / "bloom_upscaler.exe"
WAIFU_EXE    = UPSCALER_EXE  # alias interno para compatibilidad
# startup.wav: cuando corre como .exe debe estar al lado del ejecutable (WORK_DIR),
# no dentro del paquete. Así winsound puede accederlo sin problemas.
STARTUP_SND = WORK_DIR / "startup.wav" if (WORK_DIR / "startup.wav").exists() \
              else APP_DIR / "startup.wav"

def _find_models(model_name):
    for c in [WORK_DIR / model_name, APP_DIR / model_name]:
        if c.exists(): return c
    return WORK_DIR / model_name

FORMATS_IN  = {".jpg",".jpeg",".png",".webp",".bmp",".gif",
               ".tiff",".tif",".psd",".psb",".avif"}
FORMATS_OUT = ["PNG","JPEG","WEBP","BMP","TIFF"]

# ═══════════════════════════════════════════════════════════════════════════════
#  PSD / PSB READER
# ═══════════════════════════════════════════════════════════════════════════════
def open_psd_psb(path):
    """Abre PSD/PSB con cascada: psd-tools → PIL nativo → parser propio."""
    try:
        import psd_tools
        psd = psd_tools.PSDImage.open(path)
        img = psd.composite() or psd.topil()
        if img: return img.convert("RGBA")
    except Exception: pass

    if path.lower().endswith(".psd"):
        try:
            img = Image.open(path); img.load(); return img
        except Exception: pass

    return _parse_psd_binary(path)


def _parse_psd_binary(path):
    """Lee la imagen compuesta (merged) de PSD v1 y PSB v2 sin librerías externas."""
    with open(path, "rb") as f:
        raw = f.read()
    pos = 0
    def rd(n):
        nonlocal pos; v = raw[pos:pos+n]; pos += n; return v
    def u16(): return struct.unpack(">H", rd(2))[0]
    def u32(): return struct.unpack(">I", rd(4))[0]
    def u64(): return struct.unpack(">Q", rd(8))[0]

    if rd(4) != b"8BPS": raise ValueError("No es PSD/PSB")
    ver   = u16(); is_psb = (ver == 2)
    rd(6)  # reserved
    channels  = u16()
    height    = u32(); width = u32()
    depth     = u16(); color_mode = u16()

    pos += 4 + u32()   # color mode data
    pos += 4 + u32()   # image resources
    layer_len = u64() if is_psb else u32()
    pos += layer_len   # layer & mask info

    compression = u16()
    n_ch = min(channels, 4)
    row_bytes = width * (depth // 8)
    total_rows = height * n_ch
    channel_data = []

    if compression == 0:   # Raw
        for c in range(n_ch):
            ch = [rd(row_bytes) for _ in range(height)]
            channel_data.append(ch)

    elif compression == 1:  # RLE PackBits
        row_lens = [u32() if is_psb else u16() for _ in range(total_rows)]
        for c in range(n_ch):
            ch = []
            for r in range(height):
                rlen = row_lens[c * height + r]
                rdata = rd(rlen)
                out = bytearray(); i = 0
                while i < len(rdata):
                    h = rdata[i]; i += 1
                    if h > 127: h -= 256
                    if h >= 0:
                        out += rdata[i:i+h+1]; i += h+1
                    else:
                        if i < len(rdata): out += bytes([rdata[i]]) * (1-h); i += 1
                ch.append(bytes(out[:row_bytes]))
            channel_data.append(ch)

    elif compression in (2, 3):  # ZIP
        import zlib
        blob = raw[pos:]
        try:    uc = zlib.decompress(blob)
        except: uc = zlib.decompress(blob, -15)
        ch_size = height * row_bytes
        for c in range(n_ch):
            blk = uc[c*ch_size:(c+1)*ch_size]
            channel_data.append([blk[r*row_bytes:(r+1)*row_bytes] for r in range(height)])
    else:
        raise ValueError(f"Compresión {compression} no soportada")

    def to8(rows):
        out = bytearray()
        for row in rows:
            if depth == 8:  out += row
            elif depth == 16:
                for i in range(0, len(row), 2): out.append(row[i] if i < len(row) else 0)
            elif depth == 32:
                for i in range(0, len(row), 4):
                    if i+4 <= len(row):
                        v = struct.unpack(">f", row[i:i+4])[0]
                        out.append(max(0, min(255, int(v*255))))
        return bytes(out)

    N = width * height
    if color_mode == 3:    # RGB
        R,G,B = to8(channel_data[0]),to8(channel_data[1]),to8(channel_data[2])
        if n_ch >= 4:
            A = to8(channel_data[3])
            pix = bytes(v for i in range(N) for v in (R[i],G[i],B[i],A[i]))
            return Image.frombytes("RGBA",(width,height),pix)
        pix = bytes(v for i in range(N) for v in (R[i],G[i],B[i]))
        return Image.frombytes("RGB",(width,height),pix)
    elif color_mode == 4:  # CMYK (PS stores inverted)
        C2,M,Y,K = [to8(channel_data[i]) for i in range(4)]
        pix = bytes(v for i in range(N) for v in (255-C2[i],255-M[i],255-Y[i],255-K[i]))
        return Image.frombytes("CMYK",(width,height),pix).convert("RGB")
    elif color_mode in (0,1,8):  # Gray/Bitmap/Duotone
        return Image.frombytes("L",(width,height),to8(channel_data[0]))
    else:
        raise ValueError(f"Modo de color {color_mode} no soportado")


def open_image_safe(path):
    """Abre cualquier imagen; usa parser propio para PSD/PSB."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".psd", ".psb"):
        img = open_psd_psb(path)
        if img is None: raise IOError(f"No se pudo abrir: {os.path.basename(path)}")
        return img
    return Image.open(path)


# ═══════════════════════════════════════════════════════════════════════════════
#  PALETAS  (oscura y clara)
# ═══════════════════════════════════════════════════════════════════════════════
DARK = {
    "bg":      "#080b12", "bg2":    "#0d1120", "bg3":    "#111827",
    "bg4":     "#182030", "bg5":    "#1e2840", "border": "#1e2d47",
    "border2": "#253248", "teal":   "#00cfb5", "teal2":  "#009e8a",
    "teal3":   "#006d5e", "cyan":   "#1adeff", "text":   "#ccd9ee",
    "text2":   "#7a9cbf", "dim":    "#354d6a", "bright": "#ffffff",
    "err":     "#ef4444", "err2":   "#b91c1c", "ok":     "#22c55e",
    "warn":    "#f59e0b", "folder": "#60a5fa",
}
LIGHT = {
    "bg":      "#f0f2f7", "bg2":    "#e2e6f0", "bg3":    "#d8dce8",
    "bg4":     "#c8cedd", "bg5":    "#b8c0d2", "border": "#a0aabf",
    "border2": "#8890a8", "teal":   "#007a6e", "teal2":  "#005f55",
    "teal3":   "#004840", "cyan":   "#0099bb", "text":   "#1a2235",
    "text2":   "#3a4f70", "dim":    "#7a8ca8", "bright": "#000000",
    "err":     "#cc2222", "err2":   "#991111", "ok":     "#157a30",
    "warn":    "#a06000", "folder": "#2255cc",
}
C = dict(DARK)   # paleta activa (mutable)

def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2],16) for i in (0,2,4))

def lerp(c1,c2,t):
    r1,g1,b1=_rgb(c1); r2,g2,b2=_rgb(c2)
    return "#{:02x}{:02x}{:02x}".format(int(r1+(r2-r1)*t),int(g1+(g2-g1)*t),int(b1+(b2-b1)*t))

def make_btn(parent,text,cmd,bg=None,fg=None,hover_bg=None,hover_fg=None,
             font=None,small=False,**kw):
    _bg=bg or C["teal"]; _fg=fg or C["bg"]
    _hbg=hover_bg or C["cyan"]; _hfg=hover_fg or _fg
    _font=font or (("Segoe UI",8) if small else ("Segoe UI",9,"bold"))
    _py=3 if small else 7; _px=kw.pop("padx",8 if small else 14)
    b=tk.Button(parent,text=text,command=cmd,bg=_bg,fg=_fg,font=_font,relief="flat",
                cursor="hand2",padx=_px,pady=_py,bd=0,highlightthickness=0,
                activebackground=_hbg,activeforeground=_hfg,**kw)
    st={"t":0.0,"dir":0,"job":None}
    def _tick():
        st["t"]=max(0.0,min(1.0,st["t"]+st["dir"]*0.18))
        try: b.config(bg=lerp(_bg,_hbg,st["t"]),fg=lerp(_fg,_hfg,st["t"]))
        except tk.TclError: return
        if 0.0<st["t"]<1.0: st["job"]=b.after(12,_tick)
        else: st["job"]=None
    def _e(e): st["dir"]=1; st["job"] or (st.__setitem__("job",b.after(12,_tick)))
    def _l(e): st["dir"]=-1; st["job"] or (st.__setitem__("job",b.after(12,_tick)))
    b.bind("<Enter>",_e); b.bind("<Leave>",_l)
    b._bg_orig=_bg; b._hbg_orig=_hbg; b._fg_orig=_fg; b._state=st
    return b

def btn_set_state(b,state):
    if state=="disabled": b.config(state="disabled",bg=C["dim"],fg=C["dim"],cursor="",relief="flat")
    else: b.config(state="normal",bg=b._bg_orig,fg=b._fg_orig,cursor="hand2",relief="flat")


# ═══════════════════════════════════════════════════════════════════════════════
#  SPLASH
# ═══════════════════════════════════════════════════════════════════════════════
class SplashScreen:
    def __init__(self,root):
        self.root=root; self._prog=0
        # Play startup sound in background thread (non-blocking)
        _snd_path = str(STARTUP_SND)
        def _play_sound():
            if not STARTUP_SND.exists():
                return
            if sys.platform == "win32":
                # Intento 1: winsound nativo
                try:
                    import winsound
                    winsound.PlaySound(_snd_path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
                    return
                except Exception:
                    pass
                # Intento 2: pygame como fallback
                try:
                    import pygame
                    pygame.mixer.pre_init(44100, -16, 2, 512)
                    pygame.mixer.init()
                    snd = pygame.mixer.Sound(_snd_path)
                    snd.play()
                    import time; time.sleep(snd.get_length() + 0.2)
                    return
                except Exception:
                    pass
            else:
                try:
                    import subprocess as _sp
                    player = "afplay" if sys.platform == "darwin" else "aplay"
                    _sp.run([player, _snd_path], capture_output=True, timeout=15)
                except Exception:
                    pass
        threading.Thread(target=_play_sound, daemon=True).start()
        self.win=tk.Toplevel(root); self.win.overrideredirect(True)
        self.win.configure(bg=C["bg"])
        W,H=500,310
        sw,sh=root.winfo_screenwidth(),root.winfo_screenheight()
        self.win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.win.attributes("-topmost",True)
        cv=tk.Canvas(self.win,width=W,height=H,bg=C["bg"],highlightthickness=0)
        cv.pack(fill="both",expand=True); self.cv=cv; self.W=W; self.H=H
        # gradient bg
        for i in range(H): cv.create_line(0,i,W,i,fill=lerp(C["bg2"],C["bg"],i/H))
        cv.create_line(0,0,W,0,fill=C["teal"],width=2)
        cv.create_rectangle(0,0,W-1,H-1,outline=C["border2"],fill="")
        # logo
        self._logo_drawn = False
        if PIL_OK:
            for lf in [ICON_FILE, ICON_ALT]:   # logo azul en splash
                if lf.exists():
                    try:
                        raw=Image.open(lf).convert("RGBA")
                        raw.thumbnail((110,80),Image.LANCZOS)
                        # Composite onto splash bg
                        def _hex2rgb(hx):
                            hx=hx.lstrip("#"); return tuple(int(hx[i:i+2],16) for i in (0,2,4))
                        bg_rgb=_hex2rgb(C["bg2"])+(255,)
                        bg_layer=Image.new("RGBA",(raw.width,raw.height),bg_rgb)
                        bg_layer.alpha_composite(raw)
                        ph=ImageTk.PhotoImage(bg_layer.convert("RGB"))
                        cv.create_image(W//2,65,image=ph); cv._logo=ph
                        self._logo_drawn=True; break
                    except: pass
        if not self._logo_drawn:
            self._draw_bunny(cv,W//2-31,10,0.48)
        cv.create_text(W//2,130,text="BloomStitch",fill=C["bright"],font=("Segoe UI",26,"bold"))
        cv.create_text(W//2,157,text="by BloomScans",fill=C["teal"],font=("Segoe UI",10))
        cv.create_line(W//2-80,173,W//2+80,173,fill=C["border2"])
        bx,by,bw,bh=130,255,240,5
        cv.create_rectangle(bx,by,bx+bw,by+bh,fill=C["bg4"],outline="")
        self._bar=cv.create_rectangle(bx,by,bx,by+bh,fill=C["teal"],outline="")
        self._bx,self._bw,self._by,self._bh=bx,bw,by,bh
        self._lbl=cv.create_text(W//2,270,text="Iniciando…",fill=C["dim"],font=("Segoe UI",9))
        cv.create_text(W//2,285,text="v7.2  ·  by BloomScans",fill=C["dim"],font=("Segoe UI",7))
        self._anim()

    def _draw_bunny(self,cv,ox,oy,s):
        def e(x1,y1,x2,y2,f):
            cv.create_oval(int(ox+x1*s),int(oy+y1*s),int(ox+x2*s),int(oy+y2*s),fill=f,outline="")
        e(15,0,42,65,C["teal"]); e(78,0,105,65,C["teal"])
        e(20,4,37,55,C["bg2"]); e(83,4,100,55,C["bg2"])
        e(10,60,110,160,C["teal"])
        e(25,78,48,100,"#c5ede8"); e(72,78,95,100,"#c5ede8")
        e(30,83,43,95,C["bg"]); e(77,83,90,95,C["bg"])

    def _anim(self):
        if self._prog>=100: return
        self._prog=min(self._prog+1.5,100)
        fw=int(self._bw*self._prog/100)
        self.cv.coords(self._bar,self._bx,self._by,self._bx+fw,self._by+self._bh)
        col=lerp(C["teal3"],C["teal"],self._prog/50) if self._prog<50 else lerp(C["teal"],C["cyan"],(self._prog-50)/50)
        self.cv.itemconfig(self._bar,fill=col)
        msgs={0:"Iniciando…",25:"Cargando módulos…",55:"Preparando interfaz…",85:"¡Casi listo!"}
        msg="Iniciando…"
        for k,v in sorted(msgs.items()):
            if self._prog>=k: msg=v
        self.cv.itemconfig(self._lbl,text=msg)
        self.win.after(18,self._anim)

    def close(self):
        try: self.win.destroy()
        except: pass


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════════════════════
class BloomStitch:
    def __init__(self,root):
        self.root=root; self.files=[]; self.batch_entries=[]
        self._phase=0; self._drag_idx=None; self._adv_open=False
        self._btree_drag_entry=None; self._btree_drag_row=None; self._btree_drag_indicator=None
        self._preview_visible=True; self._preview_saved_width=240
        self._pv_redraw_job=None
        self._batch_mode=False; self._preview_path=None
        self._dark_mode=True
        # preview zoom/pan state
        self._pv_zoom=1.0; self._pv_ox=0; self._pv_oy=0
        self._pv_drag_start=None; self._pv_img_full=None
        self._batch_preview_files=[]; self._batch_preview_idx=0

        # ── Google Drive state ──────────────────────────────────────────────
        self._gd_service   = None        # googleapiclient resource
        self._gd_creds     = None        # Credentials object
        self._gd_src       = {"id": None, "name": "— sin seleccionar —"}
        self._gd_dst       = {"id": None, "name": "— sin seleccionar —"}
        self._gd_running   = False
        self._load_config(); self._setup_window()
        self._setup_styles(); self._build_ui()
        self._check_deps(); self._tick_accent()

    # ── SETUP ─────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("BloomStitch"); self.root.geometry("980x740")
        self.root.minsize(680,500); self.root.configure(bg=C["bg2"])
        if ICON_ICO.exists():
            try: self.root.iconbitmap(str(ICON_ICO))
            except: pass
        if PIL_OK:
            # Usar conejito azul como ícono de ventana
            for lf in [ICON_ALT, ICON_FILE]:
                if lf.exists():
                    try:
                        ico=ImageTk.PhotoImage(Image.open(lf).resize((32,32),Image.LANCZOS))
                        self.root.iconphoto(True,ico); self._ico=ico; break
                    except: pass
        global GDRIVE_TOKEN
        GDRIVE_TOKEN = WORK_DIR / 'bloomstitch_gdrive_token.json'
        GDRIVE_CACHE = WORK_DIR / 'bloomstitch_gdrive_cache.json'
        self.root.update_idletasks()
        sw,sh=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
        self.root.geometry(f"980x740+{(sw-980)//2}+{(sh-740)//2}")

    def _load_config(self):
        d={"out_format":"PNG","quality":95,"stitch_height":10000,"align":"smallest",
           "convert_enabled":True,"stitch_enabled":True,"waifu_enabled":False,
           "waifu_scale":"2","waifu_noise":"2","waifu_model":"models-cunet",
           "output_dir":"","upscaler_exe":str(WAIFU_EXE),"output_mode":"images",
           "advanced_open":False,"dark_mode":True,
           "batch_zip_folder":False,"batch_zip_folder_path":"",
           "name_template":"{n}_BloomStitch","name_use_num":True,
           "sort_method":"name_asc","workers_convert":0,"workers_stitch":0,"workers_batch":0,
           "profiles":[],"gdrive_raw_folder":"1_Raw"}
        try:
            if CONFIG_FILE.exists(): d.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except: pass
        self.cfg=d; self._adv_open=d.get("advanced_open",False)
        self._dark_mode=d.get("dark_mode",True)
        C.update(DARK if self._dark_mode else LIGHT)

    def _save_config(self):
        try: CONFIG_FILE.write_text(json.dumps(self.cfg,indent=2),encoding="utf-8")
        except: pass

    def _setup_styles(self):
        s=ttk.Style(); s.theme_use("clam")
        s.configure("Bloom.Horizontal.TProgressbar",
            troughcolor=C["bg4"],background=C["teal"],
            bordercolor=C["bg4"],lightcolor=C["teal"],darkcolor=C["teal2"])
        s.configure("TCombobox",fieldbackground=C["bg4"],background=C["bg4"],
            foreground=C["text"],selectbackground=C["teal"],selectforeground=C["bg"],arrowcolor=C["teal"])
        s.map("TCombobox",fieldbackground=[("readonly",C["bg4"])],foreground=[("readonly",C["text"])])
        s.configure("Vertical.TScrollbar",background=C["bg4"],troughcolor=C["bg3"],
            arrowcolor=C["dim"],bordercolor=C["bg3"])

    # ── THEME TOGGLE ──────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        C.update(DARK if self._dark_mode else LIGHT)
        self.cfg["dark_mode"] = self._dark_mode; self._save_config()
        # Reopen — rebuild is simplest for full theme change
        self.root.destroy()
        # Re-launch
        import subprocess as sp
        sp.Popen([sys.executable, __file__])

    # ── BUILD UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr=tk.Frame(self.root,bg=C["bg2"],height=56); hdr.pack(fill="x"); hdr.pack_propagate(False)
        lf=tk.Frame(hdr,bg=C["bg2"]); lf.pack(side="left",padx=14,pady=8)

        # Logo: mostrar logo BloomScan (azul con fondo transparente)
        logo_shown=False
        if PIL_OK:
            for lf2 in [ICON_FILE, ICON_ALT]:
                if lf2.exists() and not logo_shown:
                    try:
                        raw=Image.open(lf2).convert("RGBA")
                        h=42; w=int(h*raw.width/raw.height)
                        raw=raw.resize((w,h),Image.LANCZOS)
                        # Composite onto header bg color so transparency looks right
                        def _hex2rgb(hx):
                            hx=hx.lstrip("#"); return tuple(int(hx[i:i+2],16) for i in (0,2,4))
                        bg_rgb=_hex2rgb(C["bg2"])+(255,)
                        bg_layer=Image.new("RGBA",(w,h),bg_rgb)
                        bg_layer.alpha_composite(raw)
                        ph=ImageTk.PhotoImage(bg_layer.convert("RGB"))
                        lb=tk.Label(lf,image=ph,bg=C["bg2"]); lb.pack(side="left",padx=(0,8))
                        lb._img=ph; logo_shown=True; break
                    except: pass

        if not logo_shown:
            cv=tk.Canvas(lf,width=32,height=32,bg=C["bg2"],highlightthickness=0)
            cv.pack(side="left",padx=(0,10)); self._draw_mini_bunny(cv)

        nf=tk.Frame(lf,bg=C["bg2"]); nf.pack(side="left")
        tk.Label(nf,text="BloomStitch",bg=C["bg2"],fg=C["bright"],font=("Segoe UI",13,"bold")).pack(anchor="w")
        tk.Label(nf,text="v7.2  ·  by BloomScans",bg=C["bg2"],fg=C["dim"],font=("Segoe UI",7)).pack(anchor="w")

        # Botones derecha del header
        rbf=tk.Frame(hdr,bg=C["bg2"]); rbf.pack(side="right",padx=10)
        # Tema claro/oscuro
        theme_lbl="☀ Claro" if self._dark_mode else "🌙 Oscuro"
        make_btn(rbf,theme_lbl,self._toggle_theme,
                 bg=C["bg4"],fg=C["text2"],hover_bg=C["bg5"],hover_fg=C["text"],small=True
                 ).pack(side="right",padx=(0,6),pady=14)
        # Avanzado
        adv_lbl="⚙ Avanzado ▲" if self._adv_open else "⚙ Avanzado ▼"
        self._adv_btn=make_btn(rbf,adv_lbl,self._toggle_advanced,
            bg=C["bg4"],fg=C["teal"],hover_bg=C["bg5"],hover_fg=C["cyan"],small=True)
        self._adv_btn.pack(side="right",padx=(0,4),pady=14)
        # Drive ya es pestaña principal — sin botón en header

        tk.Frame(hdr,bg=C["border"],height=1).place(relx=0,rely=1.0,relwidth=1,anchor="sw")
        self._accent=tk.Canvas(self.root,height=2,bg=C["bg"],highlightthickness=0)
        self._accent.pack(fill="x")
        tk.Frame(self.root,bg=C["border2"],height=1).pack(fill="x")

        # Footer FIRST so it's always visible regardless of panel size
        self._build_footer()

        # Main content area: notebook with tabs (Stitch / Drive / Perfiles)
        style = ttk.Style()
        style.configure("Main.TNotebook", background=C["bg"], borderwidth=0)
        style.configure("Main.TNotebook.Tab", background=C["bg3"], foreground=C["text2"],
                        padding=[20, 8], font=("Segoe UI", 10, "bold"))
        style.map("Main.TNotebook.Tab",
                  background=[("selected", C["bg"])],
                  foreground=[("selected", C["teal"])])
        style.configure("Opts.TNotebook", background=C["bg2"], borderwidth=0, tabmargins=[0,0,0,0])
        style.configure("Opts.TNotebook.Tab", background=C["bg2"], foreground=C["dim"],
                        padding=[22, 9], font=("Segoe UI", 9, "bold"))
        style.map("Opts.TNotebook.Tab",
                  background=[("selected", C["bg3"])],
                  foreground=[("selected", C["teal"])])

        self._main_nb = ttk.Notebook(self.root, style="Main.TNotebook")
        self._main_nb.pack(fill="both", expand=True)

        # ── Pestaña Stitch ────────────────────────────────────────────────────
        stitch_tab = tk.Frame(self._main_nb, bg=C["bg"])
        self._main_nb.add(stitch_tab, text="  ✂  Stitch  ")
        wrap = tk.Frame(stitch_tab, bg=C["bg"]); wrap.pack(fill="both", expand=True)
        P = tk.Frame(wrap, bg=C["bg"]); P.pack(fill="both", expand=True)
        self._scroll_canvas = None
        self._build_panel(P)

        # ── Pestaña Google Drive ──────────────────────────────────────────────
        drive_tab = tk.Frame(self._main_nb, bg=C["bg"])
        self._main_nb.add(drive_tab, text="  ☁  Drive  ")
        self._build_drive_tab(drive_tab)

        # Global mousewheel for scrolling options pane
        self.root.bind_all("<MouseWheel>",self._on_global_scroll)
        # Linux
        self.root.bind_all("<Button-4>",lambda e:self._on_global_scroll_linux(e,-1))
        self.root.bind_all("<Button-5>",lambda e:self._on_global_scroll_linux(e,1))
        if DND_OK:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>",self._on_drop)

    def _widget_inside(self, widget, container):
        """Check if widget is container or a descendant of it."""
        w=widget
        while w:
            if w is container: return True
            try: w=w.master
            except: break
        return False

    def _on_global_scroll(self,e):
        widget=self.root.winfo_containing(e.x_root,e.y_root)
        if not widget: return
        # Let preview handle its own zoom-scroll
        if hasattr(self,'_prev_canvas') and self._widget_inside(widget,self._prev_canvas):
            return
        # Let batch tree handle its own scroll (already bound)
        if hasattr(self,'_tree_canvas') and self._widget_inside(widget,self._tree_canvas):
            return
        # Scroll the options pane
        if self._scroll_canvas:
            self._scroll_canvas.yview_scroll(int(-1*(e.delta/120)),"units")

    def _on_global_scroll_linux(self,e,direction):
        widget=self.root.winfo_containing(e.x_root,e.y_root)
        if not widget: return
        if hasattr(self,'_prev_canvas') and self._widget_inside(widget,self._prev_canvas): return
        if hasattr(self,'_tree_canvas') and self._widget_inside(widget,self._tree_canvas): return
        if self._scroll_canvas:
            self._scroll_canvas.yview_scroll(direction,"units")

    def _draw_mini_bunny(self,cv):
        s=0.215; ox=0; oy=0
        def e(x1,y1,x2,y2,f):
            cv.create_oval(int(ox+x1*s),int(oy+y1*s),int(ox+x2*s),int(oy+y2*s),fill=f,outline="")
        e(10,60,110,160,C["teal"]); e(15,0,42,65,C["teal"]); e(78,0,105,65,C["teal"])
        e(20,4,37,55,C["bg2"]); e(83,4,100,55,C["bg2"])
        e(25,78,48,100,"#c5ede8"); e(72,78,95,100,"#c5ede8")
        e(30,83,43,95,C["bg"]); e(77,83,90,95,C["bg"])

    def _tick_accent(self):
        self._phase=(self._phase+2)%360
        cv=self._accent; cv.update_idletasks()
        w=cv.winfo_width() or 980; cv.delete("all"); N=70
        for i in range(N):
            ph=((i/N)+self._phase/360)%1.0
            col=lerp(C["teal3"],C["cyan"],ph*2) if ph<0.5 else lerp(C["cyan"],C["teal3"],(ph-0.5)*2)
            cv.create_rectangle(int(w*i/N),0,int(w*(i+1)/N),2,fill=col,outline="")
        self.root.after(40,self._tick_accent)

    # ── PANEL ─────────────────────────────────────────────────────────────────
    def _build_panel(self,P):
        px=dict(padx=20)
        # Init s_fmtv early so simple mode format bar can use it
        self.s_fmtv=tk.StringVar(value=self.cfg["out_format"])

        # ── Vertical PanedWindow: top=files area, bottom=output+options ────────
        vpaned=tk.PanedWindow(P,orient="vertical",bg=C["bg"],sashwidth=7,
                               sashrelief="flat",sashpad=0,showhandle=True,
                               bd=0,relief="flat",handlesize=8,handlepad=6)
        vpaned.pack(fill="both",expand=True)
        top_pane=tk.Frame(vpaned,bg=C["bg"])
        vpaned.add(top_pane,minsize=140,height=320,stretch="always")
        _bot_outer=tk.Frame(vpaned,bg=C["bg"])
        vpaned.add(_bot_outer,minsize=80,stretch="always")
        vpaned.configure(background=C["border2"])
        # Force canvas repaint on sash drag to eliminate render artifacts
        def _vpaned_repaint(e):
            try:
                self._tree_canvas.update_idletasks()
                self._tree_canvas.configure(scrollregion=self._tree_canvas.bbox("all"))
            except: pass
        vpaned.bind("<B1-Motion>",_vpaned_repaint)
        # Scroll canvas for bottom pane (options scroll when window is small)
        _bot_scv=tk.Canvas(_bot_outer,bg=C["bg"],highlightthickness=0)
        _bot_scb=ttk.Scrollbar(_bot_outer,orient="vertical",command=_bot_scv.yview,style="Vertical.TScrollbar")
        _bot_scv.configure(yscrollcommand=_bot_scb.set)
        _bot_scb.pack(side="right",fill="y"); _bot_scv.pack(side="left",fill="both",expand=True)
        bot_pane=tk.Frame(_bot_scv,bg=C["bg"])
        _bot_win=_bot_scv.create_window((0,0),window=bot_pane,anchor="nw")
        _bot_scv.bind("<Configure>",lambda e:_bot_scv.itemconfig(_bot_win,width=e.width))
        bot_pane.bind("<Configure>",lambda e:_bot_scv.configure(scrollregion=_bot_scv.bbox("all")))
        self._scroll_canvas=_bot_scv  # global scroll target

        # ── TOP PANE: header + buttons + files/batch list + preview ───────────
        P_top=top_pane  # alias
        self._sh(P_top,"📂  Archivos / Batch")

        # Barra botones
        br=tk.Frame(P_top,bg=C["bg"]); br.pack(fill="x",**px,pady=(0,6))
        make_btn(br,"+ Agregar",self._add_unified_smart).pack(side="left",padx=(0,6))
        make_btn(br,"✕ Limpiar",self._clear_files,bg=C["bg4"],fg=C["err"],
                 hover_bg=C["err2"],hover_fg=C["bright"]).pack(side="left",padx=(0,16))
        self._batch_var=tk.BooleanVar(value=False)
        self._toggle(br,self._batch_var,self._on_mode_change).pack(side="left",padx=(0,5))
        tk.Label(br,text="Modo Batch",bg=C["bg"],fg=C["text2"],font=("Segoe UI",9)).pack(side="left")
        # Preview open/close button (always visible in button bar)
        self._pv_br_btn=self._sbtn(br,"◀ Preview",self._toggle_preview)
        self._pv_br_btn.pack(side="right")

        # Lista + Preview — panel divisor horizontal ajustable
        paned=tk.PanedWindow(P_top,orient="horizontal",bg=C["bg"],sashwidth=6,
                              sashrelief="flat",sashpad=0,showhandle=False,
                              bd=0,relief="flat")
        paned.pack(fill="both",expand=True,padx=20,pady=(0,2))
        left=tk.Frame(paned,bg=C["bg"]); paned.add(left,minsize=200,stretch="always")
        self._paned_panel=paned  # save ref
        paned.configure(background=C["border2"])

        # ── BOTTOM PANE: output + options ─────────────────────────────────────
        P=bot_pane  # redirect remaining panel builds to bottom pane

        # Modo normal: lista
        self._simple_frame=tk.Frame(left,bg=C["bg"]); self._simple_frame.pack(fill="both",expand=True)
        box=self._cframe(self._simple_frame); box.pack(fill="both",expand=True)
        vsb=tk.Scrollbar(box,width=7,bg=C["bg4"],troughcolor=C["bg3"]); vsb.pack(side="right",fill="y")
        self.s_lb=tk.Listbox(box,height=9,bg=C["bg3"],fg=C["text"],selectbackground=C["teal"],
            selectforeground=C["bg"],font=("Consolas",9),relief="flat",bd=0,
            activestyle="none",yscrollcommand=vsb.set)
        self.s_lb.pack(fill="both",expand=True,padx=6,pady=6)
        vsb.config(command=self.s_lb.yview)
        self.s_lb.bind("<Delete>",self._remove_sel)
        self.s_lb.bind("<<ListboxSelect>>",self._update_preview)
        self.s_lb.bind("<Control-Up>",lambda e:self._move_sel(-1))
        self.s_lb.bind("<Control-Down>",lambda e:self._move_sel(+1))
        self.s_lb.bind("<ButtonPress-1>",self._drag_start_cb)
        self.s_lb.bind("<B1-Motion>",self._drag_motion_cb)
        self.s_lb.bind("<ButtonRelease-1>",self._drag_end_cb)
        if DND_OK:
            self.s_lb.drop_target_register(DND_FILES)
            self.s_lb.dnd_bind("<<Drop>>",self._on_drop)

        bf=tk.Frame(self._simple_frame,bg=C["bg"]); bf.pack(fill="x",pady=(3,0))
        self._sbtn(bf,"▲ Subir",lambda:self._move_sel(-1)).pack(side="left",padx=(0,4))
        self._sbtn(bf,"▼ Bajar",lambda:self._move_sel(+1)).pack(side="left",padx=(0,8))
        # Ordenamiento
        tk.Label(bf,text="Orden:",bg=C["bg"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left")
        SORT_METHODS=[
            ("Nombre ↑","name_asc"),("Nombre ↓","name_desc"),
            ("Número ↑","num_asc"),("Número ↓","num_desc"),
            ("Fecha ↑","date_asc"),("Fecha ↓","date_desc"),
        ]
        sort_labels=[l for l,_ in SORT_METHODS]
        self.s_sortv=tk.StringVar(value=next((l for l,v in SORT_METHODS if v==self.cfg.get("sort_method","name_asc")),sort_labels[0]))
        sort_cb=self._combo(bf,self.s_sortv,sort_labels,10); sort_cb.pack(side="left",padx=(3,6))
        self._sort_methods_map=dict(SORT_METHODS)
        self._sort_labels_map={l:v for l,v in SORT_METHODS}
        def _apply_sort():
            lbl=self.s_sortv.get(); method=self._sort_labels_map.get(lbl,"name_asc")
            self.cfg["sort_method"]=method; self._sort_files(); self._sync_lists()
        self._sbtn(bf,"↕ Ordenar",_apply_sort).pack(side="left",padx=(0,8))
        tk.Label(bf,text="Formato:",bg=C["bg"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left")
        self._combo(bf,self.s_fmtv,FORMATS_OUT,6).pack(side="left",padx=(3,8))
        self.s_ct=tk.Label(bf,text="0 archivo(s)",bg=C["bg"],fg=C["dim"],font=("Segoe UI",8))
        self.s_ct.pack(side="left")

        # Modo batch: árbol
        self._batch_frame=tk.Frame(left,bg=C["bg"])
        self._build_batch_tree(self._batch_frame)

        # ── Preview con zoom/pan ───────────────────────────────────────────────
        right=tk.Frame(paned,bg=C["bg3"],highlightbackground=C["border2"],highlightthickness=1)
        paned.add(right,minsize=120,width=240,stretch="never")

        # Barra zoom + toggle preview
        zbar=tk.Frame(right,bg=C["bg4"]); zbar.pack(fill="x",padx=4,pady=(4,0))
        self._sbtn(zbar,"−",self._pv_zoom_out).pack(side="left")
        self._sbtn(zbar,"+",self._pv_zoom_in).pack(side="left",padx=(2,0))
        self._sbtn(zbar,"⟳",self._pv_reset).pack(side="left",padx=(2,0))
        self._zoom_lbl=tk.Label(zbar,text="100%",bg=C["bg4"],fg=C["text2"],font=("Segoe UI",7))
        self._zoom_lbl.pack(side="left",padx=(4,0))
        self._pv_toggle_btn=self._sbtn(zbar,"◀ Ocultar",self._toggle_preview)
        self._pv_toggle_btn.pack(side="right",padx=(0,2))
        self._paned_right=right  # save ref for toggle

        self._prev_canvas=tk.Canvas(right,bg=C["bg3"],highlightthickness=0,cursor="crosshair")
        self._prev_canvas.pack(fill="both",expand=True,padx=4,pady=(4,2))
        self._prev_canvas.bind("<Configure>",lambda e:self._pv_redraw())
        self._prev_canvas.bind("<MouseWheel>",self._pv_on_scroll)
        self._prev_canvas.bind("<ButtonPress-1>",self._pv_pan_start)
        self._prev_canvas.bind("<B1-Motion>",self._pv_pan_motion)
        self._prev_canvas.bind("<ButtonRelease-1>",self._pv_pan_end)
        self._prev_canvas.bind("<Double-Button-1>",lambda e:self._pv_reset())

        self._prev_info=tk.Label(right,text="",bg=C["bg3"],fg=C["text2"],
            font=("Segoe UI",7),wraplength=230,justify="center")
        self._prev_info.pack(pady=(0,2))

        # Barra de navegación batch (oculta por defecto)
        self._nav_bar=tk.Frame(right,bg=C["bg4"]); # no pack todavía
        self._sbtn(self._nav_bar,"◀",self._pv_batch_prev).pack(side="left",padx=2,pady=2)
        self._nav_lbl=tk.Label(self._nav_bar,text="1/1",bg=C["bg4"],fg=C["text2"],font=("Segoe UI",7))
        self._nav_lbl.pack(side="left",expand=True)
        self._sbtn(self._nav_bar,"▶",self._pv_batch_next).pack(side="right",padx=2,pady=2)

        # ── Sub-notebook: Opciones | Perfiles ────────────────────────────────
        # Custom tab bar — bigger, more breathing room
        _opts_bar = tk.Frame(P, bg=C["bg2"])
        _opts_bar.pack(fill="x", padx=0, pady=(8, 0))
        tk.Frame(P, bg=C["border"], height=1).pack(fill="x")

        opts_nb = ttk.Notebook(P)
        opts_nb.pack(fill="both", expand=True, padx=0, pady=0)
        opts_nb.configure(style="Opts.TNotebook")

        # ── TAB Opciones ──────────────────────────────────────────────────────
        tab_opts = tk.Frame(opts_nb, bg=C["bg"])
        opts_nb.add(tab_opts, text="  ⚙  Opciones  ")

        # Salida
        self._sh(tab_opts,"📤  Salida")
        or_=tk.Frame(tab_opts,bg=C["bg"]); or_.pack(fill="x",padx=20,pady=(0,8))
        self.s_outv=tk.StringVar(value=self.cfg.get("output_dir",""))
        self._entry(or_,self.s_outv,placeholder="Al lado de la carpeta original").pack(side="left",fill="x",expand=True)
        make_btn(or_,"Elegir",self._pick_out,bg=C["bg4"],fg=C["text2"],
                 hover_bg=C["bg5"],hover_fg=C["text"],small=True).pack(side="left",padx=(5,0))

        # Opciones básicas
        self._sh(tab_opts,"⚙  Formato y procesamiento")
        bc=self._cframe(tab_opts); bc.pack(fill="x",padx=20,pady=(0,4))
        rb=tk.Frame(bc,bg=C["bg3"]); rb.pack(fill="x",padx=14,pady=(10,4))
        tk.Label(rb,text="Formato:",bg=C["bg3"],fg=C["text2"],font=("Segoe UI",9)).pack(side="left")
        self._combo(rb,self.s_fmtv,FORMATS_OUT,7).pack(side="left",padx=(4,20))
        tk.Label(rb,text="Altura stitch (px):",bg=C["bg3"],fg=C["text2"],font=("Segoe UI",9)).pack(side="left")
        self.s_hv=tk.StringVar(value=str(self.cfg["stitch_height"]))
        tk.Entry(rb,textvariable=self.s_hv,width=7,bg=C["bg4"],fg=C["text"],relief="flat",
                 font=("Segoe UI",10),insertbackground=C["teal"],highlightthickness=1,
                 highlightbackground=C["border"],highlightcolor=C["teal"]).pack(side="left",padx=(4,0))
        for v in ["5000","10000","15000","30000"]:
            self._sbtn(rb,v,lambda x=v:self.s_hv.set(x)).pack(side="left",padx=(3,0))

        rb2=tk.Frame(bc,bg=C["bg3"]); rb2.pack(fill="x",padx=14,pady=(0,10))
        self.s_cv=tk.BooleanVar(value=self.cfg["convert_enabled"])
        self.s_sv=tk.BooleanVar(value=self.cfg["stitch_enabled"])
        self.s_wv=tk.BooleanVar(value=self.cfg["waifu_enabled"])
        for var,lbl in [(self.s_cv,"🔄 Convertir"),(self.s_sv,"✂ Stitch"),(self.s_wv,"✨ Mejora de calidad")]:
            f=tk.Frame(rb2,bg=C["bg3"]); f.pack(side="left",padx=(0,18))
            self._toggle(f,var,lambda:None).pack(side="left",padx=(0,5))
            tk.Label(f,text=lbl,bg=C["bg3"],fg=C["text"],font=("Segoe UI",9)).pack(side="left")

        # ── TAB Perfiles ──────────────────────────────────────────────────────
        tab_profiles = tk.Frame(opts_nb, bg=C["bg"])
        opts_nb.add(tab_profiles, text="  ⚡  Perfiles  ")
        self._build_profiles_tab(tab_profiles)

        # Hack: redirect P back so Avanzado still appends to tab_opts
        P = tab_opts

        # ── Avanzado (colapsable) ─────────────────────────────────────────────
        self._adv_frame=tk.Frame(P,bg=C["bg"])
        ac=self._cframe(self._adv_frame); ac.pack(fill="x",pady=(0,4))
        tk.Label(ac,text="Alineación de ancho",bg=C["bg3"],fg=C["teal"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14,pady=(8,2))
        r3=tk.Frame(ac,bg=C["bg3"]); r3.pack(fill="x",padx=14,pady=(0,6))
        self.s_alv=tk.StringVar(value=self.cfg.get("align","smallest"))
        for v,l in [("smallest","Más estrecho"),("largest","Más ancho"),("none","Sin escalar")]:
            tk.Radiobutton(r3,text=l,variable=self.s_alv,value=v,bg=C["bg3"],fg=C["text"],
                selectcolor=C["teal"],activebackground=C["bg3"],activeforeground=C["teal"],
                font=("Segoe UI",9),highlightthickness=0).pack(side="left",padx=(0,12))

        tk.Label(ac,text="Exportar como",bg=C["bg3"],fg=C["teal"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14,pady=(4,2))
        r4=tk.Frame(ac,bg=C["bg3"]); r4.pack(fill="x",padx=14,pady=(0,6))
        self.s_omv=tk.StringVar(value=self.cfg.get("output_mode","images"))
        for val,lbl in [("images","Solo imágenes"),("zip","Solo ZIP"),("both","Imágenes + ZIP")]:
            tk.Radiobutton(r4,text=lbl,variable=self.s_omv,value=val,bg=C["bg3"],fg=C["text"],
                selectcolor=C["teal"],activebackground=C["bg3"],activeforeground=C["teal"],
                font=("Segoe UI",9),highlightthickness=0).pack(side="left",padx=(0,14))

        # ── Batch ZIP folder ─────────────────────────────────────────────────
        tk.Label(ac,text="Batch — ZIP de salida",bg=C["bg3"],fg=C["teal"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14,pady=(4,2))
        rbz=tk.Frame(ac,bg=C["bg3"]); rbz.pack(fill="x",padx=14,pady=(0,6))
        self.s_bzfv=tk.BooleanVar(value=self.cfg.get("batch_zip_folder",False))
        self._toggle(rbz,self.s_bzfv,lambda:None).pack(side="left",padx=(0,6))
        tk.Label(rbz,text="Guardar todos los ZIPs en carpeta única",bg=C["bg3"],fg=C["text"],
                 font=("Segoe UI",9)).pack(side="left",padx=(0,10))
        self.s_bzpv=tk.StringVar(value=self.cfg.get("batch_zip_folder_path",""))
        self._entry(rbz,self.s_bzpv,placeholder="Carpeta para ZIPs batch…",width=22).pack(side="left",fill="x",expand=True)
        make_btn(rbz,"…",self._pick_batch_zip_folder,bg=C["bg4"],fg=C["text2"],
                 hover_bg=C["bg5"],hover_fg=C["text"],small=True,padx=6).pack(side="left",padx=(3,0))

        rq=tk.Frame(ac,bg=C["bg3"]); rq.pack(fill="x",padx=14,pady=(0,8))
        tk.Label(rq,text="Calidad JPEG/WEBP:",bg=C["bg3"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left",padx=(0,6))
        self.s_qv=tk.IntVar(value=self.cfg["quality"])
        tk.Scale(rq,variable=self.s_qv,from_=60,to=100,orient="horizontal",
                 bg=C["bg3"],fg=C["text"],highlightthickness=0,troughcolor=C["bg4"],
                 activebackground=C["teal"],sliderrelief="flat",bd=0,length=120).pack(side="left")

        # ── Paralelismo / Workers ─────────────────────────────────────────────
        _cores=os.cpu_count() or 1
        # Recomendaciones según cantidad de cores físicos
        if _cores <= 2:
            _rec_conv=1; _rec_stitch=1; _rec_batch=1
            _rec_txt=f"({_cores} core{'s' if _cores>1 else ''} detectado — se recomienda 1 worker para no congelar el sistema)"
        elif _cores <= 4:
            _rec_conv=2; _rec_stitch=2; _rec_batch=1
            _rec_txt=f"({_cores} cores detectados — recomendado: Convertir={_rec_conv}, Stitch={_rec_stitch}, Batch={_rec_batch})"
        elif _cores <= 8:
            _rec_conv=4; _rec_stitch=4; _rec_batch=2
            _rec_txt=f"({_cores} cores detectados — recomendado: Convertir={_rec_conv}, Stitch={_rec_stitch}, Batch={_rec_batch})"
        else:
            _rec_conv=_cores//2; _rec_stitch=_cores//2; _rec_batch=4
            _rec_txt=f"({_cores} cores detectados — recomendado: Convertir={_rec_conv}, Stitch={_rec_stitch}, Batch={_rec_batch})"

        tk.Label(ac,text="⚡  Paralelismo (workers)",bg=C["bg3"],fg=C["teal"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14,pady=(8,0))
        tk.Label(ac,text=_rec_txt,bg=C["bg3"],fg=C["dim"],
                 font=("Segoe UI",7),wraplength=520,justify="left").pack(anchor="w",padx=14,pady=(1,4))

        _wmax=max(_cores,1)
        rw=tk.Frame(ac,bg=C["bg3"]); rw.pack(fill="x",padx=14,pady=(0,10))

        def _worker_block(parent, label, cfg_key, rec_val):
            f=tk.Frame(parent,bg=C["bg3"]); f.pack(side="left",padx=(0,20))
            tk.Label(f,text=label,bg=C["bg3"],fg=C["text2"],font=("Segoe UI",8)).pack(anchor="w")
            var=tk.IntVar(value=self.cfg.get(cfg_key, rec_val))
            row=tk.Frame(f,bg=C["bg3"]); row.pack()
            tk.Scale(row,variable=var,from_=1,to=_wmax,orient="horizontal",
                     bg=C["bg3"],fg=C["text"],highlightthickness=0,troughcolor=C["bg4"],
                     activebackground=C["teal"],sliderrelief="flat",bd=0,length=90,
                     showvalue=True).pack(side="left")
            rec_btn=tk.Button(row,text=f"↺ {rec_val}",
                              command=lambda v=rec_val,vr=var: vr.set(v),
                              bg=C["bg4"],fg=C["dim"],font=("Segoe UI",7),
                              relief="flat",cursor="hand2",padx=4,pady=1,bd=0)
            rec_btn.pack(side="left",padx=(3,0))
            rec_btn.bind("<Enter>",lambda e:rec_btn.config(fg=C["teal"]))
            rec_btn.bind("<Leave>",lambda e:rec_btn.config(fg=C["dim"]))
            return var

        self.s_wk_conv   = _worker_block(rw,"Convertir",   "workers_convert", _rec_conv)
        self.s_wk_stitch = _worker_block(rw,"Stitch",      "workers_stitch",  _rec_stitch)
        self.s_wk_batch  = _worker_block(rw,"Batch (caps)","workers_batch",   _rec_batch)
        tk.Label(rw,text="↺ = volver al\nvalor recomendado",bg=C["bg3"],fg=C["dim"],
                 font=("Segoe UI",7),justify="left").pack(side="left",padx=(0,4))

        wc=self._cframe(self._adv_frame); wc.pack(fill="x",pady=(0,8))
        tk.Label(wc,text="✨  Mejora de calidad — opciones",bg=C["bg3"],fg=C["teal"],
                 font=("Segoe UI",8,"bold")).pack(anchor="w",padx=14,pady=(8,4))
        wr2=tk.Frame(wc,bg=C["bg3"]); wr2.pack(fill="x",padx=14,pady=(0,4))
        tk.Label(wr2,text="Escala:",bg=C["bg3"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left",padx=(0,6))
        self.s_wsv=tk.StringVar(value=self.cfg["waifu_scale"])
        for v,l in [("1","x1"),("2","x2"),("4","x4")]:
            tk.Radiobutton(wr2,text=l,variable=self.s_wsv,value=v,bg=C["bg3"],fg=C["text"],
                selectcolor=C["teal"],activebackground=C["bg3"],font=("Segoe UI",8),
                highlightthickness=0).pack(side="left",padx=(0,6))
        tk.Label(wr2,text="  Ruido:",bg=C["bg3"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left",padx=(0,6))
        self.s_wnv=tk.StringVar(value=self.cfg["waifu_noise"])
        for v,l in [("-1","Ninguno"),("0","Suave"),("1","Medio"),("2","Fuerte"),("3","Máx")]:
            tk.Radiobutton(wr2,text=l,variable=self.s_wnv,value=v,bg=C["bg3"],fg=C["text"],
                selectcolor=C["teal"],activebackground=C["bg3"],font=("Segoe UI",8),
                highlightthickness=0).pack(side="left",padx=(0,4))
        wr3=tk.Frame(wc,bg=C["bg3"]); wr3.pack(fill="x",padx=14,pady=(0,10))
        tk.Label(wr3,text="Modelo:",bg=C["bg3"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left",padx=(0,6))
        self.s_wmv=tk.StringVar(value=self.cfg["waifu_model"])
        for v,l in [("models-cunet","Alta calidad"),("models-upconv_7_anime_style_art_rgb","Anime rápido")]:
            tk.Radiobutton(wr3,text=l,variable=self.s_wmv,value=v,bg=C["bg3"],fg=C["text"],
                selectcolor=C["teal"],activebackground=C["bg3"],font=("Segoe UI",8),
                highlightthickness=0).pack(side="left",padx=(0,12))

        if self._adv_open:
            self._adv_frame.pack(fill="x",padx=20,pady=(0,8))

    def _toggle_advanced(self):
        self._adv_open=not self._adv_open
        if self._adv_open: self._adv_frame.pack(fill="x",padx=20,pady=(0,8)); self._adv_btn.config(text="⚙ Avanzado ▲")
        else: self._adv_frame.pack_forget(); self._adv_btn.config(text="⚙ Avanzado ▼")
        self.cfg["advanced_open"]=self._adv_open; self._save_config()

    def _toggle_preview(self):
        """Show or hide the preview panel on the right."""
        paned=self._paned_panel
        right=self._paned_right
        if self._preview_visible:
            # Save current width and hide
            try: self._preview_saved_width=paned.sash_coord(0)[0]
            except: pass
            # Collapse by setting pane to minsize
            try: paned.paneconfig(right,minsize=0,width=0)
            except: pass
            try: paned.sash_place(0,paned.winfo_width()-6,0)
            except: pass
            self._preview_visible=False
            lbl="▶ Preview"
            try: self._pv_toggle_btn.config(text="▶ Mostrar")
            except: pass
        else:
            # Restore
            try: paned.paneconfig(right,minsize=120,width=self._preview_saved_width)
            except: pass
            pw=paned.winfo_width()
            restore_x=max(0,pw-self._preview_saved_width-6)
            try: paned.sash_place(0,restore_x,0)
            except: pass
            self._preview_visible=True
            lbl="◀ Ocultar"
            try: self._pv_toggle_btn.config(text="◀ Ocultar")
            except: pass
        # Update button bar button
        try: self._pv_br_btn.config(text=lbl)
        except: pass

    # ── PREVIEW zoom/pan ──────────────────────────────────────────────────────
    def _pv_zoom_in(self):  self._pv_zoom=min(self._pv_zoom*1.25,16.0); self._pv_redraw_debounced()
    def _pv_zoom_out(self): self._pv_zoom=max(self._pv_zoom/1.25,0.05); self._pv_redraw_debounced()
    def _pv_reset(self):    self._pv_zoom=1.0; self._pv_ox=0; self._pv_oy=0; self._pv_fit(); self._pv_redraw()

    def _pv_redraw_debounced(self):
        """Schedule redraw after 80ms — prevents lag from rapid zoom events."""
        try: self.root.after_cancel(self._pv_redraw_job)
        except: pass
        self._pv_redraw_job=self.root.after(80, self._pv_redraw)

    def _pv_on_scroll(self,e):
        factor=1.15 if e.delta>0 else 1/1.15
        self._pv_zoom=max(0.05,min(16.0,self._pv_zoom*factor))
        self._pv_redraw_debounced()

    def _pv_pan_start(self,e): self._pv_drag_start=(e.x,e.y,self._pv_ox,self._pv_oy)
    def _pv_pan_motion(self,e):
        if self._pv_drag_start is None: return
        x0,y0,ox0,oy0=self._pv_drag_start
        self._pv_ox=ox0+(e.x-x0); self._pv_oy=oy0+(e.y-y0)
        self._pv_redraw()
    def _pv_pan_end(self,e): self._pv_drag_start=None

    def _pv_fit(self):
        """Calcula zoom para que la imagen entra en el canvas."""
        if self._pv_img_full is None: return
        cv=self._prev_canvas; cv.update_idletasks()
        cw=max(cv.winfo_width(),1); ch=max(cv.winfo_height(),1)
        iw,ih=self._pv_img_full.size
        self._pv_zoom=min((cw-8)/iw,(ch-8)/ih,1.0)
        self._pv_ox=0; self._pv_oy=0

    def _pv_redraw(self):
        cv=self._prev_canvas
        if self._pv_img_full is None:
            cv.update_idletasks(); cw=max(cv.winfo_width(),1); ch=max(cv.winfo_height(),1)
            cv.delete("all")
            cv.create_text(cw//2,ch//2,text="📷\nSin selección",fill=C["dim"],
                           font=("Segoe UI",9),justify="center"); return
        cv.update_idletasks(); cw=max(cv.winfo_width(),1); ch=max(cv.winfo_height(),1)
        iw,ih=self._pv_img_full.size
        nw=max(1,int(iw*self._pv_zoom)); nh=max(1,int(ih*self._pv_zoom))
        # clamp offset so image doesn't wander completely off screen
        self._pv_ox=max(-(nw-20),min(cw-20,self._pv_ox))
        self._pv_oy=max(-(nh-20),min(ch-20,self._pv_oy))
        x=cw//2+self._pv_ox; y=ch//2+self._pv_oy
        # Cap rendered size to canvas size + small margin to prevent huge allocations
        MAX_RENDER=2200
        render_w=min(nw,MAX_RENDER); render_h=min(nh,MAX_RENDER)
        # Crop to visible portion only (avoid rendering off-screen pixels)
        cx0=max(0, int((cw//2+self._pv_ox - cw//2 - 10) * iw/nw)) if nw>cw else 0
        cy0=max(0, int((ch//2+self._pv_oy - ch//2 - 10) * ih/nh)) if nh>ch else 0
        crop_w=min(iw, int(cw*iw/nw)+4); crop_h=min(ih, int(ch*ih/nh)+4)
        if nw>cw or nh>ch:
            region=self._pv_img_full.crop((cx0,cy0,min(iw,cx0+crop_w),min(ih,cy0+crop_h)))
            rw=max(1,int(region.width*self._pv_zoom)); rh=max(1,int(region.height*self._pv_zoom))
            interp=Image.NEAREST if self._pv_zoom>=4 else (Image.BILINEAR if self._pv_zoom>1 else Image.LANCZOS)
            disp=region.resize((rw,rh),interp)
            # Adjust position for crop offset
            x=x-int(cx0*self._pv_zoom); y=y-int(cy0*self._pv_zoom)
        else:
            interp=Image.NEAREST if self._pv_zoom>=4 else (Image.BILINEAR if self._pv_zoom>1 else Image.LANCZOS)
            disp=self._pv_img_full.resize((nw,nh),interp)
        photo=ImageTk.PhotoImage(disp)
        cv.delete("all")
        cv.create_image(x,y,image=photo,anchor="center")
        cv._img_ref=photo
        self._zoom_lbl.config(text=f"{int(self._pv_zoom*100)}%")

    def _update_preview(self,event=None):
        if not PIL_OK: return
        sel=self.s_lb.curselection()
        if not sel or sel[0]>=len(self.files):
            self._pv_img_full=None; self._preview_path=None; self._pv_redraw()
            self._prev_info.config(text=""); return
        path=self.files[sel[0]]
        # No saltear si el mismo archivo (recargar siempre al clicar)
        self._preview_path=path
        try: self._nav_bar.pack_forget()
        except: pass
        threading.Thread(target=self._load_preview_async,args=(path,),daemon=True).start()

    def _load_preview_async(self,path):
        try:
            img=open_image_safe(path)
            orig_w,orig_h=img.size
            # Convertir para display
            if img.mode not in ("RGB","RGBA","L"): img=img.convert("RGB")
            # Limitar tamaño en RAM a 3000px lado mayor para preview
            MAX_PV=3000
            if max(orig_w,orig_h)>MAX_PV:
                img.thumbnail((MAX_PV,MAX_PV),Image.LANCZOS)
            sz=os.path.getsize(path)/(1024*1024)
            name=os.path.basename(path)
            if len(name)>28: name=name[:25]+"…"
            info=f"{name}\n{orig_w}×{orig_h}px  ·  {sz:.1f}MB"
            def _apply():
                self._pv_img_full=img; self._pv_fit(); self._pv_redraw()
                self._prev_info.config(text=info)
            self.root.after(0,_apply)
        except Exception as ex:
            def _err():
                self._pv_img_full=None; self._pv_redraw()
                self._prev_info.config(text=f"⚠ {str(ex)[:40]}")
            self.root.after(0,_err)

    def _batch_preview_entry(self, path, etype):
        """Carga todas las imágenes de un entry batch y muestra la primera."""
        files = []
        if etype == "zip":
            try:
                with zipfile.ZipFile(path) as zf:
                    tmp = tempfile.mkdtemp(prefix="bpv_")
                    self._batch_pv_tmp = tmp  # guardar para limpiar
                    for name in sorted(zf.namelist()):
                        if os.path.splitext(name)[1].lower() in FORMATS_IN:
                            zf.extract(name, tmp)
                            files.append(os.path.join(tmp, name))
            except Exception as ex:
                self._st(f"⚠ No se pudo abrir ZIP: {ex}"); return
        elif os.path.isdir(path):
            for fname in sorted(os.listdir(path)):
                if os.path.splitext(fname)[1].lower() in FORMATS_IN:
                    files.append(os.path.join(path, fname))

        if not files:
            self._st("⚠ No se encontraron imágenes en esta entrada."); return

        self._batch_preview_files = files
        self._batch_preview_idx = 0
        # Mostrar barra de navegación
        self._nav_bar.pack(fill="x", padx=4, pady=(0,4))
        self._pv_batch_show()

    def _pv_batch_show(self):
        files = self._batch_preview_files
        idx = self._batch_preview_idx
        if not files: return
        total = len(files)
        self._nav_lbl.config(text=f"{idx+1}/{total}")
        path = files[idx]
        self._preview_path = path
        threading.Thread(target=self._load_preview_async, args=(path,), daemon=True).start()

    def _pv_batch_prev(self):
        if not self._batch_preview_files: return
        self._batch_preview_idx = (self._batch_preview_idx - 1) % len(self._batch_preview_files)
        self._pv_batch_show()

    def _pv_batch_next(self):
        if not self._batch_preview_files: return
        self._batch_preview_idx = (self._batch_preview_idx + 1) % len(self._batch_preview_files)
        self._pv_batch_show()

    # ── BATCH TREE ────────────────────────────────────────────────────────────
    def _build_batch_tree(self,P):
        top=tk.Frame(P,bg=C["bg"]); top.pack(fill="x",pady=(0,4))
        make_btn(top,"+ Carpeta",self._batch_add_folder,
                 bg=C["bg5"],fg=C["text2"],hover_bg=C["teal"],hover_fg=C["bg"],small=True).pack(side="left",padx=(0,5))
        make_btn(top,"+ ZIP",self._batch_add_zip,
                 bg=C["bg5"],fg=C["text2"],hover_bg=C["teal"],hover_fg=C["bg"],small=True).pack(side="left",padx=(0,5))
        make_btn(top,"🔍 Auto-detectar",self._batch_detect_subfolders,
                 bg=C["bg4"],fg=C["cyan"],hover_bg=C["bg5"],hover_fg=C["bright"],small=True).pack(side="left",padx=(0,5))
        make_btn(top,"✕",lambda:(self.batch_entries.clear(),self._render_batch_tree()),
                 bg=C["bg4"],fg=C["err"],hover_bg=C["err2"],hover_fg=C["bright"],small=True).pack(side="left")
        self.b_ct=tk.Label(top,text="0 entradas",bg=C["bg"],fg=C["dim"],font=("Segoe UI",8))
        self.b_ct.pack(side="left",padx=(10,0))
        # Ordenamiento de entries batch
        BATCH_SORT=[("Nombre ↑","name_asc"),("Nombre ↓","name_desc"),
                    ("Número ↑","num_asc"),("Número ↓","num_desc")]
        tk.Label(top,text="Orden:",bg=C["bg"],fg=C["dim"],font=("Segoe UI",8)).pack(side="right",padx=(0,3))
        self.b_sortv=tk.StringVar(value="Nombre ↑")
        self._b_sort_map={l:v for l,v in BATCH_SORT}
        b_sort_cb=ttk.Combobox(top,textvariable=self.b_sortv,
                               values=[l for l,_ in BATCH_SORT],state="readonly",
                               width=9,font=("Segoe UI",8))
        b_sort_cb.pack(side="right",padx=(0,4))
        def _apply_batch_sort(ev=None):
            method=self._b_sort_map.get(self.b_sortv.get(),"name_asc")
            import re as _re
            def _nat(e):
                nm=os.path.basename(e["path"].rstrip("/\\")).lower()
                return [int(t) if t.isdigit() else t for t in _re.split(r"(\d+)",nm)]
            def _num(e):
                nm=os.path.basename(e["path"].rstrip("/\\"))
                m=_re.search(r"\d+",nm); return int(m.group(0)) if m else 0
            rev=method.endswith("desc")
            key=_num if "num" in method else _nat
            self.batch_entries.sort(key=key,reverse=rev)
            self._render_batch_tree()
        b_sort_cb.bind("<<ComboboxSelected>>",_apply_batch_sort)
        self._sbtn(top,"↕",_apply_batch_sort).pack(side="right",padx=(0,2))

        # ── Plantilla de nombre de capítulo ───────────────────────────────────
        nrow=tk.Frame(P,bg=C["bg"]); nrow.pack(fill="x",pady=(4,0))
        tk.Label(nrow,text="✏ Nombre salida:",bg=C["bg"],fg=C["teal"],font=("Segoe UI",8,"bold")).pack(side="left")
        self.s_tmplv=tk.StringVar(value=self.cfg.get("name_template","{n}_BloomStitch"))
        te=tk.Entry(nrow,textvariable=self.s_tmplv,width=26,bg=C["bg4"],fg=C["text"],
                    insertbackground=C["teal"],relief="flat",font=("Consolas",9),
                    highlightthickness=1,highlightbackground=C["border"],highlightcolor=C["teal"])
        te.pack(side="left",padx=(5,4))
        self.s_usenv=tk.BooleanVar(value=self.cfg.get("name_use_num",True))
        self._toggle(nrow,self.s_usenv,lambda:None).pack(side="left",padx=(0,4))
        tk.Label(nrow,text="Incluir número",bg=C["bg"],fg=C["text2"],font=("Segoe UI",8)).pack(side="left")
        tk.Label(nrow,text="  |  {n} = número del cap",bg=C["bg"],fg=C["dim"],font=("Segoe UI",7)).pack(side="left",padx=(6,0))

        tw=tk.Frame(P,bg=C["bg"]); tw.pack(fill="both",expand=True)
        self._tree_canvas=tk.Canvas(tw,bg=C["bg3"],highlightthickness=1,
                                     highlightbackground=C["border2"],height=220)
        tsb=tk.Scrollbar(tw,width=7,bg=C["bg4"],troughcolor=C["bg3"])
        self._tree_canvas.config(yscrollcommand=tsb.set); tsb.config(command=self._tree_canvas.yview)
        tsb.pack(side="right",fill="y"); self._tree_canvas.pack(side="left",fill="both",expand=True)
        self._tree_inner=tk.Frame(self._tree_canvas,bg=C["bg3"])
        self._tree_win=self._tree_canvas.create_window((0,0),window=self._tree_inner,anchor="nw")
        self._tree_canvas.bind("<Configure>",lambda e:(
            self._tree_canvas.itemconfig(self._tree_win,width=e.width),
            self._tree_canvas.update_idletasks()
        ))
        self._tree_inner.bind("<Configure>",lambda e:self._tree_canvas.configure(scrollregion=self._tree_canvas.bbox("all")))
        def _tree_scroll(e):
            self._tree_canvas.yview_scroll(int(-1*(e.delta/120)),"units")
            return "break"
        self._tree_canvas.bind("<MouseWheel>",_tree_scroll)
        # Helper: recursively bind mousewheel to all children of _tree_inner
        def _bind_tree_scroll(widget):
            widget.bind("<MouseWheel>",_tree_scroll)
            for child in widget.winfo_children():
                _bind_tree_scroll(child)
        self._bind_tree_scroll_fn=_bind_tree_scroll
        # Also bind on Linux (Button-4/5)
        def _tree_scroll_linux(e):
            delta = -1 if e.num==4 else 1
            self._tree_canvas.yview_scroll(delta,"units")
            return "break"
        self._tree_canvas.bind("<Button-4>",_tree_scroll_linux)
        self._tree_canvas.bind("<Button-5>",_tree_scroll_linux)
        if DND_OK:
            self._tree_canvas.drop_target_register(DND_FILES)
            self._tree_canvas.dnd_bind("<<Drop>>",self._on_drop)

    def _render_batch_tree(self):
        for w in self._tree_inner.winfo_children(): w.destroy()
        if not self.batch_entries:
            tk.Label(self._tree_inner,text="Arrastrá carpetas/ZIPs aquí o usá los botones",
                     bg=C["bg3"],fg=C["dim"],font=("Segoe UI",9)).pack(pady=20)
            self.b_ct.config(text="0 entradas")
        else:
            for idx,entry in enumerate(self.batch_entries):
                self._render_entry(self._tree_inner,entry,idx,0)
            total=sum(1+len(e.get("children",[])) for e in self.batch_entries)
            self.b_ct.config(text=f"{len(self.batch_entries)} carpeta(s)  ·  {total} ítem(s)")
        # Re-bind mousewheel to all new child widgets
        try: self._bind_tree_scroll_fn(self._tree_inner)
        except: pass

    def _render_entry(self,parent,entry,idx,depth):
        path=entry["path"]; etype=entry.get("type","folder")
        children=entry.get("children",[]); expanded=entry.get("expanded",True)
        files_expanded=entry.get("files_expanded",False)
        name=os.path.basename(path.rstrip("/\\")) or path
        bgc=C["bg4"] if depth==0 else C["bg3"]
        row=tk.Frame(parent,bg=bgc,pady=1); row.pack(fill="x",pady=1)
        if depth>0: tk.Frame(row,bg=bgc,width=depth*20).pack(side="left")
        # Files-expand arrow (▸/▾): shown on any entry that can contain images
        if etype in ("folder","zip") or os.path.isdir(path):
            fa="▾" if files_expanded else "▸"
            fexp=tk.Label(row,text=fa,bg=bgc,fg=C["teal2"],font=("Segoe UI",9),cursor="hand2",padx=2)
            fexp.pack(side="left"); fexp.bind("<Button-1>",lambda e,en=entry:self._toggle_files(en))
        else:
            tk.Label(row,text="  ",bg=bgc).pack(side="left")
        # Children-expand arrow (▶/▼): shown only when entry has sub-entries
        if children:
            arrow_val="▼" if expanded else "▶"
            exp=tk.Label(row,text=arrow_val,bg=bgc,fg=C["teal"],font=("Segoe UI",8),cursor="hand2",padx=2)
            exp.pack(side="left"); exp.bind("<Button-1>",lambda e,en=entry:self._toggle_entry(en))
        else:
            tk.Label(row,text=" ",bg=bgc).pack(side="left")
        ico="📦" if etype=="zip" else ("📁" if depth==0 else "📂")
        col=C["warn"] if etype=="zip" else (C["folder"] if depth==0 else C["text2"])
        tk.Label(row,text=ico,bg=bgc,font=("Segoe UI",9)).pack(side="left",padx=(0,4))
        n_img=entry.get("img_count",0)
        label=name+(f"  ({n_img} img)" if n_img else "")
        lbl=tk.Label(row,text=label,bg=bgc,fg=col,font=("Segoe UI",9),anchor="w",cursor="hand2")
        lbl.pack(side="left",fill="x",expand=True)
        lbl.bind("<Button-1>",lambda e,ep=entry["path"],et=entry.get("type","folder"):self._batch_preview_entry(ep,et))
        lbl.bind("<Enter>",lambda e,l=lbl:l.config(bg=C["bg5"]))
        lbl.bind("<Leave>",lambda e,l=lbl:l.config(bg=bgc))
        def _del(en=entry):
            if en in self.batch_entries: self.batch_entries.remove(en)
            else:
                for e in self.batch_entries:
                    if en in e.get("children",[]): e["children"].remove(en); break
            self._render_batch_tree()
        x=tk.Label(row,text="✕",bg=bgc,fg=C["dim"],font=("Segoe UI",8),cursor="hand2",padx=6)
        x.pack(side="right"); x.bind("<Button-1>",lambda e:_del())
        x.bind("<Enter>",lambda e:x.config(fg=C["err"])); x.bind("<Leave>",lambda e:x.config(fg=C["dim"]))
        # Drag-to-reorder only on root-level entries
        if depth==0 and entry in self.batch_entries:
            row.config(cursor="fleur")
            row.bind("<ButtonPress-1>",lambda e,en=entry:self._btree_drag_start(e,en))
            row.bind("<B1-Motion>",self._btree_drag_motion)
            row.bind("<ButtonRelease-1>",self._btree_drag_end)
        # Show children
        if children and expanded:
            for cidx,child in enumerate(children): self._render_entry(parent,child,cidx,depth+1)
        # Show file list when files_expanded
        if files_expanded:
            self._render_file_list(parent, entry, depth+1)

    def _toggle_entry(self,entry):
        entry["expanded"]=not entry.get("expanded",True); self._render_batch_tree()

    def _toggle_files(self,entry):
        entry["files_expanded"]=not entry.get("files_expanded",False); self._render_batch_tree()

    # ── BATCH TREE DRAG-REORDER ───────────────────────────────────────────────
    def _btree_drag_start(self, event, entry):
        """Start dragging a root-level batch entry for reordering."""
        if entry not in self.batch_entries: return  # only root entries
        self._btree_drag_entry=entry
        self._btree_drag_y=event.y_root
        # Create floating indicator label
        try:
            if self._btree_drag_indicator:
                self._btree_drag_indicator.destroy()
        except: pass
        name=os.path.basename(entry["path"].rstrip("/\\")) or entry["path"]
        self._btree_drag_indicator=tk.Toplevel(self.root)
        self._btree_drag_indicator.overrideredirect(True)
        self._btree_drag_indicator.attributes("-alpha",0.80)
        self._btree_drag_indicator.configure(bg=C["teal"])
        tk.Label(self._btree_drag_indicator,text=f"  ✥  {name}  ",bg=C["teal"],fg=C["bg"],
                 font=("Segoe UI",9,"bold")).pack(padx=2,pady=2)
        self._btree_drag_indicator.geometry(f"+{event.x_root+12}+{event.y_root-10}")

    def _btree_drag_motion(self, event):
        if not self._btree_drag_entry: return
        # Move floating indicator
        try: self._btree_drag_indicator.geometry(f"+{event.x_root+12}+{event.y_root-10}")
        except: pass
        # Find which row we're hovering over and show drop line
        widget=self.root.winfo_containing(event.x_root, event.y_root)
        # Walk up to find the entry frame row in _tree_inner
        target_idx=self._find_drop_target(event.y_root)
        self._btree_show_drop_line(target_idx)

    def _btree_drag_end(self, event):
        if not self._btree_drag_entry: return
        try:
            if self._btree_drag_indicator: self._btree_drag_indicator.destroy()
            self._btree_drag_indicator=None
        except: pass
        self._btree_hide_drop_line()
        target_idx=self._find_drop_target(event.y_root)
        src_idx=self.batch_entries.index(self._btree_drag_entry) if self._btree_drag_entry in self.batch_entries else -1
        if src_idx>=0 and target_idx is not None and target_idx!=src_idx:
            entry=self.batch_entries.pop(src_idx)
            insert_at=target_idx if target_idx<=src_idx else target_idx-1
            self.batch_entries.insert(max(0,insert_at),entry)
            self._render_batch_tree()
        self._btree_drag_entry=None

    def _find_drop_target(self, y_root):
        """Find which root-level batch entry index the cursor is over."""
        try:
            inner=self._tree_inner
            inner.update_idletasks()
            inner_y=inner.winfo_rooty()
            n=len(self.batch_entries)
            if not n: return 0
            # Get all root row widgets (first child per entry, every n-th frame)
            rows=[w for w in inner.winfo_children() if isinstance(w,tk.Frame)]
            if not rows: return 0
            # Find position relative to inner frame
            rel_y=y_root-inner_y
            for i,row in enumerate(rows[:n]):
                try:
                    row_y=row.winfo_y(); row_h=row.winfo_height()
                    if rel_y<row_y+row_h//2: return i
                except: pass
            return n
        except: return None

    def _btree_show_drop_line(self, idx):
        """Show a colored insertion line in the batch tree at position idx."""
        # We'll just highlight via _render — too complex for a real line without repaint
        pass  # visual feedback via floating label is sufficient

    def _btree_hide_drop_line(self):
        pass

    def _list_entry_files(self, entry):
        """Retorna lista de (display_name, path_or_zip_member, ftype, src_path) ordenado.
        Para ZIPs con subcarpetas, muestra la ruta relativa completa (ej: cap3/01.jpg).
        """
        path=entry["path"]; etype=entry.get("type","folder")
        files=[]
        try:
            if etype=="zip":
                with zipfile.ZipFile(path) as zf:
                    names=[n for n in zf.namelist()
                           if os.path.splitext(n)[1].lower() in FORMATS_IN and not n.endswith("/")]
                    names.sort(key=lambda n: [p.lower() for p in n.replace("\\","/").split("/")])
                    for name in names:
                        # Show relative path so user sees subfolder structure
                        display=name.replace("\\","/")
                        files.append((display, name, "zip", path))
            elif os.path.isdir(path):
                for fname in sorted(os.listdir(path)):
                    fp=os.path.join(path,fname)
                    if os.path.isfile(fp) and os.path.splitext(fname)[1].lower() in FORMATS_IN:
                        files.append((fname, fp, "file", path))
        except: pass
        return files

    def _render_file_list(self, parent, entry, depth):
        """Renderiza la lista de archivos dentro de un entry como sub-filas."""
        files=self._list_entry_files(entry)
        if not files:
            row=tk.Frame(parent,bg=C["bg3"]); row.pack(fill="x",pady=0)
            if depth>0: tk.Frame(row,bg=C["bg3"],width=depth*18).pack(side="left")
            tk.Label(row,text="  (sin imágenes)",bg=C["bg3"],fg=C["dim"],font=("Segoe UI",8)).pack(side="left",padx=4,pady=1)
            return
        # Group by subfolder for visual clarity
        last_folder=[None]
        for fname, fpath, ftype, src_path in files:
            # For ZIP entries, fpath is the member name (may include subpath like "cap3/01.jpg")
            display_name=fname  # fname is already the display path from _list_entry_files
            parts=display_name.replace("\\","/").split("/")
            subfolder="/".join(parts[:-1]) if len(parts)>1 else ""
            file_name=parts[-1]
            # Show subfolder separator if changed
            if subfolder and subfolder!=last_folder[0]:
                sep=tk.Frame(parent,bg=C["bg4"]); sep.pack(fill="x",pady=(2,0))
                if depth>0: tk.Frame(sep,bg=C["bg4"],width=depth*18).pack(side="left")
                tk.Label(sep,text=f"  📂  {subfolder}/",bg=C["bg4"],fg=C["dim"],
                         font=("Consolas",7,"italic")).pack(side="left",padx=2,pady=1)
                last_folder[0]=subfolder
            row=tk.Frame(parent,bg=C["bg3"]); row.pack(fill="x",pady=0)
            indent=depth+(1 if subfolder else 0)
            if indent>0: tk.Frame(row,bg=C["bg3"],width=indent*18).pack(side="left")
            ext=os.path.splitext(file_name)[1].lower()
            ico="🎨" if ext in (".psd",".psb") else "🖼"
            lbl=tk.Label(row,text=f"  {ico}  {file_name}",bg=C["bg3"],fg=C["text2"],
                         font=("Consolas",8),anchor="w",cursor="hand2")
            lbl.pack(side="left",fill="x",expand=True,padx=2,pady=1)
            if ftype=="file":
                def _click_file(e, fp=fpath):
                    self._preview_path=fp
                    try: self._nav_bar.pack_forget()
                    except: pass
                    threading.Thread(target=self._load_preview_async,args=(fp,),daemon=True).start()
                lbl.bind("<Button-1>",_click_file)
                lbl.bind("<Enter>",lambda e,l=lbl:l.config(bg=C["bg4"]))
                lbl.bind("<Leave>",lambda e,l=lbl:l.config(bg=C["bg3"]))
            else:
                # ZIP entry — extract to temp and preview
                def _click_zip_file(e, zpath=src_path, zname=fpath):
                    def _load():
                        try:
                            tmp=tempfile.mkdtemp(prefix="bpvf_")
                            with zipfile.ZipFile(zpath) as zf:
                                zf.extract(zname, tmp)
                                real_path=os.path.join(tmp, zname)
                            self._preview_path=real_path
                            self.root.after(0, lambda: self._nav_bar.pack_forget())
                            self._load_preview_async(real_path)
                        except Exception as ex:
                            self.root.after(0, lambda: self._prev_info.config(text=f"⚠ {ex}"))
                    threading.Thread(target=_load,daemon=True).start()
                lbl.bind("<Button-1>",_click_zip_file)
                lbl.bind("<Enter>",lambda e,l=lbl:l.config(bg=C["bg4"]))
                lbl.bind("<Leave>",lambda e,l=lbl:l.config(bg=C["bg3"]))

    def _count_images_in(self, path):
        """Cuenta imágenes directas en una carpeta (sin recursar)."""
        try:
            return sum(1 for f in os.listdir(path)
                       if os.path.isfile(os.path.join(path, f))
                       and os.path.splitext(f)[1].lower() in FORMATS_IN)
        except: return 0

    def _count_zip_images(self, zpath):
        """Cuenta imágenes dentro de un ZIP."""
        try:
            with zipfile.ZipFile(zpath) as zf:
                return sum(1 for n in zf.namelist()
                           if os.path.splitext(n)[1].lower() in FORMATS_IN)
        except: return 0

    def _scan_folder_smart(self, folder_path):
        """
        Escanea una carpeta detectando automáticamente:
        - Imágenes directas (jpg, png, psd, psb…) → img_count en el padre
        - Subcarpetas con imágenes → children tipo folder
        - ZIPs con imágenes dentro → children tipo zip
        """
        direct_imgs = self._count_images_in(folder_path)
        children = []
        try:
            for item in sorted(os.listdir(folder_path)):
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    n = self._count_images_in(item_path)
                    if n > 0:
                        children.append({
                            "path": item_path, "type": "folder",
                            "img_count": n, "children": [], "expanded": True
                        })
                elif item.lower().endswith(".zip") and os.path.isfile(item_path):
                    n = self._count_zip_images(item_path)
                    if n > 0:
                        children.append({
                            "path": item_path, "type": "zip",
                            "img_count": n, "children": [], "expanded": True
                        })
        except: pass
        return {
            "path": folder_path, "type": "folder",
            "img_count": direct_imgs, "children": children, "expanded": True
        }

    def _batch_add_folder(self):
        f = filedialog.askdirectory(title="Agregar carpeta al batch")
        if not f: return
        entry = self._scan_folder_smart(f)
        self.batch_entries.append(entry)
        self._render_batch_tree()
        total = entry["img_count"] + sum(c["img_count"] for c in entry["children"])
        subs = len(entry["children"])
        msg = f"📁 {entry['img_count']} img directas"
        if subs: msg += f" + {subs} sub(s) detectada(s) → {total} total"
        self._st(msg)

    def _batch_add_zip(self):
        zips = filedialog.askopenfilenames(title="ZIPs al batch",
                                           filetypes=[("ZIP","*.zip"),("Todos","*.*")])
        if not zips: return
        for z in zips:
            n = self._count_zip_images(z)
            self.batch_entries.append({
                "path": z, "type": "zip", "img_count": n, "children": [], "expanded": True
            })
        self._render_batch_tree()
        if len(zips)>1: self._st(f"📦 {len(zips)} ZIPs agregados al batch.")

    def _batch_detect_subfolders(self):
        """Re-escanea todas las entradas actualizando contenido."""
        for i, entry in enumerate(self.batch_entries):
            if entry["type"] == "folder":
                self.batch_entries[i] = self._scan_folder_smart(entry["path"])
            elif entry["type"] == "zip":
                entry["img_count"] = self._count_zip_images(entry["path"])
        self._render_batch_tree()
        self._st("🔍 Re-escaneo completo — subcarpetas y ZIPs actualizados.")

    def _on_mode_change(self):
        self._batch_mode=self._batch_var.get()
        if self._batch_mode:
            self._simple_frame.pack_forget()
            self._batch_frame.pack(fill="both",expand=True)
            self._render_batch_tree()
        else:
            self._batch_frame.pack_forget()
            self._simple_frame.pack(fill="both",expand=True)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        tk.Frame(self.root,bg=C["border2"],height=1).pack(fill="x",side="bottom")
        ft=tk.Frame(self.root,bg=C["bg2"],height=52); ft.pack(fill="x",side="bottom"); ft.pack_propagate(False)
        self.prog_v=tk.DoubleVar(value=0)
        self.stat_lb=tk.Label(ft,text="✅ Todo listo.",bg=C["bg2"],fg=C["dim"],font=("Segoe UI",9))
        self.stat_lb.pack(side="left",padx=16)
        self.prog=ttk.Progressbar(ft,variable=self.prog_v,maximum=100,length=200,
                                   style="Bloom.Horizontal.TProgressbar")
        self.prog.pack(side="left",pady=16)
        make_btn(ft,"⚙ Config",self._open_settings,bg=C["bg4"],fg=C["text2"],
                 hover_bg=C["bg5"],hover_fg=C["text"],small=True).pack(side="right",padx=(0,10),pady=12)
        self.run_btn=make_btn(ft,"▶  INICIAR",self._run_all,font=("Segoe UI",10,"bold"),padx=22)
        self.run_btn.pack(side="right",padx=8,pady=10)



    # ═══════════════════════════════════════════════════════════════════════════
    #  GOOGLE DRIVE  v2  —  Gestor de Manwha
    # ═══════════════════════════════════════════════════════════════════════════
    #
    #  Estructura esperada en Drive:
    #
    #    📁 [Carpeta raíz que el usuario configura]
    #        📁 Nombre del Manwha A
    #            📁 1_Raw
    #            📁 2_Clean
    #            📁 3_Traduccion
    #            📁 4_Typeo          ← fuente de PSD
    #            📁 5_Recortes       ← destino de WEBP
    #        📁 Nombre del Manwha B
    #            ...
    #
    #  El usuario pega el link (o ID) de la carpeta raíz.
    #  El sistema detecta todos los manwha que tienen la estructura
    #  4_Typeo / 5_Recortes y los lista en una tabla con buscador,
    #  filtros y ordenamiento.  Puede procesar uno o varios a la vez.
    # ═══════════════════════════════════════════════════════════════════════════

    # ── constantes de estructura (valores por defecto, configurables en UI) ──
    # ── Detección por las 5 carpetas canónicas de cada manwha ──────────────
    # Si una carpeta contiene AL MENOS 3 de estas 5 subcarpetas → es un manwha.
    # La clave es el prefijo numérico (1_ a 5_) + aliases por si varía el nombre.
    _GD_CANONICAL = [
        ("1_", ["raw", "raws", "original", "originales"]),          # RAW
        ("2_", ["clean", "clrd", "limpieza", "cleaned"]),           # CLEAN
        ("3_", ["traduccion", "traducción", "translation", "trans"]),# TRADUCCION
        ("4_", ["type", "typeo", "edicion", "edición", "tipo"]),    # TYPE (fuente)
        ("5_", ["recorte", "recortes", "output", "destino"]),       # RECORTES (destino)
    ]
    _GD_MANWHA_MIN_MATCH = 3   # mínimo de carpetas canónicas para confirmar manwha

    # Atajos para el resto del código (compatibilidad)
    _GD_SRC_FOLDER  = "4_"
    _GD_DST_FOLDER  = "5_"
    _GD_RAW_FOLDER  = "1_"
    _GD_SRC_ALIASES = ["type", "typeo", "edicion", "edición", "tipo"]
    _GD_DST_ALIASES = ["recorte", "recortes", "output", "destino"]
    _GD_RAW_ALIASES = ["raw", "raws", "original", "originales"]

    def _gd_normalize(self, s):
        """Normaliza string: minúsculas, sin acentos, sin prefijos numéricos."""
        import unicodedata
        s = s.lower().strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        # quitar prefijo tipo "4_" o "4 " al inicio
        import re as _re
        s = _re.sub(r"^\d+[_\s\-]*", "", s)
        return s

    def _gd_get_src_kw(self):
        """Keyword configurable para detectar carpeta fuente."""
        v = getattr(self, "_gd_src_kw_var", None)
        return (v.get().strip() if v else "") or self._GD_SRC_FOLDER

    def _gd_get_dst_kw(self):
        """Keyword configurable para detectar carpeta destino."""
        v = getattr(self, "_gd_dst_kw_var", None)
        return (v.get().strip() if v else "") or self._GD_DST_FOLDER

    def _gd_fuzzy_match(self, folder_names, keyword, aliases):
        """
        Busca entre folder_names la mejor coincidencia para keyword/aliases.
        Estrategia (en orden de prioridad):
          1. Nombre contiene la keyword exacta (ej: "4_Typeo" contiene "4_")
          2. Nombre normalizado (sin prefijo numérico) contiene algún alias
             PERO solo si el alias tiene 4+ caracteres (evita falsos positivos)
        Devuelve el nombre original o None.
        """
        kw_low = keyword.lower()

        # Prioridad 1: contiene keyword directamente (más confiable)
        for name in folder_names:
            if kw_low in name.lower():
                return name

        # Prioridad 2: fuzzy con aliases (solo aliases suficientemente específicos)
        for name in folder_names:
            norm = self._gd_normalize(name)  # quita prefijo numérico y acentos
            for alias in aliases:
                if len(alias) < 4:
                    continue  # alias demasiado corto = demasiado genérico
                if alias in norm:
                    return name
        return None

    # ── helpers internos ──────────────────────────────────────────────────────

    # --- Cache local --------------------------------------------------------
    def _gd_cache_save(self):
        """Guarda _gd_manwha_list en JSON (sin BooleanVar ni PhotoImage)."""
        if not GDRIVE_CACHE: return
        try:
            serializable = []
            for m in getattr(self, "_gd_manwha_list", []):
                serializable.append({
                    k: v for k, v in m.items()
                    if k not in ("selected", "thumb_img", "thumb_job")
                })
            import json as _json
            GDRIVE_CACHE.write_text(
                _json.dumps({"root": getattr(self, "_gd_root_var", None) and
                             self._gd_root_var.get().strip() or "",
                             "data": serializable},
                            ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception:
            pass

    def _gd_cache_load(self):
        """Carga caché y reconstruye _gd_manwha_list. Devuelve True si OK."""
        if not GDRIVE_CACHE or not GDRIVE_CACHE.exists(): return False
        try:
            import json as _json
            blob = _json.loads(GDRIVE_CACHE.read_text(encoding="utf-8"))
            root_now = (getattr(self, "_gd_root_var", None) and
                        self._gd_root_var.get().strip() or "")
            if blob.get("root", "") != root_now: return False
            loaded = []
            for m in blob.get("data", []):
                m["selected"] = tk.BooleanVar(value=False)
                loaded.append(m)
            self._gd_manwha_list = loaded
            self.root.after(0, self._gd_refresh_table)
            ts = GDRIVE_CACHE.stat().st_mtime
            import datetime
            dt = datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")
            self._gd_st(f"📦 Caché cargada ({len(loaded)} manwha — escaneado el {dt}). "
                        f"Pulsá Escanear para actualizar.", 100, C["ok"])
            return True
        except Exception:
            return False

    # --- Thumbnail desde Drive ----------------------------------------------
    def _gd_fetch_thumb(self, m: dict, row_widget):
        """En background: descarga thumbnail del primer PSD y lo muestra."""
        def _fetch():
            try:
                if not self._gd_service: return
                fid = m.get("src_id")
                if not fid: return
                # Pedir thumbnail via Drive v3 (campo thumbnailLink)
                resp = self._gd_api(
                    self._gd_service.files().list,
                    q=f"'{fid}' in parents and trashed=false",
                    fields="files(id, name, thumbnailLink)",
                    orderBy="name", pageSize=5)
                files = resp.get("files", [])
                # Buscar el primer PSD/imagen
                img_file = next(
                    (f for f in files
                     if any(f["name"].lower().endswith(e)
                            for e in (".psd", ".psb", ".png", ".jpg", ".jpeg"))),
                    files[0] if files else None)
                if not img_file: return
                thumb_url = img_file.get("thumbnailLink")
                if not thumb_url: return
                # Descargar thumbnail (pequeño, ~220px)
                import urllib.request, io
                thumb_url = thumb_url.replace("=s220", "=s80")
                with urllib.request.urlopen(thumb_url, timeout=6) as r:
                    data = r.read()
                img = Image.open(io.BytesIO(data))
                img.thumbnail((48, 48), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                # Guardar referencia y actualizar label
                m["thumb_img"] = photo
                def _show():
                    if row_widget.winfo_exists() and "thumb_lbl" in m:
                        m["thumb_lbl"].config(image=photo)
                self.root.after(0, _show)
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()

    # --- Estado de procesamiento (verde/naranja) ----------------------------
    def _gd_check_status(self, m: dict):
        """
        Compara modifiedTime de src vs dst para determinar si el manwha
        ya está procesado (verde) o tiene cambios nuevos (naranja).
        Corre en background y actualiza m["status"] + refresca la fila.
        """
        def _check():
            try:
                if not self._gd_service: return
                # Fecha del archivo más reciente en src (4_Edición)
                src_files = self._gd_api(
                    self._gd_service.files().list,
                    q=f"'{m['src_id']}' in parents and trashed=false",
                    fields="files(modifiedTime)",
                    orderBy="modifiedTime desc", pageSize=1)
                src_mtime = (src_files.get("files") or [{}])[0].get("modifiedTime", "")

                # Fecha del archivo más reciente en dst (5_Recortes)
                if not m.get("dst_id"):
                    m["status"] = "⚠ Sin destino"; return
                dst_files = self._gd_api(
                    self._gd_service.files().list,
                    q=f"'{m['dst_id']}' in parents and trashed=false",
                    fields="files(modifiedTime)",
                    orderBy="modifiedTime desc", pageSize=1)
                dst_mtime = (dst_files.get("files") or [{}])[0].get("modifiedTime", "")

                if not dst_mtime:
                    m["status"] = "🟠 Sin procesar"
                elif src_mtime and src_mtime > dst_mtime:
                    m["status"] = "🟠 Tiene cambios"
                else:
                    m["status"] = "🟢 Al día"
                self.root.after(0, self._gd_refresh_table)
            except Exception:
                pass
        threading.Thread(target=_check, daemon=True).start()

    def _gd_st(self, msg, pct=None, color=None):
        def _do():
            if hasattr(self, "_gd_status_lbl"):
                # mostrar mensaje completo (wraplength maneja el corte visual)
                self._gd_status_lbl.config(text=str(msg), fg=color or C["text2"])
            if pct is not None and hasattr(self, "_gd_prog_var"):
                self._gd_prog_var.set(max(0, min(100, pct)))
        self.root.after(0, _do)

    def _gd_refresh_dot(self):
        if not hasattr(self, "_gd_auth_dot"): return
        ok = self._gd_service is not None
        self._gd_auth_dot.config(
            text="● Conectado" if ok else "● No conectado",
            fg=C["ok"] if ok else C["err"])

    def _gd_api(self, fn, *a, **kw):
        """Ejecuta una llamada a la API con reintento en error 429/5xx."""
        import time
        for attempt in range(4):
            try:
                return fn(*a, **kw).execute()
            except Exception as ex:
                code = getattr(getattr(ex, "resp", None), "status", 0)
                if str(code) in ("429", "500", "503") and attempt < 3:
                    time.sleep(2 ** attempt)
                else:
                    raise

    # ── autenticación ─────────────────────────────────────────────────────────
    def _gd_authenticate(self):
        if not GDRIVE_LIBS_OK:
            messagebox.showwarning("Dependencias",
                "Primero instalá las dependencias de Google Drive.")
            return
        creds_path = getattr(self, "_gd_creds_var", tk.StringVar()).get().strip()
        self._gd_st("🔄 Abriendo navegador para autorizar…", 0, C["warn"])

        def _auth():
            try:
                creds = None
                token = GDRIVE_TOKEN
                if token and token.exists():
                    creds = Credentials.from_authorized_user_file(
                        str(token), GDRIVE_SCOPES)
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(GRequest())
                    else:
                        # Usar client secret embebido (sin archivo externo)
                        # Si además hay un credentials.json al lado del exe, usarlo
                        # (permite reemplazarlo fácilmente si cambia el proyecto)
                        import json, tempfile
                        if creds_path and Path(creds_path).exists():
                            flow = InstalledAppFlow.from_client_secrets_file(
                                creds_path, GDRIVE_SCOPES)
                        else:
                            # Escribir el secret embebido en un temp file
                            tf = tempfile.NamedTemporaryFile(
                                mode="w", suffix=".json", delete=False, encoding="utf-8")
                            json.dump(GDRIVE_CLIENT_SECRET_EMBEDDED, tf)
                            tf.close()
                            flow = InstalledAppFlow.from_client_secrets_file(
                                tf.name, GDRIVE_SCOPES)
                            try: Path(tf.name).unlink()
                            except: pass
                        creds = flow.run_local_server(port=0, open_browser=True)
                    if token:
                        token.write_text(creds.to_json(), encoding="utf-8")
                self._gd_creds   = creds
                self._gd_service = gdrive_build(
                    "drive", "v3", credentials=creds, cache_discovery=False)
                self.root.after(0, lambda: (
                    self._gd_refresh_dot(),
                    self._gd_st("✅ Conectado. Pegá el link de tu carpeta raíz.", 0, C["ok"]),
                    self._gd_scan_root() if getattr(self, "_gd_root_var", None)
                                          and self._gd_root_var.get().strip() else None
                ))
            except Exception as ex:
                msg = str(ex)
                # Detectar error de API no habilitada
                if "accessNotConfigured" in msg or "drive.googleapis.com" in msg:
                    friendly = (
                        "La API de Google Drive no está habilitada en tu proyecto.\n\n"
                        "Pasos para solucionarlo (solo se hace una vez):\n"
                        "1. Abrí: console.cloud.google.com\n"
                        "2. Seleccioná tu proyecto\n"
                        "3. Menú lateral → APIs y servicios → Biblioteca\n"
                        "4. Buscá 'Google Drive API'\n"
                        "5. Hacé clic en HABILITAR\n"
                        "6. Esperá 1-2 minutos y volvé a conectar"
                    )
                    self.root.after(0, lambda fm=friendly: (
                        self._gd_st("❌ Drive API no habilitada — ver instrucciones", 0, C["err"]),
                        messagebox.showerror("Drive API no habilitada", fm)
                    ))
                elif "invalid_client" in msg or "client_id" in msg.lower():
                    friendly = (
                        "Credenciales OAuth inválidas.\n\n"
                        "Verificá que:\n"
                        "• El credentials.json sea del tipo 'Aplicación de escritorio'\n"
                        "• No sea de tipo 'Cuenta de servicio' ni 'App web'\n"
                        "• El archivo no esté corrupto o truncado\n\n"
                        "Descargá un nuevo credentials.json desde:\n"
                        "console.cloud.google.com → Credenciales"
                    )
                    self.root.after(0, lambda fm=friendly: (
                        self._gd_st("❌ Credenciales inválidas — ver instrucciones", 0, C["err"]),
                        messagebox.showerror("Credenciales inválidas", fm)
                    ))
                else:
                    self.root.after(0, lambda m=msg: (
                        self._gd_st(f"❌ Error: {m}", 0, C["err"]),
                        messagebox.showerror("Drive — Error", m)
                    ))
        threading.Thread(target=_auth, daemon=True).start()

    def _gd_disconnect(self):
        try:
            if GDRIVE_TOKEN and GDRIVE_TOKEN.exists(): GDRIVE_TOKEN.unlink()
        except: pass
        self._gd_service = None; self._gd_creds = None
        self._gd_refresh_dot()
        self._gd_st("Sesión cerrada.", 0, C["dim"])

    # ── parsear ID desde URL de Drive ─────────────────────────────────────────
    @staticmethod
    def _gd_parse_id(url_or_id: str) -> str:
        """Extrae el folder ID de una URL de Drive o lo devuelve tal cual."""
        import re as _re
        url_or_id = url_or_id.strip()
        m = _re.search(r"/folders/([a-zA-Z0-9_\-]{10,})", url_or_id)
        if m: return m.group(1)
        m = _re.search(r"id=([a-zA-Z0-9_\-]{10,})", url_or_id)
        if m: return m.group(1)
        # Asume que es un ID directamente
        if _re.match(r"^[a-zA-Z0-9_\-]{10,}$", url_or_id):
            return url_or_id
        return ""

    # ── listar hijos de una carpeta ───────────────────────────────────────────
    def _gd_list_children(self, parent_id, only_folders=True):
        """Lista todos los hijos de parent_id. Rápido: una sola request."""
        if not self._gd_service: return []
        q = f"'{parent_id}' in parents and trashed=false"
        if only_folders:
            q += " and mimeType='application/vnd.google-apps.folder'"
        results = []; page_token = None
        while True:
            resp = self._gd_api(
                self._gd_service.files().list,
                q=q, spaces="drive",
                fields="nextPageToken, files(id, name, modifiedTime, mimeType, size)",
                pageToken=page_token, orderBy="name", pageSize=200)
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token: break
        return results

    # ── escanear carpeta raíz y detectar manwha ───────────────────────────────
    def _gd_scan_root(self):
        """
        Escanea la carpeta raíz configurada y detecta los manwha que tienen
        la estructura 4_Typeo / 5_Recortes.
        Actualiza self._gd_manwha_list y refresca la tabla.
        """
        root_raw = getattr(self, "_gd_root_var", tk.StringVar()).get().strip()
        root_id  = self._gd_parse_id(root_raw)
        if not root_id:
            messagebox.showwarning("Sin carpeta raíz",
                "Pegá el link de tu carpeta raíz de Drive.")
            return
        if not self._gd_service:
            messagebox.showwarning("No conectado", "Conectate primero."); return

        self._gd_st("🔍 Escaneando estructura de manwha…", 5, C["warn"])
        if hasattr(self, "_gd_scan_btn"):
            btn_set_state(self._gd_scan_btn, "disabled")

        def _scan():
            """
            Escáner recursivo (hasta MAX_DEPTH niveles).
            Busca cualquier carpeta que contenga 4_Typeo / 4_Edicion
            sin importar cuántos niveles de grupo haya encima.
            """
            MAX_DEPTH = 4
            src_kw = self._gd_get_src_kw()
            dst_kw = self._gd_get_dst_kw()
            found  = []
            seen_ids = set()   # evitar duplicados si hay alias de carpetas
            total_scanned = [0]

            # Progreso aproximado — usamos un contador simple
            progress = [5]

            def _advance_progress(label):
                progress[0] = min(progress[0] + 2, 92)
                self._gd_st(f"🔍 {label}", progress[0], C["warn"])

            def _recurse_and_collect(folder, found, depth, breadcrumb=None):
                """
                Baja en folder buscando manwha usando detección por las 5 carpetas canónicas.
                breadcrumb: lista de nombres de carpetas antecesoras (para mostrar grupo).
                """
                if folder["id"] in seen_ids:
                    return
                seen_ids.add(folder["id"])
                total_scanned[0] += 1

                subs = self._gd_list_children(folder["id"], only_folders=True)
                if not subs:
                    return

                sub_map = {s["name"]: s for s in subs}

                result = self._gd_is_manwha(sub_map)
                if result:
                    src_f = result["src"]
                    dst_f = result["dst"]
                    raw_f = result["raw"]
                    # El grupo es el breadcrumb inmediatamente anterior al manwha
                    grp = " › ".join(breadcrumb) if breadcrumb else ""
                    found.append({
                        "name":     folder["name"],
                        "id":       folder["id"],
                        "group":    grp,
                        "src_id":   src_f["id"]   if src_f else None,
                        "src_name": src_f["name"] if src_f else "—",
                        "dst_id":   dst_f["id"]   if dst_f else None,
                        "dst_name": dst_f["name"] if dst_f else "—",
                        "raw_id":   raw_f["id"]   if raw_f else None,
                        "raw_name": raw_f["name"] if raw_f else "—",
                        "modified": folder.get("modifiedTime", "")[:10],
                        "status":   "✅ Listo" if dst_f else "⚠ Sin destino",
                        "selected": tk.BooleanVar(value=False),
                    })
                    return

                # No es manwha — bajar si no llegamos al límite
                if depth < MAX_DEPTH:
                    new_bc = (breadcrumb or []) + [folder["name"]]
                    for sub in subs:
                        _advance_progress(f"Explorando: {sub['name'][:40]}…")
                        _recurse_and_collect(sub, found, depth + 1, new_bc)

            try:
                # Arrancar desde los hijos directos de la raíz
                level1 = self._gd_list_children(root_id, only_folders=True)
                total_l1 = len(level1)
                self._gd_st(f"🔍 Encontradas {total_l1} carpetas en raíz — escaneando…", 5, C["warn"])

                for i, mf in enumerate(level1):
                    _advance_progress(f"Escaneando {i+1}/{total_l1}: {mf['name'][:35]}…")
                    _recurse_and_collect(mf, found, depth=1)

                self._gd_manwha_list = found
                self.root.after(0, self._gd_refresh_table)
                self._gd_cache_save()
                n = len(found)
                self._gd_st(
                    f"✅ {n} manwha encontrado(s) en {total_scanned[0]} carpetas escaneadas — verificando estados…",
                    95, C["ok"])
                for mw in found:
                    self._gd_check_status(mw)
            except Exception as ex:
                import traceback; traceback.print_exc()
                msg = str(ex)
                if "accessNotConfigured" in msg or "drive.googleapis.com" in msg:
                    self._gd_st("❌ API no habilitada. Habilitá Google Drive API en console.cloud.google.com", 0, C["err"])
                else:
                    self._gd_st(f"❌ Error al escanear: {msg}", 0, C["err"])
            finally:
                self.root.after(0, lambda: (
                    btn_set_state(self._gd_scan_btn, "normal")
                    if hasattr(self, "_gd_scan_btn") else None
                ))

        threading.Thread(target=_scan, daemon=True).start()

    # ── refrescar tabla de manwha ─────────────────────────────────────────────
    def _gd_refresh_table(self):
        if not hasattr(self, "_gd_tbl_frame"): return
        for w in self._gd_tbl_frame.winfo_children(): w.destroy()

        lst = getattr(self, "_gd_manwha_list", [])
        search = getattr(self, "_gd_search_var", tk.StringVar()).get().strip().lower()
        if search:
            lst = [m for m in lst if search in m["name"].lower()]

        sort_by = getattr(self, "_gd_sort_var", tk.StringVar()).get()
        if sort_by == "Nombre A→Z":   lst = sorted(lst, key=lambda x: x["name"].lower())
        elif sort_by == "Nombre Z→A": lst = sorted(lst, key=lambda x: x["name"].lower(), reverse=True)
        elif sort_by == "Modificado ↓": lst = sorted(lst, key=lambda x: x["modified"], reverse=True)
        elif sort_by == "Modificado ↑": lst = sorted(lst, key=lambda x: x["modified"])
        elif sort_by == "Estado":       lst = sorted(lst, key=lambda x: x["status"])

        filt = getattr(self, "_gd_filter_var", tk.StringVar()).get()
        if filt == "Solo listos":   lst = [m for m in lst if "🟢" in m["status"] or "✅" in m["status"]]
        elif filt == "Sin destino": lst = [m for m in lst if "⚠" in m["status"]]

        self._gd_filtered = lst

        if not lst:
            tk.Label(self._gd_tbl_frame,
                     text="Sin resultados. Escaneá la carpeta raíz.",
                     bg=C["bg3"], fg=C["dim"],
                     font=("Segoe UI", 9)).pack(pady=20)
            self._gd_update_count()
            return

        view = getattr(self, "_gd_view_var", tk.StringVar(value="cards")).get()

        # ── Checkbox global ───────────────────────────────────────────────────
        hdr = tk.Frame(self._gd_tbl_frame, bg=C["bg4"])
        hdr.pack(fill="x", pady=(0, 2))
        self._gd_chk_all_var = tk.BooleanVar(value=False)
        def _toggle_all():
            v = self._gd_chk_all_var.get()
            for m in lst: m["selected"].set(v)
            self._gd_update_count()
        tk.Checkbutton(hdr, variable=self._gd_chk_all_var, command=_toggle_all,
                       text="Seleccionar todo", bg=C["bg4"],
                       activebackground=C["bg4"], selectcolor=C["teal"],
                       fg=C["text2"], font=("Segoe UI", 8),
                       relief="flat", bd=0, highlightthickness=0).pack(
                           side="left", padx=12, pady=5)
        tk.Label(hdr, text=f"{len(lst)} manwha", bg=C["bg4"], fg=C["dim"],
                 font=("Segoe UI", 7)).pack(side="left")

        if view == "table":
            self._gd_render_table(lst)
        elif view == "cards":
            self._gd_render_cards(lst)
        else:
            self._gd_render_grouped_list(lst)

        self._gd_update_count()

    def _gd_status_color(self, status):
        if "🟢" in status or "✅" in status: return "#22c55e", "● OK"
        if "🟠" in status: return "#f59e0b", "● Cambios"
        if "⚠" in status:  return "#ef4444", "⚠ Sin destino"
        return C["border2"], status[:18]

    def _gd_render_table(self, lst):
        """Vista tabla compacta — una fila por manwha."""
        tbl = tk.Frame(self._gd_tbl_frame, bg=C["bg3"])
        tbl.pack(fill="x", padx=0)

        # Cabecera
        cols = [("", 3), ("Manwha", 30), ("4_TYPE", 14), ("5_RECORTES", 14),
                ("Modif.", 10), ("Estado", 14), ("", 6)]
        hrow = tk.Frame(tbl, bg=C["bg4"])
        hrow.pack(fill="x")
        for col, w in cols:
            tk.Label(hrow, text=col, bg=C["bg4"], fg=C["teal"],
                     font=("Segoe UI", 8, "bold"), width=w,
                     anchor="w").pack(side="left", padx=3, pady=5)

        for i, m in enumerate(lst):
            bg = C["bg3"] if i % 2 == 0 else C["bg2"]
            row = tk.Frame(tbl, bg=bg)
            row.pack(fill="x")

            def _on_chk(m=m): self._gd_update_count()
            tk.Checkbutton(row, variable=m["selected"], command=_on_chk,
                           bg=bg, activebackground=bg, selectcolor=C["teal"],
                           relief="flat", bd=0, highlightthickness=0,
                           width=3).pack(side="left", padx=2)

            tk.Label(row, text=m["name"], bg=bg, fg=C["bright"],
                     font=("Segoe UI", 8), width=30, anchor="w").pack(side="left", padx=3, pady=4)
            tk.Label(row, text=m.get("src_name","—"), bg=bg, fg=C["text2"],
                     font=("Segoe UI", 7), width=14, anchor="w").pack(side="left", padx=3)
            dst_fg = C["ok"] if m.get("dst_id") else "#ef4444"
            tk.Label(row, text=m.get("dst_name","—"), bg=bg, fg=dst_fg,
                     font=("Segoe UI", 7), width=14, anchor="w").pack(side="left", padx=3)
            tk.Label(row, text=m.get("modified","—"), bg=bg, fg=C["dim"],
                     font=("Segoe UI", 7), width=10, anchor="w").pack(side="left", padx=3)

            accent, badge = self._gd_status_color(m.get("status",""))
            tk.Label(row, text=badge, bg=bg, fg=accent,
                     font=("Segoe UI", 7, "bold"), width=14,
                     anchor="w").pack(side="left", padx=3)

            self._sbtn(row, "▶", lambda m=m: self._gd_run_one(m)).pack(
                side="right", padx=(0, 8))

    def _gd_render_cards(self, lst):
        """Vista cards — 2 columnas (modo legado, accesible desde toggle)."""
        grid = tk.Frame(self._gd_tbl_frame, bg=C["bg3"])
        grid.pack(fill="x", padx=8, pady=4)
        COLS = 2
        for idx, m in enumerate(lst):
            col = idx % COLS
            row_n = idx // COLS
            accent_col, badge_text = self._gd_status_color(m.get("status",""))
            card = tk.Frame(grid, bg=C["bg2"],
                            highlightbackground=accent_col, highlightthickness=2)
            card.grid(row=row_n, column=col, padx=6, pady=5, sticky="nsew")
            grid.columnconfigure(col, weight=1)
            tk.Frame(card, bg=accent_col, height=3).pack(fill="x")
            body = tk.Frame(card, bg=C["bg2"])
            body.pack(fill="both", expand=True, padx=10, pady=8)
            row1 = tk.Frame(body, bg=C["bg2"]); row1.pack(fill="x")
            def _on_chk(m=m): self._gd_update_count()
            tk.Checkbutton(row1, variable=m["selected"], command=_on_chk,
                           bg=C["bg2"], activebackground=C["bg2"],
                           selectcolor=C["teal"], relief="flat",
                           bd=0, highlightthickness=0).pack(side="left")
            tk.Label(row1, text=m["name"], bg=C["bg2"], fg=C["bright"],
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(
                         side="left", fill="x", expand=True)
            tk.Label(row1, text=badge_text, bg=C["bg2"], fg=accent_col,
                     font=("Segoe UI", 7, "bold")).pack(side="right")
            tk.Frame(body, bg=C["border2"], height=1).pack(fill="x", pady=(4,4))
            info = tk.Frame(body, bg=C["bg2"]); info.pack(fill="x")
            def _info_row(icon, label, value, fg=None):
                r = tk.Frame(info, bg=C["bg2"]); r.pack(fill="x", pady=1)
                tk.Label(r, text=icon, bg=C["bg2"], fg=C["teal"],
                         font=("Segoe UI", 8), width=2).pack(side="left")
                tk.Label(r, text=label, bg=C["bg2"], fg=C["dim"],
                         font=("Segoe UI", 7), width=7, anchor="w").pack(side="left")
                tk.Label(r, text=value, bg=C["bg2"], fg=fg or C["text2"],
                         font=("Segoe UI", 7), anchor="w").pack(side="left")
            _info_row("📥", "Origen:", m.get("src_name","—"), C["text"])
            _info_row("📤", "Destino:", m.get("dst_name","—"),
                      C["ok"] if m.get("dst_id") else "#ef4444")
            _info_row("🗂", "Raw:", m.get("raw_name","—"),
                      C["text2"] if m.get("raw_id") else C["dim"])
            _info_row("📅", "Modif.:", m.get("modified","—"))
            btns = tk.Frame(body, bg=C["bg2"]); btns.pack(fill="x", pady=(6,0))
            make_btn(btns, "▶ Procesar", lambda m=m: self._gd_run_one(m),
                     bg=C["teal"], fg=C["bg"],
                     hover_bg=C["cyan"], hover_fg=C["bg"],
                     small=True).pack(side="left", padx=(0,4))
            def _open_drive(m=m):
                import webbrowser
                webbrowser.open(f"https://drive.google.com/drive/folders/{m['id']}")
            self._sbtn(btns, "☁ Abrir", _open_drive).pack(side="left")

    def _gd_render_grouped_list(self, lst):
        """
        Vista lista con agrupado jerárquico de 2 niveles.
        El campo 'group' contiene el path completo separado por ' › '
        Ej: 'Manwhas › X Dia › 5_Jueves'
        Se renderizan grupos raíz y subgrupos colapsables.
        """
        from collections import OrderedDict

        # Construir árbol: top_group → {subgroup → [manwha]}
        tree = OrderedDict()  # {top: OrderedDict({sub: [manwha]})}

        for m in lst:
            grp = m.get("group", "") or ""
            parts = [p.strip() for p in grp.split("›") if p.strip()]
            # Último elemento antes del manwha es el subgrupo (día)
            # Penúltimo es el grupo padre (X Dia)
            if len(parts) >= 2:
                top = parts[-2]   # ej: "X Dia"
                sub = parts[-1]   # ej: "5_Jueves"
            elif len(parts) == 1:
                top = parts[0]
                sub = ""
            else:
                top = "Sin grupo"
                sub = ""

            tree.setdefault(top, OrderedDict())
            tree[top].setdefault(sub, []).append(m)

        wrap = tk.Frame(self._gd_tbl_frame, bg=C["bg"])
        wrap.pack(fill="x", padx=0, pady=0)

        def _manwha_row(parent, m, indent=0, alt=False):
            """Renderiza una fila de manwha."""
            accent, badge = self._gd_status_color(m.get("status", ""))
            bg = C["bg3"] if not alt else C["bg2"]

            row = tk.Frame(parent, bg=bg)
            row.pack(fill="x")

            tk.Frame(row, bg=accent, width=3).pack(side="left", fill="y")
            if indent:
                tk.Frame(row, bg=bg, width=indent).pack(side="left")

            def _on_chk(m=m): self._gd_update_count()
            tk.Checkbutton(row, variable=m["selected"], command=_on_chk,
                           bg=bg, activebackground=bg, selectcolor=C["teal"],
                           relief="flat", bd=0, highlightthickness=0
                           ).pack(side="left", padx=(4, 0), pady=5)

            tk.Label(row, text=m["name"], bg=bg, fg=C["bright"],
                     font=("Segoe UI", 9, "bold"), anchor="w"
                     ).pack(side="left", padx=(6, 0), fill="x", expand=True)

            tk.Label(row,
                     text=f"  {m.get('src_name','—')} → {m.get('dst_name','—')}  ·  {m.get('modified','')}",
                     bg=bg, fg=C["dim"], font=("Segoe UI", 7), anchor="w"
                     ).pack(side="left", padx=(2, 0))

            tk.Label(row, text=badge, bg=bg, fg=accent,
                     font=("Segoe UI", 7, "bold")).pack(side="right", padx=(0, 8))

            make_btn(row, "▶", lambda m=m: self._gd_run_one(m),
                     bg=C["teal"], fg=C["bg"], hover_bg=C["cyan"], hover_fg=C["bg"],
                     small=True, padx=6).pack(side="right", padx=(0, 4), pady=3)

            def _open_drive(m=m):
                import webbrowser
                webbrowser.open(f"https://drive.google.com/drive/folders/{m['id']}")
            self._sbtn(row, "☁", _open_drive).pack(side="right", padx=(0, 2))

        def _group_header(parent, label, members_flat, bg=C["bg4"], font_size=8,
                          indent=0, emoji="📂"):
            """Header de grupo con checkbox de selección masiva."""
            hdr = tk.Frame(parent, bg=bg)
            hdr.pack(fill="x", pady=(5, 0))
            if indent:
                tk.Frame(hdr, bg=bg, width=indent).pack(side="left")
            grp_var = tk.BooleanVar(value=False)
            def _toggle(members=members_flat, var=grp_var):
                v = var.get()
                for mm in members: mm["selected"].set(v)
                self._gd_update_count()
            tk.Checkbutton(hdr, variable=grp_var, command=_toggle,
                           bg=bg, activebackground=bg, selectcolor=C["teal"],
                           relief="flat", bd=0, highlightthickness=0
                           ).pack(side="left", padx=(8, 0))
            tk.Label(hdr, text=f"{emoji}  {label}", bg=bg, fg=C["teal"],
                     font=("Segoe UI", font_size, "bold")).pack(side="left", padx=6, pady=5)
            total = len(members_flat)
            tk.Label(hdr, text=f"{total} manwha", bg=bg, fg=C["dim"],
                     font=("Segoe UI", 7)).pack(side="left")

        for top_name, subgroups in tree.items():
            # Todos los manwha del grupo raíz (aplanado)
            all_in_top = [m for subs in subgroups.values() for m in subs]
            has_subs = any(s for s in subgroups.keys())

            if len(subgroups) == 1 and not has_subs:
                # Solo un subgrupo vacío — renderizar plano
                _group_header(wrap, top_name, all_in_top, emoji="📂")
                for i, m in enumerate(all_in_top):
                    _manwha_row(wrap, m, indent=20, alt=(i % 2 == 1))
            else:
                # Header raíz
                _group_header(wrap, top_name, all_in_top,
                              bg=C["bg4"], font_size=9, emoji="📁")

                for sub_name, members in subgroups.items():
                    if sub_name:
                        # Sub-header del día/subgrupo
                        sub_bg = C["bg3"]
                        shdr = tk.Frame(wrap, bg=sub_bg)
                        shdr.pack(fill="x", pady=(2, 0))
                        tk.Frame(shdr, bg=sub_bg, width=20).pack(side="left")
                        sub_var = tk.BooleanVar(value=False)
                        def _toggle_sub(members=members, var=sub_var):
                            v = var.get()
                            for mm in members: mm["selected"].set(v)
                            self._gd_update_count()
                        tk.Checkbutton(shdr, variable=sub_var, command=_toggle_sub,
                                       bg=sub_bg, activebackground=sub_bg,
                                       selectcolor=C["teal"], relief="flat",
                                       bd=0, highlightthickness=0).pack(side="left", padx=(4,0))
                        tk.Label(shdr, text=f"📅  {sub_name}",
                                 bg=sub_bg, fg=C["cyan"],
                                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=6, pady=4)
                        tk.Label(shdr, text=f"{len(members)} manwha",
                                 bg=sub_bg, fg=C["dim"],
                                 font=("Segoe UI", 7)).pack(side="left")
                        for i, m in enumerate(members):
                            _manwha_row(wrap, m, indent=40, alt=(i % 2 == 1))
                    else:
                        for i, m in enumerate(members):
                            _manwha_row(wrap, m, indent=20, alt=(i % 2 == 1))
    def _gd_update_count(self):
        lst = getattr(self, "_gd_filtered", [])
        sel = sum(1 for m in lst if m["selected"].get())
        if hasattr(self, "_gd_sel_lbl"):
            self._gd_sel_lbl.config(
                text=f"{sel} seleccionado(s) de {len(lst)}")

    # ── lista de imágenes en carpeta ──────────────────────────────────────────
    def _gd_list_images(self, folder_id):
        """Lista solo archivos de imagen en folder_id (no subcarpetas)."""
        if not self._gd_service: return []
        VALID = {".jpg", ".jpeg", ".png", ".webp", ".bmp",
                 ".gif", ".tiff", ".tif", ".psd", ".psb", ".avif"}
        results = []; page_token = None
        # Excluir carpetas explícitamente en el query
        q = (f"'{folder_id}' in parents and trashed=false"
             f" and mimeType!='application/vnd.google-apps.folder'")
        while True:
            resp = self._gd_api(
                self._gd_service.files().list,
                q=q, spaces="drive",
                fields="nextPageToken, files(id, name, size, mimeType)",
                pageToken=page_token, orderBy="name", pageSize=200)
            for f in resp.get("files", []):
                if Path(f["name"]).suffix.lower() in VALID:
                    results.append(f)
            page_token = resp.get("nextPageToken")
            if not page_token: break
        return results

    def _gd_extract_cap_number(self, name):
        """Extrae el número de capítulo de un nombre de carpeta/archivo.
        Ejemplos: 'Cap 01', 'Capitulo_15', '[12] titulo', '001 - nombre' → int
        Devuelve (numero_int, nombre_limpio) o (None, name).
        """
        import re as _re
        # Patrones más comunes para capítulos
        patterns = [
            r"cap(?:itulo)?[\.\s_\-]*(\d+)",
            r"ch(?:apter)?[\.\s_\-]*(\d+)",
            r"^\[?(\d+)\]?[\s_\-]",
            r"(\d+)$",
            r"(\d+)",
        ]
        name_low = name.lower()
        for pat in patterns:
            m = _re.search(pat, name_low)
            if m:
                return int(m.group(1)), name
        return None, name

    def _gd_list_chapters(self, src_id):
        """Lista las subcarpetas de capítulos dentro de src_id (4_TYPE).
        Devuelve lista de dicts: {id, name, cap_num, files_count_approx}
        ordenada por número de capítulo.
        """
        # Primero ver qué hay directamente: ¿archivos o subcarpetas?
        all_children = self._gd_list_children(src_id, only_folders=False)
        folders = [c for c in all_children
                   if c.get("mimeType") == "application/vnd.google-apps.folder"]
        files   = [c for c in all_children
                   if c.get("mimeType") != "application/vnd.google-apps.folder"]

        VALID_EXT = {".jpg", ".jpeg", ".png", ".webp", ".psd", ".psb",
                     ".bmp", ".tiff", ".tif", ".avif"}

        if not folders:
            # Archivos sueltos directamente en 4_TYPE — tratarlo como un solo capítulo
            imgs = [f for f in files
                    if Path(f["name"]).suffix.lower() in VALID_EXT]
            if imgs:
                cap_num, _ = self._gd_extract_cap_number(
                    next((f["name"] for f in imgs), ""))
                return [{"id": src_id, "name": "Capítulo único",
                         "cap_num": cap_num or 0,
                         "file_count": len(imgs),
                         "is_direct": True}]
            return []

        # Hay subcarpetas → son los capítulos
        chapters = []
        for f in folders:
            cap_num, _ = self._gd_extract_cap_number(f["name"])
            chapters.append({
                "id":         f["id"],
                "name":       f["name"],
                "cap_num":    cap_num,
                "file_count": "?",   # se carga lazy si el usuario lo pide
                "is_direct":  False,
                "modified":   f.get("modifiedTime", "")[:10],
            })

        # Ordenar: primero por número extraído, luego por nombre
        chapters.sort(key=lambda c: (
            c["cap_num"] if c["cap_num"] is not None else 9999,
            c["name"].lower()
        ))
        return chapters

    # ── descargar / subir ─────────────────────────────────────────────────────
    def _gd_download(self, file_id, dest_path, progress_cb=None):
        """Descarga un archivo con retry automático (hasta 4 intentos)."""
        import io as _io2, time as _time
        last_ex = None
        for attempt in range(4):
            try:
                req = self._gd_service.files().get_media(fileId=file_id)
                with open(dest_path, "wb") as fh:
                    dl = MediaIoBaseDownload(fh, req, chunksize=4 * 1024 * 1024)
                    done = False
                    while not done:
                        status, done = dl.next_chunk()
                        if progress_cb and status:
                            progress_cb(status.resumable_progress,
                                        status.total_size or 1)
                # Verificar que el archivo descargado tiene tamaño > 0
                if os.path.getsize(dest_path) > 0:
                    return  # ✅ éxito
                raise IOError("Archivo descargado vacío")
            except Exception as ex:
                last_ex = ex
                if attempt < 3:
                    _time.sleep(2 ** attempt)  # backoff: 1s, 2s, 4s
                # Limpiar archivo corrupto antes de reintentar
                try: os.remove(dest_path)
                except: pass
        raise IOError(f"Descarga fallida tras 4 intentos: {last_ex}")

    def _gd_upload(self, local_path, folder_id):
        ext   = Path(local_path).suffix.lower()
        mimes = {".png": "image/png", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".webp": "image/webp",
                 ".tif": "image/tiff", ".tiff": "image/tiff"}
        mime  = mimes.get(ext, "application/octet-stream")
        name  = os.path.basename(local_path)
        q     = (f"name='{name}' and '{folder_id}' in parents "
                 f"and trashed=false")
        existing = self._gd_api(
            self._gd_service.files().list,
            q=q, fields="files(id)").get("files", [])
        media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
        if existing:
            self._gd_api(self._gd_service.files().update,
                         fileId=existing[0]["id"], media_body=media)
        else:
            self._gd_api(self._gd_service.files().create,
                         body={"name": name, "parents": [folder_id]},
                         media_body=media, fields="id")

    # ── pipeline: procesar un manwha ──────────────────────────────────────────
    def _gd_run_one(self, m: dict):
        """Abre el panel de selección de capítulos para un manwha."""
        if not m.get("src_id"):
            messagebox.showwarning("Sin origen",
                f"'{m['name']}' no tiene carpeta fuente (4_TYPE).")
            return
        self._gd_open_chapter_selector(m)

    def _gd_open_chapter_selector(self, m: dict):
        """Panel flotante para elegir qué capítulos procesar."""
        if not self._gd_service:
            messagebox.showwarning("No conectado", "Conectate a Drive primero.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Capítulos — {m['name']}")
        win.geometry("680x560")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.grab_set()

        # Header
        hd = tk.Frame(win, bg=C["bg2"], height=48)
        hd.pack(fill="x"); hd.pack_propagate(False)
        tk.Label(hd, text=f"📚  {m['name']}",
                 bg=C["bg2"], fg=C["bright"],
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(hd, text=f"Fuente: {m.get('src_name','?')}   Destino: {m.get('dst_name','?')}",
                 bg=C["bg2"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Frame(win, bg=C["border"], height=1).pack(fill="x")

        # Barra herramientas
        bar = tk.Frame(win, bg=C["bg3"])
        bar.pack(fill="x", padx=0, pady=0)
        tk.Label(bar, text="Seleccioná los capítulos a procesar:",
                 bg=C["bg3"], fg=C["text2"],
                 font=("Segoe UI", 8)).pack(side="left", padx=12, pady=8)
        status_lbl = tk.Label(bar, text="Cargando…",
                              bg=C["bg3"], fg=C["teal"],
                              font=("Segoe UI", 8))
        status_lbl.pack(side="left")

        def _sel_all():
            for v in chk_vars: v.set(True)
            _update_count()
        def _sel_none():
            for v in chk_vars: v.set(False)
            _update_count()
        make_btn(bar, "✓ Todos", _sel_all,
                 bg=C["bg4"], fg=C["text2"], small=True).pack(
                     side="right", padx=(0,4), pady=6)
        make_btn(bar, "✗ Ninguno", _sel_none,
                 bg=C["bg4"], fg=C["text2"], small=True).pack(
                     side="right", padx=(0,4), pady=6)
        sel_count_lbl = tk.Label(bar, text="0 sel.",
                                 bg=C["bg3"], fg=C["dim"],
                                 font=("Segoe UI", 7))
        sel_count_lbl.pack(side="right", padx=(0, 8))
        tk.Frame(win, bg=C["border2"], height=1).pack(fill="x")

        # Lista scrollable de capítulos
        list_outer = tk.Frame(win, bg=C["bg"])
        list_outer.pack(fill="both", expand=True, padx=0)
        cv = tk.Canvas(list_outer, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(list_outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=C["bg"])
        win_id = cv.create_window((0, 0), window=inner, anchor="nw")
        cv.bind("<Configure>", lambda e: cv.itemconfig(win_id, width=e.width))
        inner.bind("<Configure>",
                   lambda e: cv.configure(scrollregion=cv.bbox("all")))
        def _on_scroll(e):
            cv.yview_scroll(int(-1*(e.delta/120)), "units")
        cv.bind("<MouseWheel>", _on_scroll)
        inner.bind("<MouseWheel>", _on_scroll)

        def _bind_scroll_recursive(widget):
            widget.bind("<MouseWheel>", _on_scroll)
            for child in widget.winfo_children():
                _bind_scroll_recursive(child)
        # Re-bind after list builds
        inner.bind("<Configure>", lambda e: (
            cv.configure(scrollregion=cv.bbox("all")),
            _bind_scroll_recursive(inner)
        ))

        chk_vars = []
        chapters_ref = [None]   # se llena async

        def _update_count():
            n = sum(1 for v in chk_vars if v.get())
            sel_count_lbl.config(text=f"{n} sel.")

        def _build_list(chapters):
            chapters_ref[0] = chapters
            for w in inner.winfo_children(): w.destroy()
            chk_vars.clear()

            if not chapters:
                tk.Label(inner, text="No se encontraron capítulos en esta carpeta.",
                         bg=C["bg"], fg=C["dim"],
                         font=("Segoe UI", 9)).pack(pady=20)
                status_lbl.config(text="Sin capítulos")
                return

            status_lbl.config(text=f"{len(chapters)} capítulo(s) encontrado(s)")

            for i, cap in enumerate(chapters):
                bg = C["bg3"] if i % 2 == 0 else C["bg2"]
                row = tk.Frame(inner, bg=bg)
                row.pack(fill="x", padx=0)

                var = tk.BooleanVar(value=True)   # por defecto seleccionado
                chk_vars.append(var)

                def _on_chk(v=var): _update_count()
                tk.Checkbutton(row, variable=var, command=_on_chk,
                               bg=bg, activebackground=bg,
                               selectcolor=C["teal"],
                               relief="flat", bd=0, highlightthickness=0
                               ).pack(side="left", padx=(8,0), pady=6)

                # Número de cap prominente
                cap_num = cap.get("cap_num")
                num_text = f"Cap {cap_num:03d}" if cap_num is not None else "???"
                tk.Label(row, text=num_text,
                         bg=bg, fg=C["teal"],
                         font=("Segoe UI", 9, "bold"),
                         width=8, anchor="w").pack(side="left", padx=(4,0))

                # Nombre completo
                tk.Label(row, text=cap["name"],
                         bg=bg, fg=C["text"],
                         font=("Segoe UI", 8), anchor="w").pack(
                             side="left", fill="x", expand=True)

                # Fecha
                if cap.get("modified"):
                    tk.Label(row, text=cap["modified"],
                             bg=bg, fg=C["dim"],
                             font=("Segoe UI", 7)).pack(side="right", padx=12)

            _update_count()

        def _load_chapters():
            try:
                chapters = self._gd_list_chapters(m["src_id"])
                win.after(0, lambda: _build_list(chapters))
            except Exception as ex:
                import traceback; traceback.print_exc()
                err_msg = str(ex)
                win.after(0, lambda e=err_msg: status_lbl.config(
                    text=f"❌ Error: {e}", fg=C["err"]))

        threading.Thread(target=_load_chapters, daemon=True).start()

        # Footer — opciones rápidas + botón procesar
        tk.Frame(win, bg=C["border"], height=1).pack(fill="x", side="bottom")
        foot = tk.Frame(win, bg=C["bg2"], height=54)
        foot.pack(fill="x", side="bottom"); foot.pack_propagate(False)

        # Opciones rápidas inline
        opt_frame = tk.Frame(foot, bg=C["bg2"]); opt_frame.pack(side="left", padx=12, pady=8)

        fmt_v = tk.StringVar(value=getattr(self,"_gd_fmt",tk.StringVar(value="WEBP")).get())
        h_v   = tk.StringVar(value=str(self.cfg.get("gdrive_height", 10000)))

        tk.Label(opt_frame, text="Fmt:", bg=C["bg2"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="left")
        self._combo(opt_frame, fmt_v, ["WEBP","JPEG","PNG"], 5).pack(
            side="left", padx=(2,10))
        tk.Label(opt_frame, text="Altura:", bg=C["bg2"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Entry(opt_frame, textvariable=h_v, width=6,
                 bg=C["bg4"], fg=C["text"], relief="flat",
                 font=("Segoe UI", 8), insertbackground=C["teal"],
                 highlightthickness=1, highlightbackground=C["border"],
                 highlightcolor=C["teal"]).pack(side="left", padx=(2,0))
        for px in ["5000","10000","30000"]:
            self._sbtn(opt_frame, px,
                       lambda x=px: h_v.set(x)).pack(side="left", padx=(3,0))

        do_cv_v = tk.BooleanVar(value=True)
        do_st_v = tk.BooleanVar(value=True)
        for var, lbl in [(do_cv_v,"🔄 Conv"),(do_st_v,"✂ Stitch")]:
            f = tk.Frame(foot, bg=C["bg2"]); f.pack(side="left", padx=(0,8), pady=8)
            self._toggle(f, var, lambda: None).pack(side="left", padx=(0,4))
            tk.Label(f, text=lbl, bg=C["bg2"], fg=C["text2"],
                     font=("Segoe UI", 8)).pack(side="left")

        def _run():
            if chapters_ref[0] is None:
                return
            sel_caps = [cap for cap, var in zip(chapters_ref[0], chk_vars)
                        if var.get()]
            if not sel_caps:
                messagebox.showwarning("Sin selección",
                    "Marcá al menos un capítulo.", parent=win)
                return
            win.destroy()
            self._gd_run_batch_chapters(m, sel_caps,
                                        fmt=fmt_v.get(),
                                        height=int(h_v.get() or 10000),
                                        do_cv=do_cv_v.get(),
                                        do_st=do_st_v.get())

        make_btn(foot, f"▶ Procesar seleccionados", _run,
                 bg=C["teal"], fg=C["bg"],
                 hover_bg=C["cyan"], hover_fg=C["bg"],
                 font=("Segoe UI", 9, "bold"), padx=14
                 ).pack(side="right", padx=12, pady=8)

    def _gd_run_selected(self):
        """Procesa todos los manwha seleccionados con checkbox."""
        lst = getattr(self, "_gd_filtered", [])
        sel = [m for m in lst if m["selected"].get()]
        if not sel:
            messagebox.showwarning("Sin selección",
                "Marcá al menos un manwha con el checkbox.")
            return
        no_dst = [m["name"] for m in sel if not m.get("dst_id")]
        if no_dst:
            messagebox.showwarning(
                "Sin destino",
                f"Estos manwha no tienen '{self._GD_DST_FOLDER}':\n"
                + "\n".join(no_dst))
            sel = [m for m in sel if m.get("dst_id")]
        if sel:
            self._gd_run_batch(sel)

    def _gd_run_batch_chapters(self, m: dict, chapters: list,
                               fmt="WEBP", height=10000,
                               do_cv=True, do_st=True):
        """
        Pipeline Drive: descarga → convierte → stitch → ZIP → sube.
        Un ZIP por capítulo, con logs detallados en la barra de estado.
        """
        if self._gd_running:
            messagebox.showinfo("En proceso", "Ya hay un proceso en curso.")
            return

        dst_id = m.get("dst_id")
        ext    = {"JPEG":".jpg","PNG":".png","WEBP":".webp",
                  "BMP":".bmp","TIFF":".tif"}.get(fmt, ".webp")
        kw_img = {"quality": 92} if fmt in ("JPEG","WEBP") else {}

        self._gd_running = True
        if hasattr(self,"_gd_run_btn"):  btn_set_state(self._gd_run_btn,  "disabled")
        if hasattr(self,"_gd_run1_btn"): btn_set_state(self._gd_run1_btn, "disabled")

        def _st(msg, pct=None, color=None):
            """Shortcut: actualiza status bar de Drive."""
            self._gd_st(msg, pct, color)

        def _pipeline():
            total_caps = len(chapters)
            ok_count   = 0

            for cap_idx, cap in enumerate(chapters):
                if not self._gd_running: break
                cap_name = cap["name"]
                cap_num  = cap.get("cap_num")
                label    = f"[{cap_idx+1}/{total_caps}] {cap_name}"
                pct_base = int(95 * cap_idx / total_caps)

                tmp      = tempfile.mkdtemp(prefix="bloom_cap_")
                dl_dir   = os.path.join(tmp, "dl");   os.makedirs(dl_dir)
                proc_dir = os.path.join(tmp, "proc"); os.makedirs(proc_dir)

                try:
                    # ── 1. LISTAR imágenes del capítulo ───────────────────
                    _st(f"📋 {label}: listando imágenes en Drive…", pct_base)
                    images = self._gd_list_images(cap["id"])

                    if not images:
                        _st(f"⚠ {label}: sin imágenes — saltando", color=C["warn"])
                        continue

                    total_f = len(images)
                    _st(f"📋 {label}: {total_f} imagen(es) encontrada(s)", pct_base + 1)

                    # ── 2. DESCARGAR — secuencial con retry ───────────────
                    _st(f"⬇ {label}: descargando {total_f} archivo(s)…", pct_base + 2)
                    local_sorted = []
                    dl_errors    = []

                    for idx_f, img in enumerate(images):
                        if not self._gd_running: break
                        lp = os.path.join(dl_dir, f"{idx_f:04d}_{img['name']}")
                        _st(f"⬇ {label}: {idx_f+1}/{total_f} — {img['name']}…",
                            pct_base + 2 + int(18 * (idx_f+1) / total_f))
                        try:
                            self._gd_download(img["id"], lp)
                            local_sorted.append(lp)
                        except Exception as ex:
                            dl_errors.append(img['name'])
                            _st(f"⚠ DL fallido ({img['name']}): {ex}", color=C["warn"])

                    # Ya vienen en orden (images ya está ordenado por Drive API)
                    # Pero re-ordenamos por nombre del archivo local por si acaso
                    local_sorted.sort(key=lambda p: os.path.basename(p).lower())

                    if not local_sorted:
                        _st(f"❌ {label}: todos los downloads fallaron", color=C["err"])
                        continue

                    dl_ok = len(local_sorted)
                    if dl_errors:
                        _st(f"⚠ {label}: {dl_ok}/{total_f} descargados "
                            f"({len(dl_errors)} fallidos: {', '.join(dl_errors[:3])}{'…' if len(dl_errors)>3 else ''})",
                            pct_base + 20, C["warn"])
                    else:
                        _st(f"✅ {label}: {dl_ok}/{total_f} descargados OK", pct_base + 20)

                    # ── 3. CONVERTIR (PSD/PNG → WEBP/JPEG/PNG) ────────────
                    processed = list(local_sorted)
                    if do_cv:
                        _st(f"🔄 {label}: convirtiendo {dl_ok} imagen(es) a {fmt}…",
                            pct_base + 22)
                        conv_res = []
                        for i, src in enumerate(processed):
                            try:
                                img = open_image_safe(src)
                                if img.mode in ("RGBA","LA","P") and fmt == "JPEG":
                                    img = img.convert("RGB")
                                elif img.mode not in ("RGB","RGBA","L"):
                                    img = img.convert("RGB")
                                dst = os.path.join(proc_dir, f"conv_{i:04d}{ext}")
                                img.save(dst, fmt, **kw_img)
                                img.close(); del img
                                conv_res.append(dst)
                                _st(f"🔄 {label}: convirtiendo {i+1}/{dl_ok}…",
                                    pct_base + 22 + int(13 * (i+1) / dl_ok))
                            except Exception as ex:
                                _st(f"⚠ Conv {os.path.basename(src)}: {ex}", color=C["warn"])
                                conv_res.append(src)  # fallback: usar original
                        processed = conv_res
                        _st(f"✅ {label}: conversión lista ({len(processed)} imgs)",
                            pct_base + 35)

                    # ── 4. MEDIR dimensiones para log y ajuste de seg ──────
                    total_px_h = 0
                    img_widths = []
                    for fp in processed:
                        try:
                            with Image.open(fp) as im:
                                total_px_h += im.height
                                img_widths.append(im.width)
                        except Exception:
                            pass

                    n_imgs = len(processed)
                    seg    = height  # altura de cada tira
                    if total_px_h > 0 and img_widths:
                        tiras_est = max(1, math.ceil(total_px_h / seg))
                        _st(f"📐 {label}: {n_imgs} imgs · {total_px_h}px alto total "
                            f"· seg={seg}px → {tiras_est} tira(s) esperada(s)",
                            pct_base + 36)
                    else:
                        tiras_est = 0
                        _st(f"⚠ {label}: no se pudieron leer dimensiones", color=C["warn"])

                    # ── 5. STITCH ─────────────────────────────────────────
                    if do_st and processed:
                        _st(f"✂ {label}: haciendo stitch (seg={seg}px)…", pct_base + 38)

                        # Calcular ancho objetivo
                        align = self.cfg.get("align","smallest")
                        if img_widths:
                            if align == "smallest": W = min(img_widths)
                            elif align == "largest": W = max(img_widths)
                            else: W = img_widths[0]
                        else:
                            W = 0

                        stitch_res = []
                        stitch_n   = 1
                        buf        = None
                        bf         = 0  # píxeles acumulados en buf

                        if W > 0:
                            buf = Image.new("RGB", (W, max(seg * 2, 1)), (255,255,255))

                            def _flush():
                                nonlocal buf, bf, stitch_n
                                while bf >= seg:
                                    dst2 = os.path.join(proc_dir, f"stitch_{stitch_n:04d}{ext}")
                                    buf.crop((0, 0, W, seg)).save(dst2, fmt, **kw_img)
                                    stitch_res.append(dst2)
                                    _st(f"✂ {label}: tira {stitch_n} guardada ({seg}px)",
                                        pct_base + 38 + int(17 * stitch_n / max(tiras_est, 1)))
                                    stitch_n += 1
                                    remaining = bf - seg
                                    new_h = max(seg * 2, remaining + seg)
                                    new_buf = Image.new("RGB", (W, new_h), (255,255,255))
                                    if remaining > 0:
                                        new_buf.paste(buf.crop((0, seg, W, seg + remaining)), (0,0))
                                    buf.close()
                                    buf = new_buf
                                    bf  = remaining

                            for fi, fpath in enumerate(processed):
                                try:
                                    img = open_image_safe(fpath)
                                    img.load()
                                    if img.mode not in ("RGB","RGBA"):
                                        img = img.convert("RGB")
                                    if img.width != W:
                                        ratio = W / img.width
                                        img = img.resize(
                                            (W, max(1, int(img.height * ratio))),
                                            Image.BILINEAR)
                                    if img.mode != "RGB":
                                        img = img.convert("RGB")
                                    ih = img.height
                                    # Expandir buffer si no cabe
                                    if bf + ih > buf.height:
                                        new_h = max(buf.height + ih + seg, seg * 3)
                                        new_buf = Image.new("RGB",(W,new_h),(255,255,255))
                                        new_buf.paste(buf.crop((0,0,W,bf)),(0,0))
                                        buf.close(); buf = new_buf
                                    buf.paste(img, (0, bf))
                                    bf += ih
                                    img.close(); del img
                                    _flush()
                                    _st(f"✂ {label}: página {fi+1}/{n_imgs} procesada "
                                        f"(buf={bf}px, tiras={len(stitch_res)})",
                                        pct_base + 38 + int(17 * fi / max(n_imgs,1)))
                                except Exception as ex:
                                    _st(f"⚠ Stitch pág {fi+1}: {ex}", color=C["warn"])

                            # Último segmento (resto)
                            if bf > 0:
                                dst2 = os.path.join(proc_dir, f"stitch_{stitch_n:04d}{ext}")
                                buf.crop((0, 0, W, bf)).save(dst2, fmt, **kw_img)
                                stitch_res.append(dst2)
                                _st(f"✂ {label}: última tira guardada ({bf}px)",
                                    pct_base + 55)
                            buf.close()

                        processed = stitch_res if stitch_res else processed
                        _st(f"✅ {label}: stitch listo → {len(processed)} tira(s)",
                            pct_base + 56, C["ok"])

                    # ── 6. CREAR ZIP ──────────────────────────────────────
                    n_files = len(processed)
                    # Nombre del ZIP = número de capítulo con ceros, ej "07.zip"
                    if cap_num is not None:
                        zip_stem = f"{cap_num:02d}"
                    else:
                        zip_stem = cap_name
                    zip_name = f"{zip_stem}.zip"
                    zip_path = os.path.join(proc_dir, zip_name)

                    _st(f"🗜 {label}: comprimiendo {n_files} archivo(s) → {zip_name}…",
                        pct_base + 58)
                    already_compressed = ext in (".jpg",".jpeg",".webp")
                    zmode = zipfile.ZIP_STORED if already_compressed else zipfile.ZIP_DEFLATED
                    with zipfile.ZipFile(zip_path, "w", zmode) as zf:
                        for i, fp in enumerate(processed):
                            if os.path.exists(fp):
                                zf.write(fp, os.path.basename(fp))
                                _st(f"🗜 {label}: añadiendo {i+1}/{n_files} al ZIP…",
                                    pct_base + 58 + int(10 * (i+1) / max(n_files,1)))

                    zip_size_mb = os.path.getsize(zip_path) / (1024*1024) if os.path.exists(zip_path) else 0
                    _st(f"✅ {label}: ZIP creado → {zip_name} ({zip_size_mb:.1f} MB)",
                        pct_base + 68, C["ok"])

                    # ── 7. SUBIR ZIP a Drive ──────────────────────────────
                    if dst_id:
                        _st(f"⬆ {label}: subiendo {zip_name} a Drive…", pct_base + 70)
                        try:
                            self._gd_upload(zip_path, dst_id)
                            _st(f"✅ {label}: {zip_name} subido a '{m.get('dst_name','5_RECORTES')}'",
                                pct_base + 88, C["ok"])
                        except Exception as ex:
                            _st(f"❌ {label}: error al subir {zip_name}: {ex}",
                                color=C["err"])
                    else:
                        # Sin destino Drive → guardar localmente
                        local_out = os.path.join(str(WORK_DIR), "output_drive", m["name"])
                        os.makedirs(local_out, exist_ok=True)
                        shutil.copy2(zip_path, os.path.join(local_out, zip_name))
                        _st(f"💾 {label}: guardado en {local_out}", pct_base + 88, C["ok"])

                    ok_count += 1

                except Exception as ex:
                    import traceback; traceback.print_exc()
                    _st(f"❌ {label}: {ex}", color=C["err"])
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

            # ── FIN ────────────────────────────────────────────────────────
            if self._gd_running:
                msg = (f"✅ {ok_count}/{total_caps} capítulo(s) procesado(s)\n"
                       f"{m['name']} — {fmt} {height}px")
                _st(msg, 100, C["ok"])
                self.root.after(0, lambda: messagebox.showinfo(
                    "Completado", msg.replace("\n","\n")))

            self._gd_running = False
            self.root.after(0, lambda: (
                btn_set_state(self._gd_run_btn, "normal")
                if hasattr(self,"_gd_run_btn") else None,
                btn_set_state(self._gd_run1_btn, "normal")
                if hasattr(self,"_gd_run1_btn") else None,
            ))

        threading.Thread(target=_pipeline, daemon=True).start()

    def _gd_run_batch(self, manwha_list: list):
        if self._gd_running:
            messagebox.showinfo("En proceso", "Ya hay un proceso en curso."); return

        fmt    = getattr(self, "_gd_fmt",    tk.StringVar(value="WEBP")).get()
        height = int(getattr(self, "_gd_height",
                             tk.StringVar(value="10000")).get() or 10000)
        do_cv  = getattr(self, "_gd_cv",  tk.BooleanVar(value=True)).get()
        do_st  = getattr(self, "_gd_sv",  tk.BooleanVar(value=True)).get()
        ext    = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp",
                  "BMP": ".bmp",  "TIFF": ".tif"}.get(fmt, ".webp")

        self._gd_running = True
        if hasattr(self, "_gd_run_btn"):  btn_set_state(self._gd_run_btn, "disabled")
        if hasattr(self, "_gd_run1_btn"): btn_set_state(self._gd_run1_btn, "disabled")

        def _pipeline():
            total_mw = len(manwha_list)
            for mw_idx, m in enumerate(manwha_list):
                if not self._gd_running: break
                name   = m["name"]
                src_id = m["src_id"]
                dst_id = m["dst_id"]
                prefix = f"[{mw_idx+1}/{total_mw}] {name}"
                tmp = tempfile.mkdtemp(prefix="bloom_gd_")
                dl_dir   = os.path.join(tmp, "dl");   os.makedirs(dl_dir)
                proc_dir = os.path.join(tmp, "proc"); os.makedirs(proc_dir)
                try:
                    # 1. Listar
                    self._gd_st(f"📋 {prefix}: listando…", 2)
                    files = self._gd_list_images(src_id)
                    if not files:
                        self._gd_st(f"⚠ {name}: sin imágenes en {m['src_name']}",
                                    color=C["warn"])
                        continue
                    total_f = len(files)
                    # 2. Descargar en paralelo
                    local = [None] * total_f
                    dl_done = [0]
                    dl_lock = threading.Lock()
                    def _dl_one(idx_f):
                        f = files[idx_f]
                        lp = os.path.join(dl_dir, f["name"])
                        try:
                            self._gd_download(f["id"], lp)
                            local[idx_f] = lp
                        except Exception as ex:
                            self._gd_st(f"⚠ DL error {f['name']}: {ex}",
                                        color=C["warn"])
                        with dl_lock:
                            dl_done[0] += 1
                            base_pct = 5 + int(85 * mw_idx / total_mw)
                            self._gd_st(
                                f"📥 {prefix}: {dl_done[0]}/{total_f} archivos…",
                                base_pct + int(30 * dl_done[0] / total_f))
                    dl_workers = min(4, total_f)
                    with ThreadPoolExecutor(max_workers=dl_workers) as dl_ex:
                        list(dl_ex.map(_dl_one, range(total_f)))
                    local = sorted([p for p in local if p],
                                   key=lambda p: os.path.basename(p).lower())
                    # 3. Procesar
                    processed = list(local)
                    old_h = self.cfg.get("stitch_height", 10000)
                    old_q = self.cfg.get("quality", 95)
                    self.cfg["stitch_height"] = height
                    if fmt in ("JPEG", "WEBP"): self.cfg["quality"] = 92
                    if do_cv:
                        base_pct = 5 + int(85 * mw_idx / total_mw) + 30
                        self._gd_st(f"🔄 {prefix}: convirtiendo…", base_pct)
                        processed = self._convert(processed, proc_dir, fmt, ext)
                    if do_st:
                        base_pct = 5 + int(85 * mw_idx / total_mw) + 55
                        self._gd_st(f"✂ {prefix}: stitch…", base_pct)
                        processed = self._stitch(processed, proc_dir, fmt, ext)
                    self.cfg["stitch_height"] = old_h
                    self.cfg["quality"]       = old_q
                    # 4. Subir
                    total_up = len(processed)
                    for i, fp in enumerate(processed):
                        if not self._gd_running: break
                        base_pct = 5 + int(85 * mw_idx / total_mw) + 75
                        up_pct   = base_pct + int(10 * i / max(total_up, 1))
                        self._gd_st(
                            f"📤 {prefix}: {i+1}/{total_up} — "
                            f"{os.path.basename(fp)}", up_pct)
                        try:
                            self._gd_upload(fp, dst_id)
                        except Exception as ex:
                            self._gd_st(
                                f"⚠ UP error {os.path.basename(fp)}: {ex}",
                                color=C["warn"])
                    self._gd_st(
                        f"✅ {prefix}: {total_up} archivo(s) subido(s) a "
                        f"'{m['dst_name']}'",
                        5 + int(85 * (mw_idx + 1) / total_mw), C["ok"])
                except Exception as ex:
                    import traceback; traceback.print_exc()
                    self._gd_st(f"❌ {prefix}: {ex}", color=C["err"])
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

            if self._gd_running:
                self._gd_st(
                    f"🎉 Completado: {len(manwha_list)} manwha procesado(s).",
                    100, C["ok"])
                self.root.after(0, lambda: messagebox.showinfo(
                    "Drive — Completado",
                    f"{len(manwha_list)} manwha procesado(s).\n"
                    f"Formato: {fmt}  |  Stitch: {height}px\n"
                    f"Los archivos están en la carpeta '{self._GD_DST_FOLDER}' de cada manwha."))
            self._gd_running = False
            self.root.after(0, lambda: (
                btn_set_state(self._gd_run_btn, "normal")
                if hasattr(self, "_gd_run_btn") else None,
                btn_set_state(self._gd_run1_btn, "normal")
                if hasattr(self, "_gd_run1_btn") else None,
            ))

        threading.Thread(target=_pipeline, daemon=True).start()

    def _gd_cancel(self):
        self._gd_running = False
        self._gd_st("⛔ Cancelado.", 0, C["warn"])
        if hasattr(self, "_gd_run_btn"):  btn_set_state(self._gd_run_btn, "normal")
        if hasattr(self, "_gd_run1_btn"): btn_set_state(self._gd_run1_btn, "normal")

    def _open_gdrive_panel(self):
        """Abre la pestaña Drive en el notebook principal."""
        try:
            for i in range(self._main_nb.index("end")):
                if "Drive" in self._main_nb.tab(i, "text"):
                    self._main_nb.select(i)
                    return
        except Exception:
            pass

    def _build_drive_tab(self, w):
        """Construye el contenido de la pestaña Drive dentro del notebook principal."""
        # Status bar abajo
        # ── Status bar Drive: 2 filas (status + progress) ─────────────────
        tk.Frame(w, bg=C["border"], height=1).pack(side="bottom", fill="x")
        ft = tk.Frame(w, bg=C["bg2"]); ft.pack(fill="x", side="bottom")
        # Fila 1: status text + cancelar
        ft1 = tk.Frame(ft, bg=C["bg2"]); ft1.pack(fill="x", padx=8, pady=(6,2))
        self._gd_status_lbl = tk.Label(
            ft1, text="Conectate y configurá tu carpeta raíz.",
            bg=C["bg2"], fg=C["dim"], font=("Segoe UI", 9),
            anchor="w", wraplength=800, justify="left")
        self._gd_status_lbl.pack(side="left", fill="x", expand=True)
        make_btn(ft1, "✕ Cancelar", self._gd_cancel,
                 bg=C["bg4"], fg=C["err"],
                 hover_bg=C["err2"], hover_fg=C["bright"],
                 small=True).pack(side="right", padx=(8,0))
        # Fila 2: barra de progreso
        ft2 = tk.Frame(ft, bg=C["bg2"]); ft2.pack(fill="x", padx=8, pady=(0,6))
        self._gd_prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(ft2, variable=self._gd_prog_var, maximum=100,
                        style="Bloom.Horizontal.TProgressbar"
                        ).pack(fill="x", expand=True)

        # Sub-notebook Drive
        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        # ── TAB 1: Configuración ─────────────────────────────────────────────
        tab_cfg_outer = tk.Frame(nb, bg=C["bg"])
        nb.add(tab_cfg_outer, text="  ⚙ Configuración  ")
        _cfg_cv = tk.Canvas(tab_cfg_outer, bg=C["bg"], highlightthickness=0)
        _cfg_sb = ttk.Scrollbar(tab_cfg_outer, orient="vertical", command=_cfg_cv.yview,
                                style="Vertical.TScrollbar")
        _cfg_cv.configure(yscrollcommand=_cfg_sb.set)
        _cfg_sb.pack(side="right", fill="y")
        _cfg_cv.pack(side="left", fill="both", expand=True)
        tab_cfg = tk.Frame(_cfg_cv, bg=C["bg"])
        _cfg_win = _cfg_cv.create_window((0,0), window=tab_cfg, anchor="nw")
        _cfg_cv.bind("<Configure>", lambda e: _cfg_cv.itemconfig(_cfg_win, width=e.width))
        tab_cfg.bind("<Configure>", lambda e: _cfg_cv.configure(scrollregion=_cfg_cv.bbox("all")))
        _cfg_cv.bind("<MouseWheel>", lambda e: _cfg_cv.yview_scroll(int(-1*(e.delta/120)),"units"))
        tab_cfg.bind("<MouseWheel>", lambda e: _cfg_cv.yview_scroll(int(-1*(e.delta/120)),"units"))

        def _sh(parent, txt):
            f = tk.Frame(parent, bg=C["bg"])
            f.pack(fill="x", padx=16, pady=(12, 4))
            tk.Label(f, text=txt, bg=C["bg"], fg=C["teal"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Frame(f, bg=C["border2"], height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0), pady=5)

        def _card(parent):
            f = tk.Frame(parent, bg=C["bg3"],
                         highlightbackground=C["border2"], highlightthickness=1)
            f.pack(fill="x", padx=16, pady=(0, 6))
            inner = tk.Frame(f, bg=C["bg3"])
            inner.pack(fill="x", padx=14, pady=10)
            return inner

        # Auth dot en la propia tab
        c_dot = tk.Frame(tab_cfg, bg=C["bg"])
        c_dot.pack(fill="x", padx=16, pady=(8, 0))
        self._gd_auth_dot = tk.Label(c_dot, text="● No conectado",
                                     bg=C["bg"], fg=C["err"],
                                     font=("Segoe UI", 8))
        self._gd_auth_dot.pack(side="left")

        # Dependencias (solo si faltan)
        if not GDRIVE_LIBS_OK:
            _sh(tab_cfg, "0 · Instalar dependencias")
            c0 = _card(tab_cfg)
            if GDRIVE_IMPORT_ERROR:
                tk.Label(c0, text=f"Error: {GDRIVE_IMPORT_ERROR}",
                         bg=C["bg3"], fg=C["err"],
                         font=("Consolas", 8), wraplength=420, justify="left").pack(anchor="w", pady=(0,4))
            if getattr(sys, "frozen", False):
                tk.Label(c0, text="⚠ EXE: las libs deben estar embebidas. Recompilá el EXE con crear_exe.bat",
                         bg=C["bg3"], fg=C["warn"],
                         font=("Segoe UI", 8), wraplength=420, justify="left").pack(anchor="w")
            else:
                tk.Label(c0, text="pip install google-auth-oauthlib google-api-python-client",
                         bg=C["bg3"], fg=C["warn"],
                         font=("Consolas", 9)).pack(anchor="w")
            dep_lbl = tk.Label(c0, text="", bg=C["bg3"], fg=C["ok"],
                               font=("Segoe UI", 8))
            dep_lbl.pack(anchor="w", pady=(4, 0))
            def _install():
                dep_lbl.config(text="⏳ Instalando…", fg=C["warn"])
                def _run():
                    try:
                        subprocess.run([sys.executable, "-m", "pip", "install",
                            "google-auth-oauthlib", "google-api-python-client",
                            "-q"], capture_output=True, timeout=180)
                        tab_cfg.after(0, lambda: dep_lbl.config(
                            text="✅ Listo. Reiniciá BloomStitch.", fg=C["ok"]))
                    except Exception as ex:
                        tab_cfg.after(0, lambda: dep_lbl.config(
                            text=f"❌ {ex}", fg=C["err"]))
                threading.Thread(target=_run, daemon=True).start()
            make_btn(c0, "⬇  Instalar ahora", _install,
                     bg=C["teal"], fg=C["bg"],
                     hover_bg=C["cyan"], hover_fg=C["bg"]).pack(
                anchor="w", pady=(6, 0))

        # Autenticación
        _sh(tab_cfg, "1 · Conectar con Google Drive")
        c1 = _card(tab_cfg)
        self._gd_creds_var = tk.StringVar(value="")
        tk.Label(c1, text="✅  Credenciales embebidas — solo hace falta autorizar una vez con tu cuenta Google.",
                 bg=C["bg3"], fg=C["ok"], font=("Segoe UI", 8),
                 wraplength=620, justify="left").pack(anchor="w", pady=(0, 6))
        rb_auth = tk.Frame(c1, bg=C["bg3"]); rb_auth.pack(anchor="w")
        make_btn(rb_auth, "🔑  Conectar con Google", self._gd_authenticate,
                 bg=C["teal"], fg=C["bg"],
                 hover_bg=C["cyan"], hover_fg=C["bg"]).pack(side="left", padx=(0, 8))
        make_btn(rb_auth, "🚪 Cerrar sesión", self._gd_disconnect,
                 bg=C["bg4"], fg=C["err"],
                 hover_bg=C["err2"], hover_fg=C["bright"],
                 small=True).pack(side="left")

        # Carpeta raíz
        _sh(tab_cfg, "2 · Carpeta raíz de Drive")
        c2 = _card(tab_cfg)
        tk.Label(c2, text="Pegá el link de tu carpeta raíz de Drive (la que contiene todos los manwha):",
                 bg=C["bg3"], fg=C["text2"],
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
        self._gd_root_var = tk.StringVar(value=self.cfg.get("gdrive_root", ""))
        tk.Entry(c2, textvariable=self._gd_root_var,
                 bg=C["bg4"], fg=C["text"], relief="flat",
                 font=("Segoe UI", 9), insertbackground=C["teal"],
                 highlightthickness=1, highlightbackground=C["border"],
                 highlightcolor=C["teal"]).pack(fill="x", pady=(0, 6))
        rb2 = tk.Frame(c2, bg=C["bg3"]); rb2.pack(anchor="w")
        self._gd_scan_btn = make_btn(rb2, "🔍  Escanear manwha",
                                     self._gd_scan_root,
                                     bg=C["teal"], fg=C["bg"],
                                     hover_bg=C["cyan"], hover_fg=C["bg"])
        self._gd_scan_btn.pack(side="left", padx=(0, 6))

        def _save_root():
            self.cfg["gdrive_root"] = self._gd_root_var.get().strip()
            self._save_config()
        make_btn(rb2, "Guardar", _save_root,
                 bg=C["bg4"], fg=C["text2"],
                 hover_bg=C["bg5"], hover_fg=C["text"],
                 small=True).pack(side="left")

        # Opciones de procesamiento
        # (panel de palabras clave eliminado — detección automática)
        self._gd_src_kw_var = tk.StringVar(value=self.cfg.get("gdrive_src_kw", "4_"))
        self._gd_dst_kw_var = tk.StringVar(value=self.cfg.get("gdrive_dst_kw", "Recorte"))
        self._gd_raw_kw_var = tk.StringVar(value=self.cfg.get("gdrive_raw_folder", "1_Raw"))
        _sh(tab_cfg, "3 · Opciones de procesamiento")
        c4 = _card(tab_cfg)
        row1 = tk.Frame(c4, bg=C["bg3"]); row1.pack(fill="x", pady=(0, 6))
        tk.Label(row1, text="Formato:", bg=C["bg3"], fg=C["text2"],
                 font=("Segoe UI", 9)).pack(side="left")
        self._gd_fmt = tk.StringVar(value=self.cfg.get("gdrive_fmt", "WEBP"))
        self._combo(row1, self._gd_fmt,
                    ["WEBP", "PNG", "JPEG"], 6).pack(side="left", padx=(6, 20))
        tk.Label(row1, text="Altura stitch:", bg=C["bg3"], fg=C["text2"],
                 font=("Segoe UI", 9)).pack(side="left")
        self._gd_height = tk.StringVar(
            value=str(self.cfg.get("gdrive_height", 10000)))
        tk.Entry(row1, textvariable=self._gd_height, width=7,
                 bg=C["bg4"], fg=C["text"], relief="flat",
                 font=("Segoe UI", 9), insertbackground=C["teal"],
                 highlightthickness=1, highlightbackground=C["border"],
                 highlightcolor=C["teal"]).pack(side="left", padx=(4, 0))
        for v in ["5000", "10000", "15000", "30000"]:
            self._sbtn(row1, v,
                       lambda x=v: self._gd_height.set(x)).pack(
                side="left", padx=(3, 0))
        row2 = tk.Frame(c4, bg=C["bg3"]); row2.pack(fill="x")
        self._gd_cv = tk.BooleanVar(value=self.cfg.get("gdrive_convert", True))
        self._gd_sv = tk.BooleanVar(value=self.cfg.get("gdrive_stitch", True))
        for var, lbl in [(self._gd_cv, "🔄 Convertir"), (self._gd_sv, "✂ Stitch")]:
            ff = tk.Frame(row2, bg=C["bg3"]); ff.pack(side="left", padx=(0, 18))
            self._toggle(ff, var, lambda: None).pack(side="left", padx=(0, 5))
            tk.Label(ff, text=lbl, bg=C["bg3"], fg=C["text"],
                     font=("Segoe UI", 9)).pack(side="left")
        def _save_opts():
            self.cfg.update({
                "gdrive_root":       self._gd_root_var.get().strip(),
                "gdrive_fmt":        self._gd_fmt.get(),
                "gdrive_height":     int(self._gd_height.get() or 10000),
                "gdrive_convert":    self._gd_cv.get(),
                "gdrive_stitch":     self._gd_sv.get(),
                "gdrive_src_kw":     self._gd_src_kw_var.get().strip(),
                "gdrive_dst_kw":     self._gd_dst_kw_var.get().strip(),
                "gdrive_raw_folder": self._gd_raw_kw_var.get().strip(),
            }); self._save_config()
        make_btn(c4, "Guardar opciones", _save_opts,
                 bg=C["bg4"], fg=C["text2"],
                 hover_bg=C["bg5"], hover_fg=C["text"],
                 small=True).pack(anchor="w", pady=(8, 0))

        # Aviso si API no habilitada
        if GDRIVE_LIBS_OK:
            import webbrowser as _wb
            _sh(tab_cfg, "⚠ Si la API da error")
            c_warn = _card(tab_cfg)
            tk.Label(c_warn,
                     text=(
                         "Si ves 'accessNotConfigured' al escanear:\n"
                         "  1. Abrí console.cloud.google.com\n"
                         "  2. Habilitá la Google Drive API\n"
                         "  3. En Credenciales asegurate que el OAuth client esté configurado"
                     ),
                     bg=C["bg3"], fg=C["dim"],
                     font=("Segoe UI", 8), justify="left").pack(anchor="w")
            make_btn(c_warn, "🌐  Abrir Google Cloud Console (habilitar Drive API)",
                     lambda: _wb.open("https://console.cloud.google.com/apis/library/drive.googleapis.com"),
                     bg=C["bg4"], fg=C["folder"],
                     hover_bg=C["teal"], hover_fg=C["bg"],
                     small=True).pack(anchor="w", pady=(6, 0))

        # ── TAB 2: Manwha ─────────────────────────────────────────────────────
        tab_mw = tk.Frame(nb, bg=C["bg"])
        nb.add(tab_mw, text="  📚 Manwha  ")

        # Barra controles
        ctrl = tk.Frame(tab_mw, bg=C["bg2"])
        ctrl.pack(fill="x", padx=0, pady=0)
        tk.Label(ctrl, text="🔎", bg=C["bg2"],
                 fg=C["teal"], font=("Segoe UI", 10)).pack(side="left", padx=(10, 2), pady=8)
        self._gd_search_var = tk.StringVar()
        search_e = tk.Entry(ctrl, textvariable=self._gd_search_var,
                            bg=C["bg4"], fg=C["text"], relief="flat",
                            font=("Segoe UI", 9), insertbackground=C["teal"],
                            highlightthickness=1,
                            highlightbackground=C["border"],
                            highlightcolor=C["teal"], width=22)
        search_e.pack(side="left", padx=(0, 10), pady=8)
        search_e.bind("<KeyRelease>", lambda e: self._gd_refresh_table())

        tk.Label(ctrl, text="Ordenar:", bg=C["bg2"],
                 fg=C["text2"], font=("Segoe UI", 8)).pack(side="left")
        self._gd_sort_var = tk.StringVar(value="Nombre A→Z")
        sort_cb = self._combo(ctrl, self._gd_sort_var,
                              ["Nombre A→Z", "Nombre Z→A",
                               "Modificado ↓", "Modificado ↑", "Estado"], 12)
        sort_cb.pack(side="left", padx=(4, 10))
        sort_cb.bind("<<ComboboxSelected>>", lambda e: self._gd_refresh_table())

        tk.Label(ctrl, text="Filtro:", bg=C["bg2"],
                 fg=C["text2"], font=("Segoe UI", 8)).pack(side="left")
        self._gd_filter_var = tk.StringVar(value="Todos")
        filt_cb = self._combo(ctrl, self._gd_filter_var,
                              ["Todos", "Solo listos", "Sin destino"], 10)
        filt_cb.pack(side="left", padx=(4, 10))
        filt_cb.bind("<<ComboboxSelected>>", lambda e: self._gd_refresh_table())

        make_btn(ctrl, "🔄 Refrescar", self._gd_scan_root,
                 bg=C["bg4"], fg=C["teal"],
                 hover_bg=C["teal"], hover_fg=C["bg"],
                 small=True).pack(side="left", padx=(0, 6))

        # Vista: cards / tabla
        # Vista por defecto: lista agrupada
        self._gd_view_var = tk.StringVar(value=self.cfg.get("gdrive_view", "list"))
        _view_cycle = ["list", "table", "cards"]
        _view_labels = {"list": "☰ Lista", "table": "📋 Tabla", "cards": "🃏 Cards"}
        def _toggle_view():
            cur = self._gd_view_var.get()
            nxt = _view_cycle[(_view_cycle.index(cur) + 1) % len(_view_cycle)]
            self._gd_view_var.set(nxt)
            self.cfg["gdrive_view"] = nxt
            _view_btn.config(text=_view_labels[nxt])
            self._gd_refresh_table()
        _view_btn = make_btn(ctrl, _view_labels[self._gd_view_var.get()],
                             _toggle_view,
                             bg=C["bg4"], fg=C["text2"],
                             hover_bg=C["bg5"], hover_fg=C["text"],
                             small=True)
        _view_btn.pack(side="left", padx=(0, 6))

        make_btn(ctrl, "▶▶ Procesar seleccionados",
                 self._gd_run_selected,
                 font=("Segoe UI", 9, "bold"), padx=12
                 ).pack(side="right", padx=(0, 8), pady=6)
        self._gd_run_btn = ctrl.winfo_children()[-1]
        self._gd_sel_lbl = tk.Label(ctrl, text="0 seleccionado(s)",
                                    bg=C["bg2"], fg=C["dim"],
                                    font=("Segoe UI", 7))
        self._gd_sel_lbl.pack(side="right", padx=(0, 8))
        tk.Frame(tab_mw, bg=C["border2"], height=1).pack(fill="x")

        # Tabla scrollable de cards
        tbl_sc = tk.Canvas(tab_mw, bg=C["bg3"], highlightthickness=0)
        tbl_sb = ttk.Scrollbar(tab_mw, orient="vertical", command=tbl_sc.yview)
        tbl_sc.configure(yscrollcommand=tbl_sb.set)
        tbl_sb.pack(side="right", fill="y")
        tbl_sc.pack(fill="both", expand=True)
        self._gd_tbl_frame = tk.Frame(tbl_sc, bg=C["bg3"])
        tbl_win = tbl_sc.create_window((0, 0), window=self._gd_tbl_frame, anchor="nw")
        tbl_sc.bind("<Configure>",
                    lambda e: tbl_sc.itemconfig(tbl_win, width=e.width))
        self._gd_tbl_frame.bind(
            "<Configure>",
            lambda e: tbl_sc.configure(scrollregion=tbl_sc.bbox("all")))
        self._gd_tbl_frame.bind(
            "<MouseWheel>",
            lambda e: tbl_sc.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._gd_refresh_table()
        self._gd_refresh_dot()
    def _gd_get_raw_kw(self):
        """Keyword configurable para detectar carpeta Raw."""
        v = getattr(self, "_gd_raw_kw_var", None)
        return (v.get().strip() if v else "") or self._GD_RAW_FOLDER

    def _gd_is_manwha(self, sub_map):
        """
        Determina si una carpeta es un manwha verificando que contenga
        al menos _GD_MANWHA_MIN_MATCH de las 5 carpetas canónicas.

        Regla de matching (AMBAS condiciones deben cumplirse):
          - El nombre empieza con el prefijo numérico correcto (1_, 2_, 3_, 4_, 5_)
          - La parte DESPUÉS del prefijo contiene uno de los aliases del slot

        Esto evita que "1_Domingo", "4_miercoles", "5_Jueves" etc.
        sean confundidos con las carpetas canónicas del manwha.
        """
        import unicodedata, re as _re

        def _norm_suffix(s):
            """Normaliza solo la parte después del prefijo numérico."""
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
            # Quitar prefijo "N_" o "N " al inicio para obtener el sufijo
            s = _re.sub(r"^\d+[_\s\-]+", "", s)
            return s

        matched = {}  # slot_index -> folder_name
        for name in sub_map:
            name_low = name.lower()
            suffix   = _norm_suffix(name)   # ej: "4_TYPE" → "type", "4_miercoles" → "miercoles"

            for i, (prefix, aliases) in enumerate(self._GD_CANONICAL):
                if i in matched:
                    continue

                has_prefix = name_low.startswith(prefix)

                # Un nombre coincide si:
                # (prefijo correcto) Y (sufijo contiene un alias del slot)
                if has_prefix:
                    for alias in aliases:
                        if len(alias) >= 3 and alias in suffix:
                            matched[i] = name
                            break
                # Fallback sin prefijo: sufijo exactamente igual a un alias largo
                if i not in matched:
                    for alias in aliases:
                        if len(alias) >= 5 and suffix == alias:
                            matched[i] = name
                            break

                if i in matched:
                    break

        if len(matched) < self._GD_MANWHA_MIN_MATCH:
            return None

        return {
            "raw":  sub_map.get(matched.get(0)),
            "src":  sub_map.get(matched.get(3)),
            "dst":  sub_map.get(matched.get(4)),
            "all_matched": [sub_map[v] for v in matched.values()],
        }

    # ── Sistema de Perfiles ────────────────────────────────────────────────────
    def _get_profiles(self):
        return self.cfg.get("profiles", [])

    def _save_profiles(self, profiles):
        self.cfg["profiles"] = profiles
        self._save_config()

    def _apply_profile(self, profile_or_vars):
        """Aplica un perfil a los controles de la UI principal.
        Acepta un dict de TkVars (editor) o un dict de valores (guardado)."""
        def _get(key, default):
            val = profile_or_vars.get(key, default)
            try: return val.get()  # TkVar
            except: return val     # valor plano
        try:
            self.s_fmtv.set(_get("format", "WEBP"))
            self.s_hv.set(str(_get("height", 10000)))
            self.s_cv.set(_get("convert", True))
            self.s_sv.set(_get("stitch", True))
            self.s_wv.set(_get("waifu", False))
            out = _get("output_dir", "")
            if out: self.s_outv.set(out)
            # Cambiar a pestaña Stitch
            try:
                for i in range(self._main_nb.index("end")):
                    if "Stitch" in self._main_nb.tab(i, "text"):
                        self._main_nb.select(i)
                        break
            except Exception:
                pass
        except Exception:
            pass

    def _build_profiles_tab(self, parent):
        """Construye la pestaña de perfiles de procesamiento."""

        # Instrucción
        hdr = tk.Frame(parent, bg=C["bg2"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚡  Perfiles de Stitch",
                 bg=C["bg2"], fg=C["teal"],
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(hdr, text="Guardá configuraciones prearmadas para aplicar con un clic",
                 bg=C["bg2"], fg=C["dim"],
                 font=("Segoe UI", 8)).pack(side="left", pady=12)
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")

        # ── Panel izquierdo: lista de perfiles ────────────────────────────────
        split = tk.Frame(parent, bg=C["bg"]); split.pack(fill="both", expand=True)
        left_pane = tk.Frame(split, bg=C["bg2"], width=220)
        left_pane.pack(side="left", fill="y")
        left_pane.pack_propagate(False)
        tk.Frame(split, bg=C["border"], width=1).pack(side="left", fill="y")
        right_pane = tk.Frame(split, bg=C["bg"]); right_pane.pack(side="left", fill="both", expand=True)

        # Cabecera lista
        lhdr = tk.Frame(left_pane, bg=C["bg3"])
        lhdr.pack(fill="x", padx=0)
        tk.Label(lhdr, text="Mis perfiles", bg=C["bg3"], fg=C["teal"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=10, pady=8)

        # Lista scrollable
        list_frame = tk.Frame(left_pane, bg=C["bg2"])
        list_frame.pack(fill="both", expand=True)

        # Estado del editor
        self._profile_selected = [None]  # índice del perfil en edición
        self._profile_editor_vars = {}
        self._profile_list_frame = list_frame

        def _refresh_list():
            for w in list_frame.winfo_children(): w.destroy()
            profiles = self._get_profiles()
            if not profiles:
                tk.Label(list_frame, text="Sin perfiles. Creá uno →",
                         bg=C["bg2"], fg=C["dim"],
                         font=("Segoe UI", 8), justify="center").pack(pady=20)
                return
            for i, p in enumerate(profiles):
                is_sel = self._profile_selected[0] == i
                bg = C["teal"] if is_sel else C["bg3"]
                fg = C["bg"] if is_sel else C["text"]
                card = tk.Frame(list_frame, bg=bg,
                                highlightbackground=C["border2"] if not is_sel else C["teal"],
                                highlightthickness=1)
                card.pack(fill="x", padx=4, pady=2)
                name_lbl = tk.Label(card, text=p.get("name", "Sin nombre"),
                                    bg=bg, fg=fg,
                                    font=("Segoe UI", 9, "bold"),
                                    anchor="w")
                name_lbl.pack(side="left", padx=8, pady=6, fill="x", expand=True)
                # tipo badge
                fmt = p.get("format", "?")
                h = p.get("height", 0)
                tk.Label(card, text=f"{fmt} {h//1000}k",
                         bg=bg, fg=C["cyan"] if is_sel else C["dim"],
                         font=("Segoe UI", 7)).pack(side="right", padx=6)

                def _select(idx=i):
                    self._profile_selected[0] = idx
                    _refresh_list()
                    _load_editor(idx)
                card.bind("<Button-1>", lambda e, f=_select: f())
                name_lbl.bind("<Button-1>", lambda e, f=_select: f())

                # Botón aplicar rápido
                def _quick_apply(p=p):
                    self._apply_profile(p)
                apply_btn = tk.Label(card, text="▶", bg=bg,
                                     fg=C["cyan"] if is_sel else C["teal"],
                                     font=("Segoe UI", 10, "bold"),
                                     cursor="hand2")
                apply_btn.pack(side="right", padx=(0, 8))
                apply_btn.bind("<Button-1>", lambda e, f=_quick_apply: f())

        # Botones nueva/borrar
        btn_row = tk.Frame(left_pane, bg=C["bg2"])
        btn_row.pack(fill="x", padx=4, pady=4)
        def _new_profile():
            profiles = self._get_profiles()
            profiles.append({
                "name":    f"Perfil {len(profiles)+1}",
                "format":  "WEBP",
                "height":  10000,
                "convert": True,
                "stitch":  True,
                "waifu":   False,
                "output_dir": "",
                "drive_upload": False,
                "description": "",
            })
            self._save_profiles(profiles)
            self._profile_selected[0] = len(profiles) - 1
            _refresh_list()
            _load_editor(self._profile_selected[0])
        def _export_profiles():
            from tkinter import filedialog as _fd
            path = _fd.asksaveasfilename(
                title="Exportar perfiles",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
                initialfile="bloomstitch_perfiles.json")
            if not path: return
            try:
                import json as _j
                Path(path).write_text(
                    _j.dumps(self._get_profiles(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo exportar: {ex}")

        def _import_profiles():
            from tkinter import filedialog as _fd
            path = _fd.askopenfilename(
                title="Importar perfiles",
                filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
            if not path: return
            try:
                import json as _j
                imported = _j.loads(Path(path).read_text(encoding="utf-8"))
                if not isinstance(imported, list):
                    raise ValueError("El archivo no contiene una lista de perfiles")
                existing = self._get_profiles()
                existing.extend(imported)
                self._save_profiles(existing)
                _refresh_list()
                messagebox.showinfo("Importar", f"{len(imported)} perfil(es) importado(s).")
            except Exception as ex:
                messagebox.showerror("Error", f"No se pudo importar: {ex}")

        make_btn(btn_row, "+ Nuevo", _new_profile,
                 bg=C["teal"], fg=C["bg"],
                 hover_bg=C["cyan"], hover_fg=C["bg"],
                 small=True).pack(side="left", padx=(0, 4))

        def _delete_profile():
            idx = self._profile_selected[0]
            if idx is None: return
            profiles = self._get_profiles()
            if 0 <= idx < len(profiles):
                profiles.pop(idx)
                self._save_profiles(profiles)
                self._profile_selected[0] = None
                _clear_editor()
                _refresh_list()
        make_btn(btn_row, "🗑 Borrar",_delete_profile,
                 bg=C["bg4"], fg=C["err"],
                 hover_bg=C["err2"], hover_fg=C["bright"],
                 small=True).pack(side="left", padx=(0,4))

        # Segunda fila: importar/exportar
        btn_row2_io = tk.Frame(left_pane, bg=C["bg2"])
        btn_row2_io.pack(fill="x", padx=4, pady=(0,4))
        make_btn(btn_row2_io, "📤 Exportar", _export_profiles,
                 bg=C["bg4"], fg=C["text2"],
                 hover_bg=C["bg5"], hover_fg=C["text"],
                 small=True).pack(side="left", padx=(0,4))
        make_btn(btn_row2_io, "📥 Importar", _import_profiles,
                 bg=C["bg4"], fg=C["text2"],
                 hover_bg=C["bg5"], hover_fg=C["text"],
                 small=True).pack(side="left")

        # ── Panel derecho: editor ─────────────────────────────────────────────
        editor_scroll = tk.Canvas(right_pane, bg=C["bg"], highlightthickness=0)
        editor_sb = ttk.Scrollbar(right_pane, orient="vertical",
                                  command=editor_scroll.yview)
        editor_scroll.configure(yscrollcommand=editor_sb.set)
        editor_sb.pack(side="right", fill="y")
        editor_scroll.pack(fill="both", expand=True)
        editor_inner = tk.Frame(editor_scroll, bg=C["bg"])
        editor_win = editor_scroll.create_window((0, 0), window=editor_inner, anchor="nw")
        editor_scroll.bind("<Configure>",
                           lambda e: editor_scroll.itemconfig(editor_win, width=e.width))
        editor_inner.bind("<Configure>",
                          lambda e: editor_scroll.configure(
                              scrollregion=editor_scroll.bbox("all")))

        def _sh_e(txt):
            f = tk.Frame(editor_inner, bg=C["bg"])
            f.pack(fill="x", padx=16, pady=(12, 4))
            tk.Label(f, text=txt, bg=C["bg"], fg=C["teal"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Frame(f, bg=C["border2"], height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0), pady=5)

        def _card_e():
            f = tk.Frame(editor_inner, bg=C["bg3"],
                         highlightbackground=C["border2"], highlightthickness=1)
            f.pack(fill="x", padx=16, pady=(0, 6))
            inner = tk.Frame(f, bg=C["bg3"])
            inner.pack(fill="x", padx=14, pady=10)
            return inner

        # Variables del editor
        ev = {}
        ev["name"]         = tk.StringVar()
        ev["description"]  = tk.StringVar()
        ev["format"]       = tk.StringVar(value="WEBP")
        ev["height"]       = tk.StringVar(value="10000")
        ev["convert"]      = tk.BooleanVar(value=True)
        ev["stitch"]       = tk.BooleanVar(value=True)
        ev["waifu"]        = tk.BooleanVar(value=False)
        ev["output_dir"]   = tk.StringVar()
        ev["drive_upload"] = tk.BooleanVar(value=False)
        self._profile_editor_vars = ev

        # Empty state
        empty_lbl = tk.Label(editor_inner,
                             text="← Seleccioná un perfil o creá uno nuevo",
                             bg=C["bg"], fg=C["dim"],
                             font=("Segoe UI", 10))
        empty_lbl.pack(pady=40)

        def _clear_editor():
            for w in editor_inner.winfo_children(): w.destroy()
            tk.Label(editor_inner,
                     text="← Seleccioná un perfil o creá uno nuevo",
                     bg=C["bg"], fg=C["dim"],
                     font=("Segoe UI", 10)).pack(pady=40)

        def _load_editor(idx):
            profiles = self._get_profiles()
            if idx is None or idx >= len(profiles):
                _clear_editor()
                return
            p = profiles[idx]
            ev["name"].set(p.get("name", ""))
            ev["description"].set(p.get("description", ""))
            ev["format"].set(p.get("format", "WEBP"))
            ev["height"].set(str(p.get("height", 10000)))
            ev["convert"].set(p.get("convert", True))
            ev["stitch"].set(p.get("stitch", True))
            ev["waifu"].set(p.get("waifu", False))
            ev["output_dir"].set(p.get("output_dir", ""))
            ev["drive_upload"].set(p.get("drive_upload", False))

            for w in editor_inner.winfo_children(): w.destroy()

            # ─ Nombre ─
            _sh_e("📝  Nombre del perfil")
            c = _card_e()
            tk.Entry(c, textvariable=ev["name"],
                     bg=C["bg4"], fg=C["bright"], relief="flat",
                     font=("Segoe UI", 11, "bold"), insertbackground=C["teal"],
                     highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["teal"]).pack(fill="x", pady=(0, 4))
            tk.Entry(c, textvariable=ev["description"],
                     bg=C["bg4"], fg=C["text2"], relief="flat",
                     font=("Segoe UI", 9), insertbackground=C["teal"],
                     highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["teal"]).pack(fill="x")
            tk.Label(c, text="Descripción opcional (ej: 'Raw → JPG 30k para subir a Drive')",
                     bg=C["bg3"], fg=C["dim"], font=("Segoe UI", 7)).pack(anchor="w", pady=(2,0))

            # ─ Formato y resolución ─
            _sh_e("🖼  Formato y resolución")
            c = _card_e()
            r1 = tk.Frame(c, bg=C["bg3"]); r1.pack(fill="x", pady=(0,6))
            tk.Label(r1, text="Formato:", bg=C["bg3"], fg=C["text2"],
                     font=("Segoe UI", 9)).pack(side="left")
            self._combo(r1, ev["format"],
                        ["WEBP", "JPEG", "PNG"], 6).pack(side="left", padx=(6, 20))
            tk.Label(r1, text="Altura stitch (px):", bg=C["bg3"], fg=C["text2"],
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Entry(r1, textvariable=ev["height"], width=7,
                     bg=C["bg4"], fg=C["text"], relief="flat",
                     font=("Segoe UI", 10), insertbackground=C["teal"],
                     highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["teal"]).pack(side="left", padx=(4,0))
            for v in ["5000","10000","15000","30000"]:
                self._sbtn(r1, v, lambda x=v: ev["height"].set(x)).pack(side="left", padx=(3,0))

            # ─ Pasos de procesamiento ─
            _sh_e("⚙  Pasos de procesamiento")
            c = _card_e()
            for var, lbl, desc in [
                (ev["convert"], "🔄 Convertir PSD → imagen", "Convierte PSD/PSB a PNG/WEBP/JPEG"),
                (ev["stitch"],  "✂ Stitch",                  "Une las imágenes en tiras verticales"),
                (ev["waifu"],   "✨ Mejora de calidad",       "Upscale con waifu2x (más lento)"),
            ]:
                rf = tk.Frame(c, bg=C["bg3"]); rf.pack(fill="x", pady=3)
                self._toggle(rf, var, lambda: None).pack(side="left", padx=(0,8))
                tk.Label(rf, text=lbl, bg=C["bg3"], fg=C["text"],
                         font=("Segoe UI", 9, "bold")).pack(side="left")
                tk.Label(rf, text=f"  — {desc}", bg=C["bg3"], fg=C["dim"],
                         font=("Segoe UI", 8)).pack(side="left")

            # ─ Destino ─
            _sh_e("📤  Destino de salida")
            c = _card_e()
            row_out = tk.Frame(c, bg=C["bg3"]); row_out.pack(fill="x", pady=(0,6))
            tk.Label(row_out, text="Carpeta local:", bg=C["bg3"], fg=C["text2"],
                     font=("Segoe UI", 8)).pack(side="left")
            tk.Entry(row_out, textvariable=ev["output_dir"],
                     bg=C["bg4"], fg=C["text"], relief="flat",
                     font=("Segoe UI", 9), insertbackground=C["teal"],
                     highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["teal"]).pack(side="left", fill="x", expand=True, padx=(6,4))
            def _pick_out_dir():
                d = filedialog.askdirectory()
                if d: ev["output_dir"].set(d)
            make_btn(row_out, "…", _pick_out_dir,
                     bg=C["bg4"], fg=C["text2"], small=True).pack(side="left")

            row_drv = tk.Frame(c, bg=C["bg3"]); row_drv.pack(fill="x")
            self._toggle(row_drv, ev["drive_upload"], lambda: None).pack(side="left", padx=(0,8))
            tk.Label(row_drv, text="Subir resultado a Drive (carpeta destino del manwha)",
                     bg=C["bg3"], fg=C["text"], font=("Segoe UI", 9)).pack(side="left")

            # ─ Guardar / Aplicar ─
            _sh_e("💾  Guardar")
            c = _card_e()
            btn_row2 = tk.Frame(c, bg=C["bg3"]); btn_row2.pack(fill="x")

            def _save_profile():
                profiles2 = self._get_profiles()
                if idx < len(profiles2):
                    profiles2[idx].update({
                        "name":         ev["name"].get().strip() or "Sin nombre",
                        "description":  ev["description"].get().strip(),
                        "format":       ev["format"].get(),
                        "height":       int(ev["height"].get() or 10000),
                        "convert":      ev["convert"].get(),
                        "stitch":       ev["stitch"].get(),
                        "waifu":        ev["waifu"].get(),
                        "output_dir":   ev["output_dir"].get().strip(),
                        "drive_upload": ev["drive_upload"].get(),
                    })
                    self._save_profiles(profiles2)
                    _refresh_list()

            make_btn(btn_row2, "💾 Guardar perfil", _save_profile,
                     bg=C["teal"], fg=C["bg"],
                     hover_bg=C["cyan"], hover_fg=C["bg"]).pack(side="left", padx=(0,8))
            make_btn(btn_row2, "▶ Aplicar al Stitch", lambda: self._apply_profile(ev),
                     bg=C["bg4"], fg=C["text"],
                     hover_bg=C["bg5"], hover_fg=C["bright"],
                     small=True).pack(side="left")
            tk.Label(btn_row2, text="  'Aplicar' carga la config en la pestaña Stitch",
                     bg=C["bg3"], fg=C["dim"], font=("Segoe UI", 7)).pack(side="left")

        _refresh_list()
        self._profile_list_refresh = _refresh_list


    def _open_settings(self):
        w=tk.Toplevel(self.root); w.title("Configuración"); w.geometry("430x200")
        w.configure(bg=C["bg"]); w.transient(self.root); w.grab_set(); w.resizable(True,False)
        hd=tk.Frame(w,bg=C["bg2"],height=44); hd.pack(fill="x"); hd.pack_propagate(False)
        tk.Label(hd,text="⚙  Configuración",bg=C["bg2"],fg=C["teal"],font=("Segoe UI",12,"bold")).pack(side="left",padx=16,pady=10)
        tk.Frame(w,bg=C["border"],height=1).pack(fill="x")
        tk.Label(w,text="Ruta del motor de mejora (bloom_upscaler.exe):",bg=C["bg"],fg=C["text2"],font=("Segoe UI",9)).pack(anchor="w",padx=18,pady=(14,2))
        pr=tk.Frame(w,bg=C["bg"]); pr.pack(fill="x",padx=18,pady=(0,12))
        self.cfg_wv=tk.StringVar(value=self.cfg.get("upscaler_exe",str(WAIFU_EXE)))
        self._entry(pr,self.cfg_wv).pack(side="left",fill="x",expand=True)
        make_btn(pr,"…",lambda:self.cfg_wv.set(filedialog.askopenfilename(
                filetypes=[("EXE","*.exe"),("Todos","*.*")]) or self.cfg_wv.get()),
                 bg=C["bg4"],fg=C["text2"],hover_bg=C["bg5"],hover_fg=C["text"],small=True,padx=8).pack(side="left",padx=(4,0))
        def save(): self.cfg["upscaler_exe"]=self.cfg_wv.get(); self._save_config(); w.destroy()
        make_btn(w,"Guardar y cerrar",save).pack(pady=12)

    # ── UI HELPERS ────────────────────────────────────────────────────────────
    def _sh(self,p,title):
        f=tk.Frame(p,bg=C["bg"]); f.pack(fill="x",padx=20,pady=(12,4))
        tk.Label(f,text=title,bg=C["bg"],fg=C["teal"],font=("Segoe UI",10,"bold")).pack(side="left")
        tk.Frame(f,bg=C["border2"],height=1).pack(side="left",fill="x",expand=True,padx=(8,0),pady=6)

    def _cframe(self,p): return tk.Frame(p,bg=C["bg3"],highlightbackground=C["border2"],highlightthickness=1)

    def _sbtn(self,p,text,cmd):
        b=tk.Button(p,text=text,command=cmd,bg=C["bg5"],fg=C["teal"],font=("Segoe UI",7),
                     relief="flat",cursor="hand2",padx=5,pady=2,bd=0,highlightthickness=0)
        b.bind("<Enter>",lambda e:b.config(bg=C["teal"],fg=C["bg"]))
        b.bind("<Leave>",lambda e:b.config(bg=C["bg5"],fg=C["teal"])); return b

    def _combo(self,p,var,values,width):
        return ttk.Combobox(p,textvariable=var,values=values,state="readonly",width=width,font=("Segoe UI",9))

    def _entry(self,p,var,placeholder="",width=None):
        kw={"width":width} if width else {}
        e=tk.Entry(p,textvariable=var,bg=C["bg4"],fg=C["text"],insertbackground=C["teal"],
                   relief="flat",font=("Segoe UI",9),highlightthickness=1,
                   highlightbackground=C["border"],highlightcolor=C["teal"],bd=0,**kw)
        if placeholder:
            if not var.get(): e.insert(0,placeholder); e.config(fg=C["dim"])
            e.bind("<FocusIn>",lambda ev:(e.delete(0,"end"),e.config(fg=C["text"])) if e.get()==placeholder else None)
            e.bind("<FocusOut>",lambda ev:(e.insert(0,placeholder),e.config(fg=C["dim"])) if not e.get() else None)
        return e

    def _toggle(self,p,var,cmd):
        W,H=38,20
        c=tk.Canvas(p,width=W,height=H,bg=p.cget("bg"),highlightthickness=0,cursor="hand2")
        def draw():
            c.delete("all"); on=var.get(); tc=C["teal"] if on else C["border2"]; r=H//2
            c.create_arc(0,0,H,H,start=90,extent=180,fill=tc,outline="")
            c.create_arc(W-H,0,W,H,start=270,extent=180,fill=tc,outline="")
            c.create_rectangle(r,0,W-r,H,fill=tc,outline="")
            kx=W-H+2 if on else 2
            c.create_oval(kx,2,kx+H-4,H-2,fill=C["bright"] if on else C["dim"],outline="")
        c.bind("<Button-1>",lambda e:(var.set(not var.get()),draw(),cmd()))
        draw(); return c

    # ── REORDENAR ─────────────────────────────────────────────────────────────
    def _move_sel(self,d):
        sel=self.s_lb.curselection()
        if not sel: return
        i=sel[0]; j=i+d
        if 0<=j<len(self.files):
            self.files[i],self.files[j]=self.files[j],self.files[i]
            self._sync_lists(keep_sel=j)

    def _drag_start_cb(self,e): self._drag_idx=self.s_lb.nearest(e.y)

    def _drag_motion_cb(self,e):
        if self._drag_idx is None: return
        lb=self.s_lb; j=lb.nearest(e.y)
        if not hasattr(self,'_drag_overlay'):
            self._drag_overlay=tk.Frame(lb,bg=C["teal"],height=2)
        try:
            bbox=lb.bbox(j if 0<=j<lb.size() else 0)
            if bbox:
                yp=bbox[1] if e.y<(bbox[1]+bbox[3]//2) else bbox[1]+bbox[3]
                self._drag_overlay.place(x=4,y=yp-1,relwidth=1,width=-8,height=2)
        except: pass
        if j!=self._drag_idx and 0<=j<len(self.files):
            self.files[self._drag_idx],self.files[j]=self.files[j],self.files[self._drag_idx]
            self._sync_lists(keep_sel=j); self._drag_idx=j

    def _drag_end_cb(self,e):
        self._drag_idx=None
        if hasattr(self,'_drag_overlay'):
            try: self._drag_overlay.place_forget()
            except: pass

    # ── SYNC ──────────────────────────────────────────────────────────────────
    def _sync_lists(self,keep_sel=None):
        self.s_lb.delete(0,"end")
        for p in self.files: self.s_lb.insert("end",os.path.basename(p))
        if keep_sel is not None and 0<=keep_sel<self.s_lb.size():
            self.s_lb.selection_set(keep_sel); self.s_lb.see(keep_sel)
        self.s_ct.config(text=f"{len(self.files)} archivo(s)")
        self._update_preview()

    def _sort_files(self):
        """Ordena self.files según el método seleccionado."""
        method=self.cfg.get("sort_method","name_asc")
        def _nat_key(s):
            """Clave de ordenamiento natural: separa números del nombre."""
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)',os.path.basename(s))]
        def _num_key(s):
            """Extrae el primer número del nombre para ordenamiento numérico."""
            m=re.search(r'\d+',os.path.basename(s))
            return int(m.group(0)) if m else 0
        def _date_key(s):
            try: return os.path.getmtime(s)
            except: return 0
        if method=="name_asc":   self.files.sort(key=_nat_key)
        elif method=="name_desc": self.files.sort(key=_nat_key,reverse=True)
        elif method=="num_asc":  self.files.sort(key=_num_key)
        elif method=="num_desc": self.files.sort(key=_num_key,reverse=True)
        elif method=="date_asc": self.files.sort(key=_date_key)
        elif method=="date_desc":self.files.sort(key=_date_key,reverse=True)

    # ── FILE OPS ──────────────────────────────────────────────────────────────
    def _add_unified_smart(self):
        """Botón único: abre diálogo para elegir imágenes, carpeta o ZIP según modo."""
        choices=[
            ("🖼 Imágenes sueltas (JPG/PNG/PSD…)","images"),
            ("📁 Carpeta(s)","folder"),
            ("📦 ZIP","zip"),
        ]
        pick_win=tk.Toplevel(self.root); pick_win.title("Agregar")
        pick_win.configure(bg=C["bg"]); pick_win.transient(self.root)
        pick_win.grab_set(); pick_win.resizable(False,False)
        W,H=280,160; sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        pick_win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        tk.Label(pick_win,text="¿Qué querés agregar?",bg=C["bg"],fg=C["teal"],
                 font=("Segoe UI",10,"bold")).pack(pady=(14,8))
        def _pick(kind):
            pick_win.destroy()
            if kind=="images":
                if self._batch_mode:
                    # En batch, imágenes sueltas no aplica — agregar carpeta padre
                    self._batch_add_folder()
                else:
                    self._add_files_only()
            elif kind=="folder":
                if self._batch_mode: self._batch_add_folder()
                else: self._add_folder_only()
            elif kind=="zip":
                if self._batch_mode: self._batch_add_zip()
                else: self._add_zip_only()
        bf=tk.Frame(pick_win,bg=C["bg"]); bf.pack(expand=True)
        for lbl,kind in choices:
            make_btn(bf,lbl,lambda k=kind:_pick(k),bg=C["bg4"],fg=C["text"],
                     hover_bg=C["teal"],hover_fg=C["bg"]).pack(pady=4,fill="x",padx=30)

    def _add_files_only(self):
        paths=filedialog.askopenfilenames(title="Seleccionar imágenes",
            filetypes=[
                ("Imágenes","*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.psd *.psb *.avif *.gif"),
                ("PSD / PSB","*.psd *.psb"),
                ("Todos","*.*")
            ])
        n=0
        for p in paths:
            if p not in self.files: self.files.append(p); n+=1
        self._sort_files(); self._sync_lists(); self._st(f"✅ {n} archivo(s) agregado(s).")

    def _add_files(self):
        # Mantener compatibilidad interna
        if self._batch_mode: self._batch_add_folder(); return
        self._add_files_only()

    def _add_folder_only(self):
        """Diálogo propio para agregar múltiples carpetas de una vez."""
        self._open_multi_folder_dialog()

    def _open_multi_folder_dialog(self):
        """Abre un diálogo custom para seleccionar múltiples carpetas."""
        dlg=tk.Toplevel(self.root); dlg.title("Agregar carpetas")
        dlg.configure(bg=C["bg"]); dlg.transient(self.root); dlg.grab_set()
        dlg.resizable(True,False)
        W2,H2=480,340; sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        dlg.geometry(f"{W2}x{H2}+{(sw-W2)//2}+{(sh-H2)//2}")
        # Header
        hd=tk.Frame(dlg,bg=C["bg2"],height=44); hd.pack(fill="x"); hd.pack_propagate(False)
        tk.Label(hd,text="📁  Agregar carpetas",bg=C["bg2"],fg=C["teal"],
                 font=("Segoe UI",12,"bold")).pack(side="left",padx=16,pady=10)
        tk.Frame(dlg,bg=C["border"],height=1).pack(fill="x")
        # Instructions
        tk.Label(dlg,text="Agregá todas las carpetas que quieras procesar juntas:",
                 bg=C["bg"],fg=C["text2"],font=("Segoe UI",9)).pack(anchor="w",padx=16,pady=(10,4))
        # List of selected folders
        lf=tk.Frame(dlg,bg=C["bg3"],highlightbackground=C["border2"],highlightthickness=1)
        lf.pack(fill="both",expand=True,padx=16,pady=(0,8))
        vsb=tk.Scrollbar(lf,width=7,bg=C["bg4"],troughcolor=C["bg3"]); vsb.pack(side="right",fill="y")
        lb=tk.Listbox(lf,bg=C["bg3"],fg=C["text"],selectbackground=C["teal"],selectforeground=C["bg"],
                      font=("Consolas",8),relief="flat",bd=0,activestyle="none",yscrollcommand=vsb.set)
        lb.pack(fill="both",expand=True,padx=4,pady=4); vsb.config(command=lb.yview)
        selected_folders=[]
        cnt_lbl=tk.Label(dlg,text="0 carpeta(s) seleccionada(s)",bg=C["bg"],fg=C["dim"],font=("Segoe UI",8))
        cnt_lbl.pack(anchor="w",padx=16)
        def _refresh():
            lb.delete(0,"end")
            for f in selected_folders:
                n=sum(1 for x in os.listdir(f) if os.path.splitext(x)[1].lower() in FORMATS_IN)
                lb.insert("end",f"  📁  {os.path.basename(f)}  ({n} img)")
            cnt_lbl.config(text=f"{len(selected_folders)} carpeta(s) seleccionada(s)")
        def _add():
            f=filedialog.askdirectory(title="Seleccionar carpeta",parent=dlg)
            if f and f not in selected_folders:
                selected_folders.append(f); _refresh()
        def _remove():
            sel=lb.curselection()
            for i in reversed(sel):
                if i<len(selected_folders): selected_folders.pop(i)
            _refresh()
        # Buttons row
        br=tk.Frame(dlg,bg=C["bg"]); br.pack(fill="x",padx=16,pady=(4,12))
        make_btn(br,"+ Agregar carpeta",_add).pack(side="left",padx=(0,6))
        make_btn(br,"✕ Quitar seleccionada",_remove,bg=C["bg4"],fg=C["err"],
                 hover_bg=C["err2"],hover_fg=C["bright"]).pack(side="left",padx=(0,16))
        def _confirm():
            if not selected_folders: dlg.destroy(); return
            total=0
            for folder in selected_folders:
                for fname in sorted(os.listdir(folder)):
                    if os.path.splitext(fname)[1].lower() in FORMATS_IN:
                        p=os.path.join(folder,fname)
                        if p not in self.files: self.files.append(p); total+=1
            self._sort_files(); self._sync_lists()
            self._st(f"📁 {total} archivo(s) de {len(selected_folders)} carpeta(s).")
            dlg.destroy()
        make_btn(br,"✅ Confirmar",_confirm,font=("Segoe UI",9,"bold")).pack(side="right")
        make_btn(br,"Cancelar",dlg.destroy,bg=C["bg4"],fg=C["text2"],
                 hover_bg=C["bg5"],hover_fg=C["bright"]).pack(side="right",padx=(0,6))

    def _add_folder_unified(self):
        if self._batch_mode: self._batch_add_folder(); return
        self._add_folder_only()

    def _add_zip_only(self):
        z=filedialog.askopenfilename(title="Seleccionar ZIP",filetypes=[("ZIP","*.zip"),("Todos","*.*")])
        if z: n=self._unzip(z); self._sort_files(); self._sync_lists(); self._st(f"📦 {n} imagen(es) extraída(s).")

    def _add_zip_unified(self):
        if self._batch_mode: self._batch_add_zip(); return
        self._add_zip_only()

    def _unzip(self,zpath):
        tmp=Path(zpath).parent/(Path(zpath).stem+"_extracted"); tmp.mkdir(exist_ok=True); n=0
        with zipfile.ZipFile(zpath) as zf:
            for name in zf.namelist():
                if os.path.splitext(name)[1].lower() in FORMATS_IN:
                    zf.extract(name,tmp); p=str(tmp/name)
                    if p not in self.files: self.files.append(p); n+=1
        return n

    def _on_drop(self,event):
        paths=re.findall(r'\{([^}]+)\}|(\S+)',event.data)
        paths=[a or b for a,b in paths]; n=0
        if self._batch_mode:
            for p in paths:
                p=p.strip()
                if not p: continue
                if os.path.isdir(p):
                    self.batch_entries.append(self._scan_folder_smart(p))
                elif p.lower().endswith(".zip"):
                    self.batch_entries.append({"path":p,"type":"zip","img_count":0,"children":[],"expanded":True})
            self._render_batch_tree()
        else:
            for p in paths:
                p=p.strip()
                if not p: continue
                if os.path.isdir(p):
                    for fname in sorted(os.listdir(p)):
                        if os.path.splitext(fname)[1].lower() in FORMATS_IN:
                            fp=os.path.join(p,fname)
                            if fp not in self.files: self.files.append(fp); n+=1
                elif p.lower().endswith(".zip"): n+=self._unzip(p)
                elif os.path.splitext(p)[1].lower() in FORMATS_IN:
                    if p not in self.files: self.files.append(p); n+=1
            self._sort_files(); self._sync_lists(); self._st(f"✅ {n} archivo(s) por drag & drop.")

    def _remove_sel(self,event=None):
        for i in reversed(self.s_lb.curselection()):
            if i<len(self.files): self.files.pop(i)
        self._sync_lists()

    def _clear_files(self):
        if self._batch_mode: self.batch_entries.clear(); self._render_batch_tree()
        else: self.files.clear(); self._sync_lists()
        self._st("🗑 Lista limpiada.")

    def _pick_out(self):
        d=filedialog.askdirectory(title="Carpeta de salida")
        if d: self.s_outv.set(d)

    def _pick_batch_zip_folder(self):
        d=filedialog.askdirectory(title="Carpeta para ZIPs batch")
        if d: self.s_bzpv.set(d)

    def _out_dir(self):
        d=self.s_outv.get().strip()
        if d=="Al lado de la carpeta original": d=""
        if d and os.path.isdir(d): return d
        # Por defecto: carpeta al lado de la original (padre de donde están los archivos)
        if self.files:
            src_dir=os.path.dirname(self.files[0])
            parent=os.path.dirname(src_dir)
            return parent if parent and os.path.isdir(parent) else src_dir
        return str(Path.home())

    # ── STATUS ────────────────────────────────────────────────────────────────
    def _st(self,msg): self.root.after(0,lambda:self.stat_lb.config(text=msg[:90]))
    def _sp(self,pct,msg=""):
        def _do(): self.prog_v.set(pct); msg and self.stat_lb.config(text=msg[:90])
        self.root.after(0,_do)

    def _check_deps(self):
        if not PIL_OK: self._st("⚠ Instala Pillow: pip install Pillow")
        elif Path(self.cfg.get("upscaler_exe",str(WAIFU_EXE))).exists():
            self._st("✅ Todo listo. Agrega imágenes para comenzar.")
        else: self._st("✅ Listo. (bloom_upscaler.exe no encontrado — otras funciones OK)")

    # ── RUN ───────────────────────────────────────────────────────────────────
    def _collect(self):
        self.cfg.update({"out_format":self.s_fmtv.get(),"quality":self.s_qv.get(),
            "stitch_height":int(self.s_hv.get() or 10000),"align":self.s_alv.get(),
            "convert_enabled":self.s_cv.get(),"stitch_enabled":self.s_sv.get(),
            "waifu_enabled":self.s_wv.get(),"waifu_scale":self.s_wsv.get(),
            "waifu_noise":self.s_wnv.get(),"waifu_model":self.s_wmv.get(),
            "output_mode":self.s_omv.get(),"output_dir":self.s_outv.get().strip(),
            "advanced_open":self._adv_open,"dark_mode":self._dark_mode,
            "batch_zip_folder":self.s_bzfv.get(),"batch_zip_folder_path":self.s_bzpv.get().strip(),
            "name_template":self.s_tmplv.get().strip() or "{n}_BloomStitch",
            "name_use_num":self.s_usenv.get(),
            "sort_method":self._sort_labels_map.get(self.s_sortv.get(),"name_asc"),
            "workers_convert":self.s_wk_conv.get(),
            "workers_stitch":self.s_wk_stitch.get(),
            "workers_batch":self.s_wk_batch.get()})
        self._save_config()

    def _run_all(self):
        self._collect()
        if self._batch_mode:
            paths=self._collect_batch_paths()
            if not paths: messagebox.showwarning("Sin carpetas","Agrega carpetas/ZIPs al batch primero."); return
            btn_set_state(self.run_btn,"disabled")
            threading.Thread(target=self._process_batch,args=(paths,),daemon=True).start()
        else:
            if not self.files: messagebox.showwarning("Sin archivos","Agrega imágenes primero."); return
            btn_set_state(self.run_btn,"disabled")
            threading.Thread(target=self._process,daemon=True).start()

    def _collect_batch_paths(self):
        """
        Genera la lista de paths a procesar.
        Reglas:
          - Si la carpeta raíz tiene imágenes directas → incluir la carpeta raíz
          - Si tiene children (subcarpetas/ZIPs) → incluir cada child
          - Si no tiene children y no tiene imgs directas → ignorar
        """
        paths = []
        for entry in self.batch_entries:
            children = entry.get("children", [])
            direct   = entry.get("img_count", 0)
            if children:
                # Procesar cada child individualmente
                for c in children:
                    paths.append(c["path"])
                # Si además hay imágenes directas en la raíz, procesar la raíz también
                if direct > 0:
                    paths.insert(0, entry["path"])  # raíz primero
            elif direct > 0 or entry["type"] == "zip":
                paths.append(entry["path"])
        return paths

    def _reveal_in_explorer(self, path):
        """
        Abre el explorador de archivos con el archivo/carpeta SELECCIONADO y resaltado.
        - Windows: explorer /select,"path"  → resalta la carpeta dentro de su padre
        - Mac:     open -R "path"           → mismo efecto en Finder
        - Linux:   xdg-open padre           → abre la carpeta padre (no hay select nativo)
        """
        path = str(path)
        try:
            if sys.platform == "win32":
                # /select hace que Explorer abra el padre y resalte el item
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                # Linux: abrir la carpeta padre para que sea visible
                parent = os.path.dirname(path) if os.path.isfile(path) else os.path.dirname(path.rstrip("/"))
                subprocess.Popen(["xdg-open", parent or path])
        except Exception:
            # Fallback: abrir directamente
            try:
                if sys.platform == "win32": os.startfile(path if os.path.isdir(path) else os.path.dirname(path))
                elif sys.platform == "darwin": subprocess.Popen(["open", path])
                else: subprocess.Popen(["xdg-open", path])
            except Exception: pass

    def _show_done_dialog(self, result_path, n_files):
        """Diálogo de éxito con botón para abrir carpeta."""
        w=tk.Toplevel(self.root); w.title("¡Listo!"); w.resizable(False,False)
        w.configure(bg=C["bg"]); w.transient(self.root); w.grab_set()
        W2,H2=360,180; sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        w.geometry(f"{W2}x{H2}+{(sw-W2)//2}+{(sh-H2)//2}")
        hd=tk.Frame(w,bg=C["bg2"],height=44); hd.pack(fill="x"); hd.pack_propagate(False)
        tk.Label(hd,text="✅  Proceso completado",bg=C["bg2"],fg=C["ok"],
                 font=("Segoe UI",12,"bold")).pack(side="left",padx=16,pady=10)
        tk.Frame(w,bg=C["border"],height=1).pack(fill="x")
        folder=result_path if os.path.isdir(result_path) else os.path.dirname(result_path)
        tk.Label(w,text=f"{n_files} archivo(s) generado(s)",bg=C["bg"],fg=C["text"],
                 font=("Segoe UI",10)).pack(pady=(16,4))
        name=os.path.basename(folder.rstrip("/\\")) or folder
        if len(name)>42: name="…"+name[-39:]
        tk.Label(w,text=name,bg=C["bg"],fg=C["teal"],font=("Consolas",8)).pack(pady=(0,12))
        bf=tk.Frame(w,bg=C["bg"]); bf.pack()
        make_btn(bf,"📂 Mostrar en carpeta",lambda f=folder:self._reveal_in_explorer(f),
                 bg=C["teal"],fg=C["bg"],hover_bg=C["cyan"],hover_fg=C["bg"]).pack(side="left",padx=8)
        make_btn(bf,"✕ Cerrar",w.destroy,bg=C["bg4"],fg=C["text2"],
                 hover_bg=C["bg5"],hover_fg=C["bright"]).pack(side="left",padx=8)

    def _show_batch_done_dialog(self, msg, show_dir):
        """Diálogo de fin de batch con botón para abrir carpeta de salida."""
        w=tk.Toplevel(self.root); w.title("Batch listo"); w.resizable(False,False)
        w.configure(bg=C["bg"]); w.transient(self.root); w.grab_set()
        W2,H2=400,220; sw=self.root.winfo_screenwidth(); sh=self.root.winfo_screenheight()
        w.geometry(f"{W2}x{H2}+{(sw-W2)//2}+{(sh-H2)//2}")
        hd=tk.Frame(w,bg=C["bg2"],height=44); hd.pack(fill="x"); hd.pack_propagate(False)
        tk.Label(hd,text="✅  Batch completado",bg=C["bg2"],fg=C["ok"],
                 font=("Segoe UI",12,"bold")).pack(side="left",padx=16,pady=10)
        tk.Frame(w,bg=C["border"],height=1).pack(fill="x")
        tk.Label(w,text=msg,bg=C["bg"],fg=C["text"],font=("Segoe UI",9),
                 justify="left",wraplength=360).pack(pady=(12,8),padx=20,anchor="w")
        bf=tk.Frame(w,bg=C["bg"]); bf.pack(pady=(0,14))
        if show_dir and os.path.isdir(str(show_dir)):
            make_btn(bf,"📂 Mostrar en carpeta",lambda d=show_dir:self._reveal_in_explorer(d),
                     bg=C["teal"],fg=C["bg"],hover_bg=C["cyan"],hover_fg=C["bg"]).pack(side="left",padx=8)
        make_btn(bf,"✕ Cerrar",w.destroy,bg=C["bg4"],fg=C["text2"],
                 hover_bg=C["bg5"],hover_fg=C["bright"]).pack(side="left",padx=8)

    def _process(self):
        self._sp(0,"Iniciando…")
        out_dir=self._out_dir(); out_mode=self.cfg.get("output_mode","images")
        fmt=self.cfg["out_format"]
        ext={"JPEG":".jpg","PNG":".png","WEBP":".webp","BMP":".bmp","TIFF":".tif"}.get(fmt,".png")
        src_folder=Path(os.path.dirname(self.files[0])).name or "output"
        folder_name=f"{src_folder}_BloomStitch"; final_dir=os.path.join(out_dir,folder_name)
        tmp_dir=tempfile.mkdtemp(prefix="bloomstitch_")
        try:
            files=list(self.files)
            if self.cfg["convert_enabled"]: self._sp(5,"🔄 Convirtiendo…"); files=self._convert(files,tmp_dir,fmt,ext)
            if self.cfg["stitch_enabled"]:  self._sp(40,"✂ Stitch…");       files=self._stitch(files,tmp_dir,fmt,ext)
            if self.cfg["waifu_enabled"]:   self._sp(70,"✨ Mejorando calidad…");      files=self._waifu(files,tmp_dir,ext)
            self._sp(88,"88%"); os.makedirs(final_dir,exist_ok=True); ff=[]
            for i,src in enumerate(files):
                dest=os.path.join(final_dir,f"{i+1:03d}{ext}"); shutil.copy2(src,dest); ff.append(dest)
            zp=None
            if out_mode in ("zip","both"):
                self._sp(95,"🗜 Comprimiendo…"); zp=os.path.join(out_dir,f"{folder_name}.zip")
                with zipfile.ZipFile(zp,"w",zipfile.ZIP_DEFLATED) as zf:
                    [zf.write(f,os.path.basename(f)) for f in ff if os.path.exists(f)]
            result=zp if out_mode=="zip" else (out_dir if out_mode=="both" else final_dir)
            if out_mode=="zip": shutil.rmtree(final_dir,ignore_errors=True)
            self._sp(100,f"✅ Listo — {len(ff)} archivo(s)")
            self.root.after(0,lambda r=result,n=len(ff):self._show_done_dialog(r,n))
        except Exception as ex:
            self._sp(0,f"❌ {ex}")
            self.root.after(0,lambda:messagebox.showerror("Error",str(ex)))
        finally:
            shutil.rmtree(tmp_dir,ignore_errors=True)
            self.root.after(0,lambda:btn_set_state(self.run_btn,"normal"))

    def _process_batch(self,folders):
        total=len(folders); fmt=self.cfg["out_format"]
        ext={"JPEG":".jpg","PNG":".png","WEBP":".webp","BMP":".bmp","TIFF":".tif"}.get(fmt,".png")
        om=self.cfg.get("output_mode","images")
        out_base=self.s_outv.get().strip()
        if out_base=="Al lado de la carpeta original": out_base=""

        # ── Carpeta de destino para todos los ZIPs ────────────────────────────
        use_zip_folder=self.cfg.get("batch_zip_folder",False)
        zip_folder_path=self.cfg.get("batch_zip_folder_path","").strip()
        if use_zip_folder and zip_folder_path:
            try: os.makedirs(zip_folder_path,exist_ok=True); batch_out_dir=zip_folder_path
            except: batch_out_dir=None
        elif out_base and os.path.isdir(out_base):
            batch_out_dir=out_base
        else:
            batch_out_dir=None  # next to each source folder

        # ── Carpeta contenedora única para el batch ──────────────────────────
        # Si no hay batch_out_dir explícito, crear una carpeta contenedora
        # al lado de la carpeta padre de los sources.
        # Ej: /Series/MiManga/Cap1 → /Series/MiManga_BloomStitch/Cap1_BS
        if not batch_out_dir and folders:
            def _get_parent(s):
                return os.path.dirname(s.rstrip("/\\"))
            parents = [_get_parent(s) for s in folders]
            common = parents[0]  # usar primer padre como raíz
            container_name = os.path.basename(common.rstrip("/\\")) or "Batch"
            container_dir = os.path.join(
                os.path.dirname(common.rstrip("/\\")),
                f"{container_name}_BloomStitch"
            )
            try:
                os.makedirs(container_dir, exist_ok=True)
                batch_out_dir = container_dir
            except Exception:
                pass  # fallback al comportamiento anterior

        # Nro de capítulos a procesar en paralelo
        # Con upscaler (GPU) procesar de a 1 para no saturar la GPU.
        if self.cfg.get("waifu_enabled",False):
            batch_workers=1  # GPU: siempre de a 1
        else:
            _wk_b=self.cfg.get("workers_batch",0)
            if _wk_b>0:
                batch_workers=min(_wk_b,total)
            else:
                # Auto: mitad de cores, máximo 4
                batch_workers=max(1,min((os.cpu_count() or 2)//2, total, 4))

        errors=[]; errors_lock=threading.Lock()
        generated_dirs=[]; dirs_lock=threading.Lock()
        done_count=[0]; done_lock=threading.Lock()

        def _process_one(src):
            nonlocal batch_out_dir
            with done_lock:
                done_count[0]+=1
                idx=done_count[0]
            self._sp(int(100*(idx-1)/total),
                     f"📂 {idx}/{total}: {os.path.basename(src.rstrip(chr(47)+chr(92)))}…")
            try:
                files=[]; tmp_x=None
                if src.lower().endswith(".zip"):
                    tmp_x=tempfile.mkdtemp(prefix="bz_")
                    with zipfile.ZipFile(src) as zf:
                        members=[n for n in zf.namelist()
                                 if os.path.splitext(n)[1].lower() in FORMATS_IN and not n.endswith("/")]
                        members.sort(key=lambda n:[p.lower() for p in n.replace("\\","/").split("/")])
                        for name in members:
                            zf.extract(name,tmp_x)
                            files.append(os.path.join(tmp_x,name.replace("/",os.sep)))
                elif os.path.isdir(src):
                    for fname in sorted(os.listdir(src)):
                        if os.path.splitext(fname)[1].lower() in FORMATS_IN:
                            files.append(os.path.join(src,fname))
                if not files:
                    with errors_lock: errors.append(f"{os.path.basename(src)}: sin imágenes")
                    return

                _src_clean=src.rstrip("/\\")
                bn=os.path.basename(_src_clean)
                if batch_out_dir:
                    od=batch_out_dir
                else:
                    src_parent=os.path.dirname(_src_clean)
                    grandparent=os.path.dirname(src_parent)
                    od=grandparent if grandparent and os.path.isdir(grandparent) else src_parent

                tmpl=self.cfg.get("name_template","{n}_BloomStitch")
                use_num=self.cfg.get("name_use_num",True)
                cap_num=re.search(r'\d+',bn); cap_str=cap_num.group(0) if cap_num else bn
                if use_num:
                    fn=tmpl.replace("{n}",cap_str) if "{n}" in tmpl else f"{tmpl}_{cap_str}"
                else:
                    fn=tmpl.replace("{n}","").strip("_- ") if tmpl else bn
                fn=fn or bn
                fd=os.path.join(od,fn); td=tempfile.mkdtemp(prefix="bb_")
                try:
                    if self.cfg["convert_enabled"]: files=self._convert(files,td,fmt,ext)
                    if self.cfg["stitch_enabled"]:  files=self._stitch(files,td,fmt,ext)
                    if self.cfg["waifu_enabled"]:   files=self._waifu(files,td,ext)
                    os.makedirs(fd,exist_ok=True); ff=[]
                    with dirs_lock: generated_dirs.append(od)
                    for i,s in enumerate(files):
                        dest=os.path.join(fd,f"{i+1:03d}{ext}"); shutil.copy2(s,dest); ff.append(dest)
                    if om in ("zip","both"):
                        zdir=batch_out_dir if batch_out_dir else od
                        zp=os.path.join(zdir,f"{fn}.zip")
                        already_compressed=ext in (".jpg",".jpeg",".webp")
                        zmode=zipfile.ZIP_STORED if already_compressed else zipfile.ZIP_DEFLATED
                        with zipfile.ZipFile(zp,"w",zmode) as zf:
                            for f2 in ff:
                                if os.path.exists(f2):
                                    zf.write(f2,os.path.basename(f2))
                    if om=="zip": shutil.rmtree(fd,ignore_errors=True)
                finally:
                    shutil.rmtree(td,ignore_errors=True)
                    if tmp_x: shutil.rmtree(tmp_x,ignore_errors=True)
            except Exception as ex:
                with errors_lock: errors.append(f"{os.path.basename(src)}: {ex}")

        # Ejecutar capítulos en paralelo
        with ThreadPoolExecutor(max_workers=batch_workers) as pool:
            list(pool.map(_process_one, folders))
        self._sp(100,f"✅ Batch — {total-len(errors)}/{total} OK")
        msg=f"Batch completado.\n{total-len(errors)}/{total} OK."
        show_dir=batch_out_dir if (batch_out_dir and os.path.isdir(str(batch_out_dir))) else (generated_dirs[0] if generated_dirs else None)
        if show_dir: msg+=f"\n📂 Salida: {show_dir}"
        if errors: msg+="\n\nErrores:\n"+"\n".join(errors)
        self.root.after(0,lambda m=msg,sd=show_dir:self._show_batch_done_dialog(m,sd))
        self.root.after(0,lambda:btn_set_state(self.run_btn,"normal"))

    # ── IMAGE PROCESSING ──────────────────────────────────────────────────────
    def _convert(self,files,tmp_dir,fmt,ext):
        """Convierte imágenes de a una, liberando RAM después de cada una."""
        if not PIL_OK: return files
        import gc
        n=len(files); res=[]; kw={"quality":self.cfg["quality"]} if fmt in ("JPEG","WEBP") else {}
        for i, src in enumerate(files):
            self._sp(5+int(28*(i+1)/n), f"Convirtiendo {i+1}/{n}…")
            try:
                img = open_image_safe(src)
                if img.mode in ("RGBA","LA","P") and fmt=="JPEG":
                    img = img.convert("RGB")
                elif img.mode not in ("RGB","RGBA","L"):
                    img = img.convert("RGB")
                dst = os.path.join(tmp_dir, f"conv_{i:04d}{ext}")
                img.save(dst, fmt, **kw)
                img.close(); del img
                res.append(dst)
            except Exception as ex:
                self._st(f"⚠ {os.path.basename(src)}: {ex}")
                res.append(src)
            if (i+1) % 10 == 0:
                gc.collect()
        return res

    def _stitch(self,files,tmp_dir,fmt,ext):
        """
        Stitch por streaming — nunca carga más de BATCH_IMGS imágenes a la vez.
        Esto evita crashes por OOM en capítulos con muchas páginas PSD pesadas.
        """
        if not PIL_OK or not files: return files
        import gc
        seg   = self.cfg["stitch_height"]
        align = self.cfg.get("align","smallest")
        kw    = {"quality":self.cfg["quality"]} if fmt in ("JPEG","WEBP") else {}
        n_files = len(files)

        # Paso 1: detectar ancho objetivo leyendo solo los headers (barato en RAM)
        self._sp(35, f"Detectando ancho de {n_files} imágenes…")
        widths = []
        for f in files:
            try:
                with Image.open(f) as im:
                    widths.append(im.width)
            except:
                pass
        if not widths: return files
        tw = min(widths) if align=="smallest" else (max(widths) if align=="largest" else None)
        W  = tw or widths[0]

        # Paso 2: streaming stitch — leer, pegar, descartar, nunca > BATCH_IMGS en RAM
        # Usamos un canvas acumulador de altura seg*2 y lo volcamos a disco cuando llena
        BATCH_IMGS = 8   # máximo de imágenes abiertas simultáneamente
        res  = []
        n    = 1
        buf  = Image.new("RGB", (W, seg * 2), (255,255,255))
        bf   = 0   # altura acumulada en buf

        def _flush_segment():
            nonlocal buf, bf, n
            while bf >= seg:
                cut = seg
                dst = os.path.join(tmp_dir, f"stitch_{n:04d}{ext}")
                buf.crop((0, 0, W, cut)).save(dst, fmt, **kw)
                res.append(dst); n += 1
                remaining = bf - cut
                new_buf = Image.new("RGB", (W, max(seg * 2, remaining + seg)), (255,255,255))
                if remaining > 0:
                    new_buf.paste(buf.crop((0, cut, W, cut + remaining)), (0, 0))
                buf.close()
                buf = new_buf
                bf = remaining

        for fi, fpath in enumerate(files):
            self._sp(35 + int(28 * fi / n_files),
                     f"Stitch {fi+1}/{n_files}…")
            try:
                img = open_image_safe(fpath)
                img.load()
                # Convertir a RGB
                if img.mode not in ("RGB","RGBA"): img = img.convert("RGB")
                # Escalar si es necesario
                if tw and img.width != tw:
                    ratio = tw / img.width
                    img = img.resize((W, max(1, int(img.height * ratio))), Image.BILINEAR)
                if img.mode != "RGB": img = img.convert("RGB")
                ih = img.height
                # Expandir buffer si la imagen no cabe
                if bf + ih > buf.height:
                    new_h = max(buf.height + ih + seg, seg * 3)
                    new_buf = Image.new("RGB", (W, new_h), (255,255,255))
                    new_buf.paste(buf.crop((0, 0, W, bf)), (0, 0))
                    buf.close(); buf = new_buf
                buf.paste(img, (0, bf))
                bf += ih
                img.close()
                del img
                # Volcar segmentos completos al disco
                _flush_segment()
                # Liberar memoria cada BATCH_IMGS imágenes
                if (fi + 1) % BATCH_IMGS == 0:
                    gc.collect()
            except Exception as ex:
                self._sp(35 + int(28 * fi / n_files),
                         f"⚠ {os.path.basename(fpath)}: {ex}")

        # Volcar lo que queda (último segmento incompleto)
        if bf > 0:
            dst = os.path.join(tmp_dir, f"stitch_{n:04d}{ext}")
            buf.crop((0, 0, W, bf)).save(dst, fmt, **kw)
            res.append(dst)
        buf.close()
        gc.collect()
        self._sp(63, f"✂ {len(res)} segmento(s) generados")
        return res

    def _waifu(self,files,tmp_dir,ext):
        exe=Path(self.cfg.get("upscaler_exe",str(WAIFU_EXE)))
        if not exe.exists(): return files
        sc=self.cfg.get("waifu_scale","2"); ns=self.cfg.get("waifu_noise","2")
        mp=_find_models(self.cfg.get("waifu_model","models-cunet"))
        res=[]; flags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
        for i,src in enumerate(files):
            dst=os.path.join(tmp_dir,f"waifu_{i:04d}{ext}")
            cmd=[str(exe),"-i",src,"-o",dst,"-s",sc,"-n",ns,"-m",str(mp)]
            try:
                r=subprocess.run(cmd,capture_output=True,timeout=600,creationflags=flags)
                res.append(dst if r.returncode==0 else src)
            except: res.append(src)
            self._sp(70+int(16*i/len(files)),f"Upscaling {i+1}/{len(files)}…")
        return res


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    root=TkinterDnD.Tk() if DND_OK else tk.Tk()
    root.withdraw()
    splash=SplashScreen(root)
    def launch():
        if splash._prog<100: root.after(30,launch); return
        root.after(250,_show)
    def _show():
        splash.close(); root.deiconify(); BloomStitch(root)
    root.after(50,launch); root.mainloop()

if __name__=="__main__":
    multiprocessing.freeze_support()
    main()

