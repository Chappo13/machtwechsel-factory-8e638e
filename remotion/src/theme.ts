// Общая тема всех композиций: один источник шрифта/цветов/фона.
// Inter ставится в Docker-образ (fonts-inter); фолбэки на случай локальной студии.
export const FONT_STACK =
  'Inter, "Inter Variable", -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif';

export const BG = '#0A0E1A';
export const BG_GRADIENT =
  'radial-gradient(ellipse 120% 90% at 50% 35%, #141b30 0%, #0A0E1A 60%, #070a13 100%)';
export const ACCENT = '#E63946';
export const TEXT = '#F4F4F4';
export const GRID = '#1a2030';

// Кегль с учётом ДЛИНЫ и доступной ШИРИНЫ контейнера: драматическое «Y.» — огромное,
// немецкий компаунд на 60 символов — гарантированно влезает. Раньше учитывалась только
// длина → длинные слова вылезали за кадр/наезжали. byWidth: средний глиф ~0.6em.
export const fitFontSize = (text: string, base: number, minSize = 44, maxWidthPx = 1700): number => {
  const len = Math.max((text || '').length, 1);
  const byWidth = maxWidthPx / (len * 0.6);
  let byLen: number;
  if (len <= 3) byLen = base * 1.6;
  else if (len <= 8) byLen = base;
  else byLen = (base * 8) / len;
  return Math.max(minSize, Math.round(Math.min(byLen, byWidth)));
};

// Числовая коэрсия пропсов от LLM: строка «1,9 Mrd» или undefined не должны
// уронить рендер в NaN на экране.
export const num = (v: unknown, fallback = 0): number => {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/[^\d.,-]/g, '').replace(',', '.'));
  return Number.isFinite(n) ? n : fallback;
};
