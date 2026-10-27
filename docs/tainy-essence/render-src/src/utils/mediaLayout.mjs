const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// Return one transform for BOTH pixels and annotations. Keep all protected boxes
// visible throughout camera motion; fall back to contain if cover cannot do so.
export function mediaLayout({ mediaW, mediaH, frameW, frameH, fit = 'cover', focus = { x: 0.5, y: 0.5 }, annotations = [], progress = 0, caption = false, format = 'long' }) {
  const p = clamp(progress, 0, 1);
  const boxes = annotations.map((a) => a.bbox).filter(Boolean);
  const cover = Math.max(frameW / mediaW, frameH / mediaH);
  const margin = Math.min(frameW, frameH) * 0.025;
  const bounds = boxes.length ? {
    x0: Math.max(0, Math.min(...boxes.map((b) => b.x)) * mediaW - margin / cover),
    y0: Math.max(0, Math.min(...boxes.map((b) => b.y)) * mediaH - margin / cover),
    x1: Math.min(mediaW, Math.max(...boxes.map((b) => b.x + b.w)) * mediaW + margin / cover),
    y1: Math.min(mediaH, Math.max(...boxes.map((b) => b.y + b.h)) * mediaH + margin / cover),
  } : null;
  const safeTop = frameH * 0.11;
  const safeBottom = frameH - (caption ? (format === 'long' ? frameH * 0.24 : frameH * 0.27) : frameH * 0.06);
  // Портрет из ландшафтного источника (шорт 1080x1920 из 16:9): cover показывает лишь ~30% ширины. Старт с центра кадра
  // выбросил бы точку фокуса за экран до конца плана, поэтому по оси с сильной обрезкой (видно < 75% источника) камера
  // сразу стоит на фокусе, а движение даёт только push-in масштабом. Только для short; long остаётся как раньше.
  const visX = frameW / (mediaW * cover), visY = frameH / (mediaH * cover);
  const px = format === 'short' && visX < 0.75 ? 1 : p;
  const py = format === 'short' && visY < 0.75 ? 1 : p;
  function coverAt(scale) {
    const w = mediaW * scale, h = mediaH * scale;
    let xmin = frameW - w, xmax = 0, ymin = frameH - h, ymax = 0;
    if (bounds) {
      xmin = Math.max(xmin, margin - bounds.x0 * scale);
      xmax = Math.min(xmax, frameW - margin - bounds.x1 * scale);
      ymin = Math.max(ymin, safeTop - bounds.y0 * scale);
      ymax = Math.min(ymax, safeBottom - bounds.y1 * scale);
    }
    if (xmin > xmax + 1e-7 || ymin > ymax + 1e-7) return null;
    return { scale, tx: clamp(frameW / 2 - (0.5 + (focus.x - 0.5) * px) * w, xmin, xmax), ty: clamp(frameH / 2 - (0.5 + (focus.y - 0.5) * py) * h, ymin, ymax), fit: 'cover' };
  }
  if (fit !== 'contain' && coverAt(cover)) {
    // BOTH endpoints must be feasible: zoom may make an unsafe initial crop
    // feasible later, but that must not yield null geometry on the first frames.
    // Select a safe maximum zoom once, independent of the current frame (no jumps).
    const zoom = coverAt(cover * 1.08) ? 1.08 : 1;
    if (coverAt(cover * zoom)) return coverAt(cover * (1 + (zoom - 1) * p));
  }
  // Full artifact within header/caption safe area, not cropped Ken Burns.
  const scale = Math.min((frameW - margin * 2) / mediaW, (safeBottom - safeTop) / mediaH);
  return { scale, tx: (frameW - mediaW * scale) / 2, ty: safeTop + (safeBottom - safeTop - mediaH * scale) / 2, fit: 'contain' };
}

const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

// Фокус-зум (15.10): плавный наезд на точку интереса стилла вместо 2.5D-параллакса.
// Старт: cover по центру кадра, финиш: масштаб cover*to и центр на предмете. Предмет (zoom.box, доли 0..1; нет бокса:
// квадрат вокруг точки) целиком остаётся в кадре на ВСЕЙ траектории (зум ограничивается размером бокса), края картинки
// не показываются (центр зажимается). Возвращает {scale, tx, ty, to} — тот же формат, что mediaLayout.
export function focusZoomLayout({ mediaW, mediaH, frameW, frameH, zoom, progress = 0, safeTop = frameH * 0.1, safeBottom = frameH * 0.06 }) {
  const cover = Math.max(frameW / mediaW, frameH / mediaH);
  const px = clamp(zoom.x, 0, 1), py = clamp(zoom.y, 0, 1);
  const b = zoom.box || { x: px - 0.1, y: py - 0.1, w: 0.2, h: 0.2 };
  const bx0 = clamp(b.x, 0, 1) * mediaW, by0 = clamp(b.y, 0, 1) * mediaH;
  const bx1 = clamp(b.x + b.w, 0, 1) * mediaW, by1 = clamp(b.y + b.h, 0, 1) * mediaH;
  const bw = Math.max(1, bx1 - bx0), bh = Math.max(1, by1 - by0);
  // предмет целиком в 88% ширины и в безопасной по вертикали зоне (ниже шапки)
  const maxFit = Math.min((frameW * 0.88) / bw, ((frameH - safeTop - safeBottom) * 0.92) / bh);
  const to = clamp(Math.min(zoom.to ?? 1.22, maxFit / cover), 1, 1.6);
  const s0 = cover, s1 = cover * to;
  const clampCenter = (cx, cy, s) => {
    const hw = frameW / 2 / s, hh = frameH / 2 / s;
    // край картинки не показываем, предмет не выходит за кадр (с запасом 4%)
    let x = clamp(cx, hw, mediaW - hw), y = clamp(cy, hh, mediaH - hh);
    // бокс шире окна (портрет из 16:9): целиком не влезает — центрируем на боксе, чтобы точка интереса не уходила за кадр
    x = bx1 - hw * 0.96 > bx0 + hw * 0.96 ? (bx0 + bx1) / 2 : clamp(x, bx1 - hw * 0.96, bx0 + hw * 0.96);
    y = by1 - hh * 0.96 > by0 + hh * 0.96 ? (by0 + by1) / 2 : clamp(y, by1 - hh * 0.96, by0 + hh * 0.96);
    return { cx: clamp(x, hw, mediaW - hw), cy: clamp(y, hh, mediaH - hh) };
  };
  const p = easeInOutCubic(clamp(progress, 0, 1));
  const c0 = clampCenter(mediaW / 2, mediaH / 2, s0);
  const c1 = clampCenter((bx0 + bx1) / 2, (by0 + by1) / 2, s1);
  const scale = Math.exp(Math.log(s0) + (Math.log(s1) - Math.log(s0)) * p);
  const c = clampCenter(c0.cx + (c1.cx - c0.cx) * p, c0.cy + (c1.cy - c0.cy) * p, scale);
  return { scale, tx: frameW / 2 - c.cx * scale, ty: frameH / 2 - c.cy * scale, to };
}
