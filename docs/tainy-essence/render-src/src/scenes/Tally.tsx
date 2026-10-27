import React, { useMemo } from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY } from "../theme";
import { SceneProps } from "./sceneProps";
import { TallyIcon, TALLY_ICON_RATIO } from "../components/TallyIcon";
import { TallyIconKind } from "../types";

// Счётчик предметов (tally): total силуэтов выстраиваются сеткой и считаются числом.
//  mode "lose"  (есть remain): после tally_at (total-remain) силуэтов тонут, число падает total -> remain, красное «−N».
//  mode "count" (нет remain): силуэты появляются по одному, число растёт 1 -> total.
// Только числа и рисунок, никаких слов (владелец 15.10). Раскладка подстраивается под 16:9 и 9:16.
function mulberry(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Подбор числа колонок: максимизируем размер ячейки в заданной области.
export function tallyGrid(total: number, kind: TallyIconKind, areaW: number, areaH: number) {
  const ratio = TALLY_ICON_RATIO[kind];
  let best = { cols: 1, rows: total, cell: 0, iconW: 0 };
  for (let cols = 1; cols <= total; cols++) {
    const rows = Math.ceil(total / cols);
    const cellW = areaW / cols, cellH = areaH / rows;
    const iconW = Math.min(cellW * 0.82, (cellH * 0.82) / ratio, kind === "ship" ? 190 : 150);
    if (iconW > best.iconW) best = { cols, rows, cell: Math.min(cellW, cellH), iconW };
  }
  return best;
}

export const Tally: React.FC<SceneProps> = ({ data, fps, frameW, frameH, seed }) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const kind: TallyIconKind = (data.icon as TallyIconKind) || "dot";
  const total = Math.max(1, Math.min(60, Math.round(data.total ?? 10)));
  const mode = data.remain !== undefined && data.remain !== null ? "lose" : "count";
  const remain = Math.max(0, Math.min(total, Math.round(data.remain ?? total)));
  const lost = total - remain;
  const portrait = frameH > frameW;
  const loseAt = data.tally_at ?? 3.6, loseDur = data.tally_dur ?? 1.4;

  // область иконок: слева (16:9) или сверху (9:16); число справа / снизу
  const area = portrait
    ? { x: 70, y: 170, w: frameW - 140, h: frameH * 0.5 }
    : { x: 90, y: 150, w: 1000, h: frameH - 300 };
  const grid = useMemo(() => tallyGrid(total, kind, area.w, area.h), [total, kind, area.w, area.h]);
  const rowsW = grid.cols * (area.w / grid.cols);
  void rowsW;
  const cellW = area.w / grid.cols, cellH = Math.min(area.h / grid.rows, cellW * 1.15);
  const gridH = grid.rows * cellH;
  const gy = area.y + (area.h - gridH) / 2;

  const order = useMemo(() => {
    const r = mulberry(seed * 7919 + 13);
    const idx = Array.from({ length: total }, (_, i) => i);
    for (let i = idx.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
    return idx.slice(0, lost);
  }, [total, lost, seed]);

  const appearStart = 0.3;
  const appearStep = Math.min(0.12, 3.6 / total);
  const icons = Array.from({ length: total }, (_, i) => {
    const col = i % grid.cols, row = Math.floor(i / grid.cols);
    // последняя строка центрируется, если неполная
    const inRow = row === grid.rows - 1 ? total - row * grid.cols : grid.cols;
    const shift = ((grid.cols - inRow) * cellW) / 2;
    const x = area.x + shift + col * cellW + (cellW - grid.iconW) / 2;
    const y = gy + row * cellH + (cellH - grid.iconW * TALLY_ICON_RATIO[kind]) / 2;
    const aT = appearStart + i * appearStep;
    const p = interpolate(t, [aT, aT + 0.45], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.back(1.5)) });
    const k = order.indexOf(i);
    let sink = 0;
    if (k >= 0) {
      const st = loseAt + (k / Math.max(1, lost - 1)) * (loseDur * 0.55);
      sink = interpolate(t, [st, st + loseDur * 0.45], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) });
    }
    const bob = Math.sin(t * 1.7 + i * 1.3) * 2.2;
    const tilt = Math.sin(t * 1.3 + i) * 1.4 + sink * (i % 2 ? 16 : -14);
    return { i, x, y, p, sink, bob, tilt, aT };
  });

  let shown: number, lp = 0;
  if (mode === "lose") {
    lp = interpolate(t, [loseAt + 0.1, loseAt + loseDur + 0.2], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
    shown = Math.round(total - lost * lp);
  } else {
    shown = icons.filter((ic) => t >= ic.aT + 0.15).length;
  }
  const numPop = interpolate(t, [0, 0.45], [0.7, 1], { extrapolateRight: "clamp", easing: Easing.out(Easing.back(1.6)) });
  const numOp = interpolate(t, [0, 0.25], [0, 1], { extrapolateRight: "clamp" });
  const settleAt = mode === "lose" ? loseAt + loseDur + 0.2 : appearStart + total * appearStep + 0.2;
  const settle = interpolate(t, [settleAt, settleAt + 0.5], [1, 1.06], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const minusOp = interpolate(t, [loseAt + 0.25, loseAt + 0.75], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const minusSlide = interpolate(t, [loseAt + 0.25, loseAt + 0.75], [18, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });

  const numBox: React.CSSProperties = portrait
    ? { left: 0, right: 0, top: area.y + area.h + 40, bottom: 0 }
    : { left: area.x + area.w + 30, right: 0, top: 0, bottom: 0 };
  const numSize = portrait ? 300 : String(total).length > 2 ? 300 : 380;

  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }}>
        <defs>
          {icons.map((s) => (
            <clipPath key={s.i} id={`tl-${s.i}`}><rect x={s.x - 40} y={s.y - 70} width={grid.iconW + 80} height={grid.iconW * TALLY_ICON_RATIO[kind] + 110} /></clipPath>
          ))}
        </defs>
        {icons.map((s) => {
          if (s.p <= 0) return null;
          const sc = 0.55 + 0.45 * s.p;
          const op = s.p * (1 - s.sink);
          const iw = grid.iconW, ih = iw * TALLY_ICON_RATIO[kind];
          const dy = s.bob + s.sink * 58 + (1 - s.p) * 16;
          return (
            <g key={s.i} clipPath={kind === "ship" ? `url(#tl-${s.i})` : undefined}>
              <g transform={`translate(${s.x + iw / 2}, ${s.y + ih / 2}) rotate(${s.tilt}) scale(${sc}) translate(${-iw / 2}, ${-ih / 2 + dy})`} opacity={op}>
                <TallyIcon kind={kind} width={iw} wave={s.sink < 0.01} />
              </g>
            </g>
          );
        })}
      </svg>
      <div style={{ position: "absolute", ...numBox, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: numSize, lineHeight: 1, color: COLORS.ink, opacity: numOp, transform: `scale(${numPop * settle})`, fontVariantNumeric: "lining-nums", letterSpacing: -4, textShadow: "0 4px 0 rgba(176,141,87,0.35)" }}>
          {shown}
        </div>
        {mode === "lose" && lost > 0 && (
          <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: 132, lineHeight: 1, marginTop: 6, color: COLORS.red, opacity: minusOp, transform: `translateY(${minusSlide}px)`, fontVariantNumeric: "lining-nums" }}>
            −{lost}
          </div>
        )}
      </div>
    </div>
  );
};
