# main.py — ESP32 PC Link Server
# Sirve la interfaz web PWA y actúa de proxy hacia el PC Agent
import usocket as socket
import uasyncio as asyncio
import urequests as requests
import ujson as json
import config
import gc
import network

# ──────────────────────────────────
# Wake-on-LAN
# ──────────────────────────────────
def send_wol():
    try:
        mac = config.PC_MAC_ADDRESS.replace("-", "").replace(":", "")
        data = b'\xff' * 6 + bytes.fromhex(mac) * 16
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(data, ('255.255.255.255', 9))
        sock.close()
        return True
    except Exception as e:
        print("[WOL] Error:", e)
        return False

# ──────────────────────────────────
# Proxy hacia el PC Agent
# ──────────────────────────────────
def pc_request(method, path, body=None):
    url = "http://{}:{}{}".format(config.PC_AGENT_IP, config.PC_AGENT_PORT, path)
    try:
        if method == "GET":
            r = requests.get(url, timeout=5)
        else:
            r = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
        text = r.text
        r.close()
        gc.collect()
        return text
    except Exception as e:
        gc.collect()
        return json.dumps({"error": str(e)})

# ──────────────────────────────────
# HTML de la interfaz PWA
# ──────────────────────────────────
PAGE_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0a0b10">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect fill='%230a0b10' width='100' height='100' rx='20'/><text y='68' x='50' text-anchor='middle' font-size='50'>&#9889;</text></svg>">
<title>PC Link</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0b10;--card:rgba(255,255,255,.04);--border:rgba(255,255,255,.08);--accent:#00e5ff;--red:#ff3d5a;--green:#00e676;--orange:#ff9100;--purple:#b388ff;--text:#e0e0e0;--dim:rgba(255,255,255,.45)}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:16px 16px 100px}
.hdr{text-align:center;padding:18px 0 12px}
.hdr h1{font-size:1.15rem;font-weight:700;letter-spacing:2px;background:linear-gradient(135deg,var(--accent),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .sub{font-size:.7rem;color:var(--dim);margin-top:2px;letter-spacing:1px}
.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;animation:pulse 2s infinite}
.online{background:var(--green);box-shadow:0 0 8px var(--green)}
.offline{background:var(--red);box-shadow:0 0 8px var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px;margin-bottom:14px;backdrop-filter:blur(12px)}
.card-title{font-size:.65rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--dim);margin-bottom:12px;font-weight:600}
.stats{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.stat{text-align:center}
.stat-val{font-size:1.6rem;font-weight:700;color:var(--accent)}
.stat-lbl{font-size:.6rem;color:var(--dim);text-transform:uppercase;letter-spacing:1px;margin-top:2px}
.actions{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btn{padding:14px 8px;border-radius:14px;border:1px solid var(--border);background:var(--card);color:var(--text);font-family:'Inter',sans-serif;font-weight:600;font-size:.75rem;cursor:pointer;transition:all .2s;display:flex;flex-direction:column;align-items:center;gap:6px;-webkit-tap-highlight-color:transparent}
.btn:active{transform:scale(.94);border-color:var(--accent);background:rgba(0,229,255,.08)}
.btn .ico{font-size:1.4rem}
.btn-power{border-color:rgba(0,230,118,.2);background:rgba(0,230,118,.06)}
.btn-power:active{background:rgba(0,230,118,.2);border-color:var(--green)}
.btn-off{border-color:rgba(255,61,90,.2);background:rgba(255,61,90,.06)}
.btn-off:active{background:rgba(255,61,90,.2);border-color:var(--red)}
.ai-section{margin-top:2px}
.ai-row{display:flex;gap:8px}
.ai-input{flex:1;padding:12px 14px;border-radius:14px;border:1px solid var(--border);background:rgba(0,0,0,.3);color:#fff;font-family:'Inter',sans-serif;font-size:.8rem;outline:none;transition:border .2s}
.ai-input:focus{border-color:var(--accent)}
.ai-send{padding:12px 18px;border-radius:14px;border:none;background:linear-gradient(135deg,var(--accent),var(--purple));color:#000;font-weight:700;font-size:.8rem;cursor:pointer;transition:opacity .2s}
.ai-send:active{opacity:.7}
.ai-log{margin-top:10px;max-height:220px;overflow-y:auto;display:flex;flex-direction:column;gap:8px;scroll-behavior:smooth}
.msg{padding:10px 14px;border-radius:12px;font-size:.78rem;line-height:1.45;max-width:92%;word-wrap:break-word}
.msg-user{background:rgba(0,229,255,.1);border:1px solid rgba(0,229,255,.15);align-self:flex-end;text-align:right}
.msg-ai{background:rgba(179,136,255,.08);border:1px solid rgba(179,136,255,.12);align-self:flex-start;border-left:3px solid var(--purple)}
.msg-sys{background:rgba(255,145,0,.08);border:1px solid rgba(255,145,0,.12);align-self:center;text-align:center;font-size:.7rem;color:var(--orange)}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--dim);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="hdr">
  <h1>PC CONTROL CENTER</h1>
  <div class="sub"><span id="dot" class="status-dot offline"></span><span id="pc-status">Verificando...</span></div>
</div>

<div class="card">
  <div class="card-title">Sistema</div>
  <div class="stats">
    <div class="stat"><div class="stat-val" id="s-cpu">--</div><div class="stat-lbl">CPU %</div></div>
    <div class="stat"><div class="stat-val" id="s-ram">--</div><div class="stat-lbl">RAM %</div></div>
    <div class="stat"><div class="stat-val" id="s-disk">--</div><div class="stat-lbl">Disco %</div></div>
  </div>
</div>

<div class="card">
  <div class="card-title">Controles Rapidos</div>
  <div class="actions">
    <button class="btn btn-power" onclick="doAction('power')"><span class="ico">&#9889;</span>Encender</button>
    <button class="btn btn-off" onclick="doAction('shutdown')"><span class="ico">&#9211;</span>Apagar</button>
    <button class="btn" onclick="doAction('lock')"><span class="ico">&#128274;</span>Bloquear</button>
    <button class="btn" onclick="doAction('minimize_all')"><span class="ico">&#128377;</span>Minimizar</button>
  </div>
</div>

<div class="card ai-section">
  <div class="card-title">Asistente IA (Gemini)</div>
  <div class="ai-row">
    <input class="ai-input" id="ai-in" placeholder="Escribe una orden o pregunta..." autocomplete="off">
    <button class="ai-send" id="ai-btn" onclick="sendAI()">Enviar</button>
  </div>
  <div class="ai-log" id="ai-log"></div>
</div>

<script>
const B="http://"+location.hostname;
let busy=false;

function $(id){return document.getElementById(id)}

function addMsg(text,type){
  const d=document.createElement("div");
  d.className="msg msg-"+type;
  d.textContent=text;
  $("ai-log").appendChild(d);
  $("ai-log").scrollTop=$("ai-log").scrollHeight;
}

async function doAction(a){
  if(a==="power"){
    addMsg("Enviando senal de encendido (WOL)...","sys");
    try{const r=await fetch(B+"/control?action=power");const d=await r.json();addMsg(d.result,"sys")}catch(e){addMsg("Error: "+e,"sys")}
    return;
  }
  if(a==="shutdown"&&!confirm("Seguro que quieres APAGAR la PC?"))return;
  addMsg("Ejecutando: "+a+"...","sys");
  try{
    const r=await fetch(B+"/control?action="+a);
    const d=await r.json();
    addMsg(d.result,"sys");
    if(a==="shutdown")setTimeout(()=>addMsg("La PC se apagara en segundos.","sys"),1000);
  }catch(e){addMsg("PC no responde. Esta encendida?","sys")}
  setTimeout(refreshStats,2000);
}

async function sendAI(){
  if(busy)return;
  const inp=$("ai-in");
  const q=inp.value.trim();
  if(!q)return;
  inp.value="";
  addMsg(q,"user");
  busy=true;
  $("ai-btn").innerHTML='<span class="spinner"></span>';
  try{
    const r=await fetch(B+"/ai?query="+encodeURIComponent(q));
    const d=await r.json();
    addMsg(d.response||d.error||"Sin respuesta","ai");
    if(d.exec_result)addMsg("Resultado: "+d.exec_result,"sys");
  }catch(e){addMsg("Error de conexion con la PC","ai")}
  busy=false;
  $("ai-btn").textContent="Enviar";
  refreshStats();
}

$("ai-in").addEventListener("keydown",e=>{if(e.key==="Enter")sendAI()});

async function refreshStats(){
  try{
    const r=await fetch(B+"/status",{signal:AbortSignal.timeout(4000)});
    const d=await r.json();
    if(d.error||d.status==="offline"){
      $("dot").className="status-dot offline";
      $("pc-status").textContent="PC Offline";
      $("s-cpu").textContent="--";$("s-ram").textContent="--";$("s-disk").textContent="--";
      return;
    }
    $("dot").className="status-dot online";
    $("pc-status").textContent="Online | "+d.os;
    $("s-cpu").textContent=d.cpu;
    $("s-ram").textContent=d.ram;
    $("s-disk").textContent=d.disk;
  }catch(e){
    $("dot").className="status-dot offline";
    $("pc-status").textContent="PC Offline";
  }
}

setInterval(refreshStats,5000);
refreshStats();
</script>
</body>
</html>"""

MANIFEST = '{"name":"PC Control Center","short_name":"PC Link","start_url":"/","display":"standalone","background_color":"#0a0b10","theme_color":"#0a0b10","icons":[{"src":"data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 100 100\'><rect fill=\'%230a0b10\' width=\'100\' height=\'100\' rx=\'20\'/><text y=\'68\' x=\'50\' text-anchor=\'middle\' font-size=\'50\'>&#9889;</text></svg>","sizes":"any","type":"image/svg+xml"}]}'

# ──────────────────────────────────
# URL-decode helper
# ──────────────────────────────────
def url_decode(s):
    res = s.replace("+", " ")
    parts = res.split("%")
    decoded = parts[0]
    for p in parts[1:]:
        try:
            decoded += chr(int(p[:2], 16)) + p[2:]
        except:
            decoded += "%" + p
    return decoded

# ──────────────────────────────────
# Parseo de la request HTTP
# ──────────────────────────────────
def parse_request(raw):
    try:
        first_line = raw.split(b"\r\n")[0].decode()
        method = first_line.split(" ")[0]
        full_path = first_line.split(" ")[1]
        path = full_path.split("?")[0]
        query = {}
        if "?" in full_path:
            qs = full_path.split("?")[1]
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query[k] = url_decode(v)
        return method, path, query
    except:
        return "GET", "/", {}

# ──────────────────────────────────
# Handler principal
# ──────────────────────────────────
def handle(method, path, query):
    if path == "/":
        return "text/html", PAGE_HTML

    elif path == "/manifest.json":
        return "application/json", MANIFEST

    elif path == "/status":
        body = pc_request("GET", "/status")
        return "application/json", body

    elif path == "/control":
        action = query.get("action", "")
        if action == "power":
            ok = send_wol()
            return "application/json", json.dumps({"result": "Paquete WOL enviado!" if ok else "Error al enviar WOL"})
        else:
            body = pc_request("POST", "/control", {"action": action})
            return "application/json", body

    elif path == "/ai":
        q = query.get("query", "")
        body = pc_request("POST", "/ai", {"query": q})
        return "application/json", body

    elif path == "/health":
        wlan = network.WLAN(network.STA_IF)
        ip = wlan.ifconfig()[0] if wlan.isconnected() else "N/A"
        return "application/json", json.dumps({"esp32": "alive", "ip": ip})

    return "text/plain", "404 Not Found"

# ──────────────────────────────────
# Servidor async
# ──────────────────────────────────
async def serve_client(reader, writer):
    try:
        raw = await asyncio.wait_for(reader.read(2048), timeout=5)
        if not raw:
            writer.close()
            await writer.wait_closed()
            return

        method, path, query = parse_request(raw)
        content_type, body = handle(method, path, query)

        header = "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n".format(content_type)
        writer.write(header.encode())
        
        # Enviar body en chunks para no agotar la RAM
        if isinstance(body, str):
            body = body.encode()
        chunk_size = 1024
        for i in range(0, len(body), chunk_size):
            writer.write(body[i:i+chunk_size])
            await writer.drain()

    except Exception as e:
        print("[HTTP] Error:", e)
        try:
            writer.write(b"HTTP/1.1 500 Error\r\n\r\nError")
            await writer.drain()
        except:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass
        gc.collect()

async def main():
    wlan = network.WLAN(network.STA_IF)
    ip = wlan.ifconfig()[0]
    print("=" * 44)
    print("  ESP32 PC Link")
    print("  Abre en tu celular: http://{}".format(ip))
    print("=" * 44)
    
    server = await asyncio.start_server(serve_client, "0.0.0.0", 80)
    print("[OK] Servidor listo en puerto 80")
    
    while True:
        await asyncio.sleep(60)
        gc.collect()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Detenido.")
