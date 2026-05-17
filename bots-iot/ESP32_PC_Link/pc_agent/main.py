# -*- coding: utf-8 -*-
"""
PC Agent — ESP32 PC Link v2
Servidor de control local que corre en Windows.
Sirve la interfaz PWA directamente + API de control + Gemini via Vertex AI.
"""
import os
import platform
import subprocess
import time
import json
import ctypes
import threading
import tempfile

# --- Credenciales de Windows (server-side only) ---
WIN_USER = "Corbalan Cristian"
WIN_PASS = "27042005"

from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import psutil
import pyperclip
import io
import mss
import pygetwindow as gw
import sqlite3
import pyautogui
from PIL import Image

# --- Volume Control ---
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# --- Vertex AI con Service Account ---
import google.oauth2.service_account
import google.auth.transport.requests
import urllib.request as url_req

SA_FILE = os.path.join(os.path.dirname(__file__), "sa.json")
PROJECT = "project-c2908a92-8889-4d26-98d"
LOCATIONS = ["us-central1", "us-east1", "europe-west1"]
MODEL = "gemini-2.5-flash"

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True,
     allow_headers=["Content-Type", "X-PIN", "ngrok-skip-browser-warning", "Authorization"],
     methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'Inbox')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Seguridad y DB ---
SECURITY_PIN = "1234"
DB_FILE = os.path.join(os.path.dirname(__file__), "serenity.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS error_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, message TEXT, context TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def log_error(source, error_msg, context=""):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO error_log (source, message, context) VALUES (?, ?, ?)", (source, str(error_msg), str(context)))
        conn.commit()
        conn.close()
    except: pass
    print(f"[ERROR][{source}] {error_msg}")

def is_locked():
    """Detecta si la PC esta bloqueada (lock screen activo)."""
    try:
        for p in psutil.process_iter(['name']):
            if p.info['name'] and p.info['name'].lower() == 'logonui.exe':
                return True
    except: pass
    return False

# ──────────────────────────────────────
# AUTENTICACIÓN VERTEX AI
# ──────────────────────────────────────
_cached_token = None
_token_expiry = 0

def get_access_token():
    """Obtiene un token OAuth2 válido. Se renueva automáticamente."""
    global _cached_token, _token_expiry
    now = time.time()
    if _cached_token and now < _token_expiry - 60:
        return _cached_token
    
    scopes = ['https://www.googleapis.com/auth/cloud-platform']
    creds = google.oauth2.service_account.Credentials.from_service_account_file(SA_FILE, scopes=scopes)
    req = google.auth.transport.requests.Request()
    creds.refresh(req)
    _cached_token = creds.token
    _token_expiry = now + 3500  # ~58 minutos
    print("[AUTH] Token renovado.")
    return _cached_token

def call_vertex(prompt_text, retry=0, image_b64=None):
    """Llama a Vertex AI con rotación de regiones, soporte opcional para imagenes."""
    if retry >= 6:
        return None
    
    token = get_access_token()
    loc = LOCATIONS[retry % len(LOCATIONS)]
    url = (f"https://{loc}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
           f"/locations/{loc}/publishers/google/models/{MODEL}:generateContent")
    
    parts = [{"text": prompt_text}]
    if image_b64:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_b64}})
        
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096}
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        req = url_req.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        with url_req.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        if "429" in str(e):
            print(f"[VERTEX] 429 en {loc}, reintentando...")
            time.sleep(5)
            return call_vertex(prompt_text, retry + 1)
        log_error("vertex_ai", str(e), f"region={loc}, retry={retry}")
        return None


# ──────────────────────────────────────
# FUNCIONES DE CONTROL DE PC
# ──────────────────────────────────────
import base64

def take_screenshot_base64():
    """Toma una captura de la pantalla, la comprime en JPEG y la devuelve en base64."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Pantalla principal
            sct_img = sct.grab(monitor)
            # Convertir a PIL Image para comprimir
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Guardar en memoria como JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=75)
            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode("utf-8")
    except Exception as e:
        log_error("screenshot_b64", str(e))
        return None

def get_system_stats():
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Temperatura via WMI (Windows)
    temp = "N/A"
    try:
        r = subprocess.check_output(
            ['powershell', '-Command',
             'Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi -ErrorAction SilentlyContinue | '
             'Select-Object -First 1 -ExpandProperty CurrentTemperature'],
            stderr=subprocess.DEVNULL, timeout=3
        )
        val = r.decode().strip()
        if val:
            kelvin_tenths = int(val)
            celsius = (kelvin_tenths / 10.0) - 273.15
            temp = f"{celsius:.0f}C"
    except:
        pass
    
    active_win = "Ninguna"
    try:
        w = gw.getActiveWindow()
        if w: active_win = w.title
    except: pass
    
    locked = is_locked()
    return {
        "cpu": cpu,
        "ram": ram.percent,
        "ram_used": round(ram.used / (1024**3), 1),
        "ram_total": round(ram.total / (1024**3), 1),
        "disk": disk.percent,
        "os": f"{platform.system()} {platform.release()}",
        "uptime": int(time.time() - psutil.boot_time()),
        "locked": locked,
        "temp": temp,
        "active_window": active_win
    }

def execute_command(cmd_type, params=None):
    if cmd_type == "lock":
        ctypes.windll.user32.LockWorkStation()
        return "PC Bloqueada correctamente"
    
    elif cmd_type == "minimize_all":
        subprocess.run(
            ["powershell", "(New-Object -ComObject shell.application).MinimizeAll()"],
            capture_output=True
        )
        return "Todas las ventanas minimizadas"
    
    elif cmd_type == "volume_mute":
        subprocess.run(
            ["powershell", 
             "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"],
            capture_output=True
        )
        return "Volumen silenciado/activado"
    
    elif cmd_type == "screenshot":
        try:
            import mss
            with mss.mss() as sct:
                path = os.path.join(os.path.dirname(__file__), "last_screenshot.png")
                sct.shot(output=path)
                return f"Screenshot guardada en {path}"
        except:
            return "Error: instala 'mss' para screenshots"
    
    elif cmd_type == "shell":
        try:
            result = subprocess.check_output(
                params, shell=True, stderr=subprocess.STDOUT, timeout=15
            )
            output = result.decode('latin-1', errors='replace')
            if len(output) > 3000:
                output = output[:3000] + "\n... (salida recortada)"
            return output
        except subprocess.TimeoutExpired:
            return "Error: El comando excedio el tiempo limite (15s)"
        except Exception as e:
            return f"Error: {str(e)}"
    
    elif cmd_type == "sleep":
        subprocess.run(
            ["powershell", "Add-Type -AssemblyName System.Windows.Forms; "
             "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"],
            capture_output=True
        )
        return "PC en modo suspension"
        
    elif cmd_type == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True)
        return "Apagando la PC en 5 segundos..."
    
    elif cmd_type == "unlock":
        return unlock_pc()
        
    # --- Computer Use Actions ---
    elif cmd_type == "mouse_click":
        try:
            x, y = int(params.get("x", 0)), int(params.get("y", 0))
            pyautogui.click(x=x, y=y)
            return f"Click realizado en ({x}, {y})"
        except Exception as e:
            return f"Error en mouse_click: {e}"
            
    elif cmd_type == "mouse_move":
        try:
            x, y = int(params.get("x", 0)), int(params.get("y", 0))
            pyautogui.moveTo(x=x, y=y, duration=0.3)
            return f"Mouse movido a ({x}, {y})"
        except Exception as e:
            return f"Error en mouse_move: {e}"
            
    elif cmd_type == "keyboard_type":
        try:
            text = params.get("text", "")
            pyautogui.write(text, interval=0.01)
            return f"Texto escrito: '{text}'"
        except Exception as e:
            return f"Error en keyboard_type: {e}"
            
    elif cmd_type == "keyboard_press":
        try:
            key = params.get("key", "enter")
            pyautogui.press(key)
            return f"Tecla '{key}' presionada"
        except Exception as e:
            return f"Error en keyboard_press: {e}"
    
    elif cmd_type == "processes":
        procs = []
        for p in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                if info['cpu_percent'] and info['cpu_percent'] > 0.5:
                    procs.append(info)
            except:
                pass
        procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        return json.dumps(procs[:15])
    
    return "Comando desconocido"

def unlock_pc():
    """Desbloquea la PC simulando la escritura de la contraseña."""
    try:
        # Crear script PowerShell temporal que escribe la contraseña
        script = f'''Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class KbdInput {{
    [DllImport("user32.dll")]
    public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")]
    public static extern short VkKeyScan(char ch);
}}
"@

# Despertar pantalla
[KbdInput]::keybd_event(0x1B, 0, 0, [UIntPtr]::Zero)
[KbdInput]::keybd_event(0x1B, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 500

# Click/Enter para mostrar campo de contraseña
[KbdInput]::keybd_event(0x20, 0, 0, [UIntPtr]::Zero)
[KbdInput]::keybd_event(0x20, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 800

# Escribir contraseña
foreach ($c in "{WIN_PASS}".ToCharArray()) {{
    $vk = [KbdInput]::VkKeyScan($c)
    [KbdInput]::keybd_event([byte]($vk -band 0xFF), 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 30
    [KbdInput]::keybd_event([byte]($vk -band 0xFF), 0, 2, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 30
}}

# Enter para confirmar
Start-Sleep -Milliseconds 300
[KbdInput]::keybd_event(0x0D, 0, 0, [UIntPtr]::Zero)
[KbdInput]::keybd_event(0x0D, 0, 2, [UIntPtr]::Zero)
'''
        # Guardar y ejecutar como tarea del sistema (puede interactuar con lock screen)
        script_path = os.path.join(tempfile.gettempdir(), "serenity_unlock.ps1")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)
        
        # Crear tarea programada que corre como SYSTEM con sesión interactiva
        subprocess.run([
            'schtasks', '/create', '/tn', 'SerenityUnlock',
            '/tr', f'powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "{script_path}"',
            '/sc', 'once', '/st', '00:00', '/f', '/rl', 'highest'
        ], capture_output=True)
        
        subprocess.run(['schtasks', '/run', '/tn', 'SerenityUnlock'], capture_output=True)
        time.sleep(4)
        subprocess.run(['schtasks', '/delete', '/tn', 'SerenityUnlock', '/f'], capture_output=True)
        
        try:
            os.remove(script_path)
        except:
            pass
        
        return "Desbloqueando PC..."
    except Exception as e:
        return f"Error al desbloquear: {str(e)}"


# ──────────────────────────────────────
# INTEGRACIÓN GEMINI (VERTEX AI)
# ──────────────────────────────────────

# Historial de conversación (últimos N mensajes)
MAX_HISTORY = 20

def load_chat_history():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (MAX_HISTORY,))
        rows = c.fetchall()
        conn.close()
        return [{"role": r[0], "text": r[1]} for r in reversed(rows)]
    except:
        return []

def save_chat_msg(role, text):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, text))
        conn.commit()
        conn.close()
    except: pass

def ask_gemini(user_input):
    """Usa Vertex AI para interpretar comandos o conversar."""
    stats = get_system_stats()
    
    _chat_history = load_chat_history()
    
    # Agregar mensaje del usuario al historial
    _chat_history.append({"role": "user", "text": user_input})
    save_chat_msg("user", user_input)
    
    # Construir contexto del chat reciente
    history_text = ""
    for msg in _chat_history[-10:]:
        prefix = "Usuario" if msg["role"] == "user" else "Asistente"
        history_text += f"{prefix}: {msg['text']}\n"
    
    prompt = f"""Eres "Serenity", un asistente AI avanzado integrado en la computadora de tu usuario.
Eres inteligente, amigable, y hablas siempre en español.

CAPACIDADES:
- Puedes ver la pantalla actual del usuario (se te adjunta como imagen). La resolución de pantalla es 1360x768.
- Puedes usar el ratón y el teclado de forma autónoma.
- Puedes ejecutar CUALQUIER comando de Windows via shell (PowerShell/CMD).
- Puedes conversar, programar, ayudar con tareas e investigar temas.

ESTADO ACTUAL DE LA PC:
- CPU: {stats['cpu']}%
- RAM: {stats['ram']}% ({stats['ram_used']}/{stats['ram_total']} GB)
- Disco: {stats['disk']}%
- Ventana Activa en Pantalla: {stats['active_window']}
- Sistema: {stats['os']}

HISTORIAL DE CONVERSACION:
{history_text}

ULTIMO MENSAJE DEL USUARIO: "{user_input}"

INSTRUCCIONES DE RESPUESTA:
1. Analiza cuidadosamente la captura de pantalla si el usuario te pide interactuar con la interfaz gráfica.
2. Si el usuario te pide hacer clic en algo, encuentra las coordenadas (X, Y) en la imagen y usa la acción "mouse_click".
3. Si el usuario te pide escribir, usa la acción "keyboard_type".
4. Si el usuario pide ejecutar algo en consola, usa "shell".
5. Si es solo una pregunta o conversación, usa "none" y responde naturalmente.

Responde UNICAMENTE en JSON valido (sin markdown, sin bloques de codigo):
{{
  "action": "mouse_click|mouse_move|keyboard_type|keyboard_press|lock|minimize_all|sleep|shutdown|volume_mute|shell|processes|none",
  "params": {{ "x": 123, "y": 456 }} o {{ "text": "hola" }} o {{ "key": "enter" }} o "comando_shell",
  "response": "tu_respuesta_aqui"
}}

Ejemplos de Computer Use:
- Usuario: "haz click en el boton rojo de arriba a la derecha" -> {{"action":"mouse_click","params":{{"x": 1300, "y": 20}},"response":"Haciendo click en el botón rojo..."}}
- Usuario: "escribe Serenity en el buscador" -> {{"action":"keyboard_type","params":{{"text":"Serenity"}},"response":"Escribiendo Serenity..."}}
- Usuario: "presiona enter" -> {{"action":"keyboard_press","params":{{"key":"enter"}},"response":"Presionando Enter..."}}
"""
    
    try:
        # Tomar captura de pantalla para visión
        image_b64 = take_screenshot_base64()
        
        raw = call_vertex(prompt, image_b64=image_b64)
        if not raw:
            return {"action": "none", "params": None, "response": "No pude conectar con Gemini. Reintentando..."}
        
        # Limpiar posibles tags de markdown
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            if lines[0].startswith("```"): lines = lines[1:]
            clean = "\n".join(lines)
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        
        result = json.loads(clean, strict=False)
        
        # Guardar respuesta en historial
        save_chat_msg("assistant", result.get("response", ""))
        
        return result
    except Exception as e:
        log_error("json_parse", str(e), raw)
        return {"action": "none", "params": None, "response": f"Error de formato IA. 🚩 Revisar log."}


# ──────────────────────────────────────
# INTERFAZ WEB PWA (servida directamente)
# ──────────────────────────────────────

PAGE_HTML = """<!DOCTYPE html>
<html><body><h1>Serenity PC Agent</h1><p>El servidor local esta funcionando. Por favor usa la PWA desde GitHub Pages para controlar la PC.</p></body></html>"""

MANIFEST_JSON = json.dumps({
    "name": "Serenity — PC Control",
    "short_name": "Serenity",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0a0b10",
    "theme_color": "#0a0b10",
    "icons": [{"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect fill='%230a0b10' width='100' height='100' rx='20'/><text y='68' x='50' text-anchor='middle' font-size='50'>&#9889;</text></svg>","sizes":"any","type":"image/svg+xml"}]
})

# ──────────────────────────────────────
# RUTAS API
# ──────────────────────────────────────

@app.before_request
def require_pin():
    # CORS preflight must pass through without auth
    if request.method == 'OPTIONS':
        return
    if request.path in ['/', '/manifest.json', '/health', '/errors']:
        return
    pin = request.headers.get("X-PIN") or request.args.get("pin")
    if not pin or pin != SECURITY_PIN:
        return jsonify({"error": "Unauthorized", "action": "none", "result": "Unauthorized"}), 401

@app.route('/')
def index():
    """Sirve la interfaz PWA principal."""
    return Response(PAGE_HTML, content_type='text/html; charset=utf-8')

@app.route('/manifest.json')
def manifest():
    return Response(MANIFEST_JSON, content_type='application/json')

@app.route('/status', methods=['GET'])
def status():
    """Devuelve estadísticas del sistema."""
    return jsonify(get_system_stats())

@app.route('/control', methods=['POST'])
def control():
    """Ejecuta un comando directo."""
    data = request.json
    action = data.get("action", "")
    params = data.get("params")
    result = execute_command(action, params)
    return jsonify({"result": result})

@app.route('/ai', methods=['POST'])
def ai_control():
    """Procesa una petición con Gemini AI."""
    user_input = request.json.get("query", "")
    if not user_input:
        return jsonify({"action": "none", "params": None, "response": "Consulta vacia."})
    
    decision = ask_gemini(user_input)
    
    # Ejecutar la acción decidida por Gemini
    if decision.get("action") and decision["action"] != "none":
        exec_result = execute_command(decision["action"], decision.get("params"))
        decision["exec_result"] = exec_result
    
    return jsonify(decision)

@app.route('/report', methods=['POST'])
def report():
    msg = request.json.get("msg", "")
    log_error("user_report", "Reportado desde UI", msg)
    return jsonify({"success": True})

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de salud para que el ESP32 sepa que estamos vivos."""
    return jsonify({"status": "alive", "ts": int(time.time())})

@app.route('/errors', methods=['GET'])
def errors():
    """Devuelve el log de errores para revisión."""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT timestamp, source, message, context FROM error_log ORDER BY id DESC LIMIT 50")
        rows = c.fetchall()
        conn.close()
        logs = [{"ts": r[0], "source": r[1], "error": r[2], "context": r[3]} for r in rows]
        return jsonify(logs)
    except: pass
    return jsonify([])

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"})
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({"success": True, "filename": filename})

@app.route('/clipboard', methods=['GET', 'POST'])
def clipboard():
    if request.method == 'GET':
        try:
            return jsonify({"text": pyperclip.paste()})
        except:
            return jsonify({"text": ""})
    else:
        try:
            txt = request.json.get("text", "")
            pyperclip.copy(txt)
            return jsonify({"success": True})
        except:
            return jsonify({"success": False})

@app.route('/screenshot', methods=['GET'])
def screenshot():
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            return send_file(io.BytesIO(img_bytes), mimetype='image/png')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/volume', methods=['POST'])
def volume():
    try:
        level = int(request.json.get("level", 50))
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
        # Nivel de pycaw va de -65.25 a 0.0, mapeamos rudimentariamente
        scalar = level / 100.0
        volume_ctrl.SetMasterVolumeLevelScalar(scalar, None)
        return jsonify({"success": True})
    except:
        return jsonify({"success": False}), 500

@app.route('/process/kill', methods=['POST'])
def kill_process():
    try:
        name = request.json.get("name")
        for p in psutil.process_iter(['name']):
            if p.info['name'] == name:
                p.kill()
        return jsonify({"success": True})
    except:
        return jsonify({"success": False}), 500

# ──────────────────────────────────────
# ARRANQUE Y TÚNEL NGROK (CON FIREBASE)
# ──────────────────────────────────────

from pyngrok import ngrok
import requests

FIREBASE_URL = "https://serenity-pc-link-default-rtdb.firebaseio.com"
FIREBASE_SECRET = "3nVXGaf8jySKmvxWzA4EcQG7wJzJmEvCnFU5skZG"

def clipboard_sync_loop():
    """Mantiene sincronizado el portapapeles entre la PC y Firebase."""
    last_pc_clip = ""
    last_cloud_clip = ""
    
    while True:
        try:
            # 1. PC -> Nube
            current_pc = pyperclip.paste()
            if current_pc != last_pc_clip and current_pc.strip():
                url = f"{FIREBASE_URL}/clipboard/pc.json?auth={FIREBASE_SECRET}"
                requests.put(url, json=current_pc)
                last_pc_clip = current_pc
                print(f"[CLIP] PC -> Nube: {current_pc[:20]}...")

            # 2. Nube -> PC
            url_mobile = f"{FIREBASE_URL}/clipboard/mobile.json?auth={FIREBASE_SECRET}"
            res = requests.get(url_mobile)
            if res.status_code == 200:
                cloud_clip = res.json()
                if cloud_clip and cloud_clip != last_cloud_clip:
                    pyperclip.copy(cloud_clip)
                    last_cloud_clip = cloud_clip
                    last_pc_clip = cloud_clip # Evitar rebote
                    print(f"[CLIP] Nube -> PC: {cloud_clip[:20]}...")
        except Exception as e:
            print(f"Error en sincronizacion de portapapeles: {e}")
        
        time.sleep(3)

def start_ngrok():
    try:
        ngrok.set_auth_token("3DXpQEftQizHHOARVMKgQVjtJUu_4VJKqCztZh1Eb1WydHvcc")
        
        public_url = ""
        try:
            public_url = ngrok.connect(5000).public_url
        except Exception as e:
            if "already online" in str(e):
                tunnels = ngrok.get_tunnels()
                for t in tunnels:
                    if "5000" in t.config['addr']:
                        public_url = t.public_url
                        break
            if not public_url:
                raise e

        print("="*50)
        print(f"🌍 TÚNEL NGROK ACTIVO: {public_url}")
        print("="*50)
        
        # Registrar URL en Firebase
        url = f"{FIREBASE_URL}/server.json?auth={FIREBASE_SECRET}"
        data = {
            "pc_url": public_url,
            "status": "online",
            "last_seen": time.time(),
            "action": "none"
        }
        requests.put(url, json=data)
        print("[OK] Enlace publicado en Firebase correctamente.")
        
        # Heartbeat loop
        while True:
            time.sleep(60)
            url = f"{FIREBASE_URL}/server/last_seen.json?auth={FIREBASE_SECRET}"
            requests.put(url, json=time.time())
            
    except Exception as e:
        print(f"Error iniciando ngrok o Firebase: {e}")

if __name__ == '__main__':
    print("=" * 50)
    print("  Serenity — PC Agent v2")
    print("  http://localhost:5000")
    print("=" * 50)
    
    # Verificar que existe sa.json
    if not os.path.exists(SA_FILE):
        print("[ERROR] No se encontro sa.json! Gemini no funcionara.")
    else:
        print(f"[OK] Service Account cargada: {SA_FILE}")
        try:
            get_access_token()
            print("[OK] Token de Vertex AI obtenido correctamente.")
        except Exception as e:
            print(f"[WARN] Error al obtener token: {e}")
            
    threading.Thread(target=start_ngrok, daemon=True).start()
    threading.Thread(target=clipboard_sync_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
