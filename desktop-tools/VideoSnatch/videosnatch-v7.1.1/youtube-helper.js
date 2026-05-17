// youtube-helper.js — VideoSnatch YouTube Integration v5 (7.0.5)
// Fix 7.0.5: patrones de descifrado de firma y anti-throttle (n) actualizados
// para el player JS moderno de YouTube (2024-2025).
// Fix previo (7.0.3): extractor de cuerpos de función con conteo de llaves
// balanceadas para no cortarse ante objetos/funciones anidadas.

class YouTubeHelper {
  constructor() {
    this._playerCache = new Map();
  }

  // ── Extrae datos del player desde la pestaña (world: MAIN) ──────────────
  async extractFromTab(tabId) {
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId },
        world: 'MAIN',
        func: () => {
          try {
            const pr = window.ytInitialPlayerResponse
              || window.ytplayer?.config?.args?.player_response_dict
              || null;
            if (!pr?.streamingData) return null;

            const d  = pr.videoDetails || {};
            const sd = pr.streamingData;

            let playerUrl = null;
            let innertube = null;

            try {
              playerUrl = window.yt?.config_?.PLAYER_JS_URL
                || document.querySelector('script[src*="/base.js"]')?.src
                || document.querySelector('script[src*="player/"]')?.src
                || null;
            } catch {}

            try {
              const cfg  = window.yt?.config_ || {};
              const icfg = window.ytcfg?.data_ || {};
              innertube = {
                apiKey:    cfg.INNERTUBE_API_KEY        || icfg.INNERTUBE_API_KEY        || null,
                clientVer: cfg.INNERTUBE_CLIENT_VERSION || icfg.INNERTUBE_CLIENT_VERSION || null,
                visitorId: cfg.VISITOR_DATA             || icfg.VISITOR_DATA             || null,
              };
            } catch {}

            return {
              videoId:       d.videoId || '',
              title:         d.title || 'YouTube Video',
              author:        d.author || '',
              thumbnail:     (d.thumbnail?.thumbnails || []).slice(-1)[0]?.url || '',
              lengthSeconds: parseInt(d.lengthSeconds || 0),
              playerUrl,
              innertube,
              formats: [
                ...(sd.formats || []),
                ...(sd.adaptiveFormats || [])
              ].map(f => ({
                itag:            f.itag,
                url:             f.url || null,
                signatureCipher: f.signatureCipher || f.cipher || null,
                mimeType:        f.mimeType || '',
                bitrate:         f.bitrate || 0,
                averageBitrate:  f.averageBitrate || 0,
                qualityLabel:    f.qualityLabel || '',
                quality:         f.quality || '',
                audioQuality:    f.audioQuality || null,
                audioChannels:   f.audioChannels || 0,
                width:           f.width || 0,
                height:          f.height || 0,
                fps:             f.fps || 0,
                contentLength:   f.contentLength ? parseInt(f.contentLength) : 0
              }))
            };
          } catch (e) {
            return { error: e.message };
          }
        }
      });
      return results?.[0]?.result || null;
    } catch (e) {
      return { error: e.message };
    }
  }

  // ── Descarga y cachea el player JS ──────────────────────────────────────
  async fetchPlayerJs(playerUrl) {
    if (!playerUrl) return null;
    const url = playerUrl.startsWith('//')
      ? 'https:' + playerUrl
      : playerUrl.startsWith('/')
        ? 'https://www.youtube.com' + playerUrl
        : playerUrl;

    if (this._playerCache.has(url)) return this._playerCache.get(url);
    try {
      const r = await fetch(url);
      if (!r.ok) return null;
      const js = await r.text();
      this._playerCache.set(url, js);
      return js;
    } catch { return null; }
  }

  // ── Extrae el bloque balanceado {…} a partir de un índice de apertura ────
  // Maneja llaves anidadas y strings JS para no cortar prematuramente.
  _extractBalancedBlock(src, startIdx) {
    let depth = 0;
    let inStr = null;  // '"' | "'" | '`'
    for (let i = startIdx; i < src.length; i++) {
      const c = src[i];
      if (inStr) {
        if (c === '\\') { i++; continue; } // escape
        if (c === inStr) inStr = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') { inStr = c; continue; }
      if (c === '{') { depth++; continue; }
      if (c === '}') {
        depth--;
        if (depth === 0) return src.slice(startIdx + 1, i); // contenido sin llaves externas
      }
    }
    return null;
  }

  // ── Busca la primera '{' de una función/objeto por nombre ─────────────────
  // Devuelve el cuerpo interior o null
  _extractNamedBlock(src, name) {
    const esc = name.replace(/[$]/g, '\\$');
    // Patrones que terminan justo antes de la '{' de apertura
    const leads = [
      new RegExp(`(?:var|let|const)\\s+${esc}\\s*=\\s*\\{`, 'g'),
      new RegExp(`${esc}\\s*=\\s*function\\s*\\([^)]*\\)\\s*\\{`, 'g'),
      new RegExp(`function\\s+${esc}\\s*\\([^)]*\\)\\s*\\{`, 'g'),
      new RegExp(`${esc}\\s*=\\s*\\{`, 'g'),
      // Arrow functions: fnName = (a) => { ... }  o  fnName = a => {
      new RegExp(`${esc}\\s*=\\s*(?:\\([^)]*\\)|[a-zA-Z0-9$]+)\\s*=>\\s*\\{`, 'g'),
      // Propiedad en objeto: fnName:function(...){  o  fnName(...){
      new RegExp(`[,{;]\\s*${esc}\\s*:\\s*function\\s*\\([^)]*\\)\\s*\\{`, 'g'),
      new RegExp(`[,{;(]\\s*${esc}\\s*\\([^)]*\\)\\s*\\{`, 'g'),
    ];
    for (const re of leads) {
      let m;
      while ((m = re.exec(src)) !== null) {
        // La '{' de apertura está al final del match
        const openIdx = m.index + m[0].length - 1;
        const body = this._extractBalancedBlock(src, openIdx);
        if (body !== null) return body;
      }
    }
    return null;
  }

  // ── Encuentra el nombre de la función de descifrado de firma ─────────────
  _findDecipherFnName(playerJs) {
    const patterns = [
      // Patrones modernos 2024-2025: busca la función que hace a.split("")...join("")
      /\b([a-zA-Z0-9$]{2,})\s*=\s*function\s*\([a-zA-Z0-9$]\)\s*\{\s*[a-zA-Z0-9$]\s*=\s*[a-zA-Z0-9$]\.split\(["']{2}\)[\s\S]{0,300}\.join\(["']{2}\)/,
      // Variante: asignación con split("") directamente en la firma
      /(?:^|[,;(\s])([a-zA-Z0-9$]{2,})\s*=\s*function\s*\(\s*[a-zA-Z0-9$]\s*\)\s*\{\s*[a-zA-Z0-9$]+\s*=\s*[a-zA-Z0-9$]+\.split\(["']{2}\)/m,
      // Patrones clásicos (siguen apareciendo en variantes del player)
      /\bc\s*&&\s*d\.set\([^,]+,\s*\([^)]*\)\s*\(\s*([a-zA-Z0-9$]{2,})\s*\(/,
      /\bc&&d\.set\([^,]+,([a-zA-Z0-9$]{2,})\(/,
      /\.sig\s*\|\|\s*([a-zA-Z0-9$]{2,})\s*\(/,
      /\bm=([a-zA-Z0-9$]{2,})\(decodeURIComponent\(h\.s\)\)/,
      /\.set\([^,]+,\s*encodeURIComponent\(\s*([a-zA-Z0-9$]{2,})\(/,
      /\bsig\s*=\s*([a-zA-Z0-9$]{2,})\([^)]+\)/,
      /\("signature"\)\s*,\s*([a-zA-Z0-9$]{2,})\s*\(/,
      /a\[b\]&&\(c=([a-zA-Z0-9$]{2,})\(decodeURIComponent/,
      // Variante con sp= en signatureCipher
      /[a-zA-Z0-9$]\s*=\s*([a-zA-Z0-9$]{2,})\s*\(\s*decodeURIComponent\s*\([a-zA-Z0-9$]\.s\)\)/,
      // Variante moderna: encodeURIComponent aplicado al resultado
      /encodeURIComponent\s*\(\s*([a-zA-Z0-9$]{2,})\s*\(\s*decodeURIComponent/,
    ];
    for (const p of patterns) {
      const m = playerJs.match(p);
      if (m?.[1]) return m[1];
    }
    return null;
  }

  // ── Descifra la firma (signatureCipher) ──────────────────────────────────
  decipherSignature(playerJs, scrambled) {
    if (!playerJs || !scrambled) return null;
    try {
      const mainFnName = this._findDecipherFnName(playerJs);
      if (!mainFnName) {
        console.warn('[YT][sig] Nombre de función principal no encontrado');
        return null;
      }

      const mainBody = this._extractNamedBlock(playerJs, mainFnName);
      if (!mainBody) {
        console.warn('[YT][sig] Cuerpo de función principal no encontrado para:', mainFnName);
        return null;
      }

      // Buscar el objeto helper dentro del cuerpo (ej: "Ab.split", "Cd.reverse")
      const helperRef = mainBody.match(/([a-zA-Z0-9$]{2,})\.[a-zA-Z0-9$]{2,}\s*\(/);
      if (!helperRef) {
        console.warn('[YT][sig] Referencia al helper no encontrada en body');
        return null;
      }
      const helperName = helperRef[1];

      const helperBody = this._extractNamedBlock(playerJs, helperName);
      if (!helperBody) {
        console.warn('[YT][sig] Cuerpo del helper no encontrado para:', helperName);
        return null;
      }

      // Reconstruir la función en un scope aislado
      const code = `(function(){
        var ${helperName}={${helperBody}};
        function ${mainFnName}(a){${mainBody}}
        return ${mainFnName}(${JSON.stringify(scrambled)});
      })()`;

      return new Function('return ' + code)();
    } catch (e) {
      console.warn('[YT][sig] Error:', e.message);
      return null;
    }
  }

  // ── Descifra parámetro 'n' anti-throttle ────────────────────────────────
  decipherNsig(playerJs, n) {
    if (!playerJs || !n) return n;
    try {
      let nFnName = null;
      const nPatterns = [
        // Modernos 2024-2025: el nombre puede estar en un array o llamarse directamente
        /\.get\("n"\)\)&&\([a-zA-Z0-9$]=[a-zA-Z0-9$]\.get\("n"\)\)&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\[(\d+)\]/,
        /\.get\("n"\)\)&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\[(\d+)\]\([a-zA-Z0-9$]\)/,
        /\.get\("n"\)\)&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\[\d+\]/,
        /\.get\("n"\)\)&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\(/,
        /[a-zA-Z0-9$]&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\[0\]\(/,
        /\([a-zA-Z0-9$]="n"\)&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\(/,
        /c=([a-zA-Z0-9$]{2,})\[0\]\(c\)/,
        // Variante: asignación directa con &&
        /&&\([a-zA-Z0-9$]=([a-zA-Z0-9$]{2,})\(\s*[a-zA-Z0-9$]\s*\)\s*,\s*[a-zA-Z0-9$]\.set\("n"/,
        // Variante moderna: nombre de función en variable separada
        /;([a-zA-Z0-9$]{2,})\s*=\s*([a-zA-Z0-9$]{2,})\s*\(\s*([a-zA-Z0-9$]{2,})\s*\)\s*;[a-zA-Z0-9$]+\.set\("n"/,
      ];
      for (const p of nPatterns) {
        const m = playerJs.match(p);
        if (m?.[1]) {
          const cand = m[1];
          // Puede estar guardado en un array: var Xx=[fnName]
          const arrM = playerJs.match(new RegExp(`var\\s+${cand.replace(/[$]/g,'\\$')}\\s*=\\s*\\[([a-zA-Z0-9$]{2,})`));
          nFnName = arrM ? arrM[1] : cand;
          break;
        }
      }
      if (!nFnName) return n;

      const nBody = this._extractNamedBlock(playerJs, nFnName);
      if (!nBody) return n;

      const result = new Function(`return (function(a){${nBody}})(${JSON.stringify(n)})`)();
      return (typeof result === 'string' && result.length > 0) ? result : n;
    } catch(e) {
      console.warn('[YT][nsig] Error:', e.message);
      return n;
    }
  }

  // ── Aplica fix n a una URL ────────────────────────────────────────────────
  async _fixN(url, playerJs) {
    if (!playerJs || !url) return url;
    try {
      const u = new URL(url);
      const n = u.searchParams.get('n');
      if (!n) return url;
      const nFixed = this.decipherNsig(playerJs, n);
      if (nFixed && nFixed !== n) u.searchParams.set('n', nFixed);
      return u.toString();
    } catch { return url; }
  }

  // ── Fallback InnerTube API ───────────────────────────────────────────────
  async _tryInnertubeFallback(videoId, itag, innertube) {
    if (!videoId || !itag || !innertube?.apiKey) return null;
    try {
      const clientVer = innertube.clientVer || '2.20240101.00.00';
      const resp = await fetch(
        `https://www.youtube.com/youtubei/v1/player?key=${innertube.apiKey}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-YouTube-Client-Name': '1',
            'X-YouTube-Client-Version': clientVer,
          },
          credentials: 'include',
          body: JSON.stringify({
            videoId,
            context: {
              client: {
                clientName: 'WEB',
                clientVersion: clientVer,
                visitorData: innertube.visitorId || '',
              }
            }
          })
        }
      );
      if (!resp.ok) return null;
      const data = await resp.json();
      const all = [
        ...(data.streamingData?.formats || []),
        ...(data.streamingData?.adaptiveFormats || []),
      ];
      const match = all.find(f => f.itag === itag);
      if (match?.url) {
        console.log('[YT][innertube] URL directa obtenida para itag', itag);
        return match.url;
      }
      // Si también viene con cipher en la respuesta InnerTube, intentar descifrarlo
      if (match?.signatureCipher) {
        console.log('[YT][innertube] Cipher en respuesta InnerTube, intentando descifrar...');
        return null; // el caller lo manejará
      }
      return null;
    } catch(e) {
      console.warn('[YT][innertube] Error:', e.message);
      return null;
    }
  }

  // ── Resuelve la URL final de un formato ─────────────────────────────────
  async resolveUrl(format, playerUrl, innertube, videoId) {
    const playerJs = playerUrl ? await this.fetchPlayerJs(playerUrl) : null;

    // URL directa — formatos muxed (360p, etc.)
    if (format.url) {
      return this._fixN(format.url, playerJs);
    }

    if (!format.signatureCipher) return null;

    const params = new URLSearchParams(format.signatureCipher);
    const s   = params.get('s') || '';
    const sp  = params.get('sp') || 'signature';
    const url = decodeURIComponent(params.get('url') || '');
    if (!url) return null;

    let finalUrl = url;

    if (s) {
      if (!playerJs) {
        console.warn('[YT] Sin playerJs — intentando InnerTube...');
        if (videoId && innertube) {
          const fbUrl = await this._tryInnertubeFallback(videoId, format.itag, innertube);
          if (fbUrl) return this._fixN(fbUrl, playerJs);
        }
        return null;
      }

      const sig = this.decipherSignature(playerJs, s);
      if (sig) {
        finalUrl = `${url}&${sp}=${encodeURIComponent(sig)}`;
      } else {
        console.warn('[YT] Descifrado fallido — intentando InnerTube...');
        if (videoId && innertube) {
          const fbUrl = await this._tryInnertubeFallback(videoId, format.itag, innertube);
          if (fbUrl) return this._fixN(fbUrl, playerJs);
        }
        console.warn('[YT] Todos los métodos fallaron para itag', format.itag);
        return null;
      }
    }

    return this._fixN(finalUrl, playerJs);
  }

  // ── Utilidades ───────────────────────────────────────────────────────────
  _codecFamily(mimeType) {
    if (mimeType.includes('mp4') || mimeType.includes('m4a') || mimeType.includes('avc') || mimeType.includes('aac')) return 'mp4';
    if (mimeType.includes('webm') || mimeType.includes('vp9') || mimeType.includes('opus')) return 'webm';
    return 'other';
  }

  getExt(mimeType, isAudio) {
    const f = this._codecFamily(mimeType);
    if (isAudio) return f === 'mp4' ? 'm4a' : 'webm';
    return f === 'mp4' ? 'mp4' : 'webm';
  }

  groupFormats(formats) {
    const muxed = [], audioOnly = [], videoOnly = [];
    for (const f of formats) {
      const mime = f.mimeType || '';
      if (mime.startsWith('video/') && f.audioQuality)   muxed.push(f);
      else if (mime.startsWith('video/') && !f.audioQuality) videoOnly.push(f);
      else if (mime.startsWith('audio/'))                 audioOnly.push(f);
    }

    const muxedMap = new Map();
    for (const f of muxed) {
      const key = `${f.height}_${f.fps}`;
      if (!muxedMap.has(key) || f.bitrate > muxedMap.get(key).bitrate) muxedMap.set(key, f);
    }
    const muxedDedup = [...muxedMap.values()].sort((a, b) => (b.height||0) - (a.height||0));
    const muxedHeights = new Set(muxedDedup.map(f => f.height));

    const voMap = new Map();
    for (const f of videoOnly) {
      const key = `${f.height}_${f.fps}`;
      const existing = voMap.get(key);
      if (!existing) { voMap.set(key, f); continue; }
      const newIsMp4 = this._codecFamily(f.mimeType) === 'mp4';
      const exIsMp4  = this._codecFamily(existing.mimeType) === 'mp4';
      if (newIsMp4 && !exIsMp4) voMap.set(key, f);
      else if (newIsMp4 === exIsMp4 && f.bitrate > existing.bitrate) voMap.set(key, f);
    }
    const voDedup = [...voMap.values()]
      .filter(f => !muxedHeights.has(f.height))
      .sort((a, b) => (b.height||0) - (a.height||0));

    const audioMap = new Map();
    for (const f of audioOnly) {
      const codec = this._codecFamily(f.mimeType);
      const key   = `${codec}_${f.audioQuality}`;
      const br    = f.bitrate || f.averageBitrate || 0;
      const exBr  = audioMap.get(key) ? (audioMap.get(key).bitrate || audioMap.get(key).averageBitrate || 0) : -1;
      if (br > exBr) audioMap.set(key, f);
    }
    const audioDedup = [...audioMap.values()].sort((a, b) => {
      const aM4a = this._codecFamily(a.mimeType) === 'mp4' ? 0 : 1;
      const bM4a = this._codecFamily(b.mimeType) === 'mp4' ? 0 : 1;
      if (aM4a !== bM4a) return aM4a - bM4a;
      return (b.bitrate || 0) - (a.bitrate || 0);
    });

    return { muxed: muxedDedup, audioOnly: audioDedup, videoOnly: voDedup };
  }

  audioQualityLabel(fmt) {
    const map = { AUDIO_QUALITY_HIGH: 'Alta calidad', AUDIO_QUALITY_MEDIUM: 'Calidad media', AUDIO_QUALITY_LOW: 'Baja calidad' };
    const base = map[fmt.audioQuality] || 'Audio';
    const br   = fmt.averageBitrate || fmt.bitrate;
    const kbps = br ? Math.round(br / 1000) : 0;
    return { label: base, kbps };
  }

  videoQualityLabel(fmt) {
    if (fmt.qualityLabel) return fmt.qualityLabel;
    if (fmt.height) return `${fmt.height}p${fmt.fps > 30 ? fmt.fps : ''}`;
    return fmt.quality || '?';
  }

  bitrateLabel(bps) {
    if (!bps) return '';
    if (bps >= 1_000_000) return `${(bps/1_000_000).toFixed(1)} Mbps`;
    return `${(bps/1000).toFixed(0)} kbps`;
  }

  durationLabel(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return h > 0
      ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
      : `${m}:${String(s).padStart(2,'0')}`;
  }
}

const ytHelper = new YouTubeHelper();
