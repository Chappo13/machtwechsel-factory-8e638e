// Pure timing shared by components and offline quality checks. Beats are absolute seconds.
export function buildRevealMap(ids, beats, sceneStartSec, fps, staggerSec = 0.35) {
  const explicit = new Map((beats || []).map((b) => [b.id, Math.round(b.t * fps) - Math.round(sceneStartSec * fps)]));
  const out = Object.create(null);
  let stagger = 0;
  for (const id of ids) out[id] = explicit.has(id) ? explicit.get(id) : Math.round(stagger++ * staggerSec * fps);
  return out;
}

export function boardTiming(data, beats, sceneStart, fps, durationInFrames) {
  const cards = data.cards || [];
  const card = buildRevealMap(cards.map((c) => c.id), beats, sceneStart, fps);
  const explicit = buildRevealMap((beats || []).map((b) => b.id), beats, sceneStart, fps);
  const text = Object.create(null);
  const link = Object.create(null);
  for (const c of cards) if (c.textId) text[c.textId] = Math.max(card[c.id], explicit[c.textId] ?? card[c.id]);
  for (const l of data.links || []) {
    // Explicit wire beats are independent; never draw a wire before its two anchors.
    link[l.id] = Math.max(card[l.from] ?? 0, card[l.to] ?? 0, explicit[l.id] ?? 0);
  }
  const last = Math.max(0, ...Object.values(card), ...Object.values(text), ...Object.values(link));
  const stamp = data.stampId && explicit[data.stampId] !== undefined
    ? explicit[data.stampId] : Math.max(Math.round(durationInFrames * 0.55), last + Math.round(fps * 0.6));
  const pullBack = Math.min(durationInFrames - 1, Math.max(last + Math.round(fps * 0.8), Math.round(durationInFrames * 0.78)));
  return { card, text, link, stamp, pullBack };
}

export function annotationTiming(data, beats, sceneStart, fps) {
  const ids = (data.annotations || []).map((a) => a.id);
  const times = buildRevealMap(ids, beats, sceneStart, fps);
  const explicit = new Set((beats || []).map((b) => b.id));
  for (const id of ids) if (data.caption && !explicit.has(id)) times[id] += Math.round(fps);
  return times;
}
