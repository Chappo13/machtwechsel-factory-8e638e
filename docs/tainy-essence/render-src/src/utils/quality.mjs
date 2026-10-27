import { buildRevealMap, boardTiming, annotationTiming } from './revealTiming.mjs';
import { MAP_REGIONS } from './regions.mjs';

export const SCENE_TYPES = ['title_card', 'diary', 'map', 'timeline', 'blueprint', 'board', 'document', 'scale', 'number', 'stars', 'quote', 'media', 'compare', 'counter', 'steps', 'fact_stack', 'table', 'map_route', 'tally'];
export const TALLY_ICONS = ['ship', 'person', 'coin', 'amphora', 'dot'];
export const ATMOS_KINDS = ['snow', 'spray', 'fog', 'dust', 'embers'];
export const MAP_MARKERS = ['ship', 'person', 'dot'];
// 15.10: на экране нет русского текста (кроме водяного знака канала): подписи карт и годы только латиницей/цифрами.
export const hasCyrillic = (v) => /[\u0400-\u04FF]/.test(String(v ?? ''));
export const STEP_ICONS = ['gear', 'flask', 'bolt', 'coin', 'sun', 'water', 'fire', 'hammer', 'scroll', 'eye', 'key', 'ship', 'stone', 'skull'];
export const MAX_LABEL_WORDS = 6;
const kinds = ['circle', 'arrow', 'label', 'box', 'underline', 'loupe'];
const fail = (where, message) => { throw new Error(`${where}: ${message}`); };
const finite = (v, where) => { if (typeof v !== 'number' || !Number.isFinite(v)) fail(where, 'expected finite number'); return v; };
const object = (v, where) => { if (!v || typeof v !== 'object' || Array.isArray(v)) fail(where, 'expected object'); return v; };
const id = (v, where) => { if (typeof v !== 'string' || !v.trim()) fail(where, 'required non-empty id'); return v; };
function array(v, where) { if (!Array.isArray(v)) fail(where, 'expected array'); return v; }
function unique(values, where) { const seen = new Set(); for (const v of values) { id(v, where); if (seen.has(v)) fail(where, `duplicate id ${v}`); seen.add(v); } }
export const sceneFrames = (scene, fps) => Math.round(scene.end * fps) - Math.round(scene.start * fps);

export function normalizeAnnotation(annotation, where = 'annotation') {
  const a = { ...object(annotation, where) };
  id(a.id, where);
  const legacy = Array.isArray(a.bbox) || a.bbox === undefined;
  if (Array.isArray(a.bbox)) {
    if (a.bbox.length !== 4) fail(where, 'legacy bbox must be [x0,y0,x1,y1]');
    a.bbox.forEach((v) => finite(v, `${where}.bbox`));
    const [x0, y0, x1, y1] = a.bbox;
    a.bbox = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  } else if (a.bbox === undefined) {
    // Legacy flat x,y were centers. Keep supported defaults, but validate the result.
    const x = finite(a.x ?? 0.5, where), y = finite(a.y ?? 0.5, where);
    const w = finite(a.w ?? 0.2, where), h = finite(a.h ?? 0.14, where);
    a.bbox = { x: x - w / 2, y: y - h / 2, w, h };
  }
  const b = object(a.bbox, `${where}.bbox`);
  for (const k of ['x', 'y', 'w', 'h']) finite(b[k], `${where}.bbox.${k}`);
  if (b.x < 0 || b.y < 0 || b.w <= 0 || b.h <= 0 || b.x + b.w > 1 + 1e-12 || b.y + b.h > 1 + 1e-12) fail(where, 'bbox must have positive size and lie within normalized [0,1] image bounds');
  if (a.kind === undefined && legacy) a.kind = 'label';
  if (!kinds.includes(a.kind)) fail(where, `kind required; expected ${kinds.join('|')}`);
  if (a.confidence !== undefined && (finite(a.confidence, where) < 0 || a.confidence > 1)) fail(where, 'confidence must be in [0,1]');
  if (a.kind === 'loupe' && a.zoom !== undefined && (finite(a.zoom, `${where}.zoom`) < 1.5 || a.zoom > 4)) fail(where, 'loupe zoom must be in [1.5,4]');
  delete a.x; delete a.y; delete a.w; delete a.h;
  return a;
}

export function elementIds(scene) {
  const d = scene.data;
  const keys = { diary: ['items'], map: ['pins'], timeline: ['events'], blueprint: ['labels', 'dims'], board: ['cards', 'links'], document: ['lines'] }[scene.type] || [];
  const ids = keys.flatMap((k) => array(d[k] ?? [], `${scene.id}.${k}`).map((e) => id(e?.id, `${scene.id}.${k}`)));
  const extra = { counter: ['items'], steps: ['steps'], fact_stack: ['facts'], table: ['rows'] }[scene.type];
  if (extra) for (const k of extra) ids.push(...array(d[k] ?? [], `${scene.id}.${k}`).map((e) => id(e?.id, `${scene.id}.${k}`)));
  if (scene.type === 'compare') ids.push('left', 'right');
  if (scene.type === 'media' && d.lower_third?.id !== undefined) ids.push(id(d.lower_third.id, `${scene.id}.lower_third`));
  if (scene.type === 'media') {
    for (const sh of d.shots || []) ids.push(...array(sh.annotations ?? [], `${scene.id}.${sh.id}.annotations`).map((e) => id(e?.id, `${scene.id}.${sh.id}.annotations`)));
  }
  if (scene.type === 'board') {
    for (const c of d.cards || []) if (c.textId !== undefined) { id(c.textId, `${scene.id}.textId`); if (!c.text) fail(scene.id, 'textId requires card text'); ids.push(c.textId); }
    if (d.stampId !== undefined) { id(d.stampId, `${scene.id}.stampId`); if (!d.stamp) fail(scene.id, 'stampId requires stamp'); ids.push(d.stampId); }
  }
  return ids;
}

const words = (v) => String(v ?? '').trim().split(/\s+/).filter(Boolean).length;
const label = (v, where, { required = true, max = MAX_LABEL_WORDS } = {}) => {
  if (v === undefined && !required) return;
  if (typeof v !== 'string' || (required && !v.trim())) fail(where, 'expected non-empty string');
  if (words(v) > max) fail(where, `label longer than ${max} words (thesis label, not narration copy)`);
};
// Shape checks for the new typed scenes (mirror of pipeline/visual_quality.py scene_data_issues).
export function validateSceneShape(s, where) {
  const d = s.data;
  const list = (key, lo, hi) => { const a = array(d[key], `${where}.${key}`); if (a.length < lo || a.length > hi) fail(where, `${key} needs ${lo}-${hi} elements, has ${a.length}`); return a; };
  if (s.type === 'counter') {
    for (const [i, it] of list('items', 1, 3).entries()) {
      object(it, `${where}.items[${i}]`); finite(it.value, `${where}.items[${i}].value`); label(it.label, `${where}.items[${i}].label`);
      if (it.from !== undefined) finite(it.from, `${where}.items[${i}].from`);
      if (it.decimals !== undefined && (!Number.isInteger(it.decimals) || it.decimals < 0 || it.decimals > 2)) fail(where, 'decimals must be integer 0..2');
      label(it.unit, `${where}.items[${i}].unit`, { required: false, max: 3 });
    }
  } else if (s.type === 'steps') {
    for (const [i, st] of list('steps', 3, 5).entries()) {
      object(st, `${where}.steps[${i}]`); label(st.label, `${where}.steps[${i}].label`);
      if (st.icon !== undefined && !STEP_ICONS.includes(st.icon)) fail(where, `unknown icon ${st.icon}`);
    }
    label(d.title, `${where}.title`, { required: false });
  } else if (s.type === 'fact_stack') {
    for (const [i, f] of list('facts', 3, 4).entries()) {
      object(f, `${where}.facts[${i}]`); label(f.label, `${where}.facts[${i}].label`);
      if (typeof f.big !== 'string' || !f.big.trim() || f.big.length > 12) fail(where, `facts[${i}].big must be a string up to 12 chars`);
    }
  } else if (s.type === 'table') {
    const cols = array(d.columns, `${where}.columns`);
    if (cols.length < 2 || cols.length > 4) fail(where, 'table needs 2-4 columns');
    cols.forEach((c, i) => { if (typeof c !== 'string') fail(where, `columns[${i}] must be string`); label(c, `${where}.columns[${i}]`, { required: i === 0 ? false : true, max: 3 }); });
    for (const [i, r] of list('rows', 2, 5).entries()) {
      object(r, `${where}.rows[${i}]`);
      const cells = array(r.cells, `${where}.rows[${i}].cells`);
      if (cells.length !== cols.length) fail(where, `rows[${i}] needs ${cols.length} cells`);
      cells.forEach((c, j) => label(c, `${where}.rows[${i}].cells[${j}]`, { max: 5 }));
    }
    label(d.title, `${where}.title`, { required: false });
  } else if (s.type === 'compare') {
    for (const side of ['left', 'right']) {
      object(d[side], `${where}.${side}`); label(d[side].label, `${where}.${side}.label`); label(d[side].caption, `${where}.${side}.caption`, { required: false, max: 10 });
      if (d[side].src !== undefined && (typeof d[side].src !== 'string' || !d[side].src.trim())) fail(where, `${side}.src must be a non-empty path`);
    }
    if (d.mode !== undefined && !['split', 'slider'].includes(d.mode)) fail(where, 'mode must be split|slider');
    label(d.title, `${where}.title`, { required: false });
  } else if (s.type === 'map_route') {
    if (!MAP_REGIONS.includes(d.region)) fail(where, `region must be one of ${MAP_REGIONS.join('|')}`);
    const pts = list('route_pts', 1, 12);
    pts.forEach((p, i) => {
      object(p, `${where}.route_pts[${i}]`);
      if (finite(p.lat, `${where}.route_pts[${i}].lat`) < -90 || p.lat > 90 || finite(p.lon, `${where}.route_pts[${i}].lon`) < -180 || p.lon > 180) fail(where, `route_pts[${i}] lat/lon out of range`);
    });
    if (d.places !== undefined) {
      const pl = array(d.places, `${where}.places`);
      if (pl.length > 3) fail(where, 'places: at most 3 labelled places per map');
      pl.forEach((p, i) => {
        object(p, `${where}.places[${i}]`); finite(p.lat, `${where}.places[${i}].lat`); finite(p.lon, `${where}.places[${i}].lon`);
        if (typeof p.en !== 'string' || !/^[A-Z0-9][A-Z0-9 .'-]{0,23}$/.test(p.en)) fail(where, `places[${i}].en must be short English CAPS (<=24 chars, no Cyrillic)`);
      });
    }
    if (d.year !== undefined && (typeof d.year !== 'string' || hasCyrillic(d.year) || d.year.length > 24)) fail(where, 'year must be a short Latin/digit string (no Russian)');
    if (d.marker !== undefined && !MAP_MARKERS.includes(d.marker)) fail(where, `marker must be ${MAP_MARKERS.join('|')}`);
    for (const k of ['route_from', 'route_to']) if (d[k] !== undefined) finite(d[k], `${where}.${k}`);
  } else if (s.type === 'tally') {
    if (!Number.isInteger(d.total) || d.total < 1 || d.total > 60) fail(where, 'tally.total must be an integer 1..60');
    if (d.remain !== undefined && d.remain !== null && (!Number.isInteger(d.remain) || d.remain < 0 || d.remain > d.total)) fail(where, 'tally.remain must be an integer 0..total');
    if (d.icon !== undefined && !TALLY_ICONS.includes(d.icon)) fail(where, `tally.icon must be ${TALLY_ICONS.join('|')}`);
    for (const k of ['tally_at', 'tally_dur']) if (d[k] !== undefined) finite(d[k], `${where}.${k}`);
  } else if (s.type === 'media' && d.lower_third !== undefined) {
    object(d.lower_third, `${where}.lower_third`); id(d.lower_third.id, `${where}.lower_third`);
    label(d.lower_third.title, `${where}.lower_third.title`); label(d.lower_third.subtitle, `${where}.lower_third.subtitle`, { required: false, max: 8 });
  }
}

const unit = (v, where) => { if (finite(v, where) < 0 || v > 1) fail(where, 'expected number in [0,1]'); return v; };
// Эффекты шота (15.10): красный callout на реальном фото, частицы атмосферы, фокус-зум. Все поля необязательны.
export function validateShotEffects(sh, where) {
  if (sh.callout !== undefined) {
    const c = object(sh.callout, `${where}.callout`);
    if (sh.kind === 'video') fail(where, 'callout is only for still images');
    const ci = object(c.circle, `${where}.callout.circle`);
    for (const k of ['cx', 'cy']) unit(ci[k], `${where}.callout.circle.${k}`);
    for (const k of ['rx', 'ry']) if (finite(ci[k], `${where}.callout.circle.${k}`) <= 0 || ci[k] > 0.6) fail(where, `callout.circle.${k} must be in (0,0.6]`);
    const zb = object(c.zoomBox, `${where}.callout.zoomBox`);
    for (const k of ['x', 'y', 'w', 'h']) unit(zb[k], `${where}.callout.zoomBox.${k}`);
    if (zb.w <= 0 || zb.h <= 0 || zb.x + zb.w > 1 + 1e-9 || zb.y + zb.h > 1 + 1e-9) fail(where, 'callout.zoomBox must lie within the image');
    for (const k of ['circleAt', 'zoomAt']) if (finite(c[k], `${where}.callout.${k}`) < 0) fail(where, `callout.${k} must be >= 0`);
    for (const k of ['arrowAt', 'zoomDur', 'zoomMax', 'arrowAngleDeg', 'arrowLen']) if (c[k] !== undefined) finite(c[k], `${where}.callout.${k}`);
  }
  if (sh.atmos !== undefined) {
    const a = object(sh.atmos, `${where}.atmos`);
    if (!ATMOS_KINDS.includes(a.kind)) fail(where, `atmos.kind must be ${ATMOS_KINDS.join('|')}`);
    if (a.intensity !== undefined && (finite(a.intensity, `${where}.atmos.intensity`) <= 0 || a.intensity > 2)) fail(where, 'atmos.intensity must be in (0,2]');
  }
  if (sh.zoom !== undefined) {
    const z = object(sh.zoom, `${where}.zoom`);
    if (sh.kind === 'video') fail(where, 'zoom is only for still images');
    unit(z.x, `${where}.zoom.x`); unit(z.y, `${where}.zoom.y`);
    if (z.to !== undefined && (finite(z.to, `${where}.zoom.to`) < 1 || z.to > 1.6)) fail(where, 'zoom.to must be in [1,1.6]');
    if (z.box !== undefined) {
      const b = object(z.box, `${where}.zoom.box`);
      for (const k of ['x', 'y', 'w', 'h']) unit(b[k], `${where}.zoom.box.${k}`);
      if (b.w <= 0 || b.h <= 0 || b.x + b.w > 1 + 1e-9 || b.y + b.h > 1 + 1e-9) fail(where, 'zoom.box must lie within the image');
    }
  }
}

// Canonicalize at the input boundary. Never mutate the caller/job scenes.json.
export function normalizeScenes(input) {
  object(input, 'scenesFile');
  const f = structuredClone(input);
  finite(f.fps, 'fps'); finite(f.duration_sec, 'duration_sec');
  if (f.fps <= 0 || f.fps > 120 || f.duration_sec <= 0) fail('timeline', 'fps must be (0,120], duration_sec > 0');
  if (!array(f.scenes, 'scenes').length) fail('scenes', 'at least one scene required');
  unique(f.scenes.map((s) => s?.id), 'scenes');
  let previous = 0;
  for (const s of f.scenes) {
    const where = `scene ${s.id}`;
    if (!SCENE_TYPES.includes(s.type)) fail(where, `unknown scene type ${s.type}`);
    finite(s.start, `${where}.start`); finite(s.end, `${where}.end`);
    if (s.start < 0 || s.end <= s.start || s.end > f.duration_sec + 1e-7) fail(where, 'invalid start/end or outside duration_sec');
    // Sub-frame JSON rounding accepted only if it yields EXACT adjacent frame boundaries.
    if (Math.abs(s.start - previous) > 1 / f.fps || Math.round(s.start * f.fps) !== Math.round(previous * f.fps)) fail(where, `timeline gap/overlap at ${s.start}; expected ${previous}`);
    if (sceneFrames(s, f.fps) < 1) fail(where, 'scene must occupy at least one frame');
    previous = s.end;
    object(s.data, `${where}.data`);
    // Own copy per scene: scenes built via object-spread in authoring code can
    // share a `data` reference (shallow copy) even after structuredClone, which
    // preserves that sharing. Mutating in place below must never leak across scenes.
    const d = s.data = { ...s.data };
    if (s.type === 'media') {
      // Canonical form is always d.shots: one or more consecutive shots tiling
      // the scene exactly (same contiguous-boundary rule as the top-level
      // timeline). A single legacy flat src becomes one shot spanning the scene.
      const legacyShot = d.src !== undefined ? { id: `${s.id}_shot0`, start: s.start, end: s.end, src: d.src, kind: d.kind, fit: d.fit, trimStartSec: d.trimStartSec, playbackRate: d.playbackRate, focus: d.focus, caption: d.caption, credit: d.credit, annotations: d.annotations } : undefined;
      const shotsInput = d.shots !== undefined ? array(d.shots, `${where}.shots`) : (legacyShot ? [legacyShot] : fail(where, 'media scene requires src or shots'));
      if (!shotsInput.length) fail(where, 'media scene requires at least one shot');
      unique(shotsInput.map((sh) => sh?.id), `${where}.shots`);
      let prevEnd = s.start;
      const shots = shotsInput.map((shIn, i) => {
        const sh = { ...object(shIn, `${where}.shots[${i}]`) };
        const swhere = `${where}.shots[${i}] (${sh.id})`;
        id(sh.id, swhere);
        finite(sh.start, `${swhere}.start`); finite(sh.end, `${swhere}.end`);
        if (Math.abs(sh.start - prevEnd) > 1 / f.fps || Math.round(sh.start * f.fps) !== Math.round(prevEnd * f.fps)) fail(swhere, `shot timeline gap/overlap at ${sh.start}; expected ${prevEnd}`);
        if (sh.end <= sh.start) fail(swhere, 'shot end must follow start');
        if (sceneFrames(sh, f.fps) < 1) fail(swhere, 'shot must occupy at least one frame');
        prevEnd = sh.end;
        if (typeof sh.src !== 'string' || !sh.src.trim()) fail(swhere, 'shot src required');
        sh.kind ??= /\.(mp4|mov|webm|m4v)$/i.test(sh.src) ? 'video' : 'image';
        if (!['video', 'image'].includes(sh.kind)) fail(swhere, 'shot kind must be video|image');
        sh.fit ??= 'cover'; sh.trimStartSec ??= 0; sh.playbackRate ??= 1;
        if (!['cover', 'contain'].includes(sh.fit)) fail(swhere, 'fit must be cover|contain');
        if (finite(sh.trimStartSec, swhere) < 0) fail(swhere, 'trimStartSec must be >= 0');
        if (finite(sh.playbackRate, swhere) < 0.5 || sh.playbackRate > 2) fail(swhere, 'playbackRate must be within [0.5,2]');
        if (sh.focus !== undefined) {
          object(sh.focus, `${swhere}.focus`);
          for (const k of ['x', 'y']) if (finite(sh.focus[k], `${swhere}.focus.${k}`) < 0 || sh.focus[k] > 1) fail(swhere, 'focus must lie in [0,1]');
        }
        validateShotEffects(sh, swhere);
        sh.annotations = array(sh.annotations ?? [], `${swhere}.annotations`).map((a, j) => normalizeAnnotation(a, `${swhere}.annotations[${j}]`));
        return sh;
      });
      if (Math.round(prevEnd * f.fps) !== Math.round(s.end * f.fps) || Math.abs(prevEnd - s.end) > 1 / f.fps) fail(where, `shots must tile the scene exactly; last shot ends at ${prevEnd}, expected ${s.end}`);
      d.shots = shots;
      delete d.src; delete d.kind; delete d.fit; delete d.trimStartSec; delete d.playbackRate; delete d.focus; delete d.caption; delete d.credit; delete d.annotations;
    }
    validateSceneShape(s, where);
    const ids = elementIds(s);
    unique(ids, `${where} elements`);
    s.beats = array(s.beats ?? [], `${where}.beats`);
    unique(s.beats.map((b) => b?.id), `${where} beats`);
    for (const b of s.beats) {
      finite(b.t, `${where}.beat ${b.id}`);
      if (!ids.includes(b.id)) fail(where, `beat ${b.id} does not target an element`);
      if (b.t < s.start || b.t >= s.end || Math.round(b.t * f.fps) >= Math.round(s.end * f.fps)) fail(where, `beat ${b.id} outside scene bounds`);
    }
    if (s.type === 'board') {
      const cards = new Set((d.cards || []).map((c) => c.id));
      for (const l of d.links || []) if (!cards.has(l.from) || !cards.has(l.to)) fail(where, `link ${l.id} references missing card`);
    }
    if (s.type === 'map') for (const pin of d.route || []) if (!(d.pins || []).some((p) => p.id === pin)) fail(where, `route references missing pin ${pin}`);
  }
  if (Math.round(previous * f.fps) !== Math.round(f.duration_sec * f.fps) || Math.abs(previous - f.duration_sec) > 1 / f.fps) fail('timeline', 'last scene must end at duration_sec');
  for (const w of array(f.words ?? [], 'words')) {
    finite(w.start, 'word.start'); finite(w.end, 'word.end');
    if (w.start < 0 || w.end <= w.start || w.end > f.duration_sec + 1 / f.fps || typeof w.w !== 'string') fail('words', 'invalid word interval/text');
  }
  // Alignment may overlap across paragraphs; canonical ordering keeps subtitle lookup valid.
  f.words = (f.words || []).sort((a, b) => a.start - b.start);
  for (const c of array(f.chapters ?? [], 'chapters')) if (finite(c.start, 'chapter.start') < 0 || c.start >= f.duration_sec || typeof c.title !== 'string') fail('chapters', 'invalid chapter');
  f.chapters = (f.chapters || []).sort((a, b) => a.start - b.start);
  if (f.chapter_badge !== undefined && typeof f.chapter_badge !== 'boolean') fail('chapter_badge', 'must be boolean');
  if (f.brand_en !== undefined && typeof f.brand_en !== 'boolean') fail('brand_en', 'must be boolean');
  // standalone_short: самостоятельный мини-таймлайн шортса (shorts_scenes/shortN.json) — без глав/слов/оверлеев,
  // любая длительность (не окно длинного ролика). Флаг ставит Python-сторона; путь shorts_scenes/ тоже считается (см. lib/preflight.mjs).
  if (f.standalone_short !== undefined && typeof f.standalone_short !== 'boolean') fail('standalone_short', 'must be boolean');
  f.overlays = normalizeOverlays(f.overlays, f.duration_sec);
  if (!f.overlays.length) delete f.overlays;
  return f;
}

export const OVERLAY_POSITIONS = ['top-right', 'bottom-left'];
export const DATE_CHIP_POSITIONS = ['top-left', 'top-right', 'bottom-left'];
// Опциональный верхнеуровневый overlays[]: старые файлы без поля не затрагиваются, но если поле есть — проверка строгая.
export function normalizeOverlays(input, duration) {
  if (input === undefined || input === null) return [];
  return array(input, 'overlays').map((raw, i) => {
    const where = `overlays[${i}]`;
    const o = { ...object(raw, where) };
    if (o.type !== 'audio_hint' && o.type !== 'date_chip') fail(where, `unknown overlay type ${o.type}; expected audio_hint|date_chip`);
    finite(o.start, `${where}.start`); finite(o.end, `${where}.end`);
    if (o.start < 0 || o.end <= o.start || o.end > duration + 1e-7) fail(where, 'invalid start/end or outside duration_sec');
    if (o.type === 'date_chip') return normalizeDateChip(o, where);
    if (o.end - o.start > 15) fail(where, 'audio_hint longer than 15s');
    const langs = array(o.langs, `${where}.langs`);
    if (langs.length < 2 || langs.length > 8) fail(where, 'langs must have 2..8 entries');
    o.langs = langs.map((l) => { if (typeof l !== 'string' || !/^[A-Za-z]{2}$/.test(l)) fail(where, 'langs must be 2-letter codes'); return l.toUpperCase(); });
    if (new Set(o.langs).size !== o.langs.length) fail(where, 'duplicate lang');
    if (o.position !== undefined && !OVERLAY_POSITIONS.includes(o.position)) fail(where, `position must be ${OVERLAY_POSITIONS.join('|')}`);
    if (o.label !== undefined && (typeof o.label !== 'string' || !o.label.trim() || o.label.length > 40)) fail(where, 'label must be a non-empty string up to 40 chars');
    for (const k of ['subscribe', 'like']) if (o[k] !== undefined && typeof o[k] !== 'boolean') fail(where, `${k} must be boolean`);
    if (o.size !== undefined && !['compact', 'large'].includes(o.size)) fail(where, 'size must be compact|large');
    o.position = o.position ?? 'top-right';
    return o;
  });
}

function normalizeDateChip(o, where) {
  if (o.end - o.start > 10) fail(where, 'date_chip longer than 10s');
  if (typeof o.text !== 'string') fail(where, 'text must be a string');
  const text = o.text.trim();
  if (!text || text.length > 40) fail(where, 'text must be 1..40 chars');
  if (/[\r\n\u2028\u2029]/.test(text)) fail(where, 'text must be a single line');
  o.text = text;
  if (o.position !== undefined && !DATE_CHIP_POSITIONS.includes(o.position)) fail(where, `position must be ${DATE_CHIP_POSITIONS.join('|')}`);
  if (o.size !== undefined && !['compact', 'large'].includes(o.size)) fail(where, 'size must be compact|large');
  o.position = o.position ?? 'top-left';
  return o;
}

export function assertVideoDuration(scene, fps, meta) {
  // Accepts either a scene ({start,end,data:{...}}) or a shot (start/end/controls
  // directly on it, no .data) — resolveShotPlayback reuses this on shots.
  const d = scene.data ?? scene;
  const duration = finite(meta.durationSec, `scene ${scene.id} source duration`);
  const rate = d.playbackRate ?? 1;
  // startFrom is in composition frames, matching OffthreadVideo's API.
  const trim = Math.round((d.trimStartSec ?? 0) * fps) / fps;
  if (duration <= trim) fail(`scene ${scene.id}`, 'trim starts at/after video end');
  const available = (duration - trim) / rate;
  const required = sceneFrames(scene, fps) / fps;
  // Only ffprobe/timebase rounding: <= ONE output frame AND <= ONE source frame.
  const tolerance = Math.min(1 / fps, 1 / ((meta.sourceFps || fps) * rate));
  if (available + tolerance + 1e-9 < required) fail(`scene ${scene.id}`, `video too short: ${available.toFixed(4)}s available after trim/speed, ${required.toFixed(4)}s needed; tolerance ${tolerance.toFixed(6)}s. Loops are forbidden; shorten scene or choose longer media.`);
  return { available, required, tolerance };
}

// Pure, importable quality helper: no CLI, disk, browser or external services.
export function qualityWarnings(file) {
  const warnings = [];
  const warn = (s, code, message, element) => warnings.push({ sceneId: s.id, code, ...(element ? { elementId: element } : {}), message });
  if (file.standalone_short === true) {
    // Самостоятельный шорт: оверлеи/главы/слова рендерером игнорируются (плашки только из overlays, у шортса их нет).
    const w0 = file.scenes[0];
    if (file.duration_sec > 180) warn(w0, 'standalone-too-long', `standalone short is ${file.duration_sec.toFixed(1)}s; YouTube Shorts limit is 180s.`);
    if ((file.overlays || []).length) warn(w0, 'standalone-overlays-ignored', 'standalone short: overlays are not drawn (no audio_hint/date_chip in shorts).');
    if ((file.chapters || []).length) warn(w0, 'standalone-chapters-ignored', 'standalone short: chapters are ignored (no chapter badge).');
  }
  for (const s of file.scenes) {
    const fps = file.fps, duration = sceneFrames(s, fps), d = s.data;
    const ids = elementIds(s);

    if (s.type === 'media') {
      // Each shot is its own independent sub-timeline: visibility/caption/credit
      // checks are per-shot, not against the whole (possibly multi-shot) scene.
      for (const shot of d.shots || []) {
        const shotDur = sceneFrames(shot, fps);
        const timing = annotationTiming(shot, s.beats, shot.start, fps);
        const text = new Map((shot.annotations || []).map((a) => [a.id, a.text || '']));
        if (shot.caption) { timing['(caption)'] = Math.round(fps * 0.4); text.set('(caption)', shot.caption); }
        for (const [element, frame] of Object.entries(timing)) {
          const hold = (shotDur - 1 - frame) / fps - 0.6;
          const wordCount = String(text.get(element) || '').trim().split(/\s+/).filter(Boolean).length;
          const needed = Math.max(1.2, wordCount / 3);
          if (hold < needed) warn(s, 'short-visibility', `${shot.id}.${element}: only ${Math.max(0, hold).toFixed(2)}s fully visible after reveal; aim for >=${needed.toFixed(2)}s`, element);
        }
        if (shot.kind === 'image' && !shot.caption && file.standalone_short !== true) warn(s, 'unexplained-image', `shot ${shot.id}: add caption explaining what the artifact is and why it matters.`, shot.id);
      }
      if (ids.length > 1 && !s.beats.length) warn(s, 'untimed-evidence', 'Multiple elements use fallback stagger; author beats against narration.');
      continue;
    }

    const orderedIds = s.type === 'timeline' ? [...(d.events || [])].sort((a, b) => a.year - b.year).map((e) => e.id) : ids;
    let timing = buildRevealMap(orderedIds, s.beats, s.start, fps);
    const text = new Map();
    for (const key of ['items', 'pins', 'events', 'labels', 'dims', 'lines', 'links', 'steps', 'facts']) {
      for (const e of d[key] || []) text.set(e.id, e.text || e.label || '');
    }
    for (const r of d.rows || []) text.set(r.id, (r.cells || []).join(' '));
    if (s.type === 'compare') { text.set('left', d.left.label); text.set('right', d.right.label); }
    for (const c of d.cards || []) {
      text.set(c.id, [c.title, c.textId ? '' : c.text].filter(Boolean).join(' '));
      if (c.textId) text.set(c.textId, c.text || '');
    }
    if (d.stamp) text.set(d.stampId || '(stamp)', d.stamp);
    let revealSec = s.type === 'document' ? 1 : 0.6;
    if (s.type === 'board') {
      const b = boardTiming(d, s.beats, s.start, fps, duration);
      timing = { ...b.card, ...b.text, ...b.link, ...(d.stamp ? { [d.stampId || '(stamp)']: b.stamp } : {}) };
    }
    if (s.type === 'document' && d.stamp) timing['(stamp)'] = Math.round(duration * 0.6);
    for (const [element, frame] of Object.entries(timing)) {
      const hold = (duration - 1 - frame) / fps - revealSec;
      const wordCount = String(text.get(element) || '').trim().split(/\s+/).filter(Boolean).length;
      const needed = Math.max(1.2, wordCount / 3);
      if (hold < needed) warn(s, 'short-visibility', `${element}: only ${Math.max(0, hold).toFixed(2)}s fully visible after reveal; aim for >=${needed.toFixed(2)}s`, element);
    }
    if (ids.length > 1 && !s.beats.length) warn(s, 'untimed-evidence', 'Multiple elements use fallback stagger; author beats against narration.');
    if (s.type === 'board') {
      const cards = new Map((d.cards || []).map((c) => [c.id, c]));
      for (const l of d.links || []) {
        const beat = s.beats.find((b) => b.id === l.id);
        const anchor = Math.max(...[l.from, l.to].map((i) => timing[cards.get(i)?.id] ?? 0));
        if (beat && Math.round(beat.t * fps) - Math.round(s.start * fps) < anchor) warn(s, 'link-before-card', `Link ${l.id} is held until both cards appear.`, l.id);
      }
    }
  }
  return warnings;
}

// Video shot shorter than its slot never loops/jumps. First try: compute the
// coverage the way assertVideoDuration always has (trim/rate/tolerance), reusing
// its tested math. If that is enough, nothing changes. If not: slow down (up to
// 0.6x, never slower — more than that reads as artificially dragging), and if
// STILL short even at 0.6x, freeze the last available source frame for the
// remainder (Ken Burns keeps moving through the freeze — no jump, no restart).
export function resolveShotPlayback(shot, fps, meta) {
  const requestedRate = shot.playbackRate ?? 1;
  try {
    assertVideoDuration(shot, fps, meta);
    return { rate: requestedRate };
  } catch (e) {
    if (!/video too short/.test(e.message)) throw e; // degenerate cases (trim>=duration) still fail loud
  }
  const trim = Math.round((shot.trimStartSec ?? 0) * fps) / fps;
  const available = meta.durationSec - trim;
  const slot = sceneFrames(shot, fps) / fps;
  const tol = (rate) => Math.min(1 / fps, 1 / ((meta.sourceFps || fps) * rate));
  const rate = Math.max(0.6, available / slot);
  const used = available / rate;
  if (used + tol(rate) + 1e-9 >= slot) return { rate, fallback: 'slowdown' };
  return { rate, freezeAtSec: used, fallback: 'freeze' };
}
