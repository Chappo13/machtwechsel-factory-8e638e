import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap } from "../utils/revealTiming.mjs";
import { easeOut, revealProgress } from "../utils/time";
import { StepItem } from "../types";
import { StepIconSvg } from "./StepIcons";

// Процесс/механизм: 3-5 узлов (иконка или номер + короткая подпись), стрелки
// дорисовываются на beat следующего шага. Горизонтально на 16:9, столбиком на 9:16.
export const Steps: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const long = format === "long";
  const steps = (data.steps as StepItem[]) || [];
  const n = steps.length;
  const reveal = buildRevealMap(steps.map((s) => s.id), beats, sceneStart, fps, 0.8);
  const titleH = data.title ? (long ? 120 : 110) : 0;
  const R = long ? Math.min(110, (frameW - 240) / n / 2.6) : 92;
  const slotX = long ? (frameW - 160) / n : 0;
  const slotY = long ? 0 : Math.min(300, (frameH - 640 - titleH) / n);
  const x0 = long ? 80 + slotX / 2 : frameW / 2;
  const y0 = long ? frameH / 2 - 20 : 250 + titleH + R;
  const pos = (i: number) => ({ x: x0 + (long ? slotX * i : 0), y: y0 + (long ? 0 : slotY * i) });
  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      {data.title && <div style={{ position: "absolute", top: long ? 60 : 150, width: frameW, textAlign: "center", fontFamily: FONT_HAND, fontSize: long ? 66 : 58, color: COLORS.ink }}>{data.title}</div>}
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }}>
        {steps.slice(1).map((s, k) => {
          const a = pos(k), b = pos(k + 1);
          const p = easeOut(revealProgress(frame, reveal[s.id] - fps * 0.1, fps, 0.55));
          if (p <= 0) return null;
          const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
          const ux = dx / len, uy = dy / len;
          const sx = a.x + ux * (R + 14), sy = a.y + uy * (R + 14);
          const ex = b.x - ux * (R + 18), ey = b.y - uy * (R + 18);
          const cx = sx + (ex - sx) * p, cy = sy + (ey - sy) * p;
          const ang = Math.atan2(uy, ux);
          const h = 20;
          return (
            <g key={s.id} stroke={COLORS.red} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" fill="none">
              <path d={`M ${sx} ${sy} L ${cx} ${cy}`} strokeDasharray="1 14" />
              <path d={`M ${sx} ${sy} L ${cx} ${cy}`} />
              {p > 0.9 && <path d={`M ${ex - Math.cos(ang - 0.5) * h} ${ey - Math.sin(ang - 0.5) * h} L ${ex} ${ey} L ${ex - Math.cos(ang + 0.5) * h} ${ey - Math.sin(ang + 0.5) * h}`} />}
            </g>
          );
        })}
      </svg>
      {steps.map((s, i) => {
        const delay = i === 0 ? 0 : fps * 0.25;
        const p = easeOut(revealProgress(frame, reveal[s.id] + delay, fps, 0.5));
        if (p <= 0) return null;
        const { x, y } = pos(i);
        const labelBelow = long;
        return (
          <div key={s.id} style={{ position: "absolute", left: x - R, top: y - R, width: R * 2, height: R * 2, opacity: p, transform: `scale(${0.6 + 0.4 * p})` }}>
            <div style={{ width: R * 2, height: R * 2, borderRadius: R, background: "rgba(233,220,185,0.85)", border: `6px solid ${COLORS.gold}`, boxShadow: "0 8px 20px rgba(43,33,24,0.3)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {s.icon ? <StepIconSvg icon={s.icon} size={R * 1.15} color={COLORS.ink} /> : <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: R * 1.1, color: COLORS.red }}>{i + 1}</span>}
            </div>
            <div style={{ position: "absolute", ...(labelBelow ? { top: R * 2 + 16, left: "50%", transform: "translateX(-50%)", width: slotX * 0.92, textAlign: "center" } : { left: R * 2 + 28, top: "50%", transform: "translateY(-50%)", width: frameW / 2 - R - 40, textAlign: "left" }), fontFamily: FONT_HAND, fontSize: long ? 50 : 54, lineHeight: 1.05, color: COLORS.ink }}>
              {s.label}
            </div>
          </div>
        );
      })}
    </div>
  );
};
