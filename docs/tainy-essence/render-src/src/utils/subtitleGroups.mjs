// Субтитры должны быть СТАБИЛЬНЫ: группа из 2-4 слов появляется целиком и
// держится до следующей группы — не растёт по одному слову и не прыгает между
// "целой фразой" и "одним словом" на соседних кадрах. Разбивка на группы
// считается ОДИН РАЗ от всего words[] (не по кадрам), разрыв — по пунктуации
// или паузе, с ограничением 2-4 слова.
export function groupWords(words, { minGroup = 2, maxGroup = 4, pauseGapSec = 0.45 } = {}) {
  if (!words || !words.length) return [];
  const groups = [];
  let cur = [];
  for (let i = 0; i < words.length; i++) {
    cur.push(words[i]);
    const next = words[i + 1];
    const atMax = cur.length >= maxGroup;
    const sentenceEnd = /[.!?;:…]$/.test(words[i].w);
    const pause = next ? next.start - words[i].end > pauseGapSec : true;
    const atLeastMin = cur.length >= minGroup;
    // Пунктуация конца фразы — самостоятельный сигнал завершения группы даже
    // для одного слова ("Да." "Нет!") — в отличие от паузы, которая обрывает
    // группу только если уже набран разумный минимум слов.
    const shouldBreak = atMax || !next || sentenceEnd || (atLeastMin && pause);
    if (shouldBreak) {
      groups.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
      cur = [];
    }
  }
  if (cur.length) groups.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
  return groups;
}

// Группа видна с её начала до начала СЛЕДУЮЩЕЙ группы (без разрыва/мигания
// между соседними фразами), либо ещё holdSec после своего конца, если дальше
// длинная пауза перед следующей репликой.
export function activeGroup(groups, t, holdSec = 0.5) {
  for (let i = 0; i < groups.length; i++) {
    const g = groups[i];
    const next = groups[i + 1];
    const windowEnd = next ? Math.max(next.start, g.end) : g.end + holdSec;
    if (t >= g.start && t < windowEnd) return g;
  }
  return null;
}

// Индекс слова внутри активной группы, которое звучит прямо сейчас (для
// подсветки) — последнее слово, чей start уже наступил.
export function activeWordIndex(group, t) {
  if (!group) return -1;
  let idx = -1;
  for (let i = 0; i < group.words.length; i++) {
    if (group.words[i].start <= t) idx = i;
    else break;
  }
  return idx;
}
