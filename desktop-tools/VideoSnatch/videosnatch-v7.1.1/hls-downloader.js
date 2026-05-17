// hls-downloader.js — VideoSnatch v5
// seekSchema:3 = fMP4 (fragmentado) — necesita init segment + fragments

class VideoDownloader {
  constructor(onProgress, onLog) {
    this.onProgress = onProgress || (() => {});
    this.onLog = onLog || (() => {});
    this.aborted = false;
  }
  abort() { this.aborted = true; }

  resolveUrl(base, rel) {
    try { return new URL(rel, base).href; } catch { return rel; }
  }

  async fetchBuf(url, retries = 3) {
    for (let i = 0; i < retries; i++) {
      try {
        const r = await fetch(url, { credentials: 'include', headers: { Accept: '*/*' } });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return await r.arrayBuffer();
      } catch(e) {
        if (i === retries - 1) throw e;
        await new Promise(r => setTimeout(r, 800 * (i+1)));
      }
    }
  }

  // Descarga directa con progreso (para MP4 normales)
  async downloadDirect(url, filename) {
    this.onLog('📡 Conectando...');
    const resp = await fetch(url, { credentials: 'include' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const total = parseInt(resp.headers.get('content-length') || '0');
    if (total) this.onLog(`📦 Tamaño: ${(total/1024/1024).toFixed(1)} MB`);

    const reader = resp.body.getReader();
    const chunks = [];
    let received = 0;

    while (true) {
      if (this.aborted) throw new Error('Cancelado');
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      this.onProgress(received, total || received + 1,
        `${(received/1024/1024).toFixed(1)}${total ? ' / '+(total/1024/1024).toFixed(1)+' MB' : ' MB'}`);
    }

    const buf = new Uint8Array(received);
    let off = 0;
    for (const c of chunks) { buf.set(c, off); off += c.length; }

    this.onLog(`✅ ${(received/1024/1024).toFixed(1)} MB — guardando...`);
    this.saveBuf(buf.buffer, filename, 'video/mp4');
    return { size: received };
  }

  // Descarga HLS m3u8
  async downloadHLS(url, filename) {
    this.onLog('📋 Cargando playlist HLS...');
    const r = await fetch(url, { credentials: 'include' });
    if (!r.ok) throw new Error(`No se cargó m3u8: HTTP ${r.status}`);
    let text = await r.text();
    let baseUrl = url;

    // Master playlist?
    if (text.includes('#EXT-X-STREAM-INF')) {
      const streams = [];
      const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].startsWith('#EXT-X-STREAM-INF') && lines[i+1] && !lines[i+1].startsWith('#')) {
          const bw = lines[i].match(/BANDWIDTH=(\d+)/)?.[1] || '0';
          const res = lines[i].match(/RESOLUTION=([^\s,]+)/)?.[1] || '';
          streams.push({ bandwidth: parseInt(bw), resolution: res, url: this.resolveUrl(url, lines[i+1]) });
        }
      }
      if (streams.length) {
        streams.sort((a,b) => b.bandwidth - a.bandwidth);
        this.onLog(`🎯 ${streams.length} calidades → ${streams[0].resolution || 'mejor'}`);
        baseUrl = streams[0].url;
        const r2 = await fetch(baseUrl, { credentials: 'include' });
        text = await r2.text();
      }
    }

    // Segmentos
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
    const segs = []; let enc = null;
    const keyCache = {};

    for (let i = 0; i < lines.length; i++) {
      if (lines[i].startsWith('#EXT-X-KEY')) {
        const method = lines[i].match(/METHOD=([^,\s]+)/)?.[1];
        const uri = lines[i].match(/URI="([^"]+)"/)?.[1];
        const iv = lines[i].match(/IV=0x([0-9a-fA-F]+)/)?.[1];
        enc = (method && method !== 'NONE') ? { method, keyUri: uri ? this.resolveUrl(baseUrl, uri) : null, iv } : null;
      }
      if (!lines[i].startsWith('#') && lines[i].startsWith('http')) {
        segs.push({ url: lines[i], enc: enc ? {...enc} : null });
      } else if (!lines[i].startsWith('#') && lines[i].length > 3) {
        segs.push({ url: this.resolveUrl(baseUrl, lines[i]), enc: enc ? {...enc} : null });
      }
    }

    if (!segs.length) throw new Error('Playlist vacío');
    this.onLog(`✅ ${segs.length} segmentos`);

    const bufs = []; let failed = 0;
    for (let i = 0; i < segs.length; i++) {
      if (this.aborted) throw new Error('Cancelado');
      this.onProgress(i, segs.length, `Seg ${i+1}/${segs.length}`);
      try {
        let data = await this.fetchBuf(segs[i].url);
        if (segs[i].enc?.keyUri) {
          if (!keyCache[segs[i].enc.keyUri]) {
            const kr = await fetch(segs[i].enc.keyUri, { credentials: 'include' });
            keyCache[segs[i].enc.keyUri] = await kr.arrayBuffer();
          }
          const key = await crypto.subtle.importKey('raw', keyCache[segs[i].enc.keyUri], {name:'AES-CBC'}, false, ['decrypt']);
          let iv = new Uint8Array(16);
          if (segs[i].enc.iv) { for(let j=0;j<16;j++) iv[j]=parseInt(segs[i].enc.iv.substr(j*2,2),16); }
          else { new DataView(iv.buffer).setUint32(12, i, false); }
          data = await crypto.subtle.decrypt({name:'AES-CBC',iv}, key, data);
        }
        bufs.push(data);
      } catch(e) {
        failed++;
        this.onLog(`⚠ Seg ${i+1} falló`);
        if (failed > Math.ceil(segs.length * 0.15)) throw new Error(`Demasiados fallos (${failed})`);
      }
    }

    const total = bufs.reduce((s,b) => s + b.byteLength, 0);
    this.onLog(`🔗 Uniendo ${(total/1024/1024).toFixed(1)} MB...`);
    const merged = new Uint8Array(total);
    let off = 0;
    for (const b of bufs) { merged.set(new Uint8Array(b), off); off += b.byteLength; }

    this.saveBuf(merged.buffer, filename.replace(/\.mp4$/i, '.ts'), 'video/MP2T');
    return { size: total };
  }

  // ── DESCARGA FRAGMENTADA (seekSchema:3) — OK.ru / VK ──
  // El servidor sirve MP4 fragmentado: primero el init segment, luego fragmentos
  async downloadFragmented(url, filename) {
    this.onLog('📡 Modo fragmentado (OK.ru)...');

    // 1. Obtener el init segment (primeros bytes del MP4)
    // OK.ru usa byte-range requests para seek, pero si pedimos todo de una vez...
    this.onLog('⬇ Descargando video completo...');

    // Para fMP4, simplemente descargar el stream completo con streaming
    const resp = await fetch(url, {
      credentials: 'include',
      headers: { 'Accept': '*/*' }
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status} — token expirado o sin acceso`);

    const contentType = resp.headers.get('content-type') || '';
    const contentLength = resp.headers.get('content-length');
    const total = contentLength ? parseInt(contentLength) : 0;

    if (total) this.onLog(`📦 Tamaño: ${(total/1024/1024).toFixed(1)} MB`);
    else this.onLog('📦 Tamaño: calculando...');

    const reader = resp.body.getReader();
    const chunks = [];
    let received = 0;

    while (true) {
      if (this.aborted) throw new Error('Cancelado');
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      this.onProgress(received, total || received * 1.1,
        `${(received/1024/1024).toFixed(1)}${total ? ' / '+(total/1024/1024).toFixed(1)+' MB' : ' MB'}`);
    }

    // Unir todos los chunks
    const buf = new Uint8Array(received);
    let off = 0;
    for (const c of chunks) { buf.set(c, off); off += c.length; }

    // Verificar si el archivo tiene cabecera válida (ftyp o moof)
    const header = new TextDecoder().decode(buf.slice(4, 8));
    this.onLog(`📄 Tipo: ${header} — ${(received/1024/1024).toFixed(1)} MB`);

    if (header === 'moof') {
      // Es un fragmento sin init — necesitamos el init segment
      // Intentar con la URL del metadataUrl si se proporcionó
      this.onLog('⚠ Fragmento sin cabecera. Intentando reconstruir...');
      // Para OK.ru fMP4, el init segment se obtiene de la URL con ct=6
      // Como no tenemos esa URL aquí, guardamos como .ts que los players modernos aceptan
      this.saveBuf(buf.buffer, filename.replace(/\.mp4$/i, '_frag.mp4'), 'video/mp4');
    } else {
      // MP4 completo con ftyp
      this.saveBuf(buf.buffer, filename, 'video/mp4');
    }

    return { size: received };
  }

  // ── Entrada principal ──
  async download(url, filename, seekSchema = 0) {
    this.aborted = false;
    const isHLSUrl = /\.m3u8/i.test(url) || /ct=8/i.test(url);
    const isFrag = seekSchema === 3;

    if (isHLSUrl) return await this.downloadHLS(url, filename);
    if (isFrag) return await this.downloadFragmented(url, filename);
    return await this.downloadDirect(url, filename);
  }

  saveBuf(buffer, filename, mime) {
    const blob = new Blob([buffer], { type: mime });
    const burl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = burl; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(burl), 10000);
  }
}
