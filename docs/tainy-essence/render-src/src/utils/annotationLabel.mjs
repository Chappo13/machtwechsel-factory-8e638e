const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
// All text is retained. Screen-space font size/available width stays stable under
// contain/cover transforms, including narrow portrait crops and labels at edges.
export function annotationLabel({ text, rect, scale, xMin, xMax, yMin, yMax, fontPx = 36 }) {
  const fontSize = fontPx / scale;
  const available = Math.max(fontSize * 2, xMax - xMin);
  const maxChars = Math.max(4, Math.floor(Math.min(available, 700 / scale) / (fontSize * 0.62)));
  const words = String(text || '').trim().split(/\s+/).filter(Boolean);
  const lines = [];
  for (const word of words) {
    if (lines.length && lines[lines.length - 1].length + word.length + 1 <= maxChars) lines[lines.length - 1] += ` ${word}`;
    else lines.push(word);
  }
  if (!lines.length) lines.push('');
  const width = Math.min(available, Math.max(...lines.map((l) => l.length)) * fontSize * 0.62);
  const height = lines.length * fontSize * 1.2;
  const x = clamp(rect.x + rect.w / 2, xMin + width / 2, xMax - width / 2);
  let y = rect.y - 22 / scale - (lines.length - 1) * fontSize * 1.2;
  let connector = false;
  if (y - fontSize < yMin) { y = rect.y + rect.h + fontSize * 1.4; connector = true; }
  const bounded = clamp(y, yMin + fontSize, Math.max(yMin + fontSize, yMax - height + fontSize));
  connector ||= bounded !== y || Math.abs(x - (rect.x + rect.w / 2)) > 1;
  return { lines, width, fontSize, lineHeight: fontSize * 1.2, x, y: bounded, connector };
}
