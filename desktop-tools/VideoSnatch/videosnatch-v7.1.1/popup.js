// popup.js — VideoSnatch v7.1.1

// ── Captura errores globales para que no maten todo el popup ──
window.addEventListener('error', e => {
  console.warn('[VideoSnatch] Error global capturado:', e.message, e.filename, e.lineno);
});
window.addEventListener('unhandledrejection', e => {
  console.warn('[VideoSnatch] Promise rechazada:', e.reason);
  e.preventDefault();
});

const scanBtn = document.getElementById('scanBtn');
const dot = document.getElementById('dot');
const stxt = document.getElementById('stxt');
const lstD = document.getElementById('lstD');
const lstN = document.getElementById('lstN');
const emD = document.getElementById('emD');
const emN = document.getElementById('emN');
const tot = document.getElementById('tot');
const clrBtn = document.getElementById('clrBtn');
const mUrl = document.getElementById('mUrl');
const mName = document.getElementById('mName');
const mDl = document.getElementById('mDl');
const mProg = document.getElementById('mProg');
const mPFill = document.getElementById('mPFill');
const mLog = document.getElementById('mLog');
const toastEl = document.getElementById('toast');

// Estado global
let all = { detected: [], network: [] };
const active = {};

// Info de la pestaña activa (para export)
let currentTabUrl   = '';
let currentTabTitle = '';

// ── Tabs ──
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  const panel = document.getElementById('tab-' + t.dataset.tab);
  if (panel) panel.classList.add('active');
}));

// ── Helpers ──
function toast(msg, type = '') {
  toastEl.textContent = msg;
  toastEl.className = 'toast ' + type;
  void toastEl.offsetWidth;
  toastEl.classList.add('show');
  setTimeout(() => toastEl.classList.remove('show'), 2600);
}

function setStatus(s, t) { dot.className = 'dot ' + s; stxt.textContent = t; }

const QUALITY_ORDER = { full: 0, hd: 1, sd: 2, low: 3, lowest: 4, mobile: 5, hls: 6 };
function sortByQuality(arr) {
  return [...arr].sort((a, b) => {
    const oa = QUALITY_ORDER[a.quality] ?? 99;
    const ob = QUALITY_ORDER[b.quality] ?? 99;
    return oa - ob;
  });
}

function fmtFmt(url, quality) {
  if (!url) return 'mp4';
  const u = url.toLowerCase();
  if (u.includes('.m3u8') || quality === 'hls' || u.includes('ct=8')) return 'm3u8';
  if (u.includes('.webm')) return 'webm';
  return 'mp4';
}

function isStream(url, quality) {
  const f = fmtFmt(url, quality);
  return f === 'm3u8';
}

function fmtSize(bytes) {
  if (!bytes || bytes <= 0) return null;
  if (bytes > 1024*1024*1024) return (bytes/1024/1024/1024).toFixed(2)+' GB';
  if (bytes > 1024*1024) return (bytes/1024/1024).toFixed(1)+' MB';
  return (bytes/1024).toFixed(0)+' KB';
}

function qualityColor(q) {
  const colors = { full:'#00e676', hd:'#00e5ff', sd:'#ffab40', low:'#ff7043', lowest:'#ff5252', mobile:'#ce93d8', hls:'#ffab40' };
  return colors[q] || '#aaa';
}

function defName(url, quality) {
  const ext = quality === 'hls' ? 'ts' : 'mp4';
  return `video_${quality || 'descarga'}.${ext}`;
}

// ── Probe size via HEAD ──
async function probeSize(url, callback) {
  try {
    const r = await fetch(url, { method: 'HEAD', credentials: 'include', signal: AbortSignal.timeout(5000) });
    const cl = r.headers.get('content-length');
    if (cl && parseInt(cl) > 1024) callback(parseInt(cl));
  } catch {}
}

// ── Crear card de video ──
function makeCard(video, source) {
  const url = video.src || video.url || '';
  const quality = video.quality || 'video';
  const seekSchema = video.seekSchema || 0;
  const format = fmtFmt(url, quality);
  const stream = isStream(url, quality);
  const id = 'v' + Math.random().toString(36).slice(2, 8);
  const qColor = qualityColor(quality);
  const canPreview = !stream;

  const d = document.createElement('div');
  d.className = 'vcard';
  d.innerHTML = `
    <div class="card-hdr">
      <div class="thumb-wrap" id="tw-${id}">
        ${video.poster
          ? `<img src="${video.poster}" onerror="this.parentNode.innerHTML='<div class=thumb-placeholder>🎬</div>'">`
          : `<div class="thumb-placeholder">🎬</div>`}
        <div class="quality-badge" style="background:${qColor};color:#000">${quality.toUpperCase()}</div>
        ${canPreview ? `<button class="preview-btn" id="pvbtn-${id}">▶</button>` : ''}
      </div>
      <div class="cinfo">
        <div class="crow1">
          <span class="csource">${source === 'network' ? (video.fromIframe ? '📡 RED·iframe' : '📡 RED') : '🔍 DOM'}</span>
          <span class="csize" id="sz-${id}">—</span>
        </div>
        <div class="curl" title="${url}">${url.replace(/\?.*/, '?…')}</div>
        <div class="cbadges">
          <span class="badge ${format}">${format.toUpperCase()}</span>
          ${seekSchema === 3 ? '<span class="badge" style="border-color:#7c4dff;color:#7c4dff">fMP4</span>' : ''}
          ${stream ? '<span class="badge hls">STREAM</span>' : ''}
          ${video.width ? `<span class="badge">${video.width}×${video.height}</span>` : ''}
          ${video.duration ? `<span class="badge">${Math.floor(video.duration/60)}:${String(video.duration%60).padStart(2,'0')}</span>` : ''}
        </div>
      </div>
    </div>
    <div class="preview-panel" id="pv-${id}"></div>
    <div class="cactions">
      <button class="btn-dl" id="dl-${id}">
        ⬇ ${quality === 'hls' ? 'HLS Stream' : quality.toUpperCase()}
      </button>
      <button class="btn-copy" id="cp-${id}" title="Copiar URL">🔗</button>
    </div>
    <div class="prog" id="pg-${id}">
      <div class="prog-bg"><div class="prog-fill" id="pf-${id}"></div></div>
      <div class="prog-txt" id="pt-${id}"></div>
      <div class="prog-log" id="pl-${id}"></div>
    </div>
  `;

  // Probe tamaño
  const sizeEl = d.querySelector(`#sz-${id}`);
  if (!stream) {
    sizeEl.textContent = '…';
    probeSize(url, size => {
      sizeEl.textContent = fmtSize(size) || '—';
    });
  } else {
    sizeEl.textContent = 'STREAM';
    sizeEl.style.color = 'var(--warn)';
  }

  // Preview
  if (canPreview) {
    d.querySelector(`#pvbtn-${id}`)?.addEventListener('click', e => {
      e.stopPropagation();
      const panel = d.querySelector(`#pv-${id}`);
      if (panel.classList.contains('open')) {
        panel.classList.remove('open');
        panel.innerHTML = '';
        return;
      }
      panel.classList.add('open');
      // Para fMP4 (seekSchema:3), el preview puede no funcionar bien en Chrome directamente
      // pero lo intentamos igual
      panel.innerHTML = `<video class="preview-video" controls preload="metadata" src="${url}"></video>`;
      const vid = panel.querySelector('video');
      vid.onerror = () => {
        if (seekSchema === 3) {
          panel.innerHTML = `<div class="preview-error">ℹ fMP4 fragmentado — no previsualizable directamente.<br>Descarga la versión HD o usa el HLS stream.</div>`;
        } else {
          panel.innerHTML = `<div class="preview-error">⚠ No se puede previsualizar (CORS o token expirado).<br>Descarga directamente.</div>`;
        }
      };
      vid.onloadedmetadata = () => {
        const dur = Math.round(vid.duration);
        if (dur > 0) {
          const m = Math.floor(dur/60), s = String(dur%60).padStart(2,'0');
          if (sizeEl.textContent === '—' || sizeEl.textContent === '…') return;
          // Mostrar duración junto al tamaño
        }
      };
    });
  }

  // Download
  d.querySelector(`#dl-${id}`).addEventListener('click', async e => {
    const btn = e.currentTarget;
    const pg = d.querySelector(`#pg-${id}`);
    const pf = d.querySelector(`#pf-${id}`);
    const pt = d.querySelector(`#pt-${id}`);
    const pl = d.querySelector(`#pl-${id}`);

    if (active[id]) {
      active[id].abort();
      delete active[id];
      btn.textContent = `⬇ ${quality.toUpperCase()}`;
      btn.disabled = false;
      pg.classList.remove('show');
      setStatus('', 'Cancelado');
      return;
    }

    // Para fMP4 (seekSchema:3) y MP4 directos: usar chrome.downloads es más fiable
    if (!stream && seekSchema !== 3) {
      chrome.downloads.download({ url, filename: defName(url, quality), saveAs: true });
      toast('⬇ Descarga iniciada!', 'ok');
      return;
    }

    // fMP4 / HLS: descargar en browser
    pg.classList.add('show');
    btn.textContent = '✕ Cancelar';
    setStatus('busy', 'Descargando...');
    pl.textContent = '';

    const dl = new VideoDownloader(
      (cur, total, label) => {
        const p = total > 0 ? Math.min(99, Math.round(cur/total*100)) : 50;
        pf.style.width = p + '%';
        pt.textContent = label;
      },
      msg => { pl.textContent = msg; }
    );
    active[id] = dl;

    try {
      const fname = defName(url, quality);
      const result = await dl.download(url, fname, seekSchema);
      btn.textContent = '✓ Listo';
      btn.style.background = 'var(--ok)';
      btn.disabled = true;
      const sz = fmtSize(result.size);
      if (sz) sizeEl.textContent = sz;
      setStatus('on', `✓ ${sz || 'Descargado'}`);
      toast(`✓ ${fname} guardado!`, 'ok');
    } catch(err) {
      btn.textContent = `⬇ ${quality.toUpperCase()}`;
      btn.disabled = false;
      pl.textContent = '❌ ' + err.message;
      setStatus('err', err.message.slice(0, 40));
      toast('Error: ' + err.message.slice(0, 48), 'err');
    } finally { delete active[id]; }
  });

  // Copy URL
  d.querySelector(`#cp-${id}`).addEventListener('click', e => {
    navigator.clipboard.writeText(url).then(() => {
      e.target.textContent = '✓';
      e.target.classList.add('copied');
      setTimeout(() => { e.target.textContent = '🔗'; e.target.classList.remove('copied'); }, 1500);
    });
  });

  return d;
}

// ── Render ──
function render() {
  const n = all.detected.length + all.network.length;
  tot.textContent = n;

  lstD.innerHTML = '';
  emD.style.display = all.detected.length ? 'none' : 'flex';
  sortByQuality(all.detected).forEach(v => lstD.appendChild(makeCard(v, 'detected')));

  lstN.innerHTML = '';
  emN.style.display = all.network.length ? 'none' : 'flex';
  all.network.forEach(v => lstN.appendChild(makeCard(v, 'network')));

  updateExportBtn();
}

// ── Export ──
function updateExportBtn() {
  const btn = document.getElementById('exportBtn');
  if (!btn) return;
  const total = all.detected.length + all.network.length;
  btn.disabled = total === 0;
  btn.title = total === 0 ? 'Nada para exportar' : `Exportar ${total} video(s) encontrados`;
}

document.getElementById('exportBtn')?.addEventListener('click', () => {
  const total = all.detected.length + all.network.length;
  if (total === 0) { toast('No hay datos para exportar', 'err'); return; }

  const formatEntry = (v, source) => ({
    source,
    url:       v.src || v.url || '',
    quality:   v.quality || 'video',
    format:    fmtFmt(v.src || v.url || '', v.quality),
    isStream:  isStream(v.src || v.url || '', v.quality),
    seekSchema: v.seekSchema || 0,
    duration:  v.duration   || null,
    width:     v.width      || null,
    height:    v.height     || null,
    poster:    v.poster     || null,
    tabTitle:  v.tabTitle   || currentTabTitle || null,
    capturedAt: v.timestamp ? new Date(v.timestamp).toISOString() : null,
    contentType: v.contentType || null,
  });

  const data = {
    exportedAt:  new Date().toISOString(),
    extensionVersion: '7.1.0',
    page: {
      url:   currentTabUrl   || '(desconocida)',
      title: currentTabTitle || '(desconocida)',
    },
    summary: {
      total:    total,
      detected: all.detected.length,
      network:  all.network.length,
    },
    detected: all.detected.map(v => formatEntry(v, 'SCAN')),
    network:  all.network.map(v  => formatEntry(v, 'RED')),
  };

  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const blobUrl = URL.createObjectURL(blob);
  const ts  = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  chrome.downloads.download({
    url:      blobUrl,
    filename: `videosnatch-export-${ts}.json`,
    saveAs:   false,
  }, () => {
    setTimeout(() => URL.revokeObjectURL(blobUrl), 3000);
    toast(`✓ JSON exportado (${total} videos)`, 'ok');
  });
});

// ── SCAN: extrae URLs del DOM — incluyendo iframes cross-origin ──
// Estrategia: executeScript con allFrames:true para inyectar en TODOS
// los frames de la pestaña (incluidos iframes de GoodStream, Streamtape, etc.)
scanBtn.addEventListener('click', async () => {
  scanBtn.classList.add('spin');
  scanBtn.textContent = '⟳ ...';
  setStatus('busy', 'Escaneando...');

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabUrl   = tab.url   || '';
  currentTabTitle = tab.title || '';

  try {
    // ── Paso 1: ejecutar extractor en TODOS los frames (main + iframes) ──
    const frameResults = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: () => {
        // Esta función corre en cada frame de la página
        const results = [];
        const seen    = new Set();
        const add = (src, extra = {}) => {
          if (!src || src.startsWith('blob:') || src.startsWith('data:')) return;
          const clean = src.split('#')[0];
          if (seen.has(clean)) return;
          seen.add(clean);
          results.push({ src: clean, ...extra });
        };

        const scanText = (text) => {
          const re = /https?:\/\/[^\s"'<>\\]+\.(?:mp4|m3u8|webm|mpd)(?:[?#][^\s"'<>\\]*)?/gi;
          let m;
          while ((m = re.exec(text)) !== null) {
            add(m[0].replace(/\\u0026/g, '&').replace(/\\\/g, '/'), { quality: 'video' });
          }
        };

        // ── A. JWPlayer setup() ──
        document.querySelectorAll('script:not([src])').forEach(s => {
          const text = s.textContent; if (!text) return;

          // jwplayer setup
          const jw = text.match(/\.setup\s*\(\s*(\{[\s\S]+?\})\s*\)/);
          if (jw) { try {
            const obj = Function('"use strict"; return (' + jw[1] + ')')();
            if (obj?.file) add(obj.file, { quality: obj.label || 'video' });
            (obj?.sources || []).forEach(s => add(s.file || s.src, { quality: s.label || 'video' }));
            (obj?.playlist || []).forEach(p => {
              if (p.file) add(p.file, { quality: 'video' });
              (p.sources || []).forEach(s => add(s.file || s.src, { quality: s.label || 'video' }));
            });
          } catch {} }

          // "file":"url"
          const fileRe = /"file"\s*:\s*"(https?:\/\/[^"]+\.(?:mp4|m3u8|webm)[^"]*)"/gi;
          let fm; while ((fm = fileRe.exec(text)) !== null) add(fm[1].replace(/\\u0026/g,'&'), { quality: 'video' });

          // src:"url"
          const srcRe = /\bsrc\s*:\s*["'](https?:\/\/[^"']+\.(?:mp4|m3u8|webm)[^"']*)["']/gi;
          let sm; while ((sm = srcRe.exec(text)) !== null) add(sm[1], { quality: 'video' });

          // window.streams = { 1080:"url" }
          const ws = text.match(/window\.streams\s*=\s*(\{[\s\S]+?\})\s*;/);
          if (ws) { try {
            const obj = Function('"use strict"; return (' + ws[1] + ')')();
            Object.entries(obj).forEach(([k, v]) => { if (typeof v === 'string') add(v, { quality: k + 'p' }); });
          } catch {} }

          // var sources/videos = [...]
          const arrRe = /(?:var|let|const)\s+\w*(?:[Ss]ources?|[Vv]ideos?)\s*=\s*(\[[\s\S]+?\])\s*[;,)]/;
          const arrM = text.match(arrRe);
          if (arrM) { try {
            const arr = Function('"use strict"; return ' + arrM[1])();
            if (Array.isArray(arr)) arr.forEach(x => {
              const u = x.file || x.src || x.url || (typeof x === 'string' ? x : null);
              if (u) add(u, { quality: x.label || x.quality || 'video' });
            });
          } catch {} }

          // __NUXT__ / __NEXT_DATA__
          const nuxt = text.match(/window\.__(?:NUXT|NEXT_DATA|APP_STATE)__\s*=\s*(\{[\s\S]+)/);
          if (nuxt) { try {
            const obj = JSON.parse(nuxt[1].replace(/;?\s*$/, ''));
            const crawl = (n, d=0) => {
              if (d > 12 || !n || typeof n !== 'object') return;
              if (typeof n.url  === 'string' && /\.(mp4|m3u8|webm)/i.test(n.url))  add(n.url,  { quality: n.quality || n.label || 'video' });
              if (typeof n.file === 'string' && /\.(mp4|m3u8|webm)/i.test(n.file)) add(n.file, { quality: 'video' });
              Object.values(n).forEach(v => crawl(v, d+1));
            };
            crawl(obj);
          } catch {} }

          // Brute-force URL scan
          scanText(text);
        });

        // ── B. OK.ru embeds ──
        try {
          const pageHTML = document.documentElement.innerHTML;
          const okM = pageHTML.match(/\\&quot;videos\\&quot;:\[([\s\S]+?)\\&quot;vkMovie/);
          if (okM) {
            const raw = okM[1].replace(/\\&quot;/g, '"').replace(/\\\\u0026/g, '&');
            const entries = raw.match(/\{[^}]+\}/g) || [];
            entries.forEach(entry => { try {
              const nm = entry.match(/"name"\s*:\s*"(\w+)"/);
              const um = entry.match(/"url"\s*:\s*"([^"]+)"/);
              const sk = entry.match(/"seekSchema"\s*:\s*(\d+)/);
              const dm = entry.match(/"disallowed"\s*:\s*(true|false)/);
              if (nm && um && dm?.[1] !== 'true') add(um[1], { quality: nm[1], seekSchema: parseInt(sk?.[1] || 0) });
            } catch {} });
            const hlsM = pageHTML.match(/\\&quot;hlsManifestUrl\\&quot;:\\&quot;(https:\/\/[^\\]+)/);
            if (hlsM) add(hlsM[1].replace(/\\\\u0026/g,'&'), { quality: 'hls', seekSchema: 0 });
          }
          // Brute scan of full HTML
          scanText(pageHTML);
        } catch {}

        // ── C. <video> elements ──
        document.querySelectorAll('video').forEach(v => {
          if (v.src && !v.src.startsWith('blob:')) add(v.src, {
            quality: 'dom',
            poster:   v.poster  || null,
            duration: isFinite(v.duration) ? Math.round(v.duration) : null,
            width:    v.videoWidth  || null,
            height:   v.videoHeight || null,
          });
          v.querySelectorAll('source').forEach(s => { if (s.src) add(s.src, { quality: 'dom' }); });
        });

        // ── D. Iframes — devolver sus src para info ──
        document.querySelectorAll('iframe[src],iframe[data-src]').forEach(fr => {
          const src = fr.src || fr.dataset.src || '';
          if (!src || src.startsWith('about:') || src.startsWith('javascript:')) return;
          if (/goodstream|streamtape|filemoon|doodstream|mixdrop|upstream|voe\.sx|mp4upload|uqload|vidhide|vidlox|vtube|streamwish|wishembed|filelions|vidmoly|vidsrc|streamruby|streamvid|smoothpre|embedrise|ridoo|dropload|highstream|supervideo|hydrax|streamhub|videovard|vave\.cc/i.test(src))
            add(src, { quality: 'iframe-player' });
        });

        return {
          frameUrl: location.href,
          isIframe: window !== window.top,
          videos: results,
        };
      }
    });

    // ── Paso 2: combinar resultados de todos los frames ──
    const allFrameVideos = frameResults.flatMap(r => r.result?.videos || []);
    const iframeSrcs     = frameResults
      .filter(r => r.result?.isIframe)
      .map(r => r.result?.frameUrl)
      .filter(Boolean);

    // También intentar vía content script (para compatibilidad)
    let csVideos = [];
    try {
      const resp = await chrome.tabs.sendMessage(tab.id, { type: 'EXTRACT_VIDEOS' });
      const { okVideos=[], goodStreamVideos=[], cuevanaVideos=[], domVideos=[] } = resp || {};
      csVideos = [...okVideos, ...goodStreamVideos, ...cuevanaVideos, ...domVideos];
    } catch {}

    // Merge sin duplicados
    const seenUrls = new Set(all.detected.map(v => v.src));
    [...allFrameVideos, ...csVideos].forEach(v => {
      const src = v.src || v.url;
      if (src && !seenUrls.has(src)) {
        seenUrls.add(src);
        all.detected.push(v);
      }
    });

    render();
    updateExportBtn();
    const c = all.detected.length;

    if (c > 0) {
      document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
      document.querySelector('[data-tab="detected"]').classList.add('active');
      document.getElementById('tab-detected').classList.add('active');
    }

    const iframeNote = iframeSrcs.length
      ? ` (${iframeSrcs.length} iframe${iframeSrcs.length>1?'s':''} escaneado${iframeSrcs.length>1?'s':''})`
      : '';
    setStatus(c > 0 ? 'on' : '', c > 0 ? `${c} calidad(es) encontrada(s)${iframeNote}` : 'Sin videos');
    toast(c > 0 ? `✓ ${c} calidades disponibles${iframeNote}` : 'Sin videos detectados', c > 0 ? 'ok' : '');

  } catch(err) {
    setStatus('err', 'Error al escanear');
    toast('Error: ' + err.message, 'err');
  }

  scanBtn.textContent = '⟳ SCAN';
  scanBtn.classList.remove('spin');
});

// ── Network captures ──
function loadNetwork() {
  chrome.runtime.sendMessage({ type: 'GET_CAPTURES' }, resp => {
    if (!resp?.captures) return;
    // Deduplicar: solo mostrar URLs únicas no cubiertas ya por detected
    const detectedUrls = new Set(all.detected.map(v => v.src));
    all.network = resp.captures.filter(c => !detectedUrls.has(c.url));
    render();
    updateExportBtn();
    if (all.network.length > 0) setStatus('on', `${all.network.length} en red`);
  });
}

// ── Clear ──
clrBtn.addEventListener('click', () => {
  all = { detected: [], network: [] };
  chrome.runtime.sendMessage({ type: 'CLEAR_CAPTURES' });
  render();
  setStatus('', 'Listo');
  toast('Lista limpiada', '');
});

// ── Manual tab ──
mDl.addEventListener('click', async () => {
  const url = mUrl.value.trim();
  if (!url) { toast('Ingresa una URL', 'err'); return; }
  const name = mName.value.trim() || 'video.mp4';
  const stream = /\.m3u8/i.test(url) || /ct=8/i.test(url);

  if (!stream) {
    chrome.downloads.download({ url, filename: name, saveAs: true });
    toast('⬇ Descarga iniciada!', 'ok');
    return;
  }

  mProg.classList.add('show');
  mDl.textContent = '✕ Cancelar';
  mLog.textContent = '';
  setStatus('busy', 'Descargando...');

  const dl = new VideoDownloader(
    (cur, tot2) => { mPFill.style.width = (tot2 > 0 ? Math.min(99, Math.round(cur/tot2*100)) : 50) + '%'; },
    msg => { mLog.innerHTML += msg + '<br>'; mLog.scrollTop = mLog.scrollHeight; }
  );
  active['manual'] = dl;
  try {
    const r = await dl.download(url, name, 0);
    mDl.textContent = '↓ DL';
    setStatus('on', `✓ ${fmtSize(r.size) || 'Listo'}`);
    toast('✓ Descargado!', 'ok');
  } catch(err) {
    mDl.textContent = '↓ DL';
    setStatus('err', 'Error');
    toast('Error: ' + err.message.slice(0,50), 'err');
  } finally { delete active['manual']; }
});

// ── Init ──
loadNetwork();
render();
setInterval(loadNetwork, 3000);


// ═══════════════════════════════════════════════════════════
// YOUTUBE INTEGRATION — VideoSnatch v6.1
// ═══════════════════════════════════════════════════════════

let ytData             = null;
let ytActiveFmt        = 'mp4';
let ytActiveDownloads  = {};

function ytShow(el)  { el && (el.style.display = ''); }
function ytHide(el)  { el && (el.style.display = 'none'); }

function ytSetState(state) {
  ['yt-not-yt','yt-loading','yt-error','yt-info-card','yt-fmt-toggle','yt-quality-list','yt-note']
    .forEach(id => ytHide(document.getElementById(id)));
  if (state === 'not-yt')  { ytShow(document.getElementById('yt-not-yt')); return; }
  if (state === 'loading') { ytShow(document.getElementById('yt-loading')); return; }
  if (state === 'error')   { ytShow(document.getElementById('yt-error')); return; }
  if (state === 'ready') {
    ytShow(document.getElementById('yt-info-card'));
    ytShow(document.getElementById('yt-fmt-toggle'));
    ytShow(document.getElementById('yt-quality-list'));
    ytShow(document.getElementById('yt-note'));
  }
}

function ytFmtSize(bytes) {
  if (!bytes) return '';
  if (bytes > 1e9) return (bytes/1e9).toFixed(2) + ' GB';
  if (bytes > 1e6) return (bytes/1e6).toFixed(1) + ' MB';
  return (bytes/1024).toFixed(0) + ' KB';
}

function ytSafeFilename(title) {
  return title.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').slice(0, 80);
}

// ── Renderiza la lista de calidades ─────────────────────────────────────
async function ytRenderQualities() {
  const listEl = document.getElementById('yt-quality-list');
  listEl.innerHTML = '';
  if (!ytData) return;

  const { muxed, audioOnly, videoOnly } = ytHelper.groupFormats(ytData.formats);

  // ────────────── MODO MP4 (Video) ──────────────
  if (ytActiveFmt === 'mp4') {
    const allVideo = [...muxed, ...videoOnly];
    if (!allVideo.length) {
      listEl.innerHTML = `<div class="empty" style="padding:20px 0"><div class="et">SIN FORMATOS</div></div>`;
      return;
    }
    allVideo.forEach((fmt, idx) => {
      const ext       = ytHelper.getExt(fmt.mimeType, false);
      const qlabel    = ytHelper.videoQualityLabel(fmt);
      const isMuxed   = !!fmt.audioQuality;
      const badgeCls  = ext === 'mp4' ? 'mp4' : 'webm';
      const br        = ytHelper.bitrateLabel(fmt.bitrate);
      const fps       = fmt.fps > 30 ? `${fmt.fps}fps` : '';
      const szLabel   = fmt.contentLength ? ytFmtSize(fmt.contentLength) : '';
      const id        = `yt-q-v${idx}`;

      // Etiqueta de tipo: "video+audio" o "solo video"
      const typeTag = isMuxed
        ? `<span class="yt-type-tag audio">▶ video + audio</span>`
        : `<span class="yt-type-tag novideo">⚠ solo video</span>`;

      const metaParts = [br, fps].filter(Boolean).join(' · ');

      const row = document.createElement('div');
      row.className = 'yt-qrow';
      row.id = id;
      row.innerHTML = `
        <div class="yt-qrow-inner">
          <span class="yt-qbadge ${badgeCls}">.${ext.toUpperCase()}</span>
          <div class="yt-qinfo">
            <div class="yt-qlabel">${qlabel} ${typeTag}</div>
            ${metaParts ? `<div class="yt-qmeta">${metaParts}</div>` : ''}
          </div>
          <span class="yt-qsize" id="${id}-size">${szLabel}</span>
          <button class="btn-yt-dl" id="${id}-btn">⬇ DL</button>
        </div>
        <div class="yt-qprog" id="${id}-prog">
          <div class="yt-qprog-bg"><div class="yt-qprog-fill" id="${id}-fill"></div></div>
          <div class="yt-qprog-txt" id="${id}-txt">Preparando...</div>
        </div>`;
      listEl.appendChild(row);

      if (!szLabel && !fmt.signatureCipher) ytProbeSizeAsync(fmt.url, id);
      row.querySelector(`#${id}-btn`).addEventListener('click',
        () => ytDownload(fmt, id, ext, false, row.querySelector(`#${id}-btn`)));
    });
    return;
  }

  // ────────────── MODO MP3 (Audio) ──────────────
  if (!audioOnly.length) {
    listEl.innerHTML = `<div class="empty" style="padding:20px 0"><div class="et">SIN AUDIO</div></div>`;
    return;
  }

  // Separador visual entre m4a y webm
  let lastCodec = null;

  audioOnly.forEach((fmt, idx) => {
    const ext       = ytHelper.getExt(fmt.mimeType, true);
    const codecFam  = ext === 'm4a' ? 'mp4' : 'webm';
    const badgeCls  = ext === 'm4a' ? 'm4a' : 'webm';
    const { label: qlabel, kbps } = ytHelper.audioQualityLabel(fmt);
    const szLabel   = fmt.contentLength ? ytFmtSize(fmt.contentLength) : '';
    const id        = `yt-q-a${idx}`;
    const channels  = fmt.audioChannels === 2 ? 'Estéreo' : fmt.audioChannels === 1 ? 'Mono' : '';

    // Separador entre grupos de codec
    if (lastCodec !== null && lastCodec !== codecFam) {
      const sep = document.createElement('div');
      sep.className = 'yt-codec-sep';
      sep.textContent = 'Otros formatos';
      listEl.appendChild(sep);
    }
    lastCodec = codecFam;

    const metaParts = [channels].filter(Boolean).join(' · ');

    const row = document.createElement('div');
    row.className = 'yt-qrow';
    row.id = id;
    row.innerHTML = `
      <div class="yt-qrow-inner">
        <span class="yt-qbadge ${badgeCls}">.${ext.toUpperCase()}</span>
        <div class="yt-qinfo">
          <div class="yt-qlabel">${qlabel}</div>
          <div class="yt-qmeta">${kbps ? `${kbps} kbps` : ''}${metaParts ? ' · ' + metaParts : ''}</div>
        </div>
        <span class="yt-qsize" id="${id}-size">${szLabel}</span>
        <button class="btn-yt-dl" id="${id}-btn">⬇ DL</button>
      </div>
      <div class="yt-qprog" id="${id}-prog">
        <div class="yt-qprog-bg"><div class="yt-qprog-fill" id="${id}-fill"></div></div>
        <div class="yt-qprog-txt" id="${id}-txt">Preparando...</div>
      </div>`;
    listEl.appendChild(row);

    if (!szLabel && !fmt.signatureCipher) ytProbeSizeAsync(fmt.url, id);
    row.querySelector(`#${id}-btn`).addEventListener('click',
      () => ytDownload(fmt, id, ext, true, row.querySelector(`#${id}-btn`)));
  });
}

// ── Probe de tamaño sin bloquear ─────────────────────────────────────────
async function ytProbeSizeAsync(url, id) {
  if (!url) return;
  try {
    const r = await fetch(url, { method: 'HEAD', credentials: 'include', signal: AbortSignal.timeout(4000) });
    const cl = r.headers.get('content-length');
    if (cl && parseInt(cl) > 1024) {
      const el = document.getElementById(`${id}-size`);
      if (el) el.textContent = ytFmtSize(parseInt(cl));
    }
  } catch {}
}

// ── Fallback: busca el mejor formato muxed (video+audio directo) ─────────
function ytGetBestMuxed() {
  if (!ytData?.formats) return null;
  const { muxed } = ytHelper.groupFormats(ytData.formats);
  // Preferir mp4, luego mayor resolución
  const mp4 = muxed.filter(f => ytHelper._codecFamily(f.mimeType) === 'mp4');
  const pool = mp4.length ? mp4 : muxed;
  return pool.length ? pool[0] : null;
}

// ── Muestra diálogo de confirmación de fallback ───────────────────────────
// Devuelve true si el usuario acepta, false si cancela
function ytConfirmFallback(requestedLabel, fallbackLabel) {
  return new Promise(resolve => {
    // Reutilizar o crear overlay
    let overlay = document.getElementById('yt-fallback-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'yt-fallback-overlay';
      overlay.style.cssText = `
        position:fixed;inset:0;background:rgba(0,0,0,.75);
        display:flex;align-items:center;justify-content:center;
        z-index:9999;padding:16px;box-sizing:border-box;`;
      document.body.appendChild(overlay);
    }
    overlay.innerHTML = `
      <div style="background:var(--bg2,#1e1e2e);border:1px solid var(--border,#333);
                  border-radius:10px;padding:20px;max-width:320px;width:100%;
                  font-family:inherit;color:var(--fg,#eee);box-shadow:0 8px 32px #000a;">
        <div style="font-size:13px;font-weight:600;margin-bottom:10px;color:var(--warn,#ffab40);">
          ⚠ No se pudo resolver la URL
        </div>
        <div style="font-size:12px;line-height:1.5;margin-bottom:16px;color:var(--fg2,#aaa);">
          No fue posible obtener el formato
          <strong style="color:var(--fg,#eee)">${requestedLabel}</strong>.<br><br>
          ¿Querés descargar el formato
          <strong style="color:var(--ok,#00e676)">${fallbackLabel}</strong>
          (video + audio ya combinados) en su lugar?
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end;">
          <button id="ytfb-cancel" style="padding:7px 14px;border-radius:6px;border:1px solid var(--border,#444);
            background:transparent;color:var(--fg2,#aaa);cursor:pointer;font-size:12px;">
            Cancelar
          </button>
          <button id="ytfb-ok" style="padding:7px 14px;border-radius:6px;border:none;
            background:var(--ok,#00e676);color:#000;cursor:pointer;font-weight:700;font-size:12px;">
            Sí, descargar ${fallbackLabel}
          </button>
        </div>
      </div>`;
    overlay.style.display = 'flex';

    const close = (val) => {
      overlay.style.display = 'none';
      resolve(val);
    };
    overlay.querySelector('#ytfb-ok').onclick     = () => close(true);
    overlay.querySelector('#ytfb-cancel').onclick  = () => close(false);
    overlay.onclick = e => { if (e.target === overlay) close(false); };
  });
}

// ── Descarga un formato ──────────────────────────────────────────────────
async function ytDownload(fmt, id, ext, isAudio, btn) {
  if (ytActiveDownloads[id]) {
    ytActiveDownloads[id].dl?.abort();
    delete ytActiveDownloads[id];
    btn.textContent = '⬇ DL';
    btn.disabled = false;
    btn.classList.remove('done');
    document.getElementById(`${id}-prog`)?.classList.remove('show');
    setStatus('', 'Cancelado');
    return;
  }

  const prog  = document.getElementById(`${id}-prog`);
  const fill  = document.getElementById(`${id}-fill`);
  const txt   = document.getElementById(`${id}-txt`);
  const title = ytSafeFilename(ytData?.title || 'youtube_video');

  btn.textContent = '✕ Cancelar';
  prog?.classList.add('show');
  setStatus('busy', 'Descargando YT...');
  txt.textContent = 'Resolviendo URL...';

  let url;
  let activeFmt = fmt;
  let activeExt = ext;

  try {
    url = await ytHelper.resolveUrl(fmt, ytData?.playerUrl, ytData?.innertube, ytData?.videoId);
  } catch (e) {
    url = null;
  }

  // ── Fallback: si no se pudo resolver, ofrecer el mejor muxed ─────────
  if (!url && !isAudio) {
    btn.textContent = '⬇ DL';
    prog?.classList.remove('show');
    setStatus('err', 'URL no resuelta');

    const muxedFmt  = ytGetBestMuxed();
    const reqLabel  = ytHelper.videoQualityLabel(fmt);
    const fbLabel   = muxedFmt ? ytHelper.videoQualityLabel(muxedFmt) + ' (video+audio)' : null;

    if (muxedFmt && fbLabel) {
      const ok = await ytConfirmFallback(reqLabel, fbLabel);
      if (!ok) { setStatus('', ''); return; }

      // El usuario aceptó: resolver el muxed
      btn.textContent = '✕ Cancelar';
      prog?.classList.add('show');
      txt.textContent = 'Resolviendo URL alternativa...';
      setStatus('busy', 'Descargando fallback...');

      try {
        url = await ytHelper.resolveUrl(muxedFmt, ytData?.playerUrl, ytData?.innertube, ytData?.videoId);
      } catch (e) { url = null; }

      if (!url) {
        txt.textContent = '❌ Tampoco se pudo resolver el fallback';
        btn.textContent = '⬇ DL';
        prog?.classList.remove('show');
        toast('Error: no se pudo resolver ninguna URL', 'err');
        setStatus('err', 'Sin URL');
        return;
      }

      activeFmt = muxedFmt;
      activeExt = ytHelper.getExt(muxedFmt.mimeType, false);
    } else {
      txt.textContent = '❌ URL no disponible';
      toast('URL no disponible', 'err');
      setStatus('err', 'Sin URL');
      return;
    }
  }

  if (!url) {
    txt.textContent = '❌ URL no disponible';
    btn.textContent = '⬇ DL';
    prog?.classList.remove('show');
    toast('URL no disponible', 'err');
    setStatus('err', 'Sin URL');
    return;
  }

  const fname = `${title}.${activeExt}`;

  const dl = new VideoDownloader(
    (cur, total, label) => {
      const p = total > 0 ? Math.min(99, Math.round(cur / total * 100)) : 50;
      if (fill) fill.style.width = p + '%';
      if (txt)  txt.textContent  = label || `${p}%`;
    },
    msg => { if (txt) txt.textContent = msg; }
  );
  ytActiveDownloads[id] = { dl };

  try {
    const result = await dl.downloadDirect(url, fname);
    btn.textContent = '✓ Listo';
    btn.classList.add('done');
    btn.disabled = true;
    if (fill) fill.style.width = '100%';
    if (txt)  txt.textContent  = `✅ ${ytFmtSize(result.size) || 'Descargado'}`;
    const sizeEl = document.getElementById(`${id}-size`);
    if (sizeEl && result.size) sizeEl.textContent = ytFmtSize(result.size);
    setStatus('on', `✓ ${fname}`);
    toast(`✓ ${fname} guardado!`, 'ok');
  } catch (err) {
    btn.textContent = '⬇ DL';
    btn.disabled    = false;
    if (txt) txt.textContent = '❌ ' + err.message;
    setStatus('err', err.message.slice(0, 40));
    toast('Error: ' + err.message.slice(0, 50), 'err');
  } finally {
    delete ytActiveDownloads[id];
  }
}

// ── Carga (o recarga) datos de YouTube ───────────────────────────────────
// FIX: siempre limpia ytData y re-extrae; comprueba que el videoId coincida
// con el de la URL para evitar mostrar el video "anterior" en SPA navigation
async function ytLoad() {
  ytData = null;                     // ← limpiar siempre antes de cargar
  ytActiveDownloads = {};
  ytSetState('loading');

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab?.url?.includes('youtube.com/watch')) {
    ytSetState('not-yt');
    return;
  }

  const urlVideoId = new URL(tab.url).searchParams.get('v') || '';

  // Intentar hasta 3 veces (YouTube es SPA: ytInitialPlayerResponse
  // puede tener el video anterior durante un breve instante)
  let data = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    data = await ytHelper.extractFromTab(tab.id);
    if (data && !data.error && data.formats?.length) {
      // Si tenemos videoId, verificar que coincida con la URL
      if (!urlVideoId || !data.videoId || data.videoId === urlVideoId) break;
    }
    // Esperar y reintentar
    if (attempt < 2) await new Promise(r => setTimeout(r, 1200));
  }

  if (!data || data.error || !data.formats?.length) {
    const errEl = document.getElementById('yt-error-msg');
    if (errEl) errEl.textContent = data?.error
      || 'No se encontraron formatos. ¿Hay un video abierto en la pestaña?';
    ytSetState('error');
    return;
  }

  ytData = data;
  document.getElementById('yt-thumb-img').src          = data.thumbnail || '';
  document.getElementById('yt-video-title').textContent = data.title || '—';
  document.getElementById('yt-video-author').textContent= data.author || '—';
  document.getElementById('yt-video-dur').textContent   = data.lengthSeconds
    ? ytHelper.durationLabel(data.lengthSeconds) : '—';

  ytSetState('ready');
  ytRenderQualities();
  setTimeout(ytRenderQualitiesV7, 80);
}

// ── Toggle MP4 / MP3 ─────────────────────────────────────────────────────
document.querySelectorAll('.yt-fmt-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.yt-fmt-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    ytActiveFmt = btn.dataset.fmt;
    ytRenderQualities();
    setTimeout(ytRenderQualitiesV7, 80);
  });
});

// ── Activar la tab YouTube → siempre recargar ────────────────────────────
document.querySelector('.tabs').addEventListener('click', e => {
  const tab = e.target.closest('.tab');
  if (tab?.dataset.tab === 'youtube') setTimeout(ytLoad, 30);
});
// ═══════════════════════════════════════════════════════════


// ═══════════════════════════════════════════════════════════
// MERGE TAB — VideoSnatch v7
// ═══════════════════════════════════════════════════════════

const mergeVideoUrl = document.getElementById('mergeVideoUrl');
const mergeAudioUrl = document.getElementById('mergeAudioUrl');
const mergeName     = document.getElementById('mergeName');
const mergeBtn      = document.getElementById('mergeBtn');
const mergeProg     = document.getElementById('mergeProg');
const mergeFill     = document.getElementById('mergeFill');
const mergeTxt      = document.getElementById('mergeTxt');
const mergeLog      = document.getElementById('mergeLog');
let activeMerger    = null;

document.getElementById('mergeVideoPaste').addEventListener('click', async () => {
  try { mergeVideoUrl.value = await navigator.clipboard.readText(); mergeVideoUrl.classList.add('has-val'); } catch {}
});
document.getElementById('mergeAudioPaste').addEventListener('click', async () => {
  try { mergeAudioUrl.value = await navigator.clipboard.readText(); mergeAudioUrl.classList.add('has-val'); } catch {}
});
mergeVideoUrl.addEventListener('input', () => mergeVideoUrl.classList.toggle('has-val', !!mergeVideoUrl.value.trim()));
mergeAudioUrl.addEventListener('input', () => mergeAudioUrl.classList.toggle('has-val', !!mergeAudioUrl.value.trim()));

mergeBtn.addEventListener('click', async () => {
  // Cancelar si está activo
  if (activeMerger) {
    activeMerger.abort();
    activeMerger = null;
    mergeBtn.textContent = '⚡ UNIR';
    mergeBtn.disabled = false;
    mergeProg.classList.remove('show');
    setStatus('', 'Cancelado');
    return;
  }

  const vUrl = mergeVideoUrl.value.trim();
  const aUrl = mergeAudioUrl.value.trim();
  if (!vUrl || !aUrl) { toast('Ingresá ambas URLs', 'err'); return; }

  const title = mergeName.value.trim() || 'video_merged';
  mergeBtn.textContent = '✕ Cancelar';
  mergeBtn.disabled = false;
  mergeProg.classList.add('show');
  mergeFill.style.width = '0%';
  mergeLog.innerHTML = '';
  mergeTxt.textContent = 'Iniciando...';
  setStatus('busy', 'Uniendo streams...');

  const merger = new VideoMerger(
    (cur, total, label) => {
      mergeFill.style.width = Math.min(100, cur) + '%';
      mergeTxt.textContent = label || `${cur}%`;
    },
    msg => {
      mergeLog.innerHTML += msg + '<br>';
      mergeLog.scrollTop = mergeLog.scrollHeight;
    }
  );
  activeMerger = merger;

  try {
    const result = await merger.mergeVideoAudio(vUrl, aUrl, title);
    mergeBtn.textContent = '✓ Listo';
    mergeBtn.disabled = true;
    mergeFill.style.width = '100%';
    const merged = result.merged !== false;
    const sz = result.size > 0 ? ` (${(result.size/1024/1024).toFixed(1)} MB)` : '';
    mergeTxt.textContent = merged ? `✅ Unido correctamente${sz}` : `✅ Archivos descargados${sz}`;
    setStatus('on', merged ? '✓ Merge completo' : '✓ Archivos listos');
    toast(merged ? '✓ Video unido y guardado!' : '✓ Archivos descargados!', 'ok');
  } catch (err) {
    mergeBtn.textContent = '⚡ UNIR';
    mergeBtn.disabled = false;
    mergeTxt.textContent = '❌ ' + err.message;
    setStatus('err', err.message.slice(0, 40));
    toast('Error: ' + err.message.slice(0, 50), 'err');
  } finally {
    activeMerger = null;
  }
});


// ═══════════════════════════════════════════════════════════
// CONVERT TAB — VideoSnatch v7
// ═══════════════════════════════════════════════════════════

const convUrlEl   = document.getElementById('convUrl');
const convFileEl  = document.getElementById('convFile');
const convFileBtn = document.getElementById('convFileLbl');
const convNameEl  = document.getElementById('convName');
const convBtn     = document.getElementById('convBtn');
const convProg    = document.getElementById('convProg');
const convFill    = document.getElementById('convFill');
const convTxt     = document.getElementById('convTxt');
const convLog     = document.getElementById('convLog');
let convSelectedFmt   = 'mp4';
let convLocalFile     = null;
let activeConverter   = null;

// Formato buttons
document.querySelectorAll('.conv-fmt-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.conv-fmt-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    convSelectedFmt = btn.dataset.fmt;
    // Auto-update name extension
    const cur = convNameEl.value;
    if (cur) {
      convNameEl.value = cur.replace(/\.[^.]+$/, '') + '.' + convSelectedFmt;
    }
  });
});

// Archivo local
convFileEl.addEventListener('change', () => {
  const f = convFileEl.files[0];
  if (!f) return;
  convLocalFile = f;
  convUrlEl.value = '';
  document.getElementById('convFileIcon').textContent = '✅';
  document.getElementById('convFileName').textContent = f.name.slice(0, 35);
  convFileBtn.classList.add('has-file');
  // Sugerir nombre de salida
  const base = f.name.replace(/\.[^.]+$/, '');
  convNameEl.value = `${base}.${convSelectedFmt}`;
});

convUrlEl.addEventListener('input', () => {
  if (convUrlEl.value.trim()) {
    convLocalFile = null;
    document.getElementById('convFileIcon').textContent = '📂';
    document.getElementById('convFileName').textContent = 'Elegir archivo de video/audio';
    convFileBtn.classList.remove('has-file');
    // Sugerir nombre
    const parts = convUrlEl.value.split('/').pop().split('?')[0];
    const base = parts.replace(/\.[^.]+$/, '') || 'video';
    convNameEl.value = `${base}.${convSelectedFmt}`;
  }
});

convBtn.addEventListener('click', async () => {
  if (activeConverter) {
    activeConverter.abort();
    activeConverter = null;
    convBtn.textContent = '🔄 CONVERTIR';
    convBtn.disabled = false;
    convProg.classList.remove('show');
    setStatus('', 'Cancelado');
    return;
  }

  const url  = convUrlEl.value.trim();
  const file = convLocalFile;
  if (!url && !file) { toast('Ingresá una URL o elegí un archivo', 'err'); return; }

  const outName = convNameEl.value.trim() || `video.${convSelectedFmt}`;

  convBtn.textContent = '✕ Cancelar';
  convProg.classList.add('show');
  convFill.style.width = '0%';
  convLog.innerHTML = '';
  convTxt.textContent = 'Iniciando conversión...';
  setStatus('busy', 'Convirtiendo...');

  const converter = new FormatConverter(
    (cur, total, label) => {
      convFill.style.width = Math.min(100, total > 0 ? Math.round(cur/total*100) : cur) + '%';
      convTxt.textContent = label || `${cur}%`;
    },
    msg => {
      convLog.innerHTML += msg + '<br>';
      convLog.scrollTop = convLog.scrollHeight;
    }
  );
  activeConverter = converter;

  try {
    let result;
    if (file) {
      // Archivo local: convertir directamente desde Blob
      const srcBlob = new Blob([await file.arrayBuffer()], { type: file.type });
      const fmt = FormatConverter.FORMATS.find(f => f.id === convSelectedFmt);
      result = await converter.convertViaMediaRecorder(srcBlob, fmt.mime, fmt.ext, outName);
    } else {
      // URL remota
      result = await converter.convert(url, null, convSelectedFmt, outName.replace(/\.[^.]+$/, ''));
    }
    convBtn.textContent = '✓ Listo';
    convBtn.disabled = true;
    convFill.style.width = '100%';
    convTxt.textContent = result.size ? `✅ ${(result.size/1024/1024).toFixed(1)} MB guardado` : '✅ Conversión completa';
    setStatus('on', `✓ ${outName}`);
    toast(`✓ ${outName} convertido!`, 'ok');
  } catch (err) {
    convBtn.textContent = '🔄 CONVERTIR';
    convBtn.disabled = false;
    convTxt.textContent = '❌ ' + err.message;
    setStatus('err', err.message.slice(0, 40));
    toast('Error: ' + err.message.slice(0, 50), 'err');
  } finally {
    activeConverter = null;
  }
});


// ═══════════════════════════════════════════════════════════
// YOUTUBE — Botón MERGE en tarjetas "solo video"
// Modifica ytRenderQualities para agregar botón de merge en video-only
// ═══════════════════════════════════════════════════════════

// Reemplazar ytRenderQualities para agregar soporte de merge



function ytRenderQualitiesV7() {
  // Solo inyecta botones de merge en tarjetas "solo video" ya renderizadas
  if (ytActiveFmt !== 'mp4') return;
  if (!ytData) return;

  const { audioOnly, videoOnly } = ytHelper.groupFormats(ytData.formats);
  if (!videoOnly.length || !audioOnly.length) return;

  // Encontrar el mejor audio (m4a/aac si existe)
  const bestAudio = audioOnly[0];

  const listEl = document.getElementById('yt-quality-list');
  const rows = listEl.querySelectorAll('.yt-qrow');

  // Los videoOnly se renderizan después de los muxed
  const { muxed } = ytHelper.groupFormats(ytData.formats);
  const voStartIdx = muxed.length;

  rows.forEach((row, idx) => {
    if (idx < voStartIdx) return; // saltear muxed
    const voIdx = idx - voStartIdx;
    const fmt = videoOnly[voIdx];
    if (!fmt) return;

    // Agregar botón de merge y nota
    const inner = row.querySelector('.yt-qrow-inner');
    if (!inner) return;

    const mergeBtn2 = document.createElement('button');
    mergeBtn2.className = 'btn-yt-merge';
    mergeBtn2.textContent = '⚡ +AUDIO';
    mergeBtn2.title = 'Descargar video y audio por separado para unir';
    inner.appendChild(mergeBtn2);

    // Nota explicativa
    let note = row.querySelector('.yt-merge-note');
    if (!note) {
      note = document.createElement('div');
      note.className = 'yt-merge-note';
      note.textContent = '⚡ Descarga video + mejor audio para unir en la tab MERGE';
      row.appendChild(note);
    }

    mergeBtn2.addEventListener('click', async (e) => {
      e.stopPropagation();
      mergeBtn2.disabled = true;
      mergeBtn2.textContent = '...';
      setStatus('busy', 'Obteniendo URLs...');

      try {
        let vUrl = await ytHelper.resolveUrl(fmt, ytData?.playerUrl, ytData?.innertube, ytData?.videoId);
        let aUrl = await ytHelper.resolveUrl(bestAudio, ytData?.playerUrl, ytData?.innertube, ytData?.videoId);

        // ── Fallback: si el video HD no resolvió, ofrecer el muxed ────────
        if (!vUrl) {
          const muxedFmt = ytGetBestMuxed();
          const reqLabel = ytHelper.videoQualityLabel(fmt);
          const fbLabel  = muxedFmt ? ytHelper.videoQualityLabel(muxedFmt) + ' (video+audio)' : null;

          if (!muxedFmt || !fbLabel) throw new Error('No se pudo resolver la URL del video');

          mergeBtn2.disabled = true; // mantener deshabilitado durante el diálogo
          const ok = await ytConfirmFallback(reqLabel, fbLabel);
          if (!ok) {
            setStatus('', '');
            return; // finally lo re-habilita
          }

          // Usar el muxed como video (ya tiene audio integrado, no necesita merge)
          vUrl = await ytHelper.resolveUrl(muxedFmt, ytData?.playerUrl, ytData?.innertube, ytData?.videoId);
          if (!vUrl) throw new Error('Tampoco se pudo resolver el fallback');

          // Rellenar solo el campo de video (el muxed ya tiene audio)
          document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
          document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
          document.querySelector('[data-tab="merge"]').classList.add('active');
          document.getElementById('tab-merge').classList.add('active');

          mergeVideoUrl.value = vUrl;
          mergeVideoUrl.classList.add('has-val');
          mergeAudioUrl.value = '';
          mergeAudioUrl.classList.remove('has-val');

          const ql = ytHelper.videoQualityLabel(muxedFmt);
          mergeName.value = ytSafeFilename(ytData.title) + `_${ql}`;

          toast(`✓ URL cargada (${ql}) — ya tiene audio integrado`, 'ok');
          setStatus('on', 'URL cargada en MERGE');
          return;
        }

        if (!aUrl) throw new Error('No se pudieron resolver las URLs de audio');

        // Cambiar a tab MERGE y pre-rellenar
        document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(x => x.classList.remove('active'));
        document.querySelector('[data-tab="merge"]').classList.add('active');
        document.getElementById('tab-merge').classList.add('active');

        mergeVideoUrl.value = vUrl;
        mergeVideoUrl.classList.add('has-val');
        mergeAudioUrl.value = aUrl;
        mergeAudioUrl.classList.add('has-val');

        const ql = ytHelper.videoQualityLabel(fmt);
        mergeName.value = ytSafeFilename(ytData.title) + `_${ql}`;

        toast(`✓ URLs cargadas — pulsá UNIR`, 'ok');
        setStatus('on', 'URLs cargadas en MERGE');
      } catch (err) {
        toast('Error: ' + err.message.slice(0, 48), 'err');
        setStatus('err', err.message.slice(0, 40));
      } finally {
        mergeBtn2.disabled = false;
        mergeBtn2.textContent = '⚡ +AUDIO';
      }
    });
  });
}

// VideoSnatch v7 — merge + convert integrado

// ═══════════════════════════════════════════════════════════
// DIAGNÓSTICO YouTube — Tab MAN.
// ═══════════════════════════════════════════════════════════
document.getElementById('diagBtn')?.addEventListener('click', async () => {
  const out = document.getElementById('diagOut');
  out.style.display = 'block';
  out.textContent = '⏳ Analizando...\n';

  const log = (...args) => {
    out.textContent += args.join(' ') + '\n';
    out.scrollTop = out.scrollHeight;
  };

  try {
    // 1. ¿Hay datos de YT cargados?
    if (!ytData) {
      log('❌ ytData es null — abrí la tab YT primero para cargar el video.');
      return;
    }
    log(`✅ Video: ${ytData.title}`);
    log(`   videoId: ${ytData.videoId}`);
    log(`   playerUrl: ${ytData.playerUrl ? ytData.playerUrl.slice(0, 60) + '...' : 'null'}`);
    log(`   innertube.apiKey: ${ytData.innertube?.apiKey ? ytData.innertube.apiKey.slice(0,10) + '...' : 'null'}`);
    log(`   Formatos totales: ${ytData.formats?.length ?? 0}`);

    const { muxed, videoOnly, audioOnly } = ytHelper.groupFormats(ytData.formats);
    log(`   muxed: ${muxed.length}  videoOnly: ${videoOnly.length}  audioOnly: ${audioOnly.length}`);
    log('');

    // 2. ¿Se puede obtener el player JS?
    if (!ytData.playerUrl) {
      log('❌ playerUrl es null — YouTube no expuso la URL del player.');
      log('   Causa posible: extensión cargada en pestaña sin video abierto.');
      return;
    }

    log('⏳ Descargando player JS...');
    const playerJs = await ytHelper.fetchPlayerJs(ytData.playerUrl);
    if (!playerJs) {
      log('❌ No se pudo descargar el player JS.');
      return;
    }
    log(`✅ Player JS descargado: ${(playerJs.length / 1024).toFixed(0)} KB`);
    log('');

    // 3. ¿Se puede encontrar la función de descifrado?
    const mainFnName = ytHelper._findDecipherFnName(playerJs);
    log(`🔍 Función de descifrado: ${mainFnName || '❌ NO ENCONTRADA'}`);

    if (mainFnName) {
      const mainBody = ytHelper._extractNamedBlock(playerJs, mainFnName);
      log(`   Cuerpo (${mainBody ? mainBody.length + ' chars' : '❌ NO ENCONTRADO'})`);

      if (mainBody) {
        const helperRef = mainBody.match(/([a-zA-Z0-9$]{2,})\.[a-zA-Z0-9$]{2,}\s*\(/);
        const helperName = helperRef?.[1] || null;
        log(`   Helper object: ${helperName || '❌ NO ENCONTRADO'}`);

        if (helperName) {
          const helperBody = ytHelper._extractNamedBlock(playerJs, helperName);
          log(`   Helper body (${helperBody ? helperBody.length + ' chars' : '❌ NO ENCONTRADO'})`);

          // Intentar descifrar la firma de un formato con cipher
          const cipherFmt = [...muxed, ...videoOnly, ...audioOnly].find(f => f.signatureCipher);
          if (cipherFmt) {
            log('');
            log(`🔐 Probando descifrado con itag ${cipherFmt.itag} (${ytHelper.videoQualityLabel(cipherFmt) || 'audio'})...`);
            const params = new URLSearchParams(cipherFmt.signatureCipher);
            const s = params.get('s') || '';
            log(`   s (firma cifrada, primeros 20): ${s.slice(0, 20)}...`);
            const sig = ytHelper.decipherSignature(playerJs, s);
            log(`   Resultado: ${sig ? '✅ OK (' + sig.slice(0, 20) + '...)' : '❌ FALLÓ'}`);
          } else {
            log('ℹ No hay formatos con signatureCipher para probar.');
          }
        }
      }
    }
    log('');

    // 4. ¿Se puede encontrar la función n?
    let nFnName = null;
    const nPatterns = [
      /\.get\("n"\)\)&&\([a-zA-Z]=([a-zA-Z0-9$]{2,})\[\d+\]/,
      /\.get\("n"\)\)&&\([a-zA-Z]=([a-zA-Z0-9$]{2,})\(/,
      /[a-zA-Z]&&\([a-zA-Z]=([a-zA-Z0-9$]{2,})\[0\]\(/,
      /c=([a-zA-Z0-9$]{2,})\[0\]\(c\)/,
    ];
    for (const p of nPatterns) {
      const m = playerJs.match(p);
      if (m?.[1]) {
        const cand = m[1];
        const arrM = playerJs.match(new RegExp(`var\\s+${cand.replace(/[$]/g,'\\$')}\\s*=\\s*\\[([a-zA-Z0-9$]{2,})`));
        nFnName = arrM ? arrM[1] : cand;
        break;
      }
    }
    log(`🔍 Función anti-throttle (n): ${nFnName || '❌ NO ENCONTRADA'}`);
    if (nFnName) {
      const nBody = ytHelper._extractNamedBlock(playerJs, nFnName);
      log(`   Cuerpo n: ${nBody ? nBody.length + ' chars ✅' : '❌ NO ENCONTRADO'}`);
    }

    log('');
    log('── Fragmento del player JS (context de firma) ──');
    // Mostrar contexto alrededor de donde debería estar la función
    const ctxMatch = playerJs.match(/\.sig\s*\|\|[\s\S]{0,200}/);
    if (ctxMatch) log(ctxMatch[0].slice(0, 200));
    else log('(sin contexto .sig encontrado)');

  } catch(e) {
    log('💥 Error inesperado: ' + e.message);
    log(e.stack?.slice(0, 300) || '');
  }
});
