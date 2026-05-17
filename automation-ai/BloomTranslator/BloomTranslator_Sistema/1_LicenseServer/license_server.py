"""
BLOOM TRANSLATOR - SERVIDOR DE LICENCIAS
Corre en tu PC (localhost:7777)
NO necesita estar en internet público
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3
import hashlib
import secrets
import json
from datetime import datetime
from cryptography.fernet import Fernet
import os

app = Flask(__name__)
CORS(app)

# ==================== CONFIGURACIÓN ====================

DB_FILE = 'licenses.db'
CONFIG_FILE = 'config.json'
SECRET_KEY = os.environ.get('LICENSE_SECRET', 'bloom-scans-2024-secret-key')

# Cargar configuración de costos
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'costs': {
            'cargar_imagen_local': 1,
            'importar_drive': 1,
            'ocr_imagen': 1,
            'limpiar_imagen': 2,
            'upscale_hd': 1,
            'upscale_ultra': 1,
            'traducir_100_chars': 1,
            'exportar_json': 0
        },
        'default_credits': {
            'FULL': 500,
            'STAFF': 300
        }
    }

CONFIG = load_config()

# ==================== BASE DE DATOS ====================

def init_db():
    """Crear tablas si no existen"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla de licencias
    c.execute('''CREATE TABLE IF NOT EXISTS licenses (
        key TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        credits INTEGER NOT NULL,
        status TEXT DEFAULT 'unused',
        device_id TEXT,
        drive_folder TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activated_at TIMESTAMP,
        last_sync TIMESTAMP
    )''')
    
    # Tabla de historial
    c.execute('''CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT,
        action TEXT,
        details TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

def get_db():
    """Obtener conexión a BD"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# ==================== GENERACIÓN DE KEYS ====================

def generate_key(key_type='FULL', credits=500):
    """
    Genera una key única
    Formato: TYPE-CREDITS-RANDOM
    Ejemplo: FULL-500-ABC123XYZ789
    """
    random_part = secrets.token_hex(8).upper()
    key = f"{key_type}-{credits}-{random_part}"
    return key

def create_license(key_type, credits, drive_folder=None):
    """Crear nueva licencia en BD"""
    key = generate_key(key_type, credits)
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute('''INSERT INTO licenses (key, type, credits, drive_folder)
                     VALUES (?, ?, ?, ?)''',
                  (key, key_type, credits, drive_folder))
        
        c.execute('''INSERT INTO history (license_key, action, details)
                     VALUES (?, ?, ?)''',
                  (key, 'created', f'Licencia {key_type} con {credits} créditos'))
        
        conn.commit()
        return key
    except Exception as e:
        print(f"Error creando licencia: {e}")
        return None
    finally:
        conn.close()

# ==================== API ENDPOINTS ====================

@app.route('/api/validate', methods=['POST'])
def validate_license():
    """
    Validar licencia (sin device binding)
    POST: { "key": "FULL-500-ABC..." }
    """
    data = request.json
    key = data.get('key', '').strip().upper()
    
    if not key:
        return jsonify({'success': False, 'error': 'Key requerida'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Buscar licencia
    c.execute('SELECT * FROM licenses WHERE key = ?', (key,))
    license_data = c.fetchone()
    
    if not license_data:
        conn.close()
        return jsonify({'success': False, 'error': 'Licencia no encontrada'}), 404
    
    lic = dict(license_data)
    
    # Verificar si está disponible
    if lic['status'] == 'used':
        conn.close()
        return jsonify({'success': False, 'error': 'Licencia ya utilizada'}), 403
    
    # Si es primera activación, marcar como activa
    if lic['status'] == 'available':
        c.execute('''UPDATE licenses 
                     SET status = 'active', 
                         activated_at = ?,
                         last_sync = ?
                     WHERE key = ?''',
                  (datetime.now(), datetime.now(), key))
        
        c.execute('''INSERT INTO history (license_key, action, details)
                     VALUES (?, ?, ?)''',
                  (key, 'activated', 'Licencia activada'))
        
        conn.commit()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'type': lic['type'],
        'credits': lic['credits'],
        'drive_folder': lic['drive_folder'],
        'message': f"Licencia validada: {lic['credits']} créditos disponibles"
    })

@app.route('/api/sync', methods=['POST'])
def sync_credits():
    """
    Sincronizar créditos
    POST: { "key": "...", "device_id": "...", "credits_spent": 5 }
    """
    data = request.json
    key = data.get('key', '').strip().upper()
    device_id = data.get('device_id', '')
    credits_spent = data.get('credits_spent', 0)
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM licenses WHERE key = ? AND device_id = ?', (key, device_id))
    lic = c.fetchone()
    
    if not lic:
        conn.close()
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 403
    
    lic = dict(lic)
    new_credits = max(0, lic['credits'] - credits_spent)
    
    c.execute('''UPDATE licenses 
                 SET credits = ?, last_sync = ?
                 WHERE key = ?''',
              (new_credits, datetime.now(), key))
    
    if credits_spent > 0:
        c.execute('''INSERT INTO history (license_key, action, details)
                     VALUES (?, ?, ?)''',
                  (key, 'spent', f'{credits_spent} créditos gastados'))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'credits': new_credits,
        'message': 'Créditos sincronizados'
    })

@app.route('/api/reload', methods=['POST'])
def reload_credits():
    """
    Recargar créditos con key de recarga
    POST: { "main_key": "FULL-500-...", "reload_key": "RELOAD-100-..." }
    """
    data = request.json
    main_key = data.get('main_key', '').strip().upper()
    reload_key = data.get('reload_key', '').strip().upper()
    
    if not reload_key.startswith('RELOAD-'):
        return jsonify({'success': False, 'error': 'Key de recarga inválida'}), 400
    
    # Extraer créditos de la key de recarga
    try:
        parts = reload_key.split('-')
        reload_credits = int(parts[1])
    except:
        return jsonify({'success': False, 'error': 'Formato de key inválido'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Verificar que reload_key no haya sido usada
    c.execute('SELECT * FROM licenses WHERE key = ?', (reload_key,))
    reload_lic = c.fetchone()
    
    if not reload_lic:
        conn.close()
        return jsonify({'success': False, 'error': 'Key de recarga no encontrada'}), 404
    
    reload_lic = dict(reload_lic)
    
    if reload_lic['status'] == 'used':
        conn.close()
        return jsonify({'success': False, 'error': 'Esta key de recarga ya fue usada'}), 403
    
    # Buscar licencia principal
    c.execute('SELECT * FROM licenses WHERE key = ?', (main_key,))
    main_lic = c.fetchone()
    
    if not main_lic:
        conn.close()
        return jsonify({'success': False, 'error': 'Licencia principal no encontrada'}), 404
    
    main_lic = dict(main_lic)
    new_credits = main_lic['credits'] + reload_credits
    
    # Actualizar créditos
    c.execute('UPDATE licenses SET credits = ? WHERE key = ?', (new_credits, main_key))
    c.execute('UPDATE licenses SET status = "used" WHERE key = ?', (reload_key,))
    
    c.execute('''INSERT INTO history (license_key, action, details)
                 VALUES (?, ?, ?)''',
              (main_key, 'reloaded', f'+{reload_credits} créditos añadidos'))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'credits': new_credits,
        'message': f'{reload_credits} créditos añadidos exitosamente'
    })

@app.route('/api/costs', methods=['GET'])
def get_costs():
    """Devolver tabla de costos actual"""
    return jsonify(CONFIG['costs'])

# ==================== ADMIN PANEL ====================

@app.route('/')
def index():
    return '''
    <html>
    <head><title>Bloom Translator - Servidor</title></head>
    <body style="font-family:sans-serif;text-align:center;padding:50px;">
        <h1>🔑 Servidor de Licencias - Bloom Translator</h1>
        <p>Estado: <strong style="color:green;">✅ ACTIVO</strong></p>
        <p><a href="/admin" style="background:#3d7ef5;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;">Ir al Panel Admin</a></p>
        <hr>
        <p style="color:#666;font-size:12px;">Puerto: 7777 | Local only</p>
    </body>
    </html>
    '''

@app.route('/admin')
def admin():
    """Redirigir al panel de administración"""
    return '''
    <html>
    <head>
        <title>Panel Admin - Bloom Translator</title>
        <meta charset="UTF-8">
        <style>
            * { margin:0; padding:0; box-sizing:border-box; }
            body { font-family: 'Segoe UI', sans-serif; background: #0a0e1a; color: #e0e6f0; }
            .container { max-width: 900px; margin: 40px auto; padding: 20px; }
            h1 { margin-bottom: 30px; font-size: 28px; }
            .card { background: #151b2e; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #252d45; }
            .btn { background: linear-gradient(135deg, #3d7ef5, #6b46c1); color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; }
            .btn:hover { opacity: 0.9; }
            input, select { width: 100%; padding: 10px; margin: 8px 0; background: #0d1320; border: 1px solid #252d45; border-radius: 6px; color: #e0e6f0; font-size: 14px; }
            .result { background: #1a2332; padding: 15px; border-radius: 8px; margin-top: 15px; font-family: monospace; word-break: break-all; }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #252d45; }
            th { background: #1a2332; font-weight: 600; }
            .status-active { color: #3dba7b; }
            .status-unused { color: #f5a623; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔑 Panel de Administración</h1>
            
            <div class="card">
                <h2 style="margin-bottom:15px;">Generar Nueva Licencia</h2>
                <select id="type">
                    <option value="FULL">FULL - Sin restricciones</option>
                    <option value="STAFF">STAFF - Solo Bloom Scans Drive</option>
                </select>
                <input type="number" id="credits" placeholder="Créditos iniciales" value="500">
                <input type="text" id="drive_folder" placeholder="ID carpeta Drive (solo STAFF)" style="display:none;">
                <button class="btn" onclick="generateLicense()">Generar Licencia</button>
                <div id="result" class="result" style="display:none;"></div>
            </div>
            
            <div class="card">
                <h2 style="margin-bottom:15px;">Generar Key de Recarga</h2>
                <input type="number" id="reload_credits" placeholder="Créditos a añadir" value="100">
                <button class="btn" onclick="generateReload()">Generar Key de Recarga</button>
                <div id="reload_result" class="result" style="display:none;"></div>
            </div>
            
            <div class="card">
                <h2 style="margin-bottom:15px;">Licencias Activas</h2>
                <button class="btn" onclick="loadLicenses()">Actualizar Lista</button>
                <div id="licenses_list"></div>
            </div>
        </div>
        
        <script>
            document.getElementById('type').addEventListener('change', function() {
                document.getElementById('drive_folder').style.display = 
                    this.value === 'STAFF' ? 'block' : 'none';
            });
            
            async function generateLicense() {
                const type = document.getElementById('type').value;
                const credits = parseInt(document.getElementById('credits').value);
                const drive_folder = document.getElementById('drive_folder').value;
                
                const res = await fetch('/admin/generate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type, credits, drive_folder: drive_folder || null})
                });
                
                const data = await res.json();
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = `
                    <strong>✅ Licencia generada:</strong><br>
                    <span style="color:#3dba7b;font-size:18px;">${data.key}</span><br><br>
                    Tipo: ${data.type} | Créditos: ${data.credits}
                `;
            }
            
            async function generateReload() {
                const credits = parseInt(document.getElementById('reload_credits').value);
                
                const res = await fetch('/admin/generate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({type: 'RELOAD', credits})
                });
                
                const data = await res.json();
                const resultDiv = document.getElementById('reload_result');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = `
                    <strong>✅ Key de recarga generada:</strong><br>
                    <span style="color:#6b46c1;font-size:18px;">${data.key}</span><br><br>
                    Créditos: +${data.credits}
                `;
            }
            
            async function loadLicenses() {
                const res = await fetch('/admin/licenses');
                const licenses = await res.json();
                
                let html = '<table><tr><th>Key</th><th>Tipo</th><th>Créditos</th><th>Estado</th><th>Activada</th></tr>';
                licenses.forEach(lic => {
                    const statusClass = lic.status === 'active' ? 'status-active' : 'status-unused';
                    html += `<tr>
                        <td style="font-family:monospace;font-size:12px;">${lic.key.substring(0,20)}...</td>
                        <td>${lic.type}</td>
                        <td>${lic.credits}</td>
                        <td class="${statusClass}">${lic.status}</td>
                        <td>${lic.activated_at || '-'}</td>
                    </tr>`;
                });
                html += '</table>';
                
                document.getElementById('licenses_list').innerHTML = html;
            }
            
            // Cargar licencias al inicio
            loadLicenses();
        </script>
    </body>
    </html>
    '''

@app.route('/admin/generate', methods=['POST'])
def admin_generate():
    """Generar licencia desde panel admin"""
    data = request.json
    key_type = data.get('type', 'FULL')
    credits = data.get('credits', 500)
    drive_folder = data.get('drive_folder')
    
    key = create_license(key_type, credits, drive_folder)
    
    if key:
        return jsonify({'success': True, 'key': key, 'type': key_type, 'credits': credits})
    else:
        return jsonify({'success': False, 'error': 'Error generando licencia'}), 500

@app.route('/admin/licenses', methods=['GET'])
def admin_licenses():
    """Listar todas las licencias"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM licenses ORDER BY created_at DESC LIMIT 50')
    licenses = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(licenses)

# ==================== INICIALIZACIÓN ====================

if __name__ == '__main__':
    print("🚀 Iniciando Servidor de Licencias - Bloom Translator")
    print("=" * 60)
    
    # Inicializar BD
    init_db()
    print("✅ Base de datos inicializada")
    
    # Guardar config por defecto
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(CONFIG, f, indent=2)
        print("✅ Archivo de configuración creado")
    
    print("\n🌐 Servidor corriendo en: http://localhost:7777")
    print("🔐 Panel Admin: http://localhost:7777/admin")
    print("=" * 60)
    print("\n💡 Presiona Ctrl+C para detener el servidor\n")
    
    app.run(host='127.0.0.1', port=7777, debug=False)