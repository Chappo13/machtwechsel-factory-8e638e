// Детерминированный выбор перехода — от id сцены/плана, без Math.random(), чтобы
// рендер был воспроизводим. Два уровня:
//  - сцены: cut (только самая первая сцена) | crossfade | dip_black | film_burn | wipe
//    wipe (старая чернильная "страница") — ТОЛЬКО на границе главы и не чаще,
//    чем раз в minWipeGapSec (45-60с), иначе будет резать глаз на каждом шаге.
//  - планы внутри media-сцены: cut | crossfade
//    один и тот же ассет подряд (та же src) — никогда не wipe/дёрганый cut,
//    всегда crossfade (переход-растворение, как будто камера просто едет дальше).
// Правило "не повторять подряд" применяется всегда, кроме случая, когда весь
// список кандидатов пуст после фильтрации (тогда остаётся единственный вариант).

function hash(s) {
  let h = 0;
  for (let i = 0; i < String(s).length; i++) h = (h * 31 + String(s).charCodeAt(i)) | 0;
  return Math.abs(h);
}

export const SCENE_TRANSITIONS = ["crossfade", "dip_black", "film_burn", "wipe"];
export const SHOT_TRANSITIONS = ["cut", "crossfade"];

// index — порядковый номер сцены (0 = первая). isChapterStart — сцена открывает
// главу (scenesFile.chapters[].start совпадает с scene.start). secSinceLastWipe —
// сколько секунд абсолютного времени прошло с последнего wipe (Infinity, если ещё не было).
export function pickSceneTransition({ sceneId, index, isChapterStart, secSinceLastWipe, prevKind, minWipeGapSec = 45 }) {
  if (index === 0) return "cut"; // первая сцена просто появляется, без наезда поверх пустоты
  const wipeAllowed = isChapterStart && secSinceLastWipe >= minWipeGapSec;
  let candidates = wipeAllowed ? SCENE_TRANSITIONS : SCENE_TRANSITIONS.filter((k) => k !== "wipe");
  if (prevKind) candidates = candidates.filter((k) => k !== prevKind);
  if (!candidates.length) candidates = wipeAllowed ? SCENE_TRANSITIONS : SCENE_TRANSITIONS.filter((k) => k !== "wipe");
  return candidates[hash(sceneId) % candidates.length];
}

// sameAsset — src текущего плана совпадает с src предыдущего (одна и та же
// фотография/клип, просто другой момент/аннотации) — тогда никогда не "жёсткий"
// cut, всегда crossfade. Иначе — в основном cut, изредка crossfade (вес 1:4).
export function pickShotTransition({ shotId, index, sameAsset }) {
  if (index === 0) return "cut";
  if (sameAsset) return "crossfade";
  // "mostly hard cut or 0.3-0.5s crossfade" — около 20% планов получают crossfade
  return hash(shotId) % 5 === 0 ? "crossfade" : "cut";
}

// Планирует переходы для ВСЕХ сцен разом (нужна последовательная память:
// prevKind и время последнего wipe), возвращает массив длиной scenes.length,
// kinds[0] всегда "cut". Чистая функция — пригодна и для рендера, и для тестов.
export function planSceneTransitions(scenes, chapters, fps, minWipeGapSec = 45, opts = {}) {
  // standalone-шорт: быстрый короткий ролик, только мягкие стыки (crossfade), без dip/burn/wipe
  if (opts.standalone) return scenes.map((_, i) => (i === 0 ? "cut" : "crossfade"));
  const chapterStarts = new Set((chapters || []).map((c) => Math.round(c.start * fps)));
  const kinds = [];
  let prevKind = null;
  let lastWipeSec = -Infinity;
  scenes.forEach((s, i) => {
    const isChapterStart = chapterStarts.has(Math.round(s.start * fps));
    const kind = pickSceneTransition({
      sceneId: s.id,
      index: i,
      isChapterStart,
      secSinceLastWipe: s.start - lastWipeSec,
      prevKind,
    });
    kinds.push(kind);
    if (kind === "wipe") lastWipeSec = s.start;
    prevKind = kind;
  });
  return kinds;
}
