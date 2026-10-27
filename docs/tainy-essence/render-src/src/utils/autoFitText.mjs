// Текст по умолчанию ДОЛЖЕН заполнять свой контейнер, а не сидеть мелким
// обрывком в углу с кучей пустоты вокруг — так выглядит незаконченным. Чистая
// функция: по доступной ширине/высоте подбирает максимальный читаемый размер
// шрифта (не ниже заданного минимума), переносит текст на строки (не больше
// maxLines) со сбалансированной длиной строк (не "длинная+одно висящее слово"),
// и возвращает геометрию для центрирования по обеим осям.
//
// charWidthFactor — средняя ширина символа как доля от fontSize (эмпирически
// подобрано под рукописный/серифный шрифты проекта; не претендует на точность
// canvas measureText, но ведёт себя стабильно и детерминированно).

function wrapAtWidth(words, maxChars) {
  const lines = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length > maxChars && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

// Сначала жадный перенос по максимальной ширине, затем повторный перенос с
// "идеальной" шириной (общая длина / число строк), чтобы строки были похожей
// длины, а не одна длинная плюс хвост из одного слова.
function wrapBalanced(text, maxChars) {
  const words = String(text).trim().split(/\s+/).filter(Boolean);
  if (!words.length) return [""];
  const greedy = wrapAtWidth(words, maxChars);
  if (greedy.length <= 1) return greedy;
  const totalChars = words.join(" ").length;
  const idealPerLine = Math.ceil(totalChars / greedy.length) + 2;
  const balanced = wrapAtWidth(words, Math.min(maxChars, idealPerLine));
  // сбалансированный проход иногда даёт на 1 строку больше впритык — берём тот,
  // что не хуже по числу строк
  return balanced.length <= greedy.length ? balanced : greedy;
}

export function fitText({
  text,
  maxWidth,
  maxHeight,
  minFont,
  maxFont,
  maxLines = 3,
  charWidthFactor = 0.56,
  lineHeightFactor = 1.22,
  step = 2,
}) {
  const clean = String(text || "").trim();
  if (!clean) return { fontSize: minFont, lines: [""], lineHeight: minFont * lineHeightFactor, truncated: false };

  let best = null;
  for (let fontSize = maxFont; fontSize >= minFont; fontSize -= step) {
    const maxChars = Math.max(1, Math.floor(maxWidth / (fontSize * charWidthFactor)));
    const lines = wrapBalanced(clean, maxChars);
    const lineHeight = fontSize * lineHeightFactor;
    const widestLine = Math.max(...lines.map((l) => l.length)) * fontSize * charWidthFactor;
    const fits = lines.length <= maxLines && lines.length * lineHeight <= maxHeight && widestLine <= maxWidth;
    if (fits) { best = { fontSize, lines, lineHeight, truncated: false }; break; }
  }
  if (best) return best;

  // Даже минимальный размер не помещается целиком — переносим на maxLines строк
  // при минимальном размере и обрезаем последнюю многоточием, но НИКОГДА не
  // опускаемся ниже заданного минимума шрифта (явное требование: держать читаемость).
  // truncated:true — сигнал вызывающему коду (например layoutCard в Board.tsx),
  // что это ВЫНУЖДЕННЫЙ худший случай, а не "нормально влезло" — чтобы не
  // выбирать маленькую карточку только потому что fitText что-то вернул.
  const maxChars = Math.max(1, Math.floor(maxWidth / (minFont * charWidthFactor)));
  let lines = wrapBalanced(clean, maxChars);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    const last = kept[maxLines - 1];
    kept[maxLines - 1] = last.length > 1 ? `${last.slice(0, Math.max(1, last.length - 1))}…` : last;
    lines = kept;
  }
  return { fontSize: minFont, lines, lineHeight: minFont * lineHeightFactor, truncated: true };
}
