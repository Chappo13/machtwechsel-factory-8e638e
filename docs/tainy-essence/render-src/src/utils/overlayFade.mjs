// Прозрачность верхнеуровневых плашек (audio_hint, date_chip) как ЧИСТАЯ функция абсолютного времени t.
// Никакого локального кадра сцены: плашка живёт на всём [start, end] ролика независимо от сцен и шотов.
// Один подъём (ease-in-out), ровное удержание =1, один спад, 0 вне окна.
export const AUDIO_HINT_FADE_IN = 0.55;
export const AUDIO_HINT_FADE_OUT = 0.6;
export const DATE_CHIP_FADE = 0.4;

const clamp01 = (v) => Math.min(1, Math.max(0, v));
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function fadeEnvelope(t, start, end, fadeIn, fadeOut) {
  const inP = easeInOutCubic(clamp01((t - start) / fadeIn));
  const outP = easeInOutCubic(clamp01((end - t) / fadeOut));
  return { inP, outP, o: Math.min(inP, outP) };
}
export const audioHintFade = (t, ov) => fadeEnvelope(t, ov.start, ov.end, AUDIO_HINT_FADE_IN, AUDIO_HINT_FADE_OUT);
export const audioHintOpacity = (t, ov) => audioHintFade(t, ov).o;
export const dateChipFade = (t, ov) => fadeEnvelope(t, ov.start, ov.end, DATE_CHIP_FADE, DATE_CHIP_FADE);
export const dateChipOpacity = (t, ov) => dateChipFade(t, ov).o;
