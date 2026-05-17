// merge-convert.js — VideoSnatch v7.1
// Muxer MP4 puro en JavaScript — sin FFmpeg, sin librerías externas
// Soporta: H.264/AVC + AAC en contenedor MP4 (ISO Base Media File Format)

// ═══════════════════════════════════════════════════════════════════════
//  UTILIDADES DE BYTES
// ═══════════════════════════════════════════════════════════════════════
const B = {
  u32be(v) { const b=new Uint8Array(4); new DataView(b.buffer).setUint32(0,v); return b; },
  str(s)   { return new TextEncoder().encode(s); },
  concat(...arrs) {
    const total = arrs.reduce((s,a)=>s+(a instanceof ArrayBuffer?a.byteLength:a.byteLength||0),0);
    const out   = new Uint8Array(total); let off=0;
    for (const a of arrs) {
      const u = a instanceof ArrayBuffer ? new Uint8Array(a) : a;
      out.set(u, off); off += u.byteLength;
    }
    return out;
  },
  // Escribe box: [size(4)] [type(4)] [data]
  box(type, ...parts) {
    const data  = B.concat(...parts);
    const total = 8 + data.byteLength;
    const out   = new Uint8Array(total);
    const dv    = new DataView(out.buffer);
    dv.setUint32(0, total);
    out.set(B.str(type.slice(0,4)), 4);
    out.set(data, 8);
    return out;
  }
};

// ═══════════════════════════════════════════════════════════════════════
//  MP4 PARSER — Itera boxes ISO BMFF
// ═══════════════════════════════════════════════════════════════════════
class MP4Parser {
  constructor(buf) {
    if (buf instanceof ArrayBuffer) buf = new Uint8Array(buf);
    this.buf  = buf;
    this.view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  }

  *boxes() {
    let off = 0;
    while (off + 8 <= this.buf.byteLength) {
      let size = this.view.getUint32(off);
      const type = String.fromCharCode(
        this.buf[off+4], this.buf[off+5], this.buf[off+6], this.buf[off+7]
      );
      if (size === 1 && off + 16 <= this.buf.byteLength) {
        const hi = this.view.getUint32(off+8);
        const lo = this.view.getUint32(off+12);
        size = hi * 0x100000000 + lo;
      }
      if (size < 8 || off + size > this.buf.byteLength + 1024) break;
      const actualEnd = Math.min(off + size, this.buf.byteLength);
      yield {
        type,
        offset: off,
        size,
        data: this.buf.slice(off + 8, actualEnd),
        raw:  this.buf.slice(off, actualEnd)
      };
      off += size;
    }
  }

  find(type) {
    for (const b of this.boxes()) if (b.type === type) return b;
    return null;
  }

  findAll(type) {
    const r = [];
    for (const b of this.boxes()) if (b.type === type) r.push(b);
    return r;
  }

  // Busca recursivamente dentro de containers conocidos
  findDeep(type, maxDepth=4) {
    for (const b of this.boxes()) {
      if (b.type === type) return b;
      if (maxDepth > 0 && ['moov','trak','mdia','minf','stbl','udta','edts'].includes(b.type)) {
        const found = new MP4Parser(b.data).findDeep(type, maxDepth-1);
        if (found) return found;
      }
    }
    return null;
  }

  // Concatena todos los mdat
  allMdat() {
    const parts = this.findAll('mdat').map(b => b.data);
    if (!parts.length) return null;
    return B.concat(...parts);
  }

  // Offset del primer mdat en el buffer
  mdatOffset() {
    for (const b of this.boxes()) if (b.type === 'mdat') return b.offset;
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════
//  MP4 REMUXER — Recombina video + audio en un único MP4 válido
// ═══════════════════════════════════════════════════════════════════════
class MP4Remuxer {
  constructor(onLog) { this.log = onLog || (()=>{}); }

  async remux(videoBuf, audioBuf) {
    this.log('🔬 Parseando video...');
    const vp = new MP4Parser(videoBuf instanceof ArrayBuffer ? new Uint8Array(videoBuf) : videoBuf);
    const ap = new MP4Parser(audioBuf instanceof ArrayBuffer ? new Uint8Array(audioBuf) : audioBuf);

    // ── Obtener moov ──
    const vMoov = vp.find('moov');
    const aMoov = ap.find('moov');
    if (!vMoov) throw new Error('Video sin box moov');
    if (!aMoov) throw new Error('Audio sin box moov');

    this.log('🔬 Parseando audio...');

    // ── Obtener trak de video (handler vide) ──
    const vTrak = this._findTrak(vMoov.data, 'vide');
    const aTrak = this._findTrak(aMoov.data, 'soun');
    if (!vTrak) throw new Error('No hay pista de video en el archivo');
    if (!aTrak) throw new Error('No hay pista de audio en el archivo');

    // ── mvhd ──
    const mvhd = new MP4Parser(vMoov.data).find('mvhd');
    if (!mvhd) throw new Error('No hay mvhd en el video');

    // ── Obtener datos media ──
    this.log('📦 Extrayendo datos de media...');
    const vMdat = vp.allMdat();
    const aMdat = ap.allMdat();
    if (!vMdat || !vMdat.byteLength) throw new Error('Video sin datos mdat');
    if (!aMdat || !aMdat.byteLength) throw new Error('Audio sin datos mdat');

    this.log(`🎬 Video mdat: ${(vMdat.byteLength/1024/1024).toFixed(1)} MB`);
    this.log(`🎵 Audio mdat: ${(aMdat.byteLength/1024/1024).toFixed(1)} MB`);

    // ── Construir ftyp ──
    const ftyp = B.box('ftyp',
      B.str('mp42'), B.u32be(0),
      B.str('mp42'), B.str('isom'), B.str('avc1')
    );

    // ── Estimar tamaño del moov para calcular offsets ──
    // ftyp(28) + moov(?) + mdat
    // Primero construimos el moov con offsets temporales y luego ajustamos
    const FTYP_SIZE = ftyp.byteLength;
    const MOOV_PLACEHOLDER = 500_000; // estimado conservador

    const baseVideoOffset = FTYP_SIZE + MOOV_PLACEHOLDER;
    const baseAudioOffset = baseVideoOffset + vMdat.byteLength;

    // ── Parchear offsets en los trak ──
    this.log('🔧 Ajustando offsets de chunks...');
    const vTrakFixed = this._patchOffsets(vTrak.raw, baseVideoOffset);
    const aTrakFixed = this._patchOffsets(aTrak.raw, baseAudioOffset);

    // ── Construir moov ──
    const mvhdBox = B.box('mvhd', mvhd.data); // reutilizar mvhd del video
    const moovData = B.concat(mvhdBox, vTrakFixed, aTrakFixed);
    const moovBox  = B.box('moov', moovData);

    // ── Recalcular offsets con tamaño real del moov ──
    const realBase  = FTYP_SIZE + moovBox.byteLength;
    const deltaV    = realBase - baseVideoOffset;
    const deltaA    = realBase + vMdat.byteLength - baseAudioOffset;

    const vTrakFinal = this._patchOffsets(vTrak.raw, realBase);
    const aTrakFinal = this._patchOffsets(aTrak.raw, realBase + vMdat.byteLength);

    const moovFinal  = B.box('moov', B.concat(mvhdBox, vTrakFinal, aTrakFinal));

    // ── Construir mdat combinado ──
    const mdatCombined = B.concat(vMdat, aMdat);
    const mdatBox = new Uint8Array(8 + mdatCombined.byteLength);
    new DataView(mdatBox.buffer).setUint32(0, 8 + mdatCombined.byteLength);
    mdatBox.set(B.str('mdat'), 4);
    mdatBox.set(mdatCombined, 8);

    // ── Ensamblar final: ftyp + moov + mdat (fast-start) ──
    this.log('✅ Ensamblando MP4...');
    return B.concat(ftyp, moovFinal, mdatBox).buffer;
  }

  // Busca el primer trak con hdlr del tipo dado
  _findTrak(moovData, handlerType) {
    const p = new MP4Parser(moovData);
    for (const b of p.findAll('trak')) {
      const mdia = new MP4Parser(b.data).find('mdia');
      if (!mdia) continue;
      const hdlr = new MP4Parser(mdia.data).find('hdlr');
      if (!hdlr) continue;
      // hdlr.data: [version(1)][flags(3)][pre_defined(4)][handler_type(4)]...
      const ht = String.fromCharCode(
        hdlr.data[8], hdlr.data[9], hdlr.data[10], hdlr.data[11]
      );
      if (ht === handlerType) return b;
    }
    return null;
  }

  // Aplica delta a todos los chunk offsets (stco / co64) dentro de un trak raw
  _patchOffsets(trakRaw, absoluteBase) {
    // Clonar el buffer del trak
    let buf = new Uint8Array(trakRaw);

    // Buscar stco
    const stcoOff = this._findBoxOffset(buf, 'stco');
    if (stcoOff !== -1) {
      const dv      = new DataView(buf.buffer, buf.byteOffset);
      const boxSize = dv.getUint32(stcoOff);
      // stco data inicia en stcoOff+8: [ver(1)][flags(3)][count(4)][offsets...]
      const count   = dv.getUint32(stcoOff + 12);
      for (let i = 0; i < count; i++) {
        const pos = stcoOff + 16 + i * 4;
        // Los offsets en el stream original apuntan a la posición relativa al inicio del mdat original
        // Los reemplazamos con el offset absoluto en el nuevo archivo
        // Asumimos que el mdat del track original empieza en 0 (relativo)
        const origOff = dv.getUint32(pos);
        dv.setUint32(pos, absoluteBase + (origOff > 1_000_000_000 ? origOff % 1_000_000_000 : origOff));
      }
      return buf;
    }

    // Buscar co64
    const co64Off = this._findBoxOffset(buf, 'co64');
    if (co64Off !== -1) {
      const dv    = new DataView(buf.buffer, buf.byteOffset);
      const count = dv.getUint32(co64Off + 12);
      for (let i = 0; i < count; i++) {
        const pos = co64Off + 16 + i * 8;
        const hi  = dv.getUint32(pos);
        const lo  = dv.getUint32(pos + 4);
        const cur = hi * 0x100000000 + lo;
        const nv  = absoluteBase + (cur > 1_000_000_000 ? cur % 1_000_000_000 : cur);
        dv.setUint32(pos,   Math.floor(nv / 0x100000000));
        dv.setUint32(pos+4, nv >>> 0);
      }
      return buf;
    }

    return buf;
  }

  // Busca un box por tipo en un buffer plano (búsqueda byte a byte del type)
  _findBoxOffset(buf, type) {
    const target = new TextEncoder().encode(type);
    for (let i = 4; i + 8 <= buf.byteLength; i++) {
      if (buf[i]===target[0] && buf[i+1]===target[1] &&
          buf[i+2]===target[2] && buf[i+3]===target[3]) {
        return i - 4; // retorna offset del box (antes del size)
      }
    }
    return -1;
  }
}

// ═══════════════════════════════════════════════════════════════════════
//  VIDEO MERGER — Descarga paralela + mux nativo
// ═══════════════════════════════════════════════════════════════════════
class VideoMerger {
  constructor(onProgress, onLog) {
    this.onProgress = onProgress || (()=>{});
    this.onLog      = onLog      || (()=>{});
    this.aborted    = false;
    this._ctrls     = [];
  }

  abort() {
    this.aborted = true;
    this._ctrls.forEach(c => { try { c.abort(); } catch {} });
  }

  _save(buffer, filename) {
    const blob = new Blob([buffer], { type: 'video/mp4' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 20000);
  }

  async _fetch(url, label, onBytes) {
    const ctrl = new AbortController();
    this._ctrls.push(ctrl);
    let resp;
    try {
      resp = await fetch(url, { credentials: 'include', signal: ctrl.signal });
    } catch(e) {
      if (e.name==='AbortError') throw new Error('Cancelado');
      throw new Error(`Red (${label}): ${e.message}`);
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status} (${label})`);
    const total  = parseInt(resp.headers.get('content-length') || '0');
    const reader = resp.body.getReader();
    const chunks = [];
    let received = 0;
    while (true) {
      if (this.aborted) { ctrl.abort(); throw new Error('Cancelado'); }
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.byteLength;
      onBytes(received, total);
    }
    const out = new Uint8Array(received);
    let off = 0;
    for (const c of chunks) { out.set(c, off); off += c.byteLength; }
    this.onLog(`✅ ${label}: ${(received/1024/1024).toFixed(1)} MB`);
    return out.buffer;
  }

  async mergeVideoAudio(videoUrl, audioUrl, title) {
    const safe = title.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').slice(0,80);

    // ── Descarga paralela ──
    this.onLog('🚀 Descargando video y audio en paralelo...');
    let vBytes=0, vTotal=0, aBytes=0, aTotal=0;

    const updateProg = () => {
      const total = (vTotal||1) + (aTotal||1);
      const done  = vBytes + aBytes;
      const pct   = Math.round(Math.min(60, done/total*60));
      this.onProgress(pct, 100,
        `▶ ${(vBytes/1024/1024).toFixed(1)}MB  🎵 ${(aBytes/1024/1024).toFixed(1)}MB`);
    };

    const [videoBuf, audioBuf] = await Promise.all([
      this._fetch(videoUrl, 'Video', (r,t) => { vBytes=r; vTotal=t; updateProg(); }),
      this._fetch(audioUrl, 'Audio', (r,t) => { aBytes=r; aTotal=t; updateProg(); }),
    ]);

    if (this.aborted) throw new Error('Cancelado');

    // ── Mux ──
    this.onProgress(65, 100, '🔧 Analizando estructura MP4...');
    try {
      const remuxer = new MP4Remuxer(msg => this.onLog(msg));
      const merged  = await remuxer.remux(videoBuf, audioBuf);
      this.onProgress(96, 100, '💾 Guardando...');
      this._save(merged, `${safe}.mp4`);
      this.onProgress(100, 100, `✅ ${(merged.byteLength/1024/1024).toFixed(1)} MB guardado`);
      this.onLog(`🎉 ${safe}.mp4`);
      return { size: merged.byteLength, merged: true };
    } catch(e) {
      this.onLog(`⚠ Mux no disponible (${e.message})`);
      this.onLog('💾 Guardando archivos por separado...');
      this.onProgress(75, 100, '💾 Guardando VIDEO...');
      this._save(videoBuf, `${safe}_VIDEO.mp4`);
      await new Promise(r => setTimeout(r, 700));
      this.onProgress(90, 100, '💾 Guardando AUDIO...');
      this._save(audioBuf, `${safe}_AUDIO.m4a`);
      this.onProgress(100, 100, '✅ Archivos separados listos');
      this.onLog('💡 Unión en VLC: Medios › Abrir múltiples archivos');
      return { size: videoBuf.byteLength + audioBuf.byteLength, merged: false };
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════
//  FORMAT CONVERTER
// ═══════════════════════════════════════════════════════════════════════
class FormatConverter {
  constructor(onProgress, onLog) {
    this.onProgress = onProgress || (()=>{});
    this.onLog      = onLog      || (()=>{});
    this.aborted    = false;
  }
  abort() { this.aborted = true; }

  static FORMATS = [
    { id:'mp4',  label:'MP4 — Video universal',       icon:'🎬', type:'video', ext:'mp4',  mime:'video/mp4'  },
    { id:'webm', label:'WebM — Web optimizado',        icon:'🌐', type:'video', ext:'webm', mime:'video/webm' },
    { id:'mp3',  label:'MP3 — Audio universal',        icon:'🎵', type:'audio', ext:'mp3',  mime:'audio/mpeg' },
    { id:'m4a',  label:'M4A — Audio AAC',              icon:'🎶', type:'audio', ext:'m4a',  mime:'audio/mp4'  },
    { id:'ogg',  label:'OGG — Audio libre',            icon:'🔊', type:'audio', ext:'ogg',  mime:'audio/ogg'  },
    { id:'wav',  label:'WAV — Sin pérdida',            icon:'📻', type:'audio', ext:'wav',  mime:'audio/wav'  },
  ];

  _save(buffer, filename, mime) {
    const blob = new Blob([buffer], { type: mime });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 20000);
  }

  async fetchFile(url) {
    this.onLog('📡 Descargando...');
    const resp = await fetch(url, { credentials: 'include' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const total  = parseInt(resp.headers.get('content-length') || '0');
    const reader = resp.body.getReader();
    const chunks = [];
    let received = 0;
    while (true) {
      if (this.aborted) throw new Error('Cancelado');
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.byteLength;
      this.onProgress(received, total || received+1,
        `📥 ${(received/1024/1024).toFixed(1)}${total?' / '+(total/1024/1024).toFixed(1)+' MB':' MB'}`);
    }
    const out = new Uint8Array(received);
    let off = 0;
    for (const c of chunks) { out.set(c, off); off += c.byteLength; }
    return out.buffer;
  }

  async convertViaMediaRecorder(srcBlob, targetMime, targetExt, filename) {
    this.onLog(`🔄 Convirtiendo a ${targetExt.toUpperCase()}...`);
    const candidates =
      targetExt==='mp3' ? ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus'] :
      targetExt==='m4a' ? ['audio/mp4','audio/webm;codecs=opus','audio/webm'] :
      targetExt==='ogg' ? ['audio/ogg;codecs=opus','audio/ogg','audio/webm'] :
      [targetMime, 'video/webm;codecs=vp9,opus', 'video/webm'];
    const supported = candidates.find(m => { try { return MediaRecorder.isTypeSupported(m); } catch { return false; } });
    if (!supported) throw new Error(`${targetExt} no soportado en este navegador`);

    return new Promise((resolve, reject) => {
      const srcUrl = URL.createObjectURL(srcBlob);
      const video  = document.createElement('video');
      video.src    = srcUrl;
      video.style.cssText = 'position:fixed;opacity:0;pointer-events:none;width:1px;height:1px;top:-9999px';
      document.body.appendChild(video);

      const ctx    = new AudioContext();
      const dest   = ctx.createMediaStreamDestination();
      const node   = ctx.createMediaElementSource(video);
      node.connect(dest);

      const recorder = new MediaRecorder(dest.stream, { mimeType: supported });
      const chunks   = [];

      recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: supported });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = filename; a.click();
        setTimeout(()=>{ URL.revokeObjectURL(srcUrl); URL.revokeObjectURL(a.href); },15000);
        document.body.removeChild(video);
        ctx.close();
        this.onLog(`✅ ${filename} guardado`);
        resolve({ size: blob.size });
      };
      recorder.onerror = e => reject(new Error(e.error?.message||'Error recorder'));

      video.onloadedmetadata = () => {
        const dur = (video.duration||60)*1000;
        recorder.start(500);
        video.play().catch(()=>{});
        let elapsed = 0;
        const iv = setInterval(()=>{
          if (this.aborted) { clearInterval(iv); recorder.stop(); return; }
          elapsed += 500;
          const pct = Math.min(98, Math.round(elapsed/dur*100));
          this.onProgress(pct, 100, `🔄 ${pct}%`);
        }, 500);
        video.onended = () => {
          clearInterval(iv);
          setTimeout(()=>recorder.stop(), 300);
          this.onProgress(100, 100, '✅ Listo');
        };
      };
      video.onerror = () => reject(new Error('No se pudo cargar el archivo'));
      video.load();
    });
  }

  async convert(sourceUrl, sourceMime, targetFormat, title) {
    const safe = (title||'video').replace(/[<>:"/\\|?*\x00-\x1F]/g,'_').slice(0,80);
    const fmt  = FormatConverter.FORMATS.find(f=>f.id===targetFormat);
    if (!fmt) throw new Error('Formato desconocido');
    const filename = `${safe}.${fmt.ext}`;
    const srcBuf   = await this.fetchFile(sourceUrl);
    if (this.aborted) throw new Error('Cancelado');
    const srcBlob  = new Blob([srcBuf], { type: sourceMime||'video/mp4' });
    if (targetFormat === 'wav') return this._toWav(srcBlob, filename);
    return this.convertViaMediaRecorder(srcBlob, fmt.mime, fmt.ext, filename);
  }

  async _toWav(srcBlob, filename) {
    this.onLog('🔊 Decodificando audio...');
    this.onProgress(20, 100, 'Decodificando...');
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = async e => {
        try {
          const ctx     = new AudioContext();
          const decoded = await ctx.decodeAudioData(e.target.result);
          this.onProgress(70, 100, 'Escribiendo WAV...');
          const wav = this._toWavBuffer(decoded);
          this._save(wav, filename, 'audio/wav');
          await ctx.close();
          this.onProgress(100, 100, `✅ WAV: ${(wav.byteLength/1024/1024).toFixed(1)} MB`);
          resolve({ size: wav.byteLength });
        } catch(e) { reject(new Error('Decode: '+e.message)); }
      };
      reader.onerror = () => reject(new Error('FileReader error'));
      reader.readAsArrayBuffer(srcBlob);
    });
  }

  _toWavBuffer(ab) {
    const nc=ab.numberOfChannels, sr=ab.sampleRate, nf=ab.length;
    const bd=16, ba=nc*2, ds=nf*ba;
    const out=new ArrayBuffer(44+ds), v=new DataView(out);
    const w=(o,s)=>{ for(let i=0;i<s.length;i++) v.setUint8(o+i,s.charCodeAt(i)); };
    w(0,'RIFF'); v.setUint32(4,36+ds,true); w(8,'WAVE'); w(12,'fmt ');
    v.setUint32(16,16,true); v.setUint16(20,1,true); v.setUint16(22,nc,true);
    v.setUint32(24,sr,true); v.setUint32(28,sr*ba,true);
    v.setUint16(32,ba,true); v.setUint16(34,bd,true);
    w(36,'data'); v.setUint32(40,ds,true);
    let off=44;
    for(let i=0;i<nf;i++) for(let c=0;c<nc;c++){
      const s=Math.max(-1,Math.min(1,ab.getChannelData(c)[i]));
      v.setInt16(off, s<0?s*0x8000:s*0x7FFF, true); off+=2;
    }
    return out;
  }
}

// Exponer globalmente
window.VideoMerger     = VideoMerger;
window.FormatConverter = FormatConverter;
