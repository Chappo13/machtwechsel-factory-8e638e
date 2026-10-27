import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap } from "../utils/revealTiming.mjs";
import { easeOut, revealProgress } from "../utils/time";
import { FactItem } from "../types";

// Тезисы одним столбцом: крупная цифра (год / размер / число) + короткий ярлык.
// Каждая строка выезжает на своём beat. Это не пересказ озвучки, а опорные факты.
export const FactStack: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const long = format === "long";
  const facts = (data.facts as FactItem[]) || [];
  const reveal = buildRevealMap(facts.map((f) => f.id), beats, sceneStart, fps, 0.9);
  const rowH = long ? Math.min(210, (frameH - 220) / facts.length) : Math.min(300, (frameH - 640) / facts.length);
  const numW = long ? 640 : 0;
  const bigSize = long ? 128 : 110;
  return (
    <div style={{ width: frameW, height: frameH, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingBottom: long ? 0 : 140 }}>
      {facts.map((f) => {
        const p = easeOut(revealProgress(frame, reveal[f.id], fps, 0.7));
        if (p <= 0) return <div key={f.id} style={{ height: rowH }} />;
        return (
          <div key={f.id} style={{ height: rowH, width: long ? 1500 : frameW - 100, display: "flex", flexDirection: long ? "row" : "column", alignItems: long ? "center" : "flex-start", justifyContent: long ? "flex-start" : "center", opacity: p, transform: `translateX(${(1 - p) * -80}px)` }}>
            <div style={{ width: numW || undefined, textAlign: long ? "right" : "left", fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: Math.round(bigSize * Math.min(1, 7 / Math.max(1, f.big.length))), lineHeight: 1, color: COLORS.red, whiteSpace: "nowrap", textShadow: "0 4px 0 rgba(43,33,24,0.15)" }}>{f.big}</div>
            {long && <div style={{ width: 6, height: rowH * 0.62, background: COLORS.gold, margin: "0 44px", clipPath: `inset(0 0 ${(1 - p) * 100}% 0)` }} />}
            <div style={{ fontFamily: FONT_HAND, fontSize: long ? 70 : 62, color: COLORS.ink, lineHeight: 1.05, marginTop: long ? 0 : 6, borderTop: long ? undefined : `4px solid ${COLORS.gold}`, paddingTop: long ? 0 : 8 }}>{f.label}</div>
          </div>
        );
      })}
    </div>
  );
};
