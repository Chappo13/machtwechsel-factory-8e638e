import { Word } from "../types";

export const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));

// Прогресс появления элемента (0..1), frame — локальный кадр сцены (от начала сцены),
// beatFrame — локальный кадр, когда должен появиться элемент.
export const revealProgress = (
  frame: number,
  beatFrame: number,
  fps: number,
  durSec = 0.6
) => {
  const durFrames = Math.max(1, fps * durSec);
  return clamp((frame - beatFrame) / durFrames);
};

// easeOutCubic
export const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
export const easeInOut = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

export { buildRevealMap } from "./revealTiming.mjs";

// Текущее слово(а) субтитров под абсолютное время t (секунды от начала ролика).
export function currentSubtitle(words: Word[] | undefined, t: number): string {
  if (!words || words.length === 0) return "";
  // находим индекс последнего слова, чей start <= t
  let idx = -1;
  for (let i = 0; i < words.length; i++) {
    if (words[i].start <= t) idx = i;
    else break;
  }
  if (idx === -1) return "";
  const cur = words[idx];
  // слово ещё не закончилось давно (держим на экране недолго после конца)
  if (t - cur.end > 0.5) return "";
  // собираем короткую фразу: текущее + предыдущие, если паузы между ними малы
  const chunk: string[] = [cur.w];
  let i = idx;
  while (chunk.length < 3 && i > 0) {
    const prev = words[i - 1];
    const gap = words[i].start - prev.end;
    if (gap > 0.45) break;
    chunk.unshift(prev.w);
    i -= 1;
  }
  return chunk.join(" ");
}
