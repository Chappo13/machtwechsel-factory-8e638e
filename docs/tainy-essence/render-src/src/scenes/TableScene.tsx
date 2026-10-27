import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap } from "../utils/revealTiming.mjs";
import { easeOut, revealProgress } from "../utils/time";
import { TableRow } from "../types";

// Таблица сравнения 2-4 столбца x 2-5 строк: заголовок-плашка, строки
// проявляются слева направо на своих beat, красная подчёркивающая линия.
export const TableScene: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const long = format === "long";
  const cols = data.columns || [];
  const rows = (data.rows as TableRow[]) || [];
  const reveal = buildRevealMap(rows.map((r) => r.id), beats, sceneStart, fps, 0.9);
  const tableW = long ? Math.min(frameW - 220, 1500) : frameW - 100;
  const rowH = long ? Math.min(130, (frameH - 380) / (rows.length + 1)) : Math.min(190, (frameH - 800) / (rows.length + 1));
  const font = long ? 52 : 44;
  const firstW = cols.length > 2 ? 0.34 : 0.45;
  const colW = (i: number) => (i === 0 ? firstW : (1 - firstW) / (cols.length - 1)) * tableW;
  const headP = easeOut(revealProgress(frame, 0, fps, 0.5));
  return (
    <div style={{ width: frameW, height: frameH, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingBottom: long ? 0 : 120 }}>
      {data.title && <div style={{ fontFamily: FONT_HAND, fontSize: long ? 64 : 56, color: COLORS.ink, marginBottom: 26 }}>{data.title}</div>}
      <div style={{ width: tableW, boxShadow: "0 10px 26px rgba(43,33,24,0.28)", background: "rgba(233,220,185,0.6)", border: `4px solid ${COLORS.ink}` }}>
        <div style={{ display: "flex", height: rowH * 0.8, background: COLORS.ink, opacity: headP }}>
          {cols.map((c, i) => (
            <div key={i} style={{ width: colW(i), display: "flex", alignItems: "center", padding: "0 28px", fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: font * 0.8, color: COLORS.gold, textTransform: "uppercase", letterSpacing: 2 }}>{c}</div>
          ))}
        </div>
        {rows.map((r, ri) => {
          const p = easeOut(revealProgress(frame, reveal[r.id], fps, 0.6));
          return (
            <div key={r.id} style={{ display: "flex", height: rowH, borderTop: ri ? `2px solid ${COLORS.parchmentDark}` : undefined, clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`, background: ri % 2 ? "rgba(199,173,124,0.25)" : "transparent" }}>
              {r.cells.map((c, i) => (
                <div key={i} style={{ width: colW(i), display: "flex", alignItems: "center", padding: "0 28px", fontFamily: i === 0 ? FONT_DISPLAY : FONT_SERIF, fontWeight: i === 0 ? 700 : 600, fontSize: font, lineHeight: 1.05, color: i === 0 ? COLORS.ink : COLORS.red }}>{c}</div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
};
