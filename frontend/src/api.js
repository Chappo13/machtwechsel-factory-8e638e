const BASE_URL = import.meta.env.VITE_API_URL || '';
const WS_URL = import.meta.env.VITE_WS_URL || (() => {
  if (typeof window === 'undefined') return 'ws://localhost:8000';
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}`;
})();

export function getPassword() { return localStorage.getItem('site_pw') || ''; }
export function setPassword(pw) { localStorage.setItem('site_pw', pw || ''); }

async function request(method, path, body = null, timeoutMs = 30000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const options = {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Site-Password': getPassword() },
    signal: controller.signal,
  };
  if (body) options.body = JSON.stringify(body);

  try {
    const res = await fetch(`${BASE_URL}${path}`, options);
    clearTimeout(timeout);
    if (res.status === 401) {
      const e = new Error('unauthorized'); e.code = 401; throw e;
    }
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`HTTP ${res.status}: ${err}`);
    }
    return res.json();
  } catch (e) {
    clearTimeout(timeout);
    if (e.name === 'AbortError') throw new Error('Таймаут запроса (30с)');
    throw e;
  }
}

export function checkHealth() {
  return request('GET', '/api/v1/health');
}

export function getChannels() {
  return request('GET', '/api/v1/channels');
}

export function getChannel(lang) {
  return request('GET', `/api/v1/channels/${lang}`);
}

export function getArchivedTopics(lang, includeUsed = true) {
  return request('GET', `/api/v1/channels/${lang}/topics?include_used=${includeUsed}`);
}
export function discoverTopics(lang, numIdeas = 5) {
  // discover скрейпит + 2 LLM-вызова — может идти ~1.5 мин; даём 180с
  return request('POST', `/api/v1/channels/${lang}/discover`, { num_ideas: numIdeas }, 180000);
}

export function createVideo(data) {
  return request('POST', '/api/v1/videos', data);
}

export function getVideos() {
  // статус-опрос при занятом сервере (рендер/ffmpeg) может отвечать дольше — 60с
  return request('GET', '/api/v1/videos', null, 60000);
}

export function getVideo(id) {
  return request('GET', `/api/v1/videos/${id}`, null, 60000);
}

export function retryVideo(id) {
  return request('POST', `/api/v1/videos/${id}/retry`);
}

export function deleteVideo(id) {
  return request('DELETE', `/api/v1/videos/${id}`);
}

export function rebuildVideo(id, ttsMode) {
  // пересборка клипов/сборки готового видео (сценарий+озвучка сохраняются)
  return request('POST', `/api/v1/videos/${id}/rebuild`, ttsMode ? { tts_mode: ttsMode } : null, 120000);
}

export function factoryReset(scope = 'all') {
  // scope: all | queue | library | drafts | topics — сброс только своей вкладки
  return request('DELETE', `/api/v1/factory/reset?scope=${encodeURIComponent(scope)}`);
}

export function downloadVideo(id) {
  // window.open не шлёт хедеры — пароль через query-param (middleware принимает оба)
  const pw = encodeURIComponent(getPassword());
  window.open(`${BASE_URL}/api/v1/videos/${id}/download?pw=${pw}`, '_blank');
}

// Перевод из ЗАГРУЖЕННОГО зипа: льём готовый es-зип → немецкая версия на тех же
// картинках (без перегенерации). multipart, без таймаута (перевод ~минуту).
export async function translateUpload({ file, targetLang, voiceId, ttsMode = 'fal' }) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('target_lang', targetLang);
  if (voiceId) fd.append('voice_id', voiceId);
  fd.append('tts_mode', ttsMode);
  fd.append('translate_metadata', 'true');
  // НЕ ставим Content-Type — браузер сам выставит multipart boundary
  const res = await fetch(`${BASE_URL}/api/v1/videos/translate-upload`, {
    method: 'POST', headers: { 'X-Site-Password': getPassword() }, body: fd,
  });
  if (res.status === 401) { const e = new Error('unauthorized'); e.code = 401; throw e; }
  if (!res.ok) { const err = await res.text(); throw new Error(`HTTP ${res.status}: ${err}`); }
  return res.json();
}

// ── Гейт сценария ──
export function createScript(data) {
  return request('POST', '/api/v1/scripts', data);
}
export function approveScript(id, ttsMode, visualMode) {
  const body = {};
  if (ttsMode) body.tts_mode = ttsMode;
  if (visualMode) body.visual_mode = visualMode;
  return request('POST', `/api/v1/videos/${id}/approve`, Object.keys(body).length ? body : null);
}
export function improveScript(id) {
  return request('POST', `/api/v1/scripts/${id}/improve`);
}

export function getMusicLibrary() {
  return request('GET', '/api/v1/music');
}

export function connectWebSocket(taskId, onMessage, onClose) {
  // Контроллер с авто-reconnect и backoff: транзитный обрыв сам переподключается
  // (1s→2s→5s), а НЕ полагается на 5s-поллинг и НЕ штормит. onClose зовём только
  // при намеренном .close() (задача больше не running) — не на каждом дропе.
  let ws = null;
  let closed = false;
  let attempt = 0;
  const delays = [1000, 2000, 5000];
  function open() {
    ws = new WebSocket(`${WS_URL}/api/v1/ws/${taskId}`);
    ws.onmessage = (event) => {
      attempt = 0;  // живое соединение сбрасывает backoff
      try { onMessage(JSON.parse(event.data)); }
      catch { onMessage({ raw: event.data }); }
    };
    ws.onerror = (err) => console.error('WebSocket error:', err);
    ws.onclose = () => {
      if (closed) { if (onClose) onClose(taskId); return; }
      const d = delays[Math.min(attempt, delays.length - 1)];
      attempt += 1;
      setTimeout(() => { if (!closed) open(); }, d);  // переподключаемся, ref не трогаем
    };
  }
  open();
  return { close() { closed = true; try { ws && ws.close(); } catch { /* noop */ } } };
}
