import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap } from "../utils/revealTiming.mjs";
import { easeOut, revealProgress } from "../utils/time";
import { CounterItem } from "../types";

// 1-3 счётчика рядом (на вертикали столбиком): число набегает от `from` (0) до value
// в момент своего beat, под ним золотая линия и короткая подпись-тезис.
export const Counter: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const long = format === "long";
  const items = (data.items as unknown as CounterItem[]) || [];
  const reveal = buildRevealMap(items.map((i) => i.id), beats, sceneStart, fps, 0.8);
  const n = items.length;
  const cellW = long ? Math.min(frameW / n - 40, 700) : frameW - 120;
  const numSize = (n === 1 ? (long ? 260 : 220) : n === 2 ? (long ? 190 : 170) : long ? 150 : 140);
  return (
    <div style={{ width: frameW, height: frameH, display: "flex", flexDirection: long ? "row" : "column", alignItems: "center", justifyContent: "center", gap: long ? 50 : 70, paddingBottom: long ? 0 : 160 }}>
      {items.map((it) => {
        const t = revealProgress(frame, reveal[it.id], fps, 1.7);
        const p = easeOut(t);
        const appear = easeOut(revealProgress(frame, reveal[it.id], fps, 0.4));
        const from = it.from ?? 0;
        const dec = it.decimals ?? 0;
        const v = from + (it.value - from) * p;
        const shown = Number(v.toFixed(dec));
        const text = it.plain
          ? shown.toFixed(dec).replace(".", ",")
          : shown.toLocaleString("ru-RU", { minimumFractionDigits: dec, maximumFractionDigits: dec });
        return (
          <div key={it.id} style={{ width: cellW, textAlign: "center", opacity: appear, transform: `translateY(${(1 - appear) * 30}px)` }}>
            <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: numSize, lineHeight: 1, color: COLORS.red, textShadow: "0 4px 0 rgba(43,33,24,0.15)", whiteSpace: "nowrap" }}>
              {text}
              {it.unit && <span style={{ fontSize: "0.36em", marginLeft: "0.2em", color: COLORS.inkSoft }}>{it.unit}</span>}
            </div>
            <div style={{ width: `${Math.round(p * 60)}%`, height: 5, background: COLORS.gold, margin: "18px auto 14px" }} />
            <div style={{ fontFamily: FONT_HAND, fontSize: long ? (n > 1 ? 56 : 66) : 58, color: COLORS.ink, lineHeight: 1.05 }}>{data.hide_words ? "" : it.label}</div>
          </div>
        );
      })}
    </div>
  );
};
