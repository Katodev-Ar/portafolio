# ==============================================================================
# ARCHIVO: cogs/naver_playwright.py
# VERSIÓN: V5.0 - ADMIN ONLY (SIN ECONOMÍA)
# ==============================================================================

import discord
from discord import app_commands, Embed, ui
from discord.ext import commands
import os
import asyncio
from playwright.async_api import async_playwright, Browser, Page
import aiohttp
import io
import re
import time
import traceback
import zipfile
import tempfile
import shutil
from PIL import Image, ImageFile
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import Counter
import gc

ImageFile.LOAD_TRUNCATED_IMAGES = True

# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR = 0xE74C3C
COLOR_PROGRESS = 0x9B59B6
COLOR_LYRA = 0x9B59B6

# Permisos
ADMIN_ROLE_ID = 1132158706851786854
ALLOWED_CHANNEL_ID = 1459937949389947010

# Google Drive
# Google Drive
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    from google.auth.transport.requests import Request
    DRIVE_ENABLED = True
    print("✅ [DRIVE] Todas las importaciones exitosas")
except Exception as e:
    print(f"❌ [DRIVE] Error en importaciones: {e}")
    print("⚠️ [DRIVE] Instala: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    DRIVE_ENABLED = False
    # Crear dummy para evitar errores
    class Request:
        pass

DRIVE_BASE_FOLDER_ID = os.getenv("DRIVE_PARENT_ID", "1rdx5RUq-9_XvslM0W8yX-d7e6oaWVM4g")
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive']

# Procesamiento
MIN_STRIP_HEIGHT = 5000
MAX_STRIP_HEIGHT = 20000

# Límite de concurrencia (3 extracciones simultáneas)
MAX_CONCURRENT_NAVER_EXTRACTIONS = 3
NAVER_EXTRACTION_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_NAVER_EXTRACTIONS)

# ==============================================================================
# ESTADO DE TAREA
# ==============================================================================

class TaskState:
    def __init__(self):
        self.status = "Iniciando..."
        self.total = 0
        self.current = 0
        self.start_time = time.time()
        self.running = True
        self.chapter = "Cargando..."
        self.series_name = ""
        self.thumb = ""
        self.total_chapters = 0
        self.current_chapter_idx = 0
        self.total_images = 0
        self.current_images = 0
    
    def update(self, status=None, cur=None, tot=None):
        if status is not None: self.status = status
        if cur is not None: self.current = cur
        if tot is not None: self.total = tot
    
    def progress_bar(self):
        if self.total == 0: return "`⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜` 0%"
        pct = min(100, int((self.current / self.total) * 100))
        filled = int(pct / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)
        return f"`{bar}` {pct}%"

def format_time(seconds):
    if seconds < 60: return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s"

def clean_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', str(name))
    return re.sub(r'[^\w\s-]', '-', name).strip('-')[:60]

def truncate(text, length=90):
    return text[:length-3] + "..." if len(text) > length else text

# ==============================================================================
# NAVEGADOR PLAYWRIGHT
# ==============================================================================

class NaverBrowser:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.is_ready = False
    
    async def start(self):
        try:
            print("🌐 [NAVER] Iniciando navegador Playwright...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            self.is_ready = True
            print("✅ [NAVER] Navegador listo")
        except Exception as e:
            print(f"❌ [NAVER] Error iniciando navegador: {e}")
            self.is_ready = False
    
    async def stop(self):
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.is_ready = False
            print("✅ [NAVER] Navegador cerrado")
        except Exception as e:
            print(f"⚠️ [NAVER] Error cerrando navegador: {e}")
    
    async def get_chapters(self, series_url: str) -> Tuple[List[Dict], Optional[str], str]:
        """Obtiene TODOS los capítulos usando botones de paginación"""
        if not self.is_ready:
            await self.start()
        
        context = None
        page = None
        
        try:
            print(f"\n{'='*80}")
            print(f"📚 [NAVER] Iniciando scraping de: {series_url}")
            print(f"{'='*80}")
            
            context = await self.browser.new_context(
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='ko-KR'
            )
            page = await context.new_page()
            
            # Navegar
            print("🔄 [NAVER] Navegando a la página...")
            await page.goto(series_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(1)
            print("✅ [NAVER] Página cargada")
            
            # Extraer título y thumbnail
            print("📝 [NAVER] Extrayendo metadatos...")
            title_thumb = await page.evaluate(r"""
                () => {
                    const titleMeta = document.querySelector('meta[property="og:title"]');
                    const thumbMeta = document.querySelector('meta[property="og:image"]');
                    return {
                        title: titleMeta ? titleMeta.content.split(' - ')[0].trim() : 'Webtoon',
                        thumbnail: thumbMeta ? thumbMeta.content : null
                    };
                }
            """)
            
            title = title_thumb['title']
            thumbnail = title_thumb['thumbnail']
            
            print(f"✅ [NAVER] Título: {title}")
            print(f"✅ [NAVER] Thumbnail: {'Sí' if thumbnail else 'No'}")
            
            # DETECTAR TOTAL DE PÁGINAS
            print("\n" + "="*80)
            print("🔍 [NAVER] DETECTANDO BOTONES DE PAGINACIÓN...")
            print("="*80)
            
            print("📜 [NAVER] Haciendo scroll para cargar paginación...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            
            print("🔍 [NAVER] Buscando botones con múltiples selectores...")
            
            pagination_info = await page.evaluate(r"""
                () => {
                    let pageButtons = [];
                    
                    pageButtons = Array.from(document.querySelectorAll('button[class*="Paginate_page"]'));
                    console.log('Selector 1 (button[class*="Paginate_page"]):', pageButtons.length, 'botones');
                    
                    if (pageButtons.length === 0) {
                        pageButtons = Array.from(document.querySelectorAll('div[class*="Paginate"] button, div[class*="paginate"] button'));
                        console.log('Selector 2 (div paginación):', pageButtons.length, 'botones');
                    }
                    
                    if (pageButtons.length === 0) {
                        pageButtons = Array.from(document.querySelectorAll('button')).filter(btn => {
                            const text = btn.textContent.trim();
                            return /^\d+$/.test(text);
                        });
                        console.log('Selector 3 (botones con números):', pageButtons.length, 'botones');
                    }
                    
                    const pageNumbers = pageButtons.map(btn => {
                        const text = btn.textContent.trim();
                        const num = parseInt(text);
                        return isNaN(num) ? null : num;
                    }).filter(n => n !== null);
                    
                    const currentButton = document.querySelector('button[aria-current="true"]') || 
                                        document.querySelector('button[class*="_current"]') ||
                                        pageButtons.find(btn => btn.getAttribute('aria-current') === 'true');
                    
                    const currentPage = currentButton ? parseInt(currentButton.textContent.trim()) : 1;
                    
                    const urlMatch = window.location.href.match(/page=(\d+)/);
                    const urlPage = urlMatch ? parseInt(urlMatch[1]) : 1;
                    
                    return {
                        pageNumbers: pageNumbers,
                        totalPages: pageNumbers.length > 0 ? Math.max(...pageNumbers) : 1,
                        currentPage: currentButton ? currentPage : urlPage,
                        foundButtons: pageButtons.length,
                        method: pageButtons.length > 0 ? 'buttons' : 'none'
                    };
                }
            """)
            
            total_pages = pagination_info['totalPages']
            current_page = pagination_info['currentPage']
            available_pages = pagination_info['pageNumbers']
            
            print(f"📊 [NAVER] Total de páginas detectadas: {total_pages}")
            print(f"📍 [NAVER] Página actual: {current_page}")
            print(f"📋 [NAVER] Botones visibles: {available_pages}")
            print(f"🔧 [NAVER] Botones encontrados: {pagination_info['foundButtons']}")
            print(f"🔧 [NAVER] Método: {pagination_info['method']}")
            
            if total_pages == 1 and pagination_info['foundButtons'] == 0:
                print("⚠️ [NAVER] No se encontraron botones, intentando método alternativo (URLs directas)...")
                
                episodes_count = await page.evaluate(r"""
                    () => {
                        const links = Array.from(document.querySelectorAll('a[href*="/webtoon/detail"]'));
                        return links.length;
                    }
                """)
                
                estimated_pages = max(1, (episodes_count // 15))
                print(f"📊 [NAVER] Episodios en página actual: {episodes_count}")
                print(f"📊 [NAVER] Páginas estimadas: {estimated_pages}")
                
                print("🔍 [NAVER] Verificando si existe página 2...")
                test_url = series_url.replace('page=1', 'page=2') if 'page=' in series_url else f"{series_url}&page=2"
                
                try:
                    await page.goto(test_url, timeout=10000)
                    await asyncio.sleep(1)
                    
                    page2_episodes = await page.evaluate(r"""
                        () => {
                            const links = Array.from(document.querySelectorAll('a[href*="/webtoon/detail"]'));
                            const firstNo = links.length > 0 ? links[0].href.match(/no=(\d+)/) : null;
                            return firstNo ? parseInt(firstNo[1]) : 0;
                        }
                    """)
                    
                    if page2_episodes > 0:
                        print(f"✅ [NAVER] Página 2 existe! Primer episodio: {page2_episodes}")
                        total_pages = estimated_pages
                    else:
                        print(f"⚠️ [NAVER] Página 2 no existe o es igual")
                    
                    await page.goto(series_url, timeout=10000)
                    await asyncio.sleep(1)
                    
                except:
                    print(f"⚠️ [NAVER] No se pudo verificar página 2")
            
            print(f"✅ [NAVER] Total de páginas final: {total_pages}")
            
            # PAGINACIÓN
            all_chapters = []
            seen_urls = set()
            
            for page_num in range(1, total_pages + 1):
                print(f"\n{'='*80}")
                print(f"📄 [NAVER] PROCESANDO PÁGINA {page_num}/{total_pages}")
                print(f"{'='*80}")
                
                if page_num > 1:
                    try:
                        if pagination_info['foundButtons'] > 0:
                            print(f"🖱️ [NAVER] Intentando clic en botón {page_num}...")
                            
                            button_clicked = await page.evaluate(f"""
                                (pageNum) => {{
                                    const buttons = Array.from(document.querySelectorAll('button'));
                                    const targetButton = buttons.find(btn => btn.textContent.trim() === String(pageNum));
                                    
                                    if (targetButton) {{
                                        targetButton.click();
                                        return true;
                                    }} else {{
                                        return false;
                                    }}
                                }}
                            """, page_num)
                            
                            if button_clicked:
                                print(f"✅ [NAVER] Clic en botón {page_num} exitoso")
                                await asyncio.sleep(1.5)
                            else:
                                raise Exception("Botón no encontrado")
                        else:
                            raise Exception("Sin botones disponibles")
                        
                    except Exception as e:
                        print(f"🔄 [NAVER] Usando navegación directa con URL (página {page_num})...")
                        
                        if 'page=' in series_url:
                            target_url = re.sub(r'page=\d+', f'page={page_num}', series_url)
                        else:
                            separator = '&' if '?' in series_url else '?'
                            target_url = f"{series_url}{separator}page={page_num}"
                        
                        print(f"🔗 [NAVER] Navegando a: {target_url}")
                        await page.goto(target_url, wait_until='networkidle', timeout=15000)
                        await asyncio.sleep(1.5)
                        print(f"✅ [NAVER] Navegación exitosa")
                
                print(f"🔍 [NAVER] Extrayendo capítulos de página {page_num}...")
                
                chapters_data = await page.evaluate(r"""
                    () => {
                        const result = [];
                        const episodeLinks = document.querySelectorAll('a[href*="/webtoon/detail?titleId="]');
                        
                        episodeLinks.forEach(link => {
                            const href = link.href;
                            const titleElement = link.querySelector('[class*="subtitle"], [class*="title"]');
                            
                            if (!href || !titleElement) return;
                            
                            const text = titleElement.textContent.trim();
                            if (text.includes('첫화보기') || text.includes('첫 화 보기')) {
                                return;
                            }
                            
                            const parent = link.closest('li, div');
                            const isLocked = parent && (
                                parent.querySelector('[class*="lock"]') ||
                                parent.querySelector('[class*="charge"]') ||
                                parent.textContent.includes('UP') ||
                                parent.textContent.includes('코인')
                            );
                            
                            if (isLocked) return;
                            
                            const match = href.match(/no=(\d+)/);
                            if (match) {
                                let cleanName = text
                                    .replace('NEW', '')
                                    .replace('UP', '')
                                    .replace(/\s+/g, ' ')
                                    .trim();
                                
                                if (!cleanName || cleanName.length < 2) {
                                    cleanName = `Episodio ${match[1]}`;
                                }
                                
                                result.push({
                                    no: match[1],
                                    name: cleanName,
                                    url: href
                                });
                            }
                        });
                        
                        return result;
                    }
                """)
                
                new_found = 0
                for ch in chapters_data:
                    if ch['url'] not in seen_urls:
                        seen_urls.add(ch['url'])
                        all_chapters.append(ch)
                        new_found += 1
                
                print(f"✅ [NAVER] Página {page_num}: {new_found} capítulos nuevos encontrados")
                print(f"📊 [NAVER] Total acumulado: {len(all_chapters)} capítulos")
            
            await context.close()
            
            print(f"\n{'='*80}")
            print(f"🔄 [NAVER] Ordenando capítulos...")
            all_chapters.sort(key=lambda x: int(x['no']))
            
            print(f"✅ [NAVER] SCRAPING COMPLETADO")
            print(f"📊 [NAVER] Total final: {len(all_chapters)} capítulos gratuitos")
            print(f"{'='*80}\n")
            
            if not all_chapters:
                return [], thumbnail, f"⚠️ {title} - Solo capítulos de pago"
            
            return all_chapters, thumbnail, title
            
        except Exception as e:
            print(f"❌ [NAVER] Error en scraping: {e}")
            traceback.print_exc()
            return [], None, str(e)
        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass
    
    async def get_chapter_images(self, chapter_url: str) -> List[str]:
        """Obtiene URLs de imágenes"""
        if not self.is_ready:
            await self.start()
        
        context = None
        page = None
        
        try:
            print(f"📖 [NAVER] Extrayendo imágenes del capítulo...")
            
            context = await self.browser.new_context(
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='ko-KR'
            )
            page = await context.new_page()
            
            await page.goto(chapter_url, wait_until='networkidle', timeout=30000)
            await page.wait_for_selector('img[src*="image-comic"]', timeout=15000)
            await asyncio.sleep(1)
            
            await page.evaluate(r"""
                async () => {
                    await new Promise((resolve) => {
                        let totalHeight = 0;
                        const distance = 1000;
                        const timer = setInterval(() => {
                            const scrollHeight = document.body.scrollHeight;
                            window.scrollBy(0, distance);
                            totalHeight += distance;
                            if(totalHeight >= scrollHeight){
                                clearInterval(timer);
                                resolve();
                            }
                        }, 50);
                    });
                }
            """)
            
            await asyncio.sleep(1)
            
            image_urls = await page.evaluate(r"""
                () => {
                    const images = Array.from(document.querySelectorAll('img'));
                    return images
                        .map(img => img.src || img.getAttribute('data-src'))
                        .filter(src => src && src.includes('image-comic.pstatic.net'))
                        .filter(src => !src.includes('thumbnail'));
                }
            """)
            
            await context.close()
            
            print(f"✅ [NAVER] {len(image_urls)} imágenes extraídas")
            return image_urls
            
        except Exception as e:
            print(f"❌ [NAVER] Error extrayendo imágenes: {e}")
            return []
        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass

# ==============================================================================
# GOOGLE DRIVE
# ==============================================================================

def get_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', DRIVE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def get_folder_sync(service, name, parent):
    q = f"name='{name}' and '{parent}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    res = service.files().list(q=q, fields='files(id)', pageSize=1).execute()
    if f := res.get('files'):
        return f[0]['id']
    body = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent]}
    folder = service.files().create(body=body, fields='id').execute()
    return folder.get('id')

def get_seq_sync(service, parent):
    try:
        q = f"'{parent}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        res = service.files().list(q=q, fields='files(name)').execute()
        nums = [int(f['name']) for f in res.get('files', []) if f['name'].isdigit()]
        return f"{max(nums)+1:03d}" if nums else "001"
    except:
        return "001"

async def upload_file_safe(service, file_data, name, parent):
    try:
        file_data.seek(0)
        meta = {'name': name, 'parents': [parent]}
        media = MediaIoBaseUpload(file_data, mimetype='application/zip', resumable=True)
        await asyncio.to_thread(service.files().create(body=meta, media_body=media, fields='id').execute)
        return True
    except Exception as e:
        print(f"❌ [DRIVE] Error subiendo: {e}")
        return False

# ==============================================================================
# DESCARGA Y PROCESAMIENTO
# ==============================================================================

async def download_img(session, url, idx, state):
    headers = {'User-Agent': USER_AGENT, 'Referer': 'https://comic.naver.com/'}
    for attempt in range(3):
        try:
            async with session.get(url, headers=headers, timeout=30) as r:
                if r.status == 200:
                    data = await r.read()
                    name = url.split('/')[-1].split('?')[0]
                    if not re.search(r'\.(jpg|jpeg|png|webp)$', name, re.I):
                        name = f"img-{idx+1:03d}.jpg"
                    
                    state.current_images += 1
                    return {'name': name, 'data': io.BytesIO(data), 'idx': idx}
        except:
            await asyncio.sleep(1 + attempt)
    return None

async def download_chapter_images(urls, state):
    state.total_images = len(urls)
    state.current_images = 0
    state.update("⚡ Descargando...", 30, 100)
    
    async with aiohttp.ClientSession() as session:
        tasks = [download_img(session, u, idx, state) for idx, u in enumerate(urls)]
        completed = 0
        results = []
        
        for f in asyncio.as_completed(tasks):
            res = await f
            if res:
                results.append(res)
                completed += 1
                progress = 30 + int((completed / len(urls)) * 30)
                state.update("⚡ Descargando...", progress, 100)
        
        results.sort(key=lambda x: x['idx'])
        return results

def create_zip_manga(imgs, chapter_name):
    if not imgs:
        return None
    
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for idx, img_item in enumerate(imgs):
                try:
                    img_item['data'].seek(0)
                    with Image.open(img_item['data']) as im:
                        if im.mode != 'RGB':
                            im = im.convert('RGB')
                        temp = io.BytesIO()
                        im.save(temp, 'JPEG', quality=95)
                        temp.seek(0)
                        zf.writestr(f"Pagina-{idx+1:03d}.jpg", temp.read())
                    img_item['data'].close()
                except:
                    pass
        zip_buffer.seek(0)
        return zip_buffer
    except:
        return None

def process_manhwa_sync(imgs, h, os_val, oe_val):
    """Procesa imágenes en tiras largas"""
    if not imgs:
        return [], 0
    
    temp_dir = tempfile.mkdtemp(prefix="naver_proc_")
    
    try:
        failed = 0
        temp_files = []
        widths = []
        
        for idx, img_item in enumerate(imgs):
            try:
                img_item['data'].seek(0)
                with Image.open(img_item['data']) as p:
                    if p.mode != 'RGB':
                        p = p.convert('RGB')
                    widths.append(p.width)
                    temp_path = os.path.join(temp_dir, f"temp_{idx:04d}.jpg")
                    p.save(temp_path, quality=95)
                    temp_files.append(temp_path)
                img_item['data'].close()
            except:
                failed += 1
        
        if not temp_files:
            return [], failed
        
        tw = Counter(widths).most_common(1)[0][0]
        
        if oe_val > 0:
            temp_files = temp_files[:-oe_val]
        if os_val > 0:
            temp_files = temp_files[os_val:]
        
        slices = []
        target_height = min(h, MAX_STRIP_HEIGHT)
        curr = Image.new('RGB', (tw, target_height), (255, 255, 255))
        y_curr = 0
        slice_idx = 1
        
        for t_path in temp_files:
            try:
                with Image.open(t_path) as p:
                    if p.width != tw:
                        rh = int(p.height * (tw / p.width))
                        p_resized = p.resize((tw, rh), Image.Resampling.BILINEAR)
                    else:
                        p_resized = p
                    
                    rem_h = p_resized.height
                    src_y = 0
                    
                    while rem_h > 0:
                        avail = target_height - y_curr
                        paste = min(rem_h, avail)
                        crop = p_resized.crop((0, src_y, tw, src_y + paste))
                        curr.paste(crop, (0, y_curr))
                        y_curr += paste
                        src_y += paste
                        rem_h -= paste
                        
                        if y_curr >= target_height:
                            out = io.BytesIO()
                            curr.save(out, 'JPEG', quality=90, optimize=True)
                            out.seek(0)
                            slices.append({'name': f"Tira-{slice_idx:03d}.jpg", 'data': out})
                            curr.close()
                            slice_idx += 1
                            curr = Image.new('RGB', (tw, target_height), (255, 255, 255))
                            y_curr = 0
                    
                    if p_resized != p:
                        p_resized.close()
            except:
                failed += 1
        
        if y_curr > 0:
            out = io.BytesIO()
            final_slice = curr.crop((0, 0, tw, y_curr))
            final_slice.save(out, 'JPEG', quality=90, optimize=True)
            out.seek(0)
            slices.append({'name': f"Tira-{slice_idx:03d}.jpg", 'data': out})
            final_slice.close()
        
        curr.close()
        return slices, failed
        
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
        gc.collect()

def create_zip_manhwa(slices, chapter_name):
    if not slices:
        return None
    
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for s in slices:
                s['data'].seek(0)
                zf.writestr(s['name'], s['data'].read())
                s['data'].close()
        zip_buffer.seek(0)
        return zip_buffer
    except:
        return None

# ==============================================================================
# VISUAL
# ==============================================================================

def create_progress_embed(state):
    emb = Embed(color=COLOR_PROGRESS)
    emb.set_author(name="Naver Webtoon Downloader")
    emb.description = f"📂 **{state.series_name}**\n📖 **{state.chapter}**"
    
    if state.thumb:
        emb.set_thumbnail(url=state.thumb)
    
    el = int(time.time() - state.start_time)
    
    emb.add_field(name="Estado", value=f"`{state.status}`", inline=True)
    emb.add_field(name="📚 Caps", value=f"`{state.current_chapter_idx} / {state.total_chapters}`", inline=True)
    emb.add_field(name="⏱️ Tiempo", value=f"`{format_time(el)}`", inline=True)
    
    if state.total_images > 0:
        emb.add_field(
            name="🖼️ Imágenes",
            value=f"`{state.current_images} / {state.total_images}`",
            inline=True
        )
    
    emb.add_field(name="Progreso", value=state.progress_bar(), inline=False)
    return emb

async def visual_loop(msg, state):
    while state.running:
        try:
            await msg.edit(embed=create_progress_embed(state))
        except:
            pass
        await asyncio.sleep(2.5)

# ==============================================================================
# ORQUESTADOR
# ==============================================================================

async def run_extraction(bot, i, chapters, title, thumb, browser, ctype, h=15000, os=0, oe=0):
    state = TaskState()
    state.series_name = title
    state.thumb = thumb
    state.total_chapters = len(chapters)
    
    dummy_state = TaskState()
    dummy_state.series_name = title
    dummy_state.thumb = thumb
    dummy_state.status = "🔍 Conectando con Naver..."
    msg = await i.channel.send(embed=create_progress_embed(dummy_state))
    
    queue_messages = [
        "🔍 Conectando con Naver...",
        "📚 Analizando estructura del webtoon...",
        "🔐 Verificando disponibilidad...",
        "⚙️ Preparando motor de extracción...",
        "🌐 Estableciendo conexión segura...",
    ]
    
    async def show_fake_progress():
        idx = 0
        while True:
            try:
                dummy_state.status = queue_messages[idx % len(queue_messages)]
                await msg.edit(embed=create_progress_embed(dummy_state))
                await asyncio.sleep(3)
                idx += 1
            except:
                break
    
    fake_task = asyncio.create_task(show_fake_progress())
    
    async with NAVER_EXTRACTION_SEMAPHORE:
        fake_task.cancel()
        
        vtask = asyncio.create_task(visual_loop(msg, state))
        
        try:
            state.update("📁 Configurando Drive...", 0, 100)
            service = await asyncio.to_thread(get_service)
            ufid = await asyncio.to_thread(get_folder_sync, service, clean_name(i.user.name), DRIVE_BASE_FOLDER_ID)
            seq = await asyncio.to_thread(get_seq_sync, service, ufid)
            ext_id = await asyncio.to_thread(get_folder_sync, service, seq, ufid)
            
            completed = 0
            
            for idx, ch in enumerate(chapters):
                state.chapter = ch['name']
                state.current_chapter_idx = idx + 1
                
                state.total_images = 0
                state.current_images = 0
                
                try:
                    print(f"🔄 [{completed+1}/{len(chapters)}] Procesando: {ch['name']}")
                    
                    state.update("📖 Extrayendo...", 0, 100)
                    urls = await browser.get_chapter_images(ch['url'])
                    if not urls:
                        continue
                    
                    state.update("📖 Extrayendo...", 30, 100)
                    
                    imgs = await download_chapter_images(urls, state)
                    if not imgs:
                        continue
                    
                    state.update("📦 Procesando...", 60, 100)
                    
                    if ctype == "manga":
                        zip_data = await asyncio.to_thread(create_zip_manga, imgs, ch['name'])
                    else:
                        slices, fails = await asyncio.to_thread(process_manhwa_sync, imgs, h, os, oe)
                        if not slices:
                            continue
                        zip_data = await asyncio.to_thread(create_zip_manhwa, slices, ch['name'])
                    
                    if not zip_data:
                        continue
                    
                    state.update("📦 Procesando...", 85, 100)
                    
                    state.update("☁️ Subiendo...", 85, 100)
                    success = await upload_file_safe(service, zip_data, f"{clean_name(ch['name'])}.zip", ext_id)
                    zip_data.close()
                    
                    if success:
                        state.update("✅ Completado", 100, 100)
                        completed += 1
                        await asyncio.sleep(0.5)
                        gc.collect()
                        print(f"✅ {ch['name']}")
                    
                except Exception as e:
                    print(f"❌ {ch['name']}: {e}")
                    continue
            
            state.running = False
            vtask.cancel()
            
            duration = format_time(int(time.time() - state.start_time))
            link = f"https://drive.google.com/drive/folders/{ext_id}"
            
            fin = Embed(title="✅ Completado", color=COLOR_SUCCESS)
            fin.description = f"**{title}**"
            fin.add_field(name="👤 Usuario", value=i.user.mention, inline=True)
            fin.add_field(name="📂 Caps", value=f"**{completed}** / {len(chapters)}", inline=True)
            fin.add_field(name="⏱️ Tiempo", value=f"`{duration}`", inline=True)
            fin.add_field(name="🔗 Link", value=f"[Google Drive]({link})", inline=False)
            fin.set_footer(text="⚠️ Expira en 24h")
            
            if thumb:
                fin.set_thumbnail(url=thumb)
            
            await msg.edit(embed=fin)
        
        except Exception as e:
            state.running = False
            vtask.cancel()
            print(f"❌ Error: {e}")
            traceback.print_exc()
            fin = Embed(title="❌ Error", description=str(e), color=COLOR_ERROR)
            await msg.edit(embed=fin)

# ==============================================================================
# UI - MODAL MANHWA
# ==============================================================================

class ConfigModal(ui.Modal, title="⚙️ Configuración Manhwa"):
    def __init__(self, bot, interaction, chapters, title, thumb, browser):
        super().__init__()
        self.bot = bot
        self.interaction = interaction
        self.chapters = chapters
        self.title = title
        self.thumb = thumb
        self.browser = browser
        
        self.height = ui.TextInput(
            label="Altura de tiras (px)",
            default="15000",
            placeholder="5000-20000",
            max_length=5
        )
        self.omit = ui.TextInput(
            label="Omitir imágenes (inicio,fin)",
            default="0,0",
            placeholder="Ej: 2,1",
            required=False
        )
        
        self.add_item(self.height)
        self.add_item(self.omit)
    
    async def on_submit(self, interaction: discord.Interaction):
        h_val = 15000
        os_val = 0
        oe_val = 0
        
        try:
            h_val = int(self.height.value)
            h_val = max(5000, min(h_val, 20000))
        except:
            pass
        
        try:
            parts = self.omit.value.split(',')
            os_val = int(parts[0])
            oe_val = int(parts[1]) if len(parts) > 1 else 0
        except:
            pass
        
        msg_status = f"✅ **Procesando {len(self.chapters)} capítulos como MANHWA**\n📏 Altura: {h_val}px"
        
        await interaction.response.send_message(msg_status, ephemeral=True)
        
        asyncio.create_task(run_extraction(
            self.bot, self.interaction, self.chapters, self.title, 
            self.thumb, self.browser, "manhwa", h=h_val, os=os_val, oe=oe_val
        ))

# ==============================================================================
# UI - BOTONES MANGA/MANHWA
# ==============================================================================

class TypeSelectView(ui.View):
    def __init__(self, bot, interaction, chapters, title, thumb, browser):
        super().__init__(timeout=300)
        self.bot = bot
        self.interaction = interaction
        self.chapters = chapters
        self.title = title
        self.thumb = thumb
        self.browser = browser
    
    @ui.button(label="📦 Extraer Manga", style=discord.ButtonStyle.primary, row=0)
    async def manga_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("❌ No es tuyo", ephemeral=True)
        
        msg_status = f"✅ **Procesando {len(self.chapters)} capítulos como MANGA**"
        await interaction.response.send_message(msg_status, ephemeral=True)
        
        asyncio.create_task(run_extraction(
            self.bot, self.interaction, self.chapters, self.title,
            self.thumb, self.browser, "manga"
        ))
    
    @ui.button(label="📜 Extraer Manhwa", style=discord.ButtonStyle.primary, row=0)
    async def manhwa_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("❌ No es tuyo", ephemeral=True)
        
        modal = ConfigModal(self.bot, self.interaction, self.chapters, self.title, self.thumb, self.browser)
        await interaction.response.send_modal(modal)
    
    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("❌ No es tuyo", ephemeral=True)
        
        emb = Embed(title="❌ Cancelado", color=COLOR_ERROR)
        await interaction.response.edit_message(embed=emb, view=None)

# ==============================================================================
# UI - SELECCIÓN DE CAPÍTULOS
# ==============================================================================

class ChapterSelectView(ui.View):
    def __init__(self, bot, user, chapters, title, thumb, browser, page=0):
        super().__init__(timeout=300)
        self.bot = bot
        self.user = user
        self.chapters = chapters
        self.title = title
        self.thumb = thumb
        self.browser = browser
        self.page = page
        
        start = page * 25
        end = min(start + 25, len(chapters))
        page_chapters = chapters[start:end]
        
        options = [
            discord.SelectOption(label=truncate(ch['name'], 85), value=str(i + start))
            for i, ch in enumerate(page_chapters)
        ]
        
        self.select = ui.Select(
            placeholder=f"Selecciona capítulos (máx 5) - Página {page + 1}/{(len(chapters) - 1) // 25 + 1}",
            options=options,
            min_values=1,
            max_values=min(5, len(options))
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
        
        if page > 0:
            prev_btn = ui.Button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
        
        if end < len(chapters):
            next_btn = ui.Button(label="Siguiente ▶", style=discord.ButtonStyle.secondary)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
    
    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ No es tuyo", ephemeral=True)
        
        selected = [self.chapters[int(x)] for x in self.select.values]
        
        view = TypeSelectView(self.bot, interaction, selected, self.title, self.thumb, self.browser)
        await interaction.response.edit_message(view=view)
    
    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ No es tuyo", ephemeral=True)
        
        new_view = ChapterSelectView(
            self.bot, self.user, self.chapters, self.title, 
            self.thumb, self.browser, self.page - 1
        )
        await interaction.response.edit_message(view=new_view)
    
    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ No es tuyo", ephemeral=True)
        
        new_view = ChapterSelectView(
            self.bot, self.user, self.chapters, self.title,
            self.thumb, self.browser, self.page + 1
        )
        await interaction.response.edit_message(view=new_view)

# ==============================================================================
# COG
# ==============================================================================

class NaverPlaywrightCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.browser = NaverBrowser()
        print("✅ Naver V5.0 - ADMIN ONLY (Sin Economía)")
        print(f"   • Rol requerido: {ADMIN_ROLE_ID}")
        print(f"   • Canal permitido: {ALLOWED_CHANNEL_ID}")
        print("   • Sin sistema de cobro/gratis")
    
    async def cog_load(self):
        await self.browser.start()
    
    async def cog_unload(self):
        await self.browser.stop()
    
    @app_commands.command(name="naver", description="[ADMIN] Extrae capítulos de Naver Webtoon")
    @app_commands.describe(url="Link de la serie de Naver")
    @app_commands.checks.has_role(ADMIN_ROLE_ID)
    async def naver(self, interaction: discord.Interaction, url: str):
        # Verificar canal
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            return await interaction.response.send_message(
                f"❌ Este comando solo puede usarse en <#{ALLOWED_CHANNEL_ID}>",
                ephemeral=True
            )
        
        if 'naver' not in url.lower():
            return await interaction.response.send_message("❌ Link inválido", ephemeral=True)
        
        await interaction.response.defer(ephemeral=False)
        
        try:
            chapters, thumb, title = await self.browser.get_chapters(url)
            
            if not chapters:
                emb = Embed(
                    title="⚠️ Sin Capítulos Gratis",
                    description=f"**{title}**\n\nSolo tiene capítulos de pago.",
                    color=COLOR_ERROR
                )
                return await interaction.followup.send(embed=emb)
            
            emb = Embed(
                title=f"🔎 {truncate(title, 60)}",
                description=f"✅ **{len(chapters)} capítulos disponibles**",
                color=COLOR_LYRA
            )
            
            if thumb:
                emb.set_image(url=thumb)
            
            emb.set_footer(text="✨ Naver Webtoon - Selecciona capítulos abajo")
            
            view = ChapterSelectView(self.bot, interaction.user, chapters, title, thumb, self.browser)
            await interaction.followup.send(embed=emb, view=view)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            traceback.print_exc()
            await interaction.followup.send(f"❌ Error: {str(e)}")
    
    @naver.error
    async def naver_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingRole):
            await interaction.response.send_message(
                "❌ No tienes permisos para usar este comando (requiere rol de Administrador)",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(NaverPlaywrightCog(bot))