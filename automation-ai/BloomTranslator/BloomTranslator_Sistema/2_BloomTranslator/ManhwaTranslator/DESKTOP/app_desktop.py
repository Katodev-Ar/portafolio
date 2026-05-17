"""
MANHWA TRANSLATOR - Desktop v4.0
Flask backend | Staff & User roles | Photoshop-compatible JSON
"""
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os, sys, json, base64, re, zipfile, pickle, threading, time
from datetime import datetime
from io import BytesIO
from PIL import Image
Image.MAX_IMAGE_PIXELS = None  # Permitir imágenes grandes (35000px+)
import cv2, numpy as np, requests

def resource_path(p):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, p)
    return os.path.join(os.path.abspath('.'), p)

app = Flask(__name__,
            template_folder=resource_path('templates'),
            static_folder=resource_path('static'))
CORS(app)

SERVER_URL    = "https://bloom-translator-server.onrender.com"
CONFIG_FILE   = "manhwa_config.json"
TAGS_FILE     = "tag_sets.json"
GLOSSARY_FILE = "glossary.txt"

state = {
    'license_key'   : None,
    'license_type'  : None,   # 'FULL' | 'STAFF' | 'USER'
    'credits'       : 0,
    'images'        : [],
    'current_index' : 0,
    'all_selections': {},     # {str(idx): [{id,x,y,w,h,text,translated}]}
    'ocr_blocks'    : [],     # [{id,img_index,img_name,text}]
    'tr_blocks'     : [],     # [{id,text}]
    'glossary'      : '',
    'tag_sets'      : [],
    'drive_service' : None,
    'current_series': None,
    'current_chapter': None,
    'series_data'   : {},
    'ocr_progress'  : {'step': 0, 'total': 0, 'msg': '', 'done': False},
}

# ── helpers ──────────────────────────────────────────────────
def natural_sort(path):
    s = os.path.basename(path)
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', s)]

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                c = json.load(f)
                state['license_key'] = c.get('license_key')
        except: pass

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'license_key': state['license_key']}, f)

def load_tag_sets():
    if os.path.exists(TAGS_FILE):
        try:
            with open(TAGS_FILE, encoding='utf-8') as f:
                state['tag_sets'] = json.load(f)
        except: pass

def save_tag_sets():
    with open(TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(state['tag_sets'], f, ensure_ascii=False, indent=2)

def load_glossary():
    if os.path.exists(GLOSSARY_FILE):
        try:
            with open(GLOSSARY_FILE, encoding='utf-8') as f:
                state['glossary'] = f.read()
        except: pass

def img_b64(path, thumb=False):
    try:
        im = Image.open(path)
        # Convertir modos especiales a RGB/RGBA para compatibilidad
        if im.mode not in ('RGB', 'RGBA', 'L'):
            im = im.convert('RGB')
        if thumb:
            im.thumbnail((80, 120), Image.LANCZOS)
        buf = BytesIO()
        fmt = 'PNG' if im.mode == 'RGBA' else 'JPEG'
        im.save(buf, format=fmt, quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f'img_b64 error {path}: {e}')
        return None

def file_dialog():
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk(); r.withdraw(); r.wm_attributes('-topmost', 1)
        files = filedialog.askopenfilenames(
            title='Seleccionar imágenes',
            filetypes=[('Imágenes', '*.png *.jpg *.jpeg *.webp *.bmp')])
        r.destroy()
        return list(files)
    except: return []

def save_dialog(name, ext):
    try:
        import tkinter as tk
        from tkinter import filedialog
        r = tk.Tk(); r.withdraw(); r.wm_attributes('-topmost', 1)
        f = filedialog.asksaveasfilename(defaultextension=ext, initialfile=name,
            filetypes=[(ext.upper().strip('.'), f'*{ext}'), ('Todos', '*.*')])
        r.destroy()
        return f
    except: return ''

load_config(); load_tag_sets(); load_glossary()

# ── routes ────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('translator.html')

@app.route('/api/state')
def get_state():
    return jsonify({
        'license_key'   : state['license_key'],
        'license_type'  : state['license_type'],
        'credits'       : state['credits'],
        'image_count'   : len(state['images']),
        'current_index' : state['current_index'],
        'image_names'   : [os.path.basename(p) for p in state['images']],
        'ocr_blocks'    : state['ocr_blocks'],
        'tr_blocks'     : state['tr_blocks'],
        'glossary'      : state['glossary'],
        'tag_sets'      : state['tag_sets'],
        'current_series': state['current_series'],
        'current_chapter': state['current_chapter'],
        'has_drive'     : state['drive_service'] is not None,
        'sel_counts'    : {k: len(v) for k, v in state['all_selections'].items()},
        'is_staff'      : state['license_type'] in ('STAFF', 'FULL'),
    })

# ── LICENSE ───────────────────────────────────────────────────
@app.route('/api/license/verify', methods=['POST'])
def verify_license():
    key = request.json.get('key', '').strip().upper()
    if not key: return jsonify({'success': False, 'error': 'Ingresa una clave'})
    try:
        r = requests.post(f"{SERVER_URL}/api/validate", json={'key': key}, timeout=20)
        if r.status_code == 200:
            d = r.json()
            if d.get('success'):
                state['license_key']  = key
                state['license_type'] = d.get('type', 'USER')
                state['credits']      = d.get('credits', 0)
                save_config()
                return jsonify({'success': True, 'type': state['license_type'],
                                'credits': state['credits'], 'message': d.get('message', '')})
            return jsonify({'success': False, 'error': d.get('error', 'Licencia inválida')})
        return jsonify({'success': False, 'error': f'Error servidor ({r.status_code})'})
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'El servidor está iniciando, intenta en 30 segundos'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/license/reload', methods=['POST'])
def reload_license():
    reload_key = request.json.get('reload_key', '').strip().upper()
    if not state['license_key']:
        return jsonify({'success': False, 'error': 'No hay licencia activa'})
    try:
        r = requests.post(f"{SERVER_URL}/api/reload",
                          json={'main_key': state['license_key'], 'reload_key': reload_key}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            if d.get('success'):
                state['credits'] = d.get('credits', state['credits'])
                return jsonify({'success': True, 'credits': state['credits'], 'message': d.get('message', '')})
            return jsonify({'success': False, 'error': d.get('error')})
        return jsonify({'success': False, 'error': f'Error {r.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/license/logout', methods=['POST'])
def logout():
    state['license_key']  = None
    state['license_type'] = None
    state['credits']      = 0
    state['images']       = []
    state['all_selections'] = {}
    state['drive_service']  = None
    save_config()
    return jsonify({'success': True})

# ── IMAGES ────────────────────────────────────────────────────
@app.route('/api/images/load', methods=['POST'])
def load_images():
    # Staff cannot load local images
    if state['license_type'] in ('STAFF',):
        return jsonify({'success': False, 'error': 'Staff solo puede cargar imágenes desde Drive'})
    files = file_dialog()
    if not files: return jsonify({'success': False, 'error': 'No se seleccionaron archivos'})
    files = sorted(files, key=natural_sort)
    _reset_images(files)
    return jsonify({'success': True, 'count': len(files),
                    'image_names': [os.path.basename(p) for p in files]})

def _reset_images(files):
    state['images']             = files
    state['current_index']      = 0
    state['all_selections']     = {}
    state['ocr_blocks']         = []
    state['tr_blocks']          = []

@app.route('/api/images/get/<int:index>')
def get_image(index):
    if index < 0 or index >= len(state['images']):
        return jsonify({'success': False, 'error': 'Índice inválido'})
    path = state['images'][index]
    try:
        im = Image.open(path)
        if im.mode not in ('RGB', 'RGBA', 'L'):
            im = im.convert('RGB')
        orig_w, orig_h = im.width, im.height

        # Para imágenes muy grandes (>8000px alto), escalar para transferencia
        # Las coordenadas siempre se guardan en espacio ORIGINAL
        MAX_TRANSFER_H = 8000
        display_w, display_h = orig_w, orig_h
        if orig_h > MAX_TRANSFER_H:
            scale = MAX_TRANSFER_H / orig_h
            display_w = int(orig_w * scale)
            display_h = MAX_TRANSFER_H
            im = im.resize((display_w, display_h), Image.LANCZOS)

        buf = BytesIO()
        fmt = 'PNG' if im.mode == 'RGBA' else 'JPEG'
        im.save(buf, format=fmt, quality=88)
        b64 = base64.b64encode(buf.getvalue()).decode()
        mime = f'image/{fmt.lower()}'
        return jsonify({'success': True,
                        'data': f'data:{mime};base64,{b64}',
                        'filename': os.path.basename(path),
                        'width': display_w, 'height': display_h,
                        'orig_width': orig_w, 'orig_height': orig_h,
                        'scale': display_w / orig_w})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/images/navigate', methods=['POST'])
def navigate_image():
    idx = request.json.get('index', 0)
    if 0 <= idx < len(state['images']):
        state['current_index'] = idx
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Índice inválido'})

@app.route('/api/images/clear', methods=['POST'])
def clear_images():
    _reset_images([])
    state['current_series']  = None
    state['current_chapter'] = None
    return jsonify({'success': True})

# ── SELECTIONS ────────────────────────────────────────────────
@app.route('/api/selections/get/<int:index>')
def get_sels(index):
    return jsonify({'success': True, 'selections': state['all_selections'].get(str(index), [])})

@app.route('/api/selections/update', methods=['POST'])
def update_sels():
    data = request.json
    state['all_selections'][str(data.get('index', state['current_index']))] = data.get('selections', [])
    return jsonify({'success': True})

@app.route('/api/selections/clear_all', methods=['POST'])
def clear_all_sels():
    state['all_selections'] = {}
    state['ocr_blocks']     = []
    state['tr_blocks']      = []
    return jsonify({'success': True})

# ── OCR ───────────────────────────────────────────────────────
@app.route('/api/ocr/progress')
def ocr_progress():
    return jsonify(state['ocr_progress'])

@app.route('/api/ocr/run', methods=['POST'])
def run_ocr():
    if not state['license_key']:
        return jsonify({'success': False, 'error': 'Configura tu licencia primero'})
    data     = request.json
    language = data.get('language', 'Korean')
    # Save current selections
    curr_sels = data.get('current_selections', [])
    if curr_sels:
        state['all_selections'][str(state['current_index'])] = curr_sels

    imgs_with_sels = [(k, v) for k, v in sorted(state['all_selections'].items(), key=lambda x: int(x[0])) if v]
    if not imgs_with_sels:
        return jsonify({'success': False, 'error': 'No hay áreas seleccionadas'})

    credits_needed = len(imgs_with_sels)
    if state['credits'] < credits_needed:
        return jsonify({'success': False,
                        'error': f'Créditos insuficientes. Necesitas {credits_needed}, tienes {state["credits"]}'})

    state['ocr_progress'] = {'step': 0, 'total': credits_needed, 'msg': 'Iniciando OCR…', 'done': False}

    blocks = []; errors = []; numero = 1

    for img_idx_str, sels in imgs_with_sels:
        img_idx = int(img_idx_str)
        if img_idx >= len(state['images']): continue
        img_path = state['images'][img_idx]
        img_name = os.path.basename(img_path)
        state['ocr_progress']['msg'] = f'Procesando {img_name}…'
        im = Image.open(img_path)
        if im.mode not in ('RGB', 'RGBA', 'L'): im = im.convert('RGB')

        for sel in sels:
            x, y, w, h = int(sel['x']), int(sel['y']), int(sel['w']), int(sel['h'])
            if w < 5 or h < 5: continue
            crop = im.crop((x, y, x+w, y+h))
            if crop.mode not in ('RGB','RGBA'): crop = crop.convert('RGB')
            buf  = BytesIO(); crop.save(buf, format='JPEG', quality=90)
            b64  = base64.b64encode(buf.getvalue()).decode()
            try:
                r = requests.post(f"{SERVER_URL}/api/ocr/process",
                                  json={'key': state['license_key'], 'image_data': b64, 'language': language},
                                  timeout=30)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('success'):
                        text = d.get('text', '').strip()
                        state['credits'] = d.get('credits_remaining', state['credits'])
                        sel['text'] = text
                        blocks.append({'id': numero, 'img_index': img_idx,
                                       'img_name': img_name, 'text': text})
                        numero += 1
                    else: errors.append(d.get('error', 'Error OCR'))
                else: errors.append(f'Error {r.status_code}')
            except Exception as e: errors.append(str(e))

        state['all_selections'][img_idx_str] = sels
        state['ocr_progress']['step'] += 1
        state['ocr_progress']['msg'] = f'✅ {img_name} listo ({state["ocr_progress"]["step"]}/{credits_needed})'

    state['ocr_blocks'] = blocks
    state['ocr_progress']['done'] = True

    if errors and not blocks:
        return jsonify({'success': False, 'error': '\n'.join(errors[:3])})
    return jsonify({'success': True, 'blocks': blocks,
                    'credits_remaining': state['credits'], 'errors': errors[:3]})

@app.route('/api/ocr/auto', methods=['POST'])
def auto_ocr():
    if not state['license_key']:
        return jsonify({'success': False, 'error': 'Configura tu licencia'})
    if not state['images']:
        return jsonify({'success': False, 'error': 'No hay imagen'})
    if state['credits'] < 1:
        return jsonify({'success': False, 'error': 'Créditos insuficientes'})
    language = request.json.get('language', 'Korean')
    idx = state['current_index']
    im  = Image.open(state['images'][idx])
    if im.mode not in ('RGB','RGBA','L'): im = im.convert('RGB')
    buf = BytesIO(); im.save(buf, format='JPEG', quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    try:
        r = requests.post(f"{SERVER_URL}/api/ocr/auto",
                          json={'key': state['license_key'], 'image_data': b64, 'language': language},
                          timeout=60)
        if r.status_code == 200:
            d = r.json()
            if d.get('success'):
                boxes = d.get('boxes', [])
                iw, ih = im.width, im.height
                state['credits'] = d.get('credits_remaining', state['credits'])
                sels = [{'id': i+1,
                         'x': int((b['x']/1000)*iw), 'y': int((b['y']/1000)*ih),
                         'w': int((b['w']/1000)*iw), 'h': int((b['h']/1000)*ih),
                         'text': b.get('text',''), 'translated': ''}
                        for i, b in enumerate(boxes)]
                state['all_selections'][str(idx)] = sels
                return jsonify({'success': True, 'selections': sels,
                                'credits_remaining': state['credits'], 'count': len(sels)})
            return jsonify({'success': False, 'error': d.get('error')})
        return jsonify({'success': False, 'error': f'Error {r.status_code}'})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ocr/blocks/update', methods=['POST'])
def update_ocr_blocks():
    state['ocr_blocks'] = request.json.get('blocks', [])
    return jsonify({'success': True})

# ── TRANSLATE ─────────────────────────────────────────────────
@app.route('/api/translate', methods=['POST'])
def translate():
    if not state['license_key']:
        return jsonify({'success': False, 'error': 'Configura tu licencia'})
    data        = request.json
    blocks      = data.get('blocks', state['ocr_blocks'])
    target_lang = data.get('target_lang', 'Español latino')
    glossary    = data.get('glossary', state['glossary'])
    if not blocks:
        return jsonify({'success': False, 'error': 'Genera el OCR primero'})

    parts = []
    cur_img = None
    for b in blocks:
        if b['img_name'] != cur_img:
            cur_img = b['img_name']
            parts.append(f"\n=== {cur_img} ===")
        parts.append(f"{b['id']}. {b['text']}")
    full_text = '\n'.join(parts).strip()
    char_count = len(full_text)
    # 1 crédito cada 600 caracteres
    credits_needed = max(1, (char_count + 599) // 600)

    if state['credits'] < credits_needed:
        return jsonify({'success': False,
                        'error': f'Créditos insuficientes. Necesitas {credits_needed} ({char_count} chars), tienes {state["credits"]}'})
    try:
        r = requests.post(f"{SERVER_URL}/api/translate/process",
                          json={'key': state['license_key'], 'text': full_text,
                                'target_lang': target_lang, 'glossary': glossary},
                          timeout=90)
        if r.status_code == 200:
            d = r.json()
            if d.get('success'):
                state['credits'] = d.get('credits_remaining', max(0, state['credits'] - credits_needed))
                raw  = d.get('translation', '')
                tbs  = []
                for line in raw.split('\n'):
                    m = re.match(r'^(\d+)\.\s*(.*)', line.strip())
                    if m: tbs.append({'id': int(m.group(1)), 'text': m.group(2)})
                state['tr_blocks'] = tbs
                return jsonify({'success': True, 'tr_blocks': tbs, 'raw': raw,
                                'credits_spent': credits_needed,
                                'credits_remaining': state['credits']})
            return jsonify({'success': False, 'error': d.get('error')})
        return jsonify({'success': False, 'error': f'Error {r.status_code}'})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/tr/blocks/update', methods=['POST'])
def update_tr():
    state['tr_blocks'] = request.json.get('blocks', [])
    return jsonify({'success': True})

@app.route('/api/glossary/save', methods=['POST'])
def save_glossary():
    t = request.json.get('text', '')
    state['glossary'] = t
    with open(GLOSSARY_FILE, 'w', encoding='utf-8') as f: f.write(t)
    return jsonify({'success': True})

# ── TAGS ──────────────────────────────────────────────────────
@app.route('/api/tags')
def get_tags():
    return jsonify({'success': True, 'tag_sets': state['tag_sets']})

@app.route('/api/tags/add', methods=['POST'])
def add_tag():
    # Only USER license can create tag sets
    if state['license_type'] in ('STAFF',):
        return jsonify({'success': False, 'error': 'Solo usuarios pueden crear conjuntos'})
    ts = request.json.get('tag_set')
    if not ts or not ts.get('name') or not ts.get('tags'):
        return jsonify({'success': False, 'error': 'Datos inválidos'})
    if len(ts['tags']) > 10:
        return jsonify({'success': False, 'error': 'Máximo 10 etiquetas por conjunto'})
    if state['credits'] < 1:
        return jsonify({'success': False, 'error': 'Necesitas 1 crédito para crear un conjunto'})
    try:
        r = requests.post(f"{SERVER_URL}/api/spend", json={'key': state['license_key'], 'amount': 1}, timeout=10)
        if r.status_code == 200:
            state['credits'] = r.json().get('credits', state['credits'] - 1)
        else: state['credits'] = max(0, state['credits'] - 1)
    except: state['credits'] = max(0, state['credits'] - 1)
    state['tag_sets'].append(ts); save_tag_sets()
    return jsonify({'success': True, 'credits': state['credits']})

@app.route('/api/tags/delete', methods=['POST'])
def del_tag():
    name = request.json.get('name')
    state['tag_sets'] = [t for t in state['tag_sets'] if t['name'] != name]
    save_tag_sets()
    return jsonify({'success': True})

# ── EXPORT ────────────────────────────────────────────────────
@app.route('/api/export/txt', methods=['POST'])
def exp_txt():
    if not state['images']: return jsonify({'success': False, 'error': 'No hay trabajo'})
    fname = save_dialog('capitulo.txt', '.txt')
    if not fname: return jsonify({'success': False, 'error': 'Cancelado'})
    ocr_t  = '\n'.join(f"{b['id']}. {b['text']}" for b in state['ocr_blocks'])
    tr_t   = '\n'.join(f"{b['id']}. {b['text']}" for b in state['tr_blocks'])
    with open(fname, 'w', encoding='utf-8') as f:
        f.write('=' * 70 + '\nMANHWA TRANSLATOR - EXPORTACIÓN\n')
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n" + '=' * 70 + '\n\n')
        f.write('── TRANSCRIPCIÓN ──\n\n' + (ocr_t or '(vacío)'))
        f.write('\n\n── TRADUCCIÓN ──\n\n' + (tr_t or '(vacío)'))
        if state['glossary'].strip():
            f.write('\n\n── GLOSARIO ──\n\n' + state['glossary'])
    return jsonify({'success': True, 'filename': os.path.basename(fname)})

@app.route('/api/export/json', methods=['POST'])
def exp_json():
    """Export in format compatible with Photoshop TypeSetter script:
    [{filename, boxes:[{x,y,w,h,t_text,final_translation}]}]
    """
    if not state['images']: return jsonify({'success': False, 'error': 'No hay imágenes'})
    if state['credits'] < 1: return jsonify({'success': False, 'error': 'Necesitas 1 crédito'})
    fname = save_dialog(f"coordenadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", '.json')
    if not fname: return jsonify({'success': False, 'error': 'Cancelado'})

    # Build translation lookup by global id
    tr_map = {b['id']: b['text'] for b in state['tr_blocks']}
    ocr_map= {b['id']: b['text'] for b in state['ocr_blocks']}

    # Map global_id → img_index for ordering
    id_to_img = {b['id']: b['img_index'] for b in state['ocr_blocks']}

    # Group ocr blocks by image
    by_img = {}
    for b in state['ocr_blocks']:
        by_img.setdefault(b['img_index'], []).append(b)

    pages = []
    for img_idx in sorted(by_img.keys()):
        blocks = sorted(by_img[img_idx], key=lambda x: x['id'])
        img_name = os.path.basename(state['images'][img_idx])
        sels = {s['id']: s for s in state['all_selections'].get(str(img_idx), [])}
        boxes = []
        for b in blocks:
            sel = sels.get(b['id'], {})
            tr_text = tr_map.get(b['id'], '')
            # Strip tag prefix from translation
            for ts in state['tag_sets']:
                for t in ts['tags']:
                    if tr_text.startswith(t['label'] + ' '):
                        tr_text = tr_text[len(t['label'])+1:].strip(); break
            boxes.append({
                'x': sel.get('x', 0), 'y': sel.get('y', 0),
                'w': sel.get('w', 0), 'h': sel.get('h', 0),
                't_text': tr_text,
                'final_translation': tr_text,
                'transcription': ocr_map.get(b['id'], ''),
            })
        pages.append({'filename': img_name, 'boxes': boxes})

    with open(fname, 'w', encoding='utf-8') as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)

    try:
        requests.post(f"{SERVER_URL}/api/spend", json={'key': state['license_key'], 'amount': 1}, timeout=5)
        state['credits'] = max(0, state['credits'] - 1)
    except: state['credits'] = max(0, state['credits'] - 1)

    return jsonify({'success': True, 'filename': os.path.basename(fname),
                    'credits': state['credits']})

@app.route('/api/export/clean', methods=['POST'])
def exp_clean():
    if state['license_type'] in ('STAFF',):
        return jsonify({'success': False, 'error': 'Staff no puede usar la función Clean'})
    curr = request.json.get('current_selections', [])
    if curr: state['all_selections'][str(state['current_index'])] = curr
    imgs = [(k, v) for k, v in state['all_selections'].items() if v]
    if not imgs: return jsonify({'success': False, 'error': 'No hay selecciones'})
    cost = len(imgs) * 2  # 2 créditos por imagen
    if state['credits'] < cost:
        return jsonify({'success': False, 'error': f'Necesitas {cost} créditos ({len(imgs)} img × 2)'})
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    zname = f"cleaned_{ts}.zip"
    try:
        cleaned = []
        for k, sels in imgs:
            idx = int(k)
            if idx >= len(state['images']): continue
            img_cv = cv2.imread(state['images'][idx])
            mask   = np.zeros(img_cv.shape[:2], dtype=np.uint8)
            for s in sels:
                x,y,w,h = int(s['x']),int(s['y']),int(s['w']),int(s['h'])
                cv2.rectangle(mask, (x,y), (x+w,y+h), 255, -1)
            out  = cv2.inpaint(img_cv, mask, 3, cv2.INPAINT_TELEA)
            fn   = f"cleaned_{os.path.basename(state['images'][idx])}"
            os.makedirs('temp', exist_ok=True)
            tmp  = os.path.join('temp', fn)
            cv2.imwrite(tmp, out); cleaned.append((fn, tmp))
        with zipfile.ZipFile(zname, 'w') as zf:
            for fn, fp in cleaned: zf.write(fp, fn)
        for _, fp in cleaned:
            try: os.remove(fp)
            except: pass
        try:
            requests.post(f"{SERVER_URL}/api/spend", json={'key': state['license_key'], 'amount': cost}, timeout=5)
            state['credits'] = max(0, state['credits'] - cost)
        except: state['credits'] = max(0, state['credits'] - cost)
        return jsonify({'success': True, 'filename': zname, 'count': len(cleaned), 'credits': state['credits']})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

# ── DRIVE ─────────────────────────────────────────────────────
@app.route('/api/drive/disconnect', methods=['POST'])
def drive_disconnect():
    state['drive_service'] = None
    # Borrar token para que pida login de nuevo
    if os.path.exists('token.pickle'):
        try: os.remove('token.pickle')
        except: pass
    return jsonify({'success': True})

@app.route('/api/drive/auth', methods=['POST'])
def drive_auth():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds  = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as f: creds = pickle.load(f)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    return jsonify({'success': False, 'error': 'credentials.json no encontrado'})
                flow  = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as f: pickle.dump(creds, f)
        state['drive_service'] = build('drive', 'v3', credentials=creds)
        return jsonify({'success': True})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/drive/series')
def drive_series():
    if not state['license_key']:
        return jsonify({'success': False, 'error': 'Sin licencia'})
    try:
        r = requests.post(f"{SERVER_URL}/api/series/list",
                          json={'key': state['license_key']}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            state['series_data'] = {s['name']: s for s in d.get('series', [])}
            return jsonify({'success': True, 'series': d.get('series', [])})
        return jsonify({'success': False, 'error': f'Error {r.status_code}'})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/drive/chapters', methods=['POST'])
def drive_chapters():
    if not state['drive_service']:
        return jsonify({'success': False, 'error': 'Drive no conectado'})
    series_name = request.json.get('series_name')
    serie = state['series_data'].get(series_name)
    if not serie: return jsonify({'success': False, 'error': 'Serie no encontrada'})
    link = serie.get('drive_link', '')
    if 'folders/' not in link: return jsonify({'success': False, 'error': 'Link inválido'})
    folder_id = link.split('folders/')[-1].split('?')[0]
    try:
        svc = state['drive_service']
        r1  = svc.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="files(id,name)").execute()
        raw_folder = None
        for f in r1.get('files', []):
            if 'raw' in f['name'].lower():
                raw_folder = f; break
        if not raw_folder: return jsonify({'success': False, 'error': 'No se encontró carpeta RAW'})
        r2 = svc.files().list(
            q=f"'{raw_folder['id']}' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="files(id,name)").execute()
        chapters = sorted([c for c in r2.get('files', [])],
                          key=lambda x: int(x['name']) if x['name'].isdigit() else 9999)
        return jsonify({'success': True,
                        'chapters': [c['name'] for c in chapters],
                        'chapter_ids': {c['name']: c['id'] for c in chapters}})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/drive/load', methods=['POST'])
def drive_load():
    from googleapiclient.http import MediaIoBaseDownload
    data = request.json
    series_name = data.get('series_name'); chapter = data.get('chapter')
    chapter_id  = data.get('chapter_id')
    if not chapter_id or not state['drive_service']:
        return jsonify({'success': False, 'error': 'Datos incompletos'})
    try:
        svc = state['drive_service']
        r   = svc.files().list(
            q=f"'{chapter_id}' in parents and mimeType contains 'image/'",
            fields="files(id,name)", orderBy="name").execute()
        files = r.get('files', [])
        if not files: return jsonify({'success': False, 'error': 'No hay imágenes'})
        tmp_dir = os.path.join('temp_drive', series_name or 'serie', chapter or '0')
        os.makedirs(tmp_dir, exist_ok=True)
        paths = []
        for f in files:
            fp  = os.path.join(tmp_dir, f['name'])
            req = svc.files().get_media(fileId=f['id'])
            fh  = open(fp, 'wb')
            dl  = MediaIoBaseDownload(fh, req)
            done = False
            while not done: _, done = dl.next_chunk()
            fh.close(); paths.append(fp)
        paths.sort(key=natural_sort)
        _reset_images(paths)
        state['current_series']  = series_name
        state['current_chapter'] = chapter
        return jsonify({'success': True, 'count': len(paths),
                        'image_names': [os.path.basename(p) for p in paths]})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/drive/save', methods=['POST'])
def drive_save():
    from googleapiclient.http import MediaFileUpload
    if not state['drive_service'] or not state['current_series']:
        return jsonify({'success': False, 'error': 'Drive no conectado o sin proyecto'})
    save_what = request.json.get('save_what', 'both')
    serie = state['series_data'].get(state['current_series'], {})
    link  = serie.get('drive_link', '')
    if 'folders/' not in link: return jsonify({'success': False, 'error': 'Link inválido'})
    folder_id = link.split('folders/')[-1].split('?')[0]
    try:
        svc = state['drive_service']
        r   = svc.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'",
            fields="files(id,name)").execute()
        tr_folder = None
        for f in r.get('files', []):
            if 'traduccion' in f['name'].lower() or 'traducción' in f['name'].lower():
                tr_folder = f; break
        if not tr_folder: return jsonify({'success': False, 'error': 'No se encontró carpeta TRADUCCION'})
        cap = state['current_chapter']; saved = []
        os.makedirs('temp', exist_ok=True)
        for what, fn, content in [
            ('translation', f'Traduccion_{cap}.txt', '\n'.join(f"{b['id']}. {b['text']}" for b in state['tr_blocks'])),
            ('ocr', f'Transcripcion_{cap}.txt', '\n'.join(f"{b['id']}. {b['text']}" for b in state['ocr_blocks'])),
        ]:
            if save_what in (what, 'both') and content.strip():
                tmp = os.path.join('temp', fn)
                with open(tmp, 'w', encoding='utf-8') as f: f.write(content)
                svc.files().create(body={'name': fn, 'parents': [tr_folder['id']]},
                                   media_body=MediaFileUpload(tmp, mimetype='text/plain'),
                                   fields='id').execute()
                os.remove(tmp); saved.append(fn)
        return jsonify({'success': True, 'saved': saved})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

# ── CLEAN CON CALIDAD MEJORADA (waifu2x) ─────────────────────
@app.route('/api/export/clean_hq', methods=['POST'])
def exp_clean_hq():
    """Clean + upscale con waifu2x (aparece como 'Mejorar calidad' en UI)"""
    if state['license_type'] in ('STAFF',):
        return jsonify({'success': False, 'error': 'Staff no puede usar Clean'})

    curr = request.json.get('current_selections', [])
    if curr:
        state['all_selections'][str(state['current_index'])] = curr

    imgs = [(k, v) for k, v in state['all_selections'].items() if v]
    if not imgs:
        return jsonify({'success': False, 'error': 'No hay selecciones'})

    # Calidad normal = 2 créditos/imagen, mejorada = 2 créditos/imagen + 1 crédito total upscale
    cost_clean  = len(imgs) * 2
    cost_upscale = 1  # 1 crédito por todo el zip mejorado
    total_cost   = cost_clean + cost_upscale

    if state['credits'] < total_cost:
        return jsonify({'success': False,
                        'error': f'Necesitas {total_cost} créditos ({len(imgs)} imgs × 2 + 1 upscale), tienes {state["credits"]}'})

    upscaler = resource_path('upscaler.exe')
    if not os.path.exists(upscaler):
        return jsonify({'success': False, 'error': 'Módulo de calidad no encontrado. Contacta soporte.'})

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    zname = f"cleaned_hq_{ts}.zip"
    tmp_dir = os.path.join('temp', f'clean_{ts}')
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        cleaned = []
        for k, sels in imgs:
            idx = int(k)
            if idx >= len(state['images']): continue
            img_cv = cv2.imread(state['images'][idx])
            mask   = np.zeros(img_cv.shape[:2], dtype=np.uint8)
            for s in sels:
                x,y,w,h = int(s['x']),int(s['y']),int(s['w']),int(s['h'])
                cv2.rectangle(mask, (x,y),(x+w,y+h), 255, -1)
            cleaned_cv = cv2.inpaint(img_cv, mask, 3, cv2.INPAINT_TELEA)
            fn  = os.path.basename(state['images'][idx])
            tmp = os.path.join(tmp_dir, fn)
            cv2.imwrite(tmp, cleaned_cv)
            cleaned.append((fn, tmp))

        # Upscale con waifu2x
        out_dir = os.path.join(tmp_dir, 'upscaled')
        os.makedirs(out_dir, exist_ok=True)
        import subprocess
        for fn, fp in cleaned:
            out_fp = os.path.join(out_dir, fn)
            subprocess.run([
                upscaler,
                '-i', fp,
                '-o', out_fp,
                '-n', '1',   # noise level 1
                '-s', '2',   # scale 2x
                '-m', resource_path('models')
            ], capture_output=True, timeout=120)

        # Zip con los upscaled (si falló upscale, usar cleaned normal)
        with zipfile.ZipFile(zname, 'w') as zf:
            for fn, _ in cleaned:
                hq_fp = os.path.join(out_dir, fn)
                src   = hq_fp if os.path.exists(hq_fp) else os.path.join(tmp_dir, fn)
                zf.write(src, fn)

        # Cobrar créditos
        try:
            requests.post(f"{SERVER_URL}/api/spend",
                          json={'key': state['license_key'], 'amount': total_cost}, timeout=5)
            state['credits'] = max(0, state['credits'] - total_cost)
        except:
            state['credits'] = max(0, state['credits'] - total_cost)

        # Limpiar temp
        import shutil
        try: shutil.rmtree(tmp_dir)
        except: pass

        return jsonify({'success': True, 'filename': zname,
                        'count': len(cleaned), 'credits': state['credits']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ── MAIN ──────────────────────────────────────────────────────
def run_flask(port):
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    import socket
    s = socket.socket(); s.bind(('', 0))
    port = s.getsockname()[1]; s.close()
    print(f"🌸 Manhwa Translator → http://localhost:{port}")

    # Flask en hilo secundario
    t = threading.Thread(target=run_flask, args=(port,), daemon=True)
    t.start()
    time.sleep(1.5)

    # Webview en hilo principal (requerido por pywebview)
    try:
        import webview
        webview.create_window('🌸 Bloom Translator', f'http://localhost:{port}',
                              width=1680, height=960, resizable=True)
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open(f'http://localhost:{port}')
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            pass
