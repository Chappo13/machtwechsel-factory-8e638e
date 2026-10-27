// Тема «дневник исследователя»: состаренный пергамент, тёмно-коричневые чернила,
// приглушённый красный и выцветшее золото.

import "@fontsource/caveat/400.css";
import "@fontsource/caveat/500.css";
import "@fontsource/caveat/600.css";
import "@fontsource/caveat/700.css";
import "@fontsource/neucha/400.css";
import "@fontsource/marck-script/400.css";
import "@fontsource/cormorant-garamond/400.css";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/cormorant-garamond/600.css";
import "@fontsource/cormorant-garamond/700.css";
import "@fontsource/playfair-display/400.css";
import "@fontsource/playfair-display/700.css";
import "@fontsource/playfair-display/900.css";
import "@fontsource/pt-serif/400.css";
import "@fontsource/pt-serif/700.css";

export const COLORS = {
  ink: "#2b2118",
  inkSoft: "#4a3a28",
  red: "#8b1e1e",
  gold: "#b08d57",
  parchmentLight: "#e9dcb9",
  parchmentMid: "#dcc89a",
  parchmentDark: "#c7ad7c",
  paperShadow: "#5a4426",
  cork: "#9c7a4e",
};

export const FONT_HAND = "'Caveat', cursive";
export const FONT_HAND_ALT = "'Neucha', cursive";
export const FONT_HAND_TITLE = "'Marck Script', cursive";
export const FONT_SERIF = "'Cormorant Garamond', 'PT Serif', serif";
export const FONT_DISPLAY = "'Playfair Display', 'PT Serif', serif";

// Размеры кадра
export const DIMENSIONS = {
  long: { width: 1920, height: 1080 },
  short: { width: 1080, height: 1920 },
} as const;

// SVG-турбулентность для зерна бумаги (фильтр, используется в Parchment.tsx)
export const NOISE_FILTER_ID = "paperNoise";
