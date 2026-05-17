"""
MANHWA TRANSLATOR SERVER - COMPLETO
Sistema con Google Drive, Series y Etiquetas
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import os
import json
from datetime import datetime
import sqlite3
import hashlib
import secrets
from PIL import Image
import io
import base64

app = Flask(__name__)
CORS(app)

# Configuración
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)

DB_FILE = 'manhwa_translator.db'

# ==================== BASE DE DATOS ====================

def init_db():
    """Inicializar base de datos"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabla de licencias
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            credits INTEGER DEFAULT 0,
            created_at TEXT,
            is_staff BOOLEAN DEFAULT 0
        )
    ''')
    
    # Tabla de claves de recarga
    c.execute('''
        CREATE TABLE IF NOT EXISTS reload_keys (
            key TEXT PRIMARY KEY,
            credits INTEGER NOT NULL,
            used BOOLEAN DEFAULT 0,
            used_by TEXT,
            used_at TEXT
        )
    ''')
    
    # Tabla de series (para Bloom Staff)
    c.execute('''
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            drive_link TEXT NOT NULL,
            created_at TEXT,
            created_by TEXT
        )
    ''')
    
    # Tabla de uso
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT,
            action TEXT,
            credits_spent INTEGER,
            timestamp TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== UTILIDADES ====================

def log_usage(license_key, action, credits_spent):
    """Registrar uso"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO usage_log (license_key, action, credits_spent, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (license_key, action, credits_spent, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def validate_key(key):
    """Validar licencia"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT type, credits, is_staff FROM licenses WHERE key = ?', (key,))
    result = c.fetchone()
    conn.close()
    return result

def update_credits(key, credits):
    """Actualizar créditos"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE licenses SET credits = ? WHERE key = ?', (credits, key))
    conn.commit()
    conn.close()

# ==================== API ENDPOINTS ====================

@app.route('/api/validate', methods=['POST'])
def validate_license():
    """Validar licencia"""
    data = request.json
    key = data.get('key')
    
    if not key:
        return jsonify({'success': False, 'error': 'No se proporcionó clave'}), 400
    
    result = validate_key(key)
    if result:
        license_type, credits, is_staff = result
        return jsonify({
            'success': True,
            'type': license_type,
            'credits': credits,
            'is_staff': bool(is_staff)
        })
    else:
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 401

@app.route('/api/reload', methods=['POST'])
def reload_credits():
    """Recargar créditos"""
    data = request.json
    main_key = data.get('main_key')
    reload_key = data.get('reload_key')
    
    if not main_key or not reload_key:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    # Validar licencia principal
    license_result = validate_key(main_key)
    if not license_result:
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 401
    
    # Validar clave de recarga
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT credits, used FROM reload_keys WHERE key = ?', (reload_key,))
    reload_result = c.fetchone()
    
    if not reload_result:
        conn.close()
        return jsonify({'success': False, 'error': 'Clave de recarga inválida'}), 401
    
    credits_to_add, used = reload_result
    if used:
        conn.close()
        return jsonify({'success': False, 'error': 'Clave ya utilizada'}), 400
    
    # Actualizar créditos
    current_credits = license_result[1]
    new_credits = current_credits + credits_to_add
    
    c.execute('UPDATE licenses SET credits = ? WHERE key = ?', (new_credits, main_key))
    c.execute('UPDATE reload_keys SET used = 1, used_by = ?, used_at = ? WHERE key = ?',
             (main_key, datetime.now().isoformat(), reload_key))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'credits': new_credits,
        'message': f'Se agregaron {credits_to_add} créditos'
    })

@app.route('/api/ocr/process', methods=['POST'])
def process_ocr():
    """Procesar OCR de imagen"""
    data = request.json
    key = data.get('key')
    image_data = data.get('image_data')
    language = data.get('language', 'Korean')
    
    if not key or not image_data:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    # Validar licencia
    result = validate_key(key)
    if not result:
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 401
    
    license_type, credits, is_staff = result
    
    if credits < 1:
        return jsonify({'success': False, 'error': 'Créditos insuficientes'}), 402
    
    try:
        # Decodificar imagen
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        
        # Configurar modelo
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prompt según idioma
        lang_prompts = {
            'Korean': 'coreano',
            'Japanese': 'japonés',
            'Chinese': 'chino',
            'English': 'inglés',
            'Spanish': 'español',
            'Russian': 'ruso'
        }
        
        lang_name = lang_prompts.get(language, 'coreano')
        
        prompt = f"""Eres un experto en OCR para manhwas y mangas.

INSTRUCCIONES:
1. Extrae TODO el texto visible en {lang_name} de esta imagen
2. Transcribe el texto EXACTAMENTE como aparece
3. Respeta saltos de línea y espacios
4. Si hay múltiples bloques de texto, sepáralos con un salto de línea
5. NO traduzcas, solo transcribe
6. Si no hay texto, responde: "(Sin texto)"

Transcripción:"""

        response = model.generate_content([prompt, image])
        text = response.text.strip()
        
        # Descontar crédito
        new_credits = credits - 1
        update_credits(key, new_credits)
        log_usage(key, 'OCR', 1)
        
        return jsonify({
            'success': True,
            'text': text,
            'credits_remaining': new_credits
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ocr/auto', methods=['POST'])
def auto_ocr():
    """Auto detectar globos de texto"""
    data = request.json
    key = data.get('key')
    image_data = data.get('image_data')
    language = data.get('language', 'Korean')
    
    if not key or not image_data:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    # Validar licencia
    result = validate_key(key)
    if not result:
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 401
    
    license_type, credits, is_staff = result
    
    if credits < 1:
        return jsonify({'success': False, 'error': 'Créditos insuficientes'}), 402
    
    try:
        # Decodificar imagen
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        
        # Configurar modelo
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""Eres un experto en detectar globos de diálogo en manhwas/mangas.

TAREA: Detecta TODOS los globos de texto en esta imagen y proporciona sus coordenadas.

FORMATO DE RESPUESTA (JSON):
{{
  "boxes": [
    {{"x": 100, "y": 50, "w": 200, "h": 80, "text": ""}},
    {{"x": 350, "y": 120, "w": 180, "h": 60, "text": ""}}
  ]
}}

REGLAS:
- x, y = esquina superior izquierda (escala 0-1000)
- w, h = ancho y alto (escala 0-1000)
- Detecta TODOS los globos visibles
- Ordena de arriba a abajo, izquierda a derecha
- text siempre vacío por ahora

Responde SOLO con el JSON, sin explicaciones."""

        response = model.generate_content([prompt, image])
        result_text = response.text.strip()
        
        # Limpiar JSON
        if '```json' in result_text:
            result_text = result_text.split('```json')[1].split('```')[0].strip()
        elif '```' in result_text:
            result_text = result_text.split('```')[1].split('```')[0].strip()
        
        boxes_data = json.loads(result_text)
        
        # Descontar crédito
        new_credits = credits - 1
        update_credits(key, new_credits)
        log_usage(key, 'AUTO_OCR', 1)
        
        return jsonify({
            'success': True,
            'boxes': boxes_data.get('boxes', []),
            'credits_remaining': new_credits
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/translate/process', methods=['POST'])
def process_translation():
    """Procesar traducción"""
    data = request.json
    key = data.get('key')
    text = data.get('text')
    target_lang = data.get('target_lang', 'Español latino')
    glossary = data.get('glossary', '')
    
    if not key or not text:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    # Validar licencia
    result = validate_key(key)
    if not result:
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 401
    
    license_type, credits, is_staff = result
    
    # Calcular créditos necesarios
    credits_needed = max(1, len(text) // 100)
    
    if credits < credits_needed:
        return jsonify({'success': False, 'error': 'Créditos insuficientes'}), 402
    
    try:
        # Configurar modelo
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Construir prompt
        glossary_section = ""
        if glossary:
            glossary_section = f"\nGLOSARIO DE CONTEXTO:\n{glossary}\n\nUsa este glosario para mantener consistencia en nombres y términos."
        
        prompt = f"""Eres un traductor profesional de manhwas/mangas a {target_lang}.

TEXTO A TRADUCIR:
{text}
{glossary_section}

INSTRUCCIONES:
1. Traduce de manera natural y fluida
2. Mantén el tono y estilo original
3. Respeta la numeración (1., 2., etc.)
4. Mantén los encabezados de imagen (=== archivo.jpg ===)
5. Si hay nombres en el glosario, úsalos consistentemente
6. NO agregues explicaciones, solo la traducción

TRADUCCIÓN:"""

        response = model.generate_content(prompt)
        translation = response.text.strip()
        
        # Descontar créditos
        new_credits = credits - credits_needed
        update_credits(key, new_credits)
        log_usage(key, 'TRANSLATE', credits_needed)
        
        return jsonify({
            'success': True,
            'translation': translation,
            'credits_spent': credits_needed,
            'credits_remaining': new_credits
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== SERIES (BLOOM STAFF) ====================

@app.route('/api/series/list', methods=['POST'])
def list_series():
    """Listar series disponibles"""
    data = request.json
    key = data.get('key')
    
    if not key:
        return jsonify({'success': False, 'error': 'No se proporcionó clave'}), 400
    
    # Validar que sea staff
    result = validate_key(key)
    if not result:
        return jsonify({'success': False, 'error': 'Licencia inválida'}), 401
    
    license_type, credits, is_staff = result
    
    if not is_staff:
        return jsonify({'success': False, 'error': 'Solo para Bloom Staff'}), 403
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id, name, drive_link, created_at FROM series ORDER BY name')
        series = c.fetchall()
        conn.close()
        
        series_list = [
            {
                'id': s[0],
                'name': s[1],
                'drive_link': s[2],
                'created_at': s[3]
            }
            for s in series
        ]
        
        return jsonify({
            'success': True,
            'series': series_list
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/series/add', methods=['POST'])
def add_series():
    """Agregar nueva serie (solo admin)"""
    data = request.json
    admin_key = data.get('admin_key')
    name = data.get('name')
    drive_link = data.get('drive_link')
    
    if not admin_key or not name or not drive_link:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    # Aquí deberías validar que admin_key sea de un admin real
    # Por ahora simplificado
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO series (name, drive_link, created_at, created_by)
            VALUES (?, ?, ?, ?)
        ''', (name, drive_link, datetime.now().isoformat(), admin_key))
        conn.commit()
        series_id = c.lastrowid
        conn.close()
        
        return jsonify({
            'success': True,
            'series_id': series_id,
            'message': 'Serie agregada correctamente'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/series/delete', methods=['POST'])
def delete_series():
    """Eliminar serie (solo admin)"""
    data = request.json
    admin_key = data.get('admin_key')
    series_id = data.get('series_id')
    
    if not admin_key or not series_id:
        return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
    
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('DELETE FROM series WHERE id = ?', (series_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Serie eliminada correctamente'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'OK', 'timestamp': datetime.now().isoformat()})

# ==================== MAIN ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
