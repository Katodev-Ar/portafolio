// background.js — VideoSnatch v7.0.5

// Patrones para capturar URLs de video reales
const VIDEO_PATTERNS = [
  /\.mp4(\?|#|$)/i,
  /\.webm(\?|#|$)/i,
  /\.m3u8(\?|#|$)/i,
  /\.mpd(\?|#|$)/i,
  // OK.ru / VK CDN
  /vd\d+\.okcdn\.ru/i,
  /ok\d+-\d+\.vkuser\.net/i,
  /vkuservideo/i,
  /\/video\.m3u8/i,
  /okcdn\.ru.*type=\d/i,
  // GoodStream / Cuevana CDN
  /goodstream\./i,
  /\.goodstream\./i,
  /cdn\.goodstream/i,
  /stream\.goodstream/i,
  /gstream\./i,
  // Servidores de hosting de video usados por Cuevana y similares (actualizado 2025)
  /streamtape\.com/i,
  /filemoon\./i,
  /dood(?:stream)?\.(?:com|watch|to|so|pm|re|la)/i,
  /mixdrop\./i,
  /voe\.sx/i,
  /mp4upload\.com/i,
  /uqload\.(?:com|co)/i,
  /upstream\.to/i,
  /vidlox\./i,
  /vidoza\./i,
  /vidhide\./i,
  /streamlare\./i,
  /vtube\./i,
  /embedsito\./i,
  // Nuevos (2024-2025)
  /streamwish\./i,
  /wishembed\./i,
  /filelions\./i,
  /vidmoly\./i,
  /vidsrc\./i,
  /streamruby\./i,
  /streamvid\./i,
  /smoothpre\./i,
  /embedrise\./i,
  /ridoo\./i,
  /dropload\./i,
  /turboplay\./i,
  /dlions\./i,
  /streamcastle\./i,
  /highstream\./i,
  /supervideo\./i,
  /sendvid\./i,
  /waaw\.tv/i,
  /fembed\./i,
  /hydrax\./i,
  /streamhub\./i,
  /streamm4u\./i,
  /videovard\./i,
  /vave\.cc/i,
  // Genérico
  /\/videoplayback/i,
  /\/hls\//i,
  /playlist\.m3u8/i,
];

const VIDEO_CONTENT_TYPES = [
  'video/mp4','video/webm','video/ogg','video/quicktime',
  'application/x-mpegurl','application/vnd.apple.mpegurl',
  'application/dash+xml','video/MP2T'
];

// Tipos OK.ru por índice
const OK_QUALITY = {
  '0': 'lowest', '1': 'low', '2': 'sd',
  '3': 'hd', '4': 'mobile', '5': 'full',
  '6': 'metadata', '8': 'hls'
};

let captures = [];
// Mapa: tabId -> { title, favicon }
let tabInfo = {};

function isVideoUrl(url) {
  if (!url || url.startsWith('chrome-extension://') || url.startsWith('data:')) return false;
  return VIDEO_PATTERNS.some(p => p.test(url));
}

function detectFormat(url) {
  const u = url.toLowerCase();
  if (u.includes('.m3u8') || u.includes('video.m3u8') || u.includes('ct=8')) return 'm3u8';
  if (u.includes('.mpd') || u.includes('dash')) return 'mpd';
  if (u.includes('.webm')) return 'webm';
  return 'mp4'; // OK.ru CDN sirve mp4 por defecto
}

function detectQuality(url) {
  // OK.ru quality: type=N en la URL
  const typeMatch = url.match(/[?&]type=(\d+)/);
  if (typeMatch) return OK_QUALITY[typeMatch[1]] || `type${typeMatch[1]}`;
  // VK: calidad en el path
  if (url.includes('1080')) return '1080p';
  if (url.includes('720')) return '720p';
  if (url.includes('480')) return '480p';
  if (url.includes('360')) return '360p';
  return 'video';
}

function addCapture(url, extra = {}) {
  if (!url) return;
  const cleanUrl = url.split('#')[0];

  // Deduplicar: si ya existe la misma URL base (sin token), ignorar
  const urlBase = cleanUrl.replace(/expires=\d+/g, 'expires=X').replace(/sig=[^&]+/g, 'sig=X');
  const existing = captures.find(c => {
    const b = c.url.replace(/expires=\d+/g, 'expires=X').replace(/sig=[^&]+/g, 'sig=X');
    return b === urlBase;
  });
  if (existing) {
    // Actualizar con URL más reciente (token fresco)
    existing.url = cleanUrl;
    existing.timestamp = Date.now();
    return;
  }

  const fmt = detectFormat(cleanUrl);
  const quality = detectQuality(cleanUrl);

  // Filtrar: no capturar HLS metadata (ct=6) ni ads
  if (cleanUrl.includes('ct=6') && !cleanUrl.includes('m3u8')) return;
  if (cleanUrl.includes('ad.') || cleanUrl.includes('/ads/')) return;

  captures.unshift({
    url: cleanUrl,
    fmt,
    quality,
    timestamp: Date.now(),
    tabTitle: extra.tabTitle || '',
    ...extra
  });

  if (captures.length > 80) captures.pop();

  chrome.action.setBadgeText({ text: String(captures.length) });
  chrome.action.setBadgeBackgroundColor({ color: '#00e5ff' });
}

// Capturar info de pestaña
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.title || info.status === 'complete') {
    tabInfo[tabId] = {
      title:   tab.title || tabInfo[tabId]?.title || '',
      favicon: tab.favIconUrl,
      url:     tab.url   || tabInfo[tabId]?.url   || '',
    };
  }
});

// Interceptar requests
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    if (isVideoUrl(details.url)) {
      const tab = tabInfo[details.tabId] || {};
      addCapture(details.url, {
        tabId:      details.tabId,
        frameId:    details.frameId,
        tabTitle:   tab.title,
        tabUrl:     tab.url,
        fromIframe: details.frameId > 0,
      });
    }
  },
  { urls: ['<all_urls>'] }
);

// Interceptar por Content-Type — también captura content-length y frameId
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    const headers = details.responseHeaders || [];
    const ct  = headers.find(h => h.name.toLowerCase() === 'content-type')?.value  || '';
    const cl  = headers.find(h => h.name.toLowerCase() === 'content-length')?.value || '';
    const cd  = headers.find(h => h.name.toLowerCase() === 'content-disposition')?.value || '';

    if (VIDEO_CONTENT_TYPES.some(t => ct.toLowerCase().includes(t.toLowerCase()))) {
      const tab = tabInfo[details.tabId] || {};
      addCapture(details.url, {
        tabId:       details.tabId,
        frameId:     details.frameId,
        contentType: ct,
        contentLength: cl ? parseInt(cl) : null,
        tabTitle:    tab.title,
        tabUrl:      tab.url,
        fromIframe:  details.frameId > 0,
      });
    }
  },
  { urls: ['<all_urls>'] },
  ['responseHeaders']
);

// Mensajes
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'GET_CAPTURES') { sendResponse({ captures }); return true; }
  if (msg.type === 'CLEAR_CAPTURES') {
    captures = [];
    chrome.action.setBadgeText({ text: '' });
    sendResponse({ ok: true }); return true;
  }
  if (msg.type === 'VIDEO_FOUND') {
    if (msg.url) addCapture(msg.url, { tabId: sender.tab?.id });
    sendResponse({ ok: true }); return true;
  }
});
