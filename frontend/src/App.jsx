import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react';
import './App.css';
import * as api from './api.js';

const PHASES = ['Сценарий', 'Улучшение', 'Виральность', 'Озвучка', 'Сцены', 'Тайминги', 'Клипы', 'Музыка', 'Сборка', 'Метаданные', 'Выдача'];
const PHASE_KEYS = ['script_generation', 'script_improvement', 'virality_filter', 'voiceover', 'scene_planning', 'alignment', 'clip_download', 'music', 'assembly', 'metadata', 'delivery'];
const STATUS_RU = { pending: 'ожидание', running: 'в работе', completed: 'готово', failed: 'ошибка', scripting: 'пишем сценарий', script_ready: 'сценарий готов' };
const DemoContext = createContext(true);

// Флаг по языку канала — единый источник, чтобы новые языки не падали на 🇪🇸
const LANG_FLAG = { de: '🇩🇪', es: '🇪🇸', en: '🇬🇧', vi: '🇻🇳' };
const flagFor = (lang) => LANG_FLAG[(lang || '').toLowerCase()] || '🏳️';

const DEMO_CHANNELS = [
  { lang: 'de', name: 'German Finance & Business', niche: 'finance', description: 'Документальные видео о бизнесе, финансах, скрытых системах', voice_id: 'Fghah4fztZORbiKfIGAs', style: 'documentary', duration_minutes: 22, history_window: 10, recent_topics: ['Die geheime Geschichte der Schweizer Banken', 'Wie KI die Medizin revolutioniert'], total_videos: 2 },
  { lang: 'vi', name: 'Ngẫm', niche: 'curiosity_history', description: 'Những câu chuyện tò mò về lịch sử, tâm lý và con người', voice_id: '', style: 'documentary', duration_minutes: 8, history_window: 15, recent_topics: [], total_videos: 0 },
];

const DEMO_IDEAS = [
  { title_original: 'Warum die deutsche Autoindustrie am Abgrund steht', title_ru: 'Почему немецкий автопром на грани краха', category: 'business_rise_fall', hook: 'Die mächtigste Industrie Europas verliert den Anschluss', hook_ru: 'Самая мощная отрасль Европы теряет позиции', virality_score: 92, why_viral: 'Актуальная тема, затрагивает национальную гордость', source_video: 'https://youtube.com/watch?v=example1', source_views: 450000 },
  { title_original: 'Die dunkle Seite der Fast-Fashion-Industrie', title_ru: 'Тёмная сторона индустрии быстрой моды', category: 'hidden_systems', hook: 'Deine Kleidung hat einen Preis, den du nicht siehst', hook_ru: 'У твоей одежды есть цена, которую ты не видишь', virality_score: 87, why_viral: 'Эмоциональный триггер + скрытая правда', source_video: 'https://youtube.com/watch?v=example2', source_views: 320000 },
  { title_original: 'Wie Dubai in 30 Jahren zur Megacity wurde', title_ru: 'Как Дубай за 30 лет стал мегаполисом', category: 'geopolitics', hook: 'Vom Fischerdorf zum reichsten Ort der Welt', hook_ru: 'Из рыбацкой деревни в богатейшее место мира', virality_score: 85, why_viral: 'Вау-фактор + история успеха', source_video: null, source_views: null },
  { title_original: 'Der geheime Krieg um seltene Erden', title_ru: 'Тайная война за редкоземельные элементы', category: 'geopolitics', hook: 'Ohne diese Rohstoffe funktioniert keine Technologie', hook_ru: 'Без этих ресурсов не работает ни одна технология', virality_score: 81, why_viral: 'Геополитика + скрытые системы, тренд', source_video: 'https://youtube.com/watch?v=example4', source_views: 280000 },
  { title_original: 'Warum Island das glücklichste Land der Welt ist', title_ru: 'Почему Исландия — самая счастливая страна в мире', category: 'geopolitics', hook: 'Ein Land mit mehr Schafen als Menschen', hook_ru: 'Страна где овец больше чем людей', virality_score: 78, why_viral: 'Любопытство + позитивный контент', source_video: null, source_views: null },
  { title_original: 'Die Psychologie hinter viralen TikTok-Videos', title_ru: 'Психология вирусных видео в TikTok', category: 'dark_psychology', hook: 'Dein Gehirn hat keine Chance gegen diesen Algorithmus', hook_ru: 'У твоего мозга нет шансов против этого алгоритма', virality_score: 74, why_viral: 'Мета-тема, затрагивает каждого пользователя', source_video: null, source_views: null },
];

const DEMO_DRAFTS = [
  { task_id: 'draft-1', topic: 'Die dunkle Seite von Amazon', lang: 'de', status: 'script_ready', script_score: 91, script_ru: '(демо) Амазон, empire стоимостью $1.7 трлн, скрывает тёмную правду. Работники умирают в жару без кондиционеров. Малый бизнес задушен алгоритмами. Деревни остаются без магазинов...', created_at: '2026-06-11T10:00:00' },
];

const DEMO_VIDEOS = [
  { id: 'demo-1', topic: 'Die geheime Geschichte der Schweizer Banken', language: 'DE', duration_minutes: 22, status: 'completed', created_at: '2026-04-06T14:30:00Z', progress: 100, cost: 0.026, titles: ['Warum die Schweiz so viele Geheimnisse hütet', 'Die dunkle Wahrheit über Schweizer Banken', 'Wie die Schweiz Europas Geld versteckt hat'] },
  { id: 'demo-2', topic: 'Wie KI die Medizin revolutioniert', language: 'DE', duration_minutes: 23, status: 'running', created_at: '2026-04-07T09:15:00Z', current_phase: 'Clips', progress: 58, cost: 0.018 },
];

function phaseIndex(name) {
  if (!name) return -1;
  return PHASE_KEYS.findIndex(p => p.toLowerCase() === name.toLowerCase());
}

function formatDate(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

// ── Components ──

function timeAgo(iso) {
  if (!iso) return '';
  try {
    const s = Math.max(0, Math.floor((Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()) / 1000));
    if (s < 60) return `${s}с назад`;
    if (s < 3600) return `${Math.floor(s / 60)}м назад`;
    return `${Math.floor(s / 3600)}ч назад`;
  } catch { return ''; }
}

function Stepper({ currentPhase, progress, detail, updatedAt }) {
  const current = currentPhase ? phaseIndex(currentPhase) : -1;
  return (
    <div className="stepper">
      <div className="stepper-title">pipeline</div>
      <div className="steps">
        {PHASES.map((phase, i) => (
          <div key={phase} className={`step ${i < current ? 'done' : ''} ${i === current ? 'active' : ''}`}>
            <span className="step-dot" />{phase}
          </div>
        ))}
      </div>
      {progress != null && <div className="progress-bar-wrap"><div className="progress-bar" style={{ width: `${progress}%` }} /></div>}
      {(currentPhase || progress != null) && (
        <div className="progress-label">
          <span>{detail || (currentPhase ? PHASES[phaseIndex(currentPhase)] || currentPhase : 'Ожидание...')}</span>
          {progress != null && <span>{Math.round(progress)}%</span>}
        </div>
      )}
      {updatedAt && <div className="progress-heartbeat">● активна · обновлено {timeAgo(updatedAt)}</div>}
    </div>
  );
}

function Badge({ status }) {
  const map = { pending: ['badge-pending', '○'], running: ['badge-running', '◉'], completed: ['badge-completed', '✓'], failed: ['badge-failed', '✕'], scripting: ['badge-running', '✎'], script_ready: ['badge-pending', '✎'] };
  const [cls, icon] = map[status] || ['badge-pending', '○'];
  return <span className={`badge ${cls}`}>{icon} {STATUS_RU[status] || status}</span>;
}

function ViralityBar({ score }) {
  const s = typeof score === 'number' && !isNaN(score) ? score : 0;
  const color = s >= 85 ? 'var(--success)' : s >= 70 ? 'var(--cyan)' : s >= 50 ? 'var(--warning)' : 'var(--error)';
  return (
    <div className="virality-bar">
      <div className="virality-fill" style={{ width: `${s}%`, background: color }} />
      <span className="virality-label">{s}%</span>
    </div>
  );
}

// ══════════════════════
// КАНАЛ + СОЗДАНИЕ
// ══════════════════════
function ScriptRubric({ rubric }) {
  if (!rubric || !Array.isArray(rubric.dimensions)) return null;
  const verdictMap = {
    ship: ['✓ можно собирать', 'var(--success)'],
    improve: ['↻ стоит улучшить', 'var(--warning)'],
    reject: ['✕ слабый — улучшить', 'var(--error)'],
  };
  const [vLabel, vColor] = verdictMap[rubric.verdict] || ['', 'var(--cyan)'];
  const dimColor = (s, m) => {
    if (s == null || !m) return 'var(--cyan)';
    const r = s / m;
    return r >= 0.8 ? 'var(--success)' : r >= 0.5 ? 'var(--cyan)' : r >= 0.3 ? 'var(--warning)' : 'var(--error)';
  };
  return (
    <div style={{ marginTop: 12, marginBottom: 8, padding: 12, background: 'rgba(255,255,255,0.03)', borderRadius: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <label className="form-label" style={{ margin: 0 }}>Оценка по критериям</label>
        {vLabel && <span style={{ color: vColor, fontWeight: 600, fontSize: '0.82rem' }}>{vLabel}</span>}
      </div>
      {rubric.summary_ru && (
        <div style={{ fontSize: '0.82rem', color: '#cfd3dc', marginBottom: 10 }}>{rubric.summary_ru}</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {rubric.dimensions.map((d) => (
          <div key={d.key} title={d.why || ''}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: 2 }}>
              <span style={{ color: '#aeb4c0' }}>{d.label}</span>
              <span style={{ color: dimColor(d.score, d.max), fontWeight: 600 }}>{d.score == null ? '—' : d.score}/{d.max}</span>
            </div>
            <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 3 }}>
              <div style={{ height: 4, borderRadius: 3, width: `${d.score == null ? 0 : (d.score / d.max) * 100}%`, background: dimColor(d.score, d.max) }} />
            </div>
            {d.why && <div style={{ fontSize: '0.72rem', color: '#7e8595', marginTop: 2 }}>{d.why}</div>}
          </div>
        ))}
      </div>
      {Array.isArray(rubric.weak_spots) && rubric.weak_spots.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: '0.78rem', color: '#aeb4c0', marginBottom: 4 }}>Что починить:</div>
          {rubric.weak_spots.map((w, i) => (
            <div key={i} style={{ fontSize: '0.76rem', color: '#c9ced8', marginBottom: 4 }}>
              <b>{w.where}</b> — {w.problem}{w.fix_hint ? ` → ${w.fix_hint}` : ''}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ScriptReview({ draft, onApprove, onImprove, onBack, busy }) {
  const [ttsMode, setTtsMode] = useState('fal');
  const score = draft.script_score ?? 0;
  const color = score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--cyan)' : score >= 40 ? 'var(--warning)' : 'var(--error)';
  return (
    <div className="card script-review card-glow">
      <div className="review-head">
        <div className="review-head-text">
          <div className="form-label">Сценарий готов — оцени перед сборкой видео</div>
          <div className="review-topic">{draft.topic}</div>
        </div>
        <div className="score-circle" style={{ borderColor: color, color }}>
          <span className="score-num">{score}</span><span className="score-max">/100</span>
        </div>
      </div>
      <ScriptRubric rubric={draft.script_rubric} />
      <label className="form-label">Перевод на русский (чтобы оценить качество)</label>
      <div className="script-ru">{draft.script_ru || '(перевод недоступен)'}</div>
      <div className="form-group" style={{ marginTop: 16 }}>
        <label className="form-label">Озвучка</label>
        <div className="lang-selector">
          <button type="button" className={`lang-btn ${ttsMode === 'fal' ? 'active' : ''}`}
            onClick={() => setTtsMode('fal')}>
            💎 Фирменный голос <span className="cost-tag">~$2</span>
          </button>
          <button type="button" className={`lang-btn ${ttsMode === 'free' ? 'active' : ''}`}
            onClick={() => setTtsMode('free')}>
            🆓 Тестовый <span className="cost-tag">бесплатно</span>
          </button>
        </div>
      </div>
      <div style={{ fontSize: '0.78rem', color: '#8b92a0', marginTop: 10 }}>
        🎨 Видеоряд подбирается автоматически под каждую сцену (сток / фото / графика / скетчи).
      </div>
      <div className="review-actions">
        <button className="btn btn-secondary" disabled={busy} onClick={onImprove}>
          {busy ? <span className="spinner" /> : '↻'} Улучшить сценарий
        </button>
        <button className="btn btn-primary" disabled={busy} onClick={() => onApprove(ttsMode)}>
          {busy ? <span className="spinner" /> : '✓'} Одобрить → собрать видео
        </button>
      </div>
      <button type="button" className="btn-link" disabled={busy} onClick={onBack}>← выбрать другую тему</button>
    </div>
  );
}

function CreateTab({ onCreated, initialLang }) {
  const IS_DEMO = useContext(DemoContext);
  const [channels, setChannels] = useState([]);
  const [selectedLang, setSelectedLang] = useState(initialLang || 'de');
  const [ideas, setIdeas] = useState([]);
  const [discovering, setDiscovering] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState('');
  const [customTopic, setCustomTopic] = useState('');
  const [phase, setPhase] = useState('form'); // form | working | review
  const [workingLabel, setWorkingLabel] = useState('');
  const [draftId, setDraftId] = useState(null);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  useEffect(() => {
    if (IS_DEMO) { setChannels(DEMO_CHANNELS); return; }
    api.getChannels().then(setChannels).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // Архив ранее отобранных тем — показываем сразу, без повторного поиска
  useEffect(() => {
    if (IS_DEMO) return;
    api.getArchivedTopics(selectedLang).then(t => setIdeas(t || [])).catch(() => setIdeas([]));
  }, [selectedLang]);

  const channel = channels.find(c => c.lang === selectedLang);

  async function handleDiscover() {
    if (IS_DEMO) { setIdeas(DEMO_IDEAS.slice(0, 5)); return; }
    setDiscovering(true);
    setError('');
    try {
      // discover доискивает новые темы и доливает в архив; ответ — весь архив
      const res = await api.discoverTopics(selectedLang, 5);
      setIdeas(res.ideas || []);
    } catch (e) { setError(e.message); }
    finally { setDiscovering(false); }
  }

  async function handleLoadMore() {
    if (IS_DEMO) { setIdeas(prev => [...prev, ...DEMO_IDEAS.slice(5)]); return; }
    setLoadingMore(true);
    setError('');
    try {
      const res = await api.discoverTopics(selectedLang, 5);
      setIdeas(res.ideas || []);  // архив кумулятивный — заменяем, не дублируем
    } catch (e) { setError(e.message); }
    finally { setLoadingMore(false); }
  }

  function pollDraft(id) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const v = await api.getVideo(id);
        if (v.status === 'script_ready') {
          clearInterval(pollRef.current);
          setDraft(v); setPhase('review'); setBusy(false);
        } else if (v.status === 'failed') {
          clearInterval(pollRef.current);
          setError('Ошибка генерации сценария: ' + (v.error || '')); setPhase('form'); setBusy(false);
        }
      } catch (e) { /* транзиент — продолжаем поллить */ }
    }, 4000);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const topic = (selectedTopic || customTopic).trim();
    if (!topic) { setError('Выбери тему или введи свою'); return; }
    setError('');
    if (IS_DEMO) { setDraft({ topic, script_score: 87, script_ru: '(демо) Здесь будет русский перевод сгенерированного сценария, чтобы ты оценил качество перед сборкой видео.' }); setPhase('review'); return; }
    setPhase('working'); setWorkingLabel('Пишу сценарий…(~3 мин)');
    try {
      const res = await api.createScript({
        topic, lang: selectedLang,
        duration_minutes: channel?.duration_minutes || 22,
        style: channel?.style || 'documentary', music_mood: 'auto',
      });
      setDraftId(res.task_id); pollDraft(res.task_id);
    } catch (e) { setError(e.message); setPhase('form'); }
  }

  async function handleApprove(ttsMode) {
    if (IS_DEMO) { onCreated?.(); return; }
    setBusy(true); setError('');
    try { await api.approveScript(draftId, ttsMode); onCreated?.({ task_id: draftId }); }
    catch (e) { setError(e.message); setBusy(false); }
  }

  async function handleImprove() {
    if (IS_DEMO) return;
    setBusy(true); setError('');
    setPhase('working'); setWorkingLabel('Улучшаю сценарий…');
    try { await api.improveScript(draftId); pollDraft(draftId); }
    catch (e) { setError(e.message); setPhase('review'); setBusy(false); }
  }

  function resetAll() {
    if (pollRef.current) clearInterval(pollRef.current);
    setPhase('form'); setDraft(null); setDraftId(null); setBusy(false);
    setSelectedTopic(''); setCustomTopic(''); setError('');
  }

  if (phase === 'working') {
    return (
      <div className="card submit-success card-glow">
        <div className="spinner spinner-lg" />
        <div className="success-title">{workingLabel}</div>
        <div className="success-sub">Можно подождать здесь — покажу балл и перевод, когда будет готово.</div>
      </div>
    );
  }

  if (phase === 'review' && draft) {
    return (
      <>
        {error && <div className="error-msg">{error}</div>}
        <ScriptReview draft={draft} busy={busy} onApprove={handleApprove} onImprove={handleImprove} onBack={resetAll} />
      </>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      {/* Channel selector */}
      <div className="card">
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Канал</label>
          <div className="lang-selector">
            {channels.map(ch => (
              <button key={ch.lang} type="button"
                className={`lang-btn ${selectedLang === ch.lang ? 'active' : ''}`}
                onClick={() => { setSelectedLang(ch.lang); setSelectedTopic(''); }}>
                {flagFor(ch.lang)} {ch.name}
              </button>
            ))}
          </div>
        </div>
        {channel && (
          <div className="channel-info">
            <span className="channel-meta">Ниша: <b>{channel.niche}</b></span>
            <span className="channel-meta">Видео: <b>{channel.total_videos}</b></span>
            <span className="channel-meta">Длительность: <b>{channel.duration_minutes} мин</b></span>
          </div>
        )}
      </div>

      {/* Topic discovery */}
      <div className="card">
        <div className="form-group">
          <label className="form-label">Архив тем{ideas.length ? ` (${ideas.length})` : ''}</label>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: ideas.length ? 16 : 0 }}>
            <button type="button" className="btn btn-secondary" onClick={handleDiscover} disabled={discovering}>
              {discovering ? <span className="spinner" /> : '◇'} Найти ещё темы
            </button>
            <span className="cost-tag">~$0.026 · сохранятся в архив</span>
          </div>
        </div>

        {ideas.length > 0 && (
          <div className="ideas-list">
            {ideas.map((idea, i) => (
              <button key={idea.id || i} type="button"
                className={`idea-item ${selectedTopic === idea.title_original ? 'selected' : ''}`}
                style={idea.status === 'used' ? { opacity: 0.55 } : undefined}
                onClick={() => { setSelectedTopic(idea.title_original); setCustomTopic(''); }}>
                <div className="idea-top">
                  <ViralityBar score={idea.virality_score} />
                  <span className="idea-category">{idea.status === 'used' ? '✓ использовано' : idea.category}</span>
                </div>
                <div className="idea-title-original">{idea.title_original}</div>
                <div className="idea-title-ru">{idea.title_ru}</div>
                <div className="idea-hook">{idea.hook_ru}</div>
                {idea.why_viral && <div className="idea-why">{idea.why_viral}</div>}
                {idea.source_views && (
                  <div className="idea-source">Источник: {(idea.source_views / 1000).toFixed(0)}K просмотров</div>
                )}
              </button>
            ))}
            <button type="button" className="btn btn-secondary" style={{ marginTop: 8, width: '100%' }}
              onClick={handleLoadMore} disabled={loadingMore}>
              {loadingMore ? <span className="spinner" /> : '+'} Загрузить ещё 5 тем
            </button>
          </div>
        )}
      </div>

      {/* Custom topic */}
      <div className="card">
        <div className="form-group" style={{ marginBottom: 0 }}>
          <label className="form-label">Или введи свою тему</label>
          <textarea className="form-input" placeholder="напр. Warum die Schweiz so reich ist"
            value={customTopic}
            onChange={e => { setCustomTopic(e.target.value); setSelectedTopic(''); }} />
        </div>
      </div>

      {/* Recent topics */}
      {channel?.recent_topics?.length > 0 && (
        <div className="card">
          <label className="form-label">Последние темы канала (не повторяются)</label>
          <div className="recent-topics">
            {channel.recent_topics.map((t, i) => (
              <div key={i} className="recent-topic">{t}</div>
            ))}
          </div>
        </div>
      )}

      {error && <div className="error-msg">{error}</div>}

      <button type="submit" className="btn btn-primary" disabled={!selectedTopic && !customTopic.trim()}>
        {`▶  Сгенерировать сценарий (${selectedLang.toUpperCase()})`}
      </button>
    </form>
  );
}

// ══════════════════════
// ОЧЕРЕДЬ
// ══════════════════════
function QueueTab({ lang }) {
  const IS_DEMO = useContext(DemoContext);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const wsRefs = useRef({});

  const load = useCallback(async () => {
    if (IS_DEMO) { setVideos(DEMO_VIDEOS); setLoading(false); return; }
    try { const d = await api.getVideos(); setVideos(Array.isArray(d) ? d : d.items || []); setError(''); }
    catch (e) { setError(e.message); /* НЕ стираем список — задачи идут на сервере в фоне */ }
    finally { setLoading(false); }
  }, []);

  // WS — основной live-канал для running-задач; опрос — фолбэк, поэтому реже (15с).
  useEffect(() => { load(); const i = setInterval(load, 15000); return () => clearInterval(i); }, [load]);

  // Сокеты пересоздаём ТОЛЬКО когда меняется набор running-задач, а НЕ на каждом
  // WS-сообщении/опросе. Раньше dep=[videos] + close-all cleanup рвал и переоткрывал
  // ВСЕ сокеты ~1.7 раза/с (videos меняется на каждом msg/poll) → WS-шторм душил
  // event-loop сервера и тормозил сборку. Ключ на стабильную сигнатуру id.
  const runningSig = videos.filter(v => v.status === 'running')
    .map(v => v.id || v.task_id).sort().join(',');
  useEffect(() => {
    if (IS_DEMO) return;
    const running = videos.filter(v => v.status === 'running');
    running.forEach(v => {
      const id = v.id || v.task_id;
      if (id && !wsRefs.current[id]) {
        wsRefs.current[id] = api.connectWebSocket(id, msg => {
          setVideos(prev => prev.map(item => (item.id || item.task_id) === id ? { ...item, ...msg } : item));
        }, (closedId) => { delete wsRefs.current[closedId]; });
      }
    });
    // Закрываем сокет ТОЛЬКО для задач, которые больше не running (без close-all).
    Object.keys(wsRefs.current).forEach(id => {
      if (!running.find(v => (v.id || v.task_id) === id)) { wsRefs.current[id]?.close(); delete wsRefs.current[id]; }
    });
  }, [runningSig]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <div style={{ textAlign: 'center', padding: '60px' }}><span className="spinner" /></div>;

  // Очередь = пайплайн в работе + ошибки. script_ready → вкладка «Черновики».
  const inChan = v => !lang || (v.lang || '') === lang;
  const active = videos.filter(v => ['running', 'pending', 'scripting'].includes(v.status) && inChan(v));
  const failed = videos.filter(v => v.status === 'failed' && inChan(v));

  return (
    <div>
      {error && (
        <div className="warn-msg">Связь прервалась — задачи продолжают идти на сервере, обновляю статус…</div>
      )}
      {active.length === 0 && failed.length === 0 && !error && (
        <div className="queue-empty"><div className="queue-empty-icon">◇</div><div>Активных задач нет. Готовые видео — в «Библиотеке».</div></div>
      )}
      {active.length > 0 && (<><div className="section-header"><span className="section-title">В работе</span><span className="section-count">{active.length}</span></div>
        {active.map(v => <QueueItem key={v.id || v.task_id} video={v} onDeleted={() => setVideos(prev => prev.filter(x => (x.id || x.task_id) !== (v.id || v.task_id)))} />)}</>)}
      {failed.length > 0 && (<><div className="section-header" style={{ marginTop: active.length ? 28 : 0 }}><span className="section-title">Требуют внимания</span><span className="section-count">{failed.length}</span></div>
        {failed.map(v => <QueueItem key={v.id || v.task_id} video={v} onDeleted={() => setVideos(prev => prev.filter(x => (x.id || x.task_id) !== (v.id || v.task_id)))} />)}</>)}
    </div>
  );
}

function QueueItem({ video, onDeleted }) {
  const IS_DEMO = useContext(DemoContext);
  const id = video.id || video.task_id;
  const isRunning = video.status === 'running';
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function doRetry() {
    if (IS_DEMO) return;
    setBusy(true);
    try { await api.retryVideo(id); } catch (e) { /* следующий опрос подхватит */ }
    setBusy(false);
  }
  async function doApprove() {
    if (IS_DEMO) return;
    setBusy(true);
    try { await api.approveScript(id); } catch (e) { }
    setBusy(false);
  }
  async function doDelete() {
    if (IS_DEMO) return;
    const msg = isRunning ? 'Прервать и удалить эту задачу из очереди?' : 'Удалить эту задачу из очереди?';
    if (!window.confirm(msg)) return;
    setDeleting(true);
    try { await api.deleteVideo(id); onDeleted?.(); }
    catch (e) { setDeleting(false); alert('Не удалось удалить: ' + e.message); }
  }

  return (
    <div className={`queue-item ${isRunning ? 'running' : ''}`}>
      <div className="queue-item-header">
        <div className="queue-item-info">
          <div className="queue-item-topic">{video.topic || 'Без названия'}</div>
          <div className="queue-item-meta">
            <span>{flagFor(video.language || video.lang)} {(video.language || video.lang || '').toUpperCase()}</span>
            {video.duration_minutes && <span>{video.duration_minutes} мин</span>}
            {video.created_at && <span>{formatDate(video.created_at)}</span>}
            {video.cost != null && <span className="cost-tag">${video.cost.toFixed(3)}</span>}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Badge status={video.status || 'pending'} />
          {!IS_DEMO && (
            <button className="btn btn-secondary btn-sm" disabled={deleting} onClick={doDelete}
              title="Удалить задачу из очереди">
              {deleting ? <span className="spinner" /> : '🗑'}
            </button>
          )}
        </div>
      </div>
      {(isRunning || video.current_phase) && <Stepper currentPhase={video.current_phase} progress={video.progress ?? video.progress_percent} detail={video.phase_detail} updatedAt={isRunning ? video.updated_at : null} />}
      {video.status === 'failed' && (
        <div className="completed-details">
          {video.error && <div className="error-msg" style={{ marginBottom: 8 }}>{video.error}</div>}
          {video.checkpoint && PHASE_KEYS.some(k => video.checkpoint[k] === true) && (
            <div className="done-phases">
              Уже готово (не будет переделываться):{' '}
              {PHASE_KEYS.filter(k => video.checkpoint[k] === true).map(k => PHASES[PHASE_KEYS.indexOf(k)]).join(' ✓ · ')} ✓
            </div>
          )}
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={doRetry}>
            {busy ? <span className="spinner" /> : '↻'} Продолжить с места ошибки
          </button>
        </div>
      )}
      {video.status === 'script_ready' && (
        <div className="completed-details">
          <div className="queue-item-meta" style={{ marginBottom: 8 }}>Сценарий готов{video.script_score != null ? ` · балл ${video.script_score}/100` : ''} — открой «Создать» для ревью, или собери сразу:</div>
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={doApprove}>
            {busy ? <span className="spinner" /> : '✓'} Одобрить → собрать видео
          </button>
        </div>
      )}
      {video.status === 'completed' && (
        <div className="completed-details">
          <button className="btn btn-secondary btn-sm" onClick={() => !IS_DEMO && api.downloadVideo(id)}>↓ Скачать ZIP (DaVinci)</button>
        </div>
      )}
    </div>
  );
}

// ══════════════════════
// БИБЛИОТЕКА
// ══════════════════════
function UploadTranslate() {
  const IS_DEMO = useContext(DemoContext);
  const [file, setFile] = useState(null);
  const [targetLang, setTargetLang] = useState('de');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  async function go() {
    if (IS_DEMO || !file) { setMsg('Сначала выбери zip-файл'); return; }
    setBusy(true);
    setMsg('Загружаю зип и перевожу… это ~1-2 мин (большой файл + перевод). Не закрывай вкладку.');
    try {
      const voiceId = targetLang === 'de' ? 'Fghah4fztZORbiKfIGAs' : '';
      const r = await api.translateUpload({ file, targetLang, voiceId });
      setMsg(`✓ Запущено: ${r.task_id}. Идёт в «Очереди» → потом появится в «Библиотеке». Скачай сразу как будет готово.`);
    } catch (e) {
      setMsg('Ошибка: ' + (e.message || e));
    } finally { setBusy(false); }
  }

  return (
    <div style={{ border: '1px dashed rgba(255,255,255,0.18)', borderRadius: 12, padding: 16, marginBottom: 20 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>📦 → 🌍 Перевести из загруженного ZIP</div>
      <div style={{ fontSize: 13, opacity: 0.6, marginBottom: 12 }}>
        Залей готовый zip (например испанский) → сделаю версию на другом языке на ТЕХ ЖЕ картинках и музыке (без перегенерации, только новый голос + тайминги).
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <input type="file" accept=".zip" onChange={e => setFile(e.target.files?.[0] || null)} />
        <select value={targetLang} onChange={e => setTargetLang(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: 8, background: '#161b22', color: '#fff', border: '1px solid rgba(255,255,255,0.15)' }}>
          <option value="de">→ Немецкий (DE)</option>
          <option value="en">→ Английский (EN)</option>
          <option value="es">→ Испанский (ES)</option>
        </select>
        <button className="btn btn-primary btn-sm" disabled={busy || !file} onClick={go}>
          {busy ? <span className="spinner" /> : '↑'} Загрузить и перевести
        </button>
      </div>
      {msg && <div style={{ fontSize: 13, marginTop: 10, opacity: 0.85 }}>{msg}</div>}
    </div>
  );
}

function LibraryTab({ lang }) {
  const IS_DEMO = useContext(DemoContext);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (IS_DEMO) { setVideos(DEMO_VIDEOS.filter(v => v.status === 'completed')); setLoading(false); return; }
    (async () => {
      try { const d = await api.getVideos(); setVideos((Array.isArray(d) ? d : d.items || []).filter(v => v.status === 'completed')); }
      catch (e) { console.error('Library load error:', e); }
      finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <div style={{ textAlign: 'center', padding: '60px' }}><span className="spinner" /></div>;

  const shown = videos.filter(v => !lang || (v.lang || v.language || '').toLowerCase() === lang);

  return (
    <>
      {!IS_DEMO && <UploadTranslate />}
      <div className="library-grid">
        {shown.length === 0 && <div className="library-empty"><div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.3 }}>◇</div><div>Готовых видео пока нет.</div></div>}
        {shown.map(v => {
          const id = v.id || v.task_id;
          return <LibraryCard key={id} v={v} id={id} onDeleted={() => setVideos(prev => prev.filter(x => (x.id || x.task_id) !== id))} />;
        })}
      </div>
    </>
  );
}

function LibraryCard({ v, id, onDeleted }) {
  const IS_DEMO = useContext(DemoContext);
  const [rebuild, setRebuild] = useState('');
  const [deleting, setDeleting] = useState(false);

  async function doRebuild() {
    if (IS_DEMO) return;
    setRebuild('busy');
    // Голос и сценарий сохраняются (берутся из zip) — tts_mode не передаём,
    // заново делаются только картинки, музыка и сборка.
    try { await api.rebuildVideo(id); setRebuild('ok'); }
    catch (e) { setRebuild('err: ' + e.message); }
  }

  async function doDelete() {
    if (IS_DEMO) return;
    if (!window.confirm('Удалить видео из библиотеки? Файлы (zip, клипы) сотрутся, чтобы не занимать место. Тема останется учтённой по твоему YouTube-каналу.')) return;
    setDeleting(true);
    try { await api.deleteVideo(id); onDeleted?.(); }
    catch (e) { setDeleting(false); alert('Не удалось удалить: ' + e.message); }
  }

  return (
    <div className="video-card">
      <div className="video-card-thumb">▶</div>
      <div className="video-card-body">
        <div className="video-card-topic">{(v.titles && v.titles[0]) || v.topic || 'Без названия'}</div>
        {v.titles_ru && v.titles_ru[0] && (
          <div style={{ fontSize: '13px', opacity: 0.6, marginTop: '2px', marginBottom: '6px' }}>🇷🇺 {v.titles_ru[0]}</div>
        )}
        <div className="video-card-meta">
          <span className="meta-chip">{flagFor(v.language || v.lang)} {(v.language || v.lang || '').toUpperCase()}</span>
          {v.script_score != null && <span className="meta-chip">балл {v.script_score}/100</span>}
          {v.duration_minutes && <span className="meta-chip">{v.duration_minutes} мин</span>}
          {v.cost != null && <span className="meta-chip cost-tag">${v.cost.toFixed(3)}</span>}
        </div>
        <div className="video-card-publish-hint">Полные названия, описание, теги и превью-промпты — в файле <b>PUBLISH_{(v.lang || v.language || 'de').toLowerCase()}.md</b> внутри ZIP</div>
        <div className="video-card-footer">
          <span className="video-card-date">{formatDate(v.created_at)}</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary btn-sm" disabled={rebuild === 'busy'}
              onClick={doRebuild}
              title="Тот же голос и сценарий — заново делаются только картинки, музыка и сборка (с последними фиксами)">
              {rebuild === 'busy' ? <span className="spinner" /> : '⟲'} Пересобрать
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => !IS_DEMO && api.downloadVideo(id)}>↓ Скачать</button>
            <button className="btn btn-secondary btn-sm" disabled={deleting} onClick={doDelete}
              title="Удалить из библиотеки и освободить место (дедуп тем теперь по YouTube-каналу)">
              {deleting ? <span className="spinner" /> : '🗑'}
            </button>
          </div>
        </div>
        {rebuild === 'busy' && <div className="done-phases" style={{ marginTop: 8 }}>Тот же голос — перегенерирую картинки заново…</div>}
        {rebuild === 'ok' && <div className="done-phases" style={{ marginTop: 8 }}>Пересборка пошла — прогресс во вкладке «Очередь»</div>}
        {rebuild.startsWith('err') && <div className="error-msg" style={{ marginTop: 8 }}>{rebuild}</div>}
      </div>
    </div>
  );
}

// Готовность сценария к продакшну (сборке на платном голосе). Чтобы клиент не гадал
// «с какого балла можно собирать» и не жёг деньги на средних сценариях / лишних правках.
// Порог откалиброван по судье (реальные топ-доки = 84-92).
function prodReadiness(score) {
  if (score >= 80) return { tag: '✅ готов к продакшну', color: 'var(--success)',
    advice: 'Можно смело собирать на фирменном голосе и публиковать — уровень топовых доков.' };
  if (score >= 70) return { tag: '👍 можно собирать', color: 'var(--cyan)',
    advice: 'Хороший сценарий — можно собирать на фирменном голосе. «Улучшить» лишь подтянет к топу, не обязателен.' };
  if (score >= 55) return { tag: '⚠️ сначала улучшить', color: 'var(--warning)',
    advice: 'Слабовато для платной сборки — сначала жми «Улучшить», иначе рискуешь потратить деньги на средний видос.' };
  return { tag: '❌ доработать', color: 'var(--error)',
    advice: 'Слабый сценарий — доработай «Улучшить» или смени тему перед сборкой.' };
}

// ══════════════════════
// ЧЕРНОВИКИ (script_ready)
// ══════════════════════
function ChannelBar({ active, onChange }) {
  const IS_DEMO = useContext(DemoContext);
  const [channels, setChannels] = useState([]);
  useEffect(() => {
    if (IS_DEMO) { setChannels(DEMO_CHANNELS); return; }
    api.getChannels().then(d => setChannels(Array.isArray(d) ? d : [])).catch(() => {});
  }, [IS_DEMO]);
  if (channels.length < 2) return null;
  return (
    <div className="lang-selector" style={{ marginBottom: 16 }}>
      <button type="button" className={`lang-btn ${!active ? 'active' : ''}`} onClick={() => onChange(null)}>Все каналы</button>
      {channels.map(ch => (
        <button key={ch.lang} type="button" className={`lang-btn ${active === ch.lang ? 'active' : ''}`} onClick={() => onChange(ch.lang)}>
          {flagFor(ch.lang)} {ch.name}
        </button>
      ))}
    </div>
  );
}

function DraftsTab({ onApproved, lang }) {
  const IS_DEMO = useContext(DemoContext);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null); // task_id открытого черновика
  const [ttsMode, setTtsMode] = useState('fal');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (IS_DEMO) { setDrafts(DEMO_DRAFTS); setLoading(false); return; }
    (async () => {
      try {
        const d = await api.getVideos();
        setDrafts((Array.isArray(d) ? d : d.items || []).filter(v => v.status === 'script_ready'));
      } catch (e) { setError(e.message); }
      finally { setLoading(false); }
    })();
    const interval = setInterval(async () => {
      if (IS_DEMO) return;
      try {
        const d = await api.getVideos();
        setDrafts((Array.isArray(d) ? d : d.items || []).filter(v => v.status === 'script_ready'));
      } catch { /* тихо */ }
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  async function handleApprove(id, alreadyBuilt = false) {
    if (IS_DEMO) { onApproved?.(); return; }
    if (alreadyBuilt && !window.confirm('По этому сценарию уже собрано видео (есть в Библиотеке). Собрать ещё раз?')) return;
    setBusy(true); setError('');
    try {
      // Сценарий клонируется в новое видео — черновик ОСТАЁТСЯ (переиспользуем),
      // поэтому из списка не убираем. Просто переходим в очередь.
      await api.approveScript(id, ttsMode);
      onApproved?.();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function handleImprove(id) {
    if (IS_DEMO) return;
    setBusy(true); setError('');
    try {
      await api.improveScript(id);
      // перезагрузим через poll
      const poll = setInterval(async () => {
        try {
          const v = await api.getVideo(id);
          if (v.status === 'script_ready') {
            clearInterval(poll);
            setDrafts(prev => prev.map(d => (d.task_id || d.id) === id ? v : d));
            setBusy(false);
          } else if (v.status === 'failed') {
            clearInterval(poll); setBusy(false); setError('Улучшение не удалось: ' + (v.error || ''));
          }
        } catch { /* poll */ }
      }, 4000);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: '60px' }}><span className="spinner" /></div>;

  const shown = drafts.filter(d => !lang || (d.lang || '') === lang);

  return (
    <div>
      {error && <div className="error-msg">{error}</div>}
      {shown.length === 0 && !error && (
        <div className="queue-empty">
          <div className="queue-empty-icon">✎</div>
          <div>Черновиков нет. Создай сценарий во вкладке «Создать».</div>
        </div>
      )}
      {shown.map(draft => {
        const id = draft.task_id || draft.id;
        const isOpen = expanded === id;
        const score = draft.script_score ?? 0;
        const color = score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--cyan)' : score >= 40 ? 'var(--warning)' : 'var(--error)';
        return (
          <div key={id} className="queue-item" style={{ cursor: 'pointer' }}>
            <div className="queue-item-header" onClick={() => setExpanded(isOpen ? null : id)}>
              <div className="queue-item-info">
                <div className="queue-item-topic">
                  {draft.topic || 'Без названия'}
                  {draft.on_channel
                    ? <span style={{ marginLeft: 8, fontSize: '0.7rem', color: 'var(--warning)', border: '1px solid var(--warning)', borderRadius: 6, padding: '1px 6px' }}>⚠ уже на YouTube</span>
                    : <span style={{ marginLeft: 8, fontSize: '0.7rem', color: 'var(--success)', border: '1px solid var(--success)', borderRadius: 6, padding: '1px 6px' }}>✓ новая тема</span>}
                  {draft.already_built && <span style={{ marginLeft: 8, fontSize: '0.7rem', color: 'var(--cyan)', border: '1px solid var(--cyan)', borderRadius: 6, padding: '1px 6px' }}>📁 уже собрано</span>}
                </div>
                <div className="queue-item-meta">
                  <span>{flagFor(draft.lang)} {(draft.lang || '').toUpperCase()}</span>
                  {(draft.updated_at || draft.created_at) && <span>🕐 {formatDate(draft.updated_at || draft.created_at)}</span>}
                  {score > 0 && <span style={{ color }}>Балл: {score}/100</span>}
                  {score > 0 && <span style={{ color: prodReadiness(score).color, fontWeight: 600 }}>{prodReadiness(score).tag}</span>}
                  {draft.improve_note && <span style={{ color: 'var(--cyan)' }}>↻ {draft.improve_note}</span>}
                </div>
              </div>
              <span style={{ fontSize: '18px', opacity: 0.5 }}>{isOpen ? '▲' : '▼'}</span>
            </div>
            {isOpen && (
              <div className="completed-details">
                <ScriptRubric rubric={draft.script_rubric} />
                {draft.script_ru && (
                  <>
                    <label className="form-label" style={{ marginBottom: 4 }}>Перевод сценария</label>
                    <div className="script-ru" style={{ maxHeight: 200, overflowY: 'auto', marginBottom: 16 }}>
                      {draft.script_ru}
                    </div>
                  </>
                )}
                <div className="form-group" style={{ marginBottom: 12 }}>
                  <label className="form-label">Озвучка</label>
                  <div className="lang-selector">
                    <button type="button" className={`lang-btn ${ttsMode === 'fal' ? 'active' : ''}`}
                      onClick={() => setTtsMode('fal')}>💎 Фирменный голос <span className="cost-tag">~$2</span></button>
                    <button type="button" className={`lang-btn ${ttsMode === 'free' ? 'active' : ''}`}
                      onClick={() => setTtsMode('free')}>🆓 Тестовый</button>
                  </div>
                </div>
                {score > 0 && (
                  <div style={{ fontSize: '0.82rem', color: prodReadiness(score).color, fontWeight: 600,
                                border: `1px solid ${prodReadiness(score).color}`, borderRadius: 8,
                                padding: '8px 10px', marginBottom: 12 }}>
                    {prodReadiness(score).tag} · {prodReadiness(score).advice}
                  </div>
                )}
                <div style={{ fontSize: '0.76rem', color: '#8b92a0', marginBottom: 12 }}>
                  🎨 Видеоряд — авто под каждую сцену (сток / фото / графика / скетчи).
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-secondary btn-sm" disabled={busy} onClick={() => handleImprove(id)}>
                    {busy ? <span className="spinner" /> : '↻'} Улучшить
                  </button>
                  <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => handleApprove(id, draft.already_built)}>
                    {busy ? <span className="spinner" /> : '✓'} {draft.already_built ? 'Собрать ещё раз' : 'Одобрить → собрать видео'}
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ══════════════════════
// LOGIN
// ══════════════════════
function LoginScreen({ onOk }) {
  const [pw, setPw] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true); setErr('');
    api.setPassword(pw);
    try { await api.getChannels(); onOk(); }
    catch (e) { setErr(e.code === 401 ? 'Неверный пароль' : e.message); api.setPassword(''); }
    finally { setBusy(false); }
  }
  return (
    <div className="login-wrap">
      <form className="card login-card card-glow" onSubmit={submit}>
        <div className="header-logo login-logo">▶</div>
        <h1 className="login-title">YouTube Factory</h1>
        <div className="login-sub">Доступ только для владельца</div>
        <input type="password" className="form-input" placeholder="Пароль доступа"
          value={pw} onChange={e => setPw(e.target.value)} autoFocus />
        {err && <div className="error-msg">{err}</div>}
        <button className="btn btn-primary" disabled={busy || !pw}>
          {busy ? <span className="spinner" /> : 'Войти'}
        </button>
      </form>
    </div>
  );
}

// ══════════════════════
// APP
// ══════════════════════
export default function App() {
  const [tab, setTab] = useState('create');
  const [authState, setAuthState] = useState('checking'); // checking | demo | needauth | ok
  const [resetConfirm, setResetConfirm] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0); // ремоунт активной вкладки после сброса
  const [activeChannel, setActiveChannel] = useState(null); // выбранный канал (lang) — фильтр Черновики/Очередь/Библиотека; null = все

  const verify = useCallback(() => {
    setAuthState('checking');
    api.checkHealth()
      .then(() => api.getChannels()
        .then(() => setAuthState('ok'))
        .catch(e => setAuthState(e.code === 401 ? 'needauth' : 'ok')))
      .catch(() => setAuthState('demo'));
  }, []);

  useEffect(() => { verify(); }, [verify]);

  if (authState === 'checking') {
    return <div className="app" style={{ textAlign: 'center', paddingTop: 120 }}><span className="spinner spinner-lg" /></div>;
  }
  if (authState === 'needauth') {
    return <LoginScreen onOk={verify} />;
  }
  const isDemo = authState === 'demo';

  async function handleFactoryReset(scope) {
    if (isDemo) { setResetConfirm(false); return; }
    setResetting(true);
    try { await api.factoryReset(scope); setResetConfirm(false); setRefreshKey(k => k + 1); }
    catch (e) { alert('Ошибка сброса: ' + e.message); }
    finally { setResetting(false); }
  }

  // Сброс ПО ВКЛАДКЕ — каждая чистит только свою часть, не трогая остальные.
  const RESET_MAP = {
    create:  { scope: 'all',     q: 'Удалить ВСЕ данные (видео, черновики, история каналов)?', link: 'Сбросить все данные' },
    queue:   { scope: 'queue',   q: 'Очистить очередь — активные и упавшие задачи? (Библиотека и черновики останутся)', link: 'Очистить очередь' },
    library: { scope: 'library', q: 'Удалить все готовые видео из библиотеки?', link: 'Очистить библиотеку' },
    drafts:  { scope: 'drafts',  q: 'Удалить все черновики-сценарии?', link: 'Удалить все черновики' },
  };
  const rc = RESET_MAP[tab] || RESET_MAP.create;

  const tabs = [
    { id: 'create',  label: 'Создать',    icon: '✦' },
    { id: 'drafts',  label: 'Черновики',  icon: '✎' },
    { id: 'queue',   label: 'Очередь',    icon: '≡' },
    { id: 'library', label: 'Библиотека', icon: '▤' },
  ];

  return (
    <DemoContext.Provider value={isDemo}>
      <div className="app">
        <header className="header">
          <div className="header-logo">▶</div>
          <div className="header-title">
            <h1>YouTube Factory</h1>
            <span className="header-sub">видео-конвейер v1.1</span>
          </div>
        </header>

        {isDemo && (
          <div className="demo-banner">
            <span className="demo-banner-icon">◈</span>
            <span><b>Превью</b> — бэкенд не подключён. Демо-данные.</span>
          </div>
        )}

        <nav className="tabs">
          {tabs.map(t => (
            <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              <span className="tab-icon">{t.icon}</span>{t.label}
            </button>
          ))}
        </nav>

        {tab !== 'create' && <ChannelBar active={activeChannel} onChange={setActiveChannel} />}

        {tab === 'create'  && <CreateTab key={`create-${refreshKey}`} initialLang={activeChannel} onCreated={() => setTab('queue')} />}
        {tab === 'drafts'  && <DraftsTab key={`drafts-${refreshKey}`} lang={activeChannel} onApproved={() => setTab('queue')} />}
        {tab === 'queue'   && <QueueTab key={`queue-${refreshKey}`} lang={activeChannel} />}
        {tab === 'library' && <LibraryTab key={`library-${refreshKey}`} lang={activeChannel} />}

        {/* Сброс данных — по активной вкладке (чистит только её) */}
        <div style={{ textAlign: 'center', padding: '32px 0 16px', opacity: 0.4 }}>
          {!resetConfirm
            ? <button className="btn-link" style={{ fontSize: '11px' }} onClick={() => setResetConfirm(true)}>{rc.link}</button>
            : (
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
                <span style={{ fontSize: '11px' }}>{rc.q}</span>
                <button className="btn btn-secondary btn-sm" disabled={resetting} onClick={() => handleFactoryReset(rc.scope)}>
                  {resetting ? <span className="spinner" /> : 'Да, сбросить'}
                </button>
                <button className="btn-link" style={{ fontSize: '11px' }} onClick={() => setResetConfirm(false)}>Отмена</button>
              </div>
            )
          }
        </div>
      </div>
    </DemoContext.Provider>
  );
}
