// content.js — VideoSnatch v7.0.5
// Extrae URLs de video del DOM/JS de la página
// Soporte: OK.ru, GoodStream, Cuevana, JWPlayer, Plyr, VideoJS y genérico

(function () {
  'use strict';

  // ── Helpers ──────────────────────────────────────────────────────────────

  function decodeHtmlEntities(str) {
    return str
      .replace(/&quot;/g, '"').replace(/&amp;/g, '&')
      .replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
  }

  function scanTextForVideoUrls(text) {
    const results = []; const seen = new Set();
    const re = /https?:\/\/[^\s"'<>\\]+\.(?:mp4|m3u8|webm|mpd)(?:[?#][^\s"'<>\\]*)?/gi;
    let m;
    while ((m = re.exec(text)) !== null) {
      const url = m[0].replace(/\\u0026/g, '&').replace(/\\\//g, '/');
      if (!seen.has(url)) { seen.add(url); results.push(url); }
    }
    return results;
  }

  // ── 1. Extraer datos de OK.ru embebidos en el HTML ──
  function extractOKruVideos() {
    const results = [];
    // OK.ru incrusta el JSON del player en un tag <script> o atributo data-
    // Buscar en todos los scripts inline
    document.querySelectorAll('script:not([src])').forEach(s => {
      const text = s.textContent;
      if (!text.includes('"videos"') && !text.includes('hlsManifestUrl')) return;

      // Intentar extraer el objeto JSON del player
      try {
        // Patrón 1: metadata en formato JSON directo
        const m1 = text.match(/"videos"\s*:\s*(\[[\s\S]+?\])/);
        if (m1) {
          const videos = JSON.parse(m1[1]);
          videos.forEach(v => {
            if (v.url && v.name && !v.disallowed) {
              results.push({ src: v.url, quality: v.name, seekSchema: v.seekSchema });
            }
          });
        }
        // Patrón 2: hlsManifestUrl
        const m2 = text.match(/"hlsManifestUrl"\s*:\s*"([^"]+)"/);
        if (m2) results.push({ src: m2[1], quality: 'hls', seekSchema: 0 });
      } catch {}
    });

    // Buscar en atributos data- de elementos del player
    document.querySelectorAll('[data-options],[data-module-data],[data-player]').forEach(el => {
      try {
        const raw = el.dataset.options || el.dataset.moduleData || el.dataset.player || '';
        if (!raw.includes('videos')) return;
        // Puede estar HTML-encoded
        const decoded = raw
          .replace(/&quot;/g, '"')
          .replace(/&amp;/g, '&')
          .replace(/&#39;/g, "'");
        const json = JSON.parse(decoded);

        const findVideos = (obj) => {
          if (!obj || typeof obj !== 'object') return;
          if (Array.isArray(obj.videos)) {
            obj.videos.forEach(v => {
              if (v.url && v.name && !v.disallowed) {
                results.push({ src: v.url, quality: v.name, seekSchema: v.seekSchema || 0 });
              }
            });
          }
          if (obj.hlsManifestUrl) results.push({ src: obj.hlsManifestUrl, quality: 'hls' });
          Object.values(obj).forEach(v => { if (v && typeof v === 'object') findVideos(v); });
        };
        findVideos(json);
      } catch {}
    });

    // Buscar en window.__VIDEO_DATA__ y similares
    try {
      const pageText = document.documentElement.innerHTML;
      // Patrón específico de OK.ru embed
      const okMatch = pageText.match(/\\&quot;videos\\&quot;:\[([\s\S]+?)\\&quot;vkMovie/);
      if (okMatch) {
        // Reconstruir JSON decodificando el escape doble
        const raw = okMatch[1]
          .replace(/\\&quot;/g, '"')
          .replace(/\\\\u0026/g, '&')
          .replace(/\\"/g, '"');

        const entries = raw.match(/\{[^}]+\}/g) || [];
        entries.forEach(entry => {
          try {
            // Parsear manualmente los campos
            const nameM = entry.match(/"name"\s*:\s*"(\w+)"/);
            const urlM = entry.match(/"url"\s*:\s*"([^"]+)"/);
            const seekM = entry.match(/"seekSchema"\s*:\s*(\d+)/);
            const disM = entry.match(/"disallowed"\s*:\s*(true|false)/);
            if (nameM && urlM && disM?.[1] !== 'true') {
              results.push({
                src: urlM[1],
                quality: nameM[1],
                seekSchema: seekM ? parseInt(seekM[1]) : 0
              });
            }
          } catch {}
        });

        // HLS manifest
        const hlsM = pageText.match(/\\&quot;hlsManifestUrl\\&quot;:\\&quot;(https:\/\/[^\\]+)/);
        if (hlsM) {
          results.push({
            src: hlsM[1].replace(/\\\\u0026/g, '&'),
            quality: 'hls',
            seekSchema: 0
          });
        }
      }
    } catch {}

    return results;
  }

  // ── 2. GoodStream ────────────────────────────────────────────────────────
  function extractGoodStreamVideos() {
    const results = []; const seen = new Set();
    const add = (src, quality = 'video') => {
      if (!src || seen.has(src) || src.startsWith('blob:')) return;
      seen.add(src); results.push({ src, quality });
    };

    // Variables globales del player
    try {
      const gs = window.player_data || window.playerData || window.streams
               || window.jwplayer_data || window.setup_data || null;
      if (gs) {
        if (gs.file) add(gs.file, gs.label || 'video');
        if (Array.isArray(gs.sources)) gs.sources.forEach(s => add(s.file || s.src, s.label || 'video'));
        if (Array.isArray(gs.playlist)) gs.playlist.forEach(p => {
          if (p.file) add(p.file, p.label || 'video');
          if (Array.isArray(p.sources)) p.sources.forEach(s => add(s.file || s.src, s.label || 'video'));
        });
      }
    } catch {}

    // Scripts inline
    document.querySelectorAll('script:not([src])').forEach(s => {
      const text = s.textContent; if (!text) return;

      // jwplayer().setup({ ... })
      const jwSetup = text.match(/\.setup\s*\(\s*(\{[\s\S]+?\})\s*\)/);
      if (jwSetup) {
        try {
          const obj = Function('"use strict"; return (' + jwSetup[1] + ')')();
          if (obj?.file) add(obj.file, obj.label || 'video');
          (obj?.sources || []).forEach(s => add(s.file || s.src, s.label || 'video'));
          (obj?.playlist || []).forEach(p => {
            if (p.file) add(p.file, p.label || 'video');
            (p.sources || []).forEach(s => add(s.file || s.src, s.label || 'video'));
          });
        } catch {}
      }

      // var sources = [...]
      const srcArr = text.match(/(?:var|let|const)\s+\w*[Ss]ources?\s*=\s*(\[[\s\S]+?\])\s*[;,)]/);
      if (srcArr) {
        try {
          const arr = Function('"use strict"; return ' + srcArr[1])();
          if (Array.isArray(arr)) arr.forEach(s => add(s.file || s.src || s.url, s.label || s.quality || 'video'));
        } catch {}
      }

      // "file":"https://...mp4"
      const fileRe = /"file"\s*:\s*"(https?:\/\/[^"]+\.(?:mp4|m3u8|webm)[^"]*)"/gi;
      let fm; while ((fm = fileRe.exec(text)) !== null) add(fm[1].replace(/\\u0026/g,'&'), 'video');

      // src:"https://..."
      const srcRe = /\bsrc\s*:\s*["'](https?:\/\/[^"']+\.(?:mp4|m3u8|webm)[^"']*)["']/gi;
      let sm; while ((sm = srcRe.exec(text)) !== null) add(sm[1], 'video');

      // window.streams = { 1080: "url", 720: "url" }
      const winStreams = text.match(/window\.streams\s*=\s*(\{[\s\S]+?\})\s*;/);
      if (winStreams) {
        try {
          const obj = Function('"use strict"; return (' + winStreams[1] + ')')();
          Object.entries(obj).forEach(([k, v]) => { if (typeof v === 'string') add(v, k + 'p'); });
        } catch {}
      }

      // var player_data = {...}
      const pdMatch = text.match(/(?:var|let|const)\s+player_data\s*=\s*(\{[\s\S]+?\})\s*;/);
      if (pdMatch) {
        try {
          const obj = Function('"use strict"; return (' + pdMatch[1] + ')')();
          if (obj?.file) add(obj.file, 'video');
          (obj?.sources || []).forEach(s => add(s.file || s.src, s.label || 'video'));
        } catch {}
      }

      scanTextForVideoUrls(text).forEach(u => add(u, 'video'));
    });

    // Atributos data-
    document.querySelectorAll('[data-file],[data-src],[data-source],[data-config]').forEach(el => {
      ['data-file','data-src','data-source'].forEach(attr => {
        const val = el.getAttribute(attr);
        if (val && /https?:\/\/.+\.(mp4|m3u8|webm)/i.test(val)) add(val, 'video');
      });
      const cfg = el.getAttribute('data-config');
      if (cfg) {
        try {
          const obj = JSON.parse(decodeHtmlEntities(cfg));
          if (obj?.file) add(obj.file, 'video');
          (obj?.sources || []).forEach(s => add(s.file || s.src, s.label || 'video'));
        } catch {}
      }
    });

    return results;
  }

  // ── 3. Cuevana ───────────────────────────────────────────────────────────
  // Lista de CDNs / players usados por Cuevana y sitios similares (actualizada)
  const CUEVANA_PLAYER_RE = /goodstream|streamtape|filemoon|doodstream|mixdrop|upstream|voe\.sx|mp4upload|uqload|streamwish|wishembed|filelions|vidmoly|vidsrc|vidhide|vidlox|vtube|embedsito|streamruby|streamvid|smoothpre|embedrise|ridoo|dropload|turboplay|dlions|streamcastle|highstream|vipstream|nuvid|supervideo|sendvid|waaw\.tv|fembed|ok\.ru\/videoembed|gvideo|gmovies|edytjedhz|hydrax|vidhide|streamhub|streamlare|streamm4u|cinegrab|videovard|vave\.cc|playm4u|ythd|adblockeronstape/i;

  function extractCuevanaVideos() {
    const results = []; const seen = new Set();
    const add = (src, quality = 'video', extra = {}) => {
      if (!src || seen.has(src) || src.startsWith('blob:')) return;
      seen.add(src); results.push({ src, quality, ...extra });
    };

    // Iframes de reproductores externos
    document.querySelectorAll('iframe[src],iframe[data-src]').forEach(fr => {
      const src = fr.src || fr.dataset.src || '';
      if (!src || src.startsWith('about:') || src.startsWith('javascript:')) return;
      if (CUEVANA_PLAYER_RE.test(src))
        add(src, 'embed-iframe');
    });

    // Scripts inline
    document.querySelectorAll('script:not([src])').forEach(s => {
      const text = s.textContent; if (!text) return;

      // var videos = { "1080p": "url" }
      const vidsMatch = text.match(/(?:var|let|const)\s+\w*[Vv]ideos?\s*=\s*(\{[\s\S]+?\})\s*[;,]/);
      if (vidsMatch) {
        try {
          const obj = Function('"use strict"; return (' + vidsMatch[1] + ')')();
          Object.entries(obj).forEach(([k, v]) => { if (typeof v === 'string' && /https?:\/\//.test(v)) add(v, k); });
        } catch {}
      }

      // sources = [...]
      const sourcesMatch = text.match(/[Ss]ources?\s*[=:]\s*(\[[\s\S]+?\])\s*[;,)]/);
      if (sourcesMatch) {
        try {
          const arr = Function('"use strict"; return ' + sourcesMatch[1])();
          if (Array.isArray(arr)) arr.forEach(s => {
            const u = s.file || s.src || s.url || (typeof s === 'string' ? s : null);
            if (u) add(u, s.label || s.quality || 'video');
          });
        } catch {}
      }

      // window.__NUXT__ / __NEXT_DATA__
      const nuxtMatch = text.match(/window\.__(?:NUXT|NEXT_DATA|APP_STATE)__\s*=\s*(\{[\s\S]+)/);
      if (nuxtMatch) {
        try {
          const obj = JSON.parse(nuxtMatch[1].replace(/;?\s*$/, ''));
          const crawl = (node, depth = 0) => {
            if (depth > 12 || !node || typeof node !== 'object') return;
            if (typeof node.url  === 'string' && /\.(mp4|m3u8|webm)/i.test(node.url))  add(node.url,  node.quality || node.label || 'video');
            if (typeof node.file === 'string' && /\.(mp4|m3u8|webm)/i.test(node.file)) add(node.file, 'video');
            // Cuevana almacena URLs de iframe en campos como "embed", "server", "link"
            if (typeof node.embed === 'string' && /https?:\/\//.test(node.embed) && CUEVANA_PLAYER_RE.test(node.embed)) add(node.embed, 'embed-iframe');
            if (typeof node.link  === 'string' && /https?:\/\//.test(node.link)  && CUEVANA_PLAYER_RE.test(node.link))  add(node.link,  'embed-iframe');
            Object.values(node).forEach(v => crawl(v, depth + 1));
          };
          crawl(obj);
        } catch {}
      }

      scanTextForVideoUrls(text).forEach(u => add(u, 'video'));
    });

    // Cuevana Next.js: leer el tag <script id="__NEXT_DATA__" type="application/json">
    try {
      const nextDataEl = document.getElementById('__NEXT_DATA__');
      if (nextDataEl) {
        const obj = JSON.parse(nextDataEl.textContent);
        const crawl = (node, depth = 0) => {
          if (depth > 15 || !node || typeof node !== 'object') return;
          if (typeof node.url   === 'string' && /\.(mp4|m3u8|webm)/i.test(node.url))   add(node.url,   node.quality || node.label || 'video');
          if (typeof node.file  === 'string' && /\.(mp4|m3u8|webm)/i.test(node.file))  add(node.file,  'video');
          if (typeof node.embed === 'string' && CUEVANA_PLAYER_RE.test(node.embed)) add(node.embed, 'embed-iframe');
          if (typeof node.link  === 'string' && CUEVANA_PLAYER_RE.test(node.link))  add(node.link,  'embed-iframe');
          if (typeof node.server=== 'string' && CUEVANA_PLAYER_RE.test(node.server))add(node.server,'embed-iframe');
          // Algunos schemas usan arrays de {option, embed}
          if (Array.isArray(node)) node.forEach(v => crawl(v, depth + 1));
          else Object.values(node).forEach(v => crawl(v, depth + 1));
        };
        crawl(obj);
      }
    } catch {}

    // Escaneo del HTML completo
    scanTextForVideoUrls(document.documentElement.innerHTML).forEach(u => add(u, 'video'));

    return results;
  }

  // ── 4. Extraer <video> elements ──
  function extractVideoElements() {
    const results = [];
    document.querySelectorAll('video').forEach(v => {
      const srcs = [];
      if (v.src && !v.src.startsWith('blob:')) srcs.push(v.src);
      v.querySelectorAll('source').forEach(s => { if (s.src) srcs.push(s.src); });
      srcs.forEach(src => {
        results.push({
          src,
          poster: v.poster || null,
          duration: isFinite(v.duration) ? Math.round(v.duration) : null,
          width: v.videoWidth || null,
          height: v.videoHeight || null
        });
      });
    });
    return results;
  }

  // ── 5. Escuchar mensajes desde popup ──
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'EXTRACT_VIDEOS') {
      const okVideos         = extractOKruVideos();
      const goodStreamVideos = extractGoodStreamVideos();
      const cuevanaVideos    = extractCuevanaVideos();
      const domVideos        = extractVideoElements();
      sendResponse({ okVideos, goodStreamVideos, cuevanaVideos, domVideos });
      return true;
    }
  });

  // ── 6. Interceptar XHR/fetch para capturar URLs de video dinámicas ──
  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    if (typeof url === 'string' && /\.(m3u8|mpd|mp4|webm)/i.test(url)) {
      chrome.runtime.sendMessage({ type: 'VIDEO_FOUND', url }).catch(() => {});
    }
    return _open.apply(this, arguments);
  };

  // Interceptar fetch nativo — capturar también mp4 y APIs de Cuevana/Streamwish
  const _fetch = window.fetch;
  window.fetch = function(input, init) {
    const url = typeof input === 'string' ? input : input?.url || '';
    if (/\.(m3u8|mpd|mp4|webm)/i.test(url)) {
      chrome.runtime.sendMessage({ type: 'VIDEO_FOUND', url }).catch(() => {});
    }
    // Interceptar respuestas JSON de APIs de reproductores (Streamwish, etc.)
    const result = _fetch.apply(this, arguments);
    if (/api|embed|player|stream|source/i.test(url)) {
      result.then(r => {
        if (!r.ok) return;
        const ct = r.headers.get('content-type') || '';
        if (!ct.includes('application/json')) return;
        r.clone().json().then(data => {
          // Buscar URLs de video en la respuesta JSON
          const scan = (obj, d = 0) => {
            if (d > 6 || !obj || typeof obj !== 'object') return;
            if (typeof obj === 'string' && /https?:\/\/.+\.(mp4|m3u8|webm)/i.test(obj))
              chrome.runtime.sendMessage({ type: 'VIDEO_FOUND', url: obj }).catch(() => {});
            Object.values(obj).forEach(v => scan(v, d + 1));
          };
          scan(data);
        }).catch(() => {});
      }).catch(() => {});
    }
    return result;
  };

  // ── 7. Observer para videos e iframes añadidos dinámicamente ──
  const observer = new MutationObserver(muts => {
    muts.forEach(m => m.addedNodes.forEach(n => {
      if (n.nodeName === 'VIDEO' && n.src && !n.src.startsWith('blob:')) {
        chrome.runtime.sendMessage({ type: 'VIDEO_FOUND', url: n.src }).catch(() => {});
      }
      if (n.nodeName === 'IFRAME') {
        const src = n.src || n.dataset?.src || '';
        if (src && /goodstream|streamtape|filemoon|doodstream/i.test(src))
          chrome.runtime.sendMessage({ type: 'VIDEO_FOUND', url: src }).catch(() => {});
      }
    }));
  });
  if (document.body) observer.observe(document.body, { childList: true, subtree: true });

})();
