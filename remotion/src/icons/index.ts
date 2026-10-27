// Реестр код-иконок (flat line, viewBox 0 0 24 24). Используется ConceptCard
// вместо AI-дудлов (Flux) для абстрактных понятий. Каждая иконка — массив SVG-
// примитивов (строки), рисуется stroke=color. Расширяемо.
// id-набор синхронизирован с backend/config/concept_icons.json.

export type IconShape = string; // готовый SVG-элемент, {C} = подставится цвет stroke

export const ICONS: Record<string, IconShape[]> = {
  // деньги / капитал
  money: [
    '<circle cx="9" cy="12" r="6.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<circle cx="15" cy="12" r="6.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<text x="9" y="15.2" font-size="7" fill="{C}" text-anchor="middle" font-family="Inter, sans-serif">€</text>',
  ],
  // рост / взлёт
  growth: [
    '<polyline points="3,18 9,12 13,15 21,6" fill="none" stroke="{C}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    '<polyline points="15,6 21,6 21,12" fill="none" stroke="{C}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  ],
  // обвал / крах
  crash: [
    '<polyline points="3,6 9,12 13,9 21,18" fill="none" stroke="{C}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    '<polyline points="15,18 21,18 21,12" fill="none" stroke="{C}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  ],
  // человек / фигура
  person: [
    '<circle cx="12" cy="8" r="3.4" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<path d="M5.5 20 C5.5 15.5 9 14 12 14 C15 14 18.5 15.5 18.5 20" fill="none" stroke="{C}" stroke-width="1.6" stroke-linecap="round"/>',
  ],
  // компания / здание
  company: [
    '<rect x="5" y="4" width="14" height="17" rx="1" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<line x1="9" y1="8" x2="9" y2="8" stroke="{C}" stroke-width="2"/>',
    '<path d="M8.5 8 h1 M11.5 8 h1 M14.5 8 h1 M8.5 12 h1 M11.5 12 h1 M14.5 12 h1 M8.5 16 h1 M11.5 16 h1 M14.5 16 h1" stroke="{C}" stroke-width="1.6" stroke-linecap="round"/>',
  ],
  // документ / контракт
  document: [
    '<path d="M7 3 h7 l4 4 v14 h-11 z" fill="none" stroke="{C}" stroke-width="1.6" stroke-linejoin="round"/>',
    '<polyline points="14,3 14,7 18,7" fill="none" stroke="{C}" stroke-width="1.6" stroke-linejoin="round"/>',
    '<path d="M9 12 h6 M9 15 h6 M9 18 h4" stroke="{C}" stroke-width="1.4" stroke-linecap="round"/>',
  ],
  // предупреждение / опасность
  warning: [
    '<path d="M12 4 L21 19 H3 Z" fill="none" stroke="{C}" stroke-width="1.7" stroke-linejoin="round"/>',
    '<line x1="12" y1="10" x2="12" y2="14.5" stroke="{C}" stroke-width="1.8" stroke-linecap="round"/>',
    '<circle cx="12" cy="17" r="0.9" fill="{C}"/>',
  ],
  // правосудие / суд (весы)
  justice: [
    '<line x1="12" y1="4" x2="12" y2="20" stroke="{C}" stroke-width="1.6" stroke-linecap="round"/>',
    '<line x1="6" y1="7" x2="18" y2="7" stroke="{C}" stroke-width="1.6" stroke-linecap="round"/>',
    '<path d="M6 7 L4 12 a2 2 0 0 0 4 0 Z" fill="none" stroke="{C}" stroke-width="1.4"/>',
    '<path d="M18 7 L16 12 a2 2 0 0 0 4 0 Z" fill="none" stroke="{C}" stroke-width="1.4"/>',
    '<line x1="9" y1="20" x2="15" y2="20" stroke="{C}" stroke-width="1.6" stroke-linecap="round"/>',
  ],
  // время / часы
  time: [
    '<circle cx="12" cy="12" r="8.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<polyline points="12,7 12,12 16,14" fill="none" stroke="{C}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
  ],
  // безопасность / замок
  lock: [
    '<rect x="5" y="11" width="14" height="9" rx="1.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<path d="M8 11 V8 a4 4 0 0 1 8 0 V11" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<circle cx="12" cy="15.5" r="1.3" fill="{C}"/>',
  ],
  // сеть / связи
  network: [
    '<circle cx="12" cy="5" r="2.2" fill="none" stroke="{C}" stroke-width="1.5"/>',
    '<circle cx="5" cy="18" r="2.2" fill="none" stroke="{C}" stroke-width="1.5"/>',
    '<circle cx="19" cy="18" r="2.2" fill="none" stroke="{C}" stroke-width="1.5"/>',
    '<path d="M11 7 L6 16 M13 7 L18 16 M7 18 h10" stroke="{C}" stroke-width="1.4" stroke-linecap="round"/>',
  ],
  // глобус / международное
  globe: [
    '<circle cx="12" cy="12" r="8.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<ellipse cx="12" cy="12" rx="3.6" ry="8.5" fill="none" stroke="{C}" stroke-width="1.4"/>',
    '<line x1="3.5" y1="12" x2="20.5" y2="12" stroke="{C}" stroke-width="1.4"/>',
  ],
  // обман / маска
  mask: [
    '<path d="M4 9 q8 -3 16 0 q1 6 -3 8 q-3 -2 -5 -2 q-2 0 -5 2 q-4 -2 -3 -8 Z" fill="none" stroke="{C}" stroke-width="1.6" stroke-linejoin="round"/>',
    '<circle cx="9" cy="11" r="1" fill="{C}"/>',
    '<circle cx="15" cy="11" r="1" fill="{C}"/>',
  ],
  // поиск / расследование
  search: [
    '<circle cx="11" cy="11" r="6" fill="none" stroke="{C}" stroke-width="1.7"/>',
    '<line x1="15.5" y1="15.5" x2="20" y2="20" stroke="{C}" stroke-width="1.8" stroke-linecap="round"/>',
  ],
  // вопрос / тайна
  question: [
    '<circle cx="12" cy="12" r="8.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<text x="12" y="16" font-size="11" fill="{C}" text-anchor="middle" font-family="Inter, sans-serif" font-weight="700">?</text>',
  ],
  // связь / звено цепи
  chain: [
    '<rect x="3" y="9.5" width="9" height="5" rx="2.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
    '<rect x="12" y="9.5" width="9" height="5" rx="2.5" fill="none" stroke="{C}" stroke-width="1.6"/>',
  ],
};

export const hasIcon = (id: string): boolean => Object.prototype.hasOwnProperty.call(ICONS, id);
