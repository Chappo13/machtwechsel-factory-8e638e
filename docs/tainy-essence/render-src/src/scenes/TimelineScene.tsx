import React, { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap, revealProgress } from "../utils/time";

const fmtYear = (y: number) => (y < 0 ? `${Math.abs(y)} до н.э.` : `${y} н.э.`);

function wrapLines(text: string, max: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length > max && cur) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 2);
}

export const TimelineScene: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const events = (data.events || []).slice().sort((a, b) => a.year - b.year);
  const fromYear = data.from_year ?? (events[0]?.year ?? 0);
  const toYear = data.to_year ?? (events[events.length - 1]?.year ?? 1);
  const span = Math.max(1, toYear - fromYear);

  const horizontal = format === "long";
  const trackStart = horizontal ? frameW * 0.08 : frameH * 0.12;
  const trackEnd = horizontal ? frameW * 0.92 : frameH * 0.9;

  const ids = events.map((e) => e.id);
  const revealMap = useMemo(() => buildRevealMap(ids, beats, sceneStart, fps), [ids.join(","), beats, sceneStart, fps]);

  const lineProgress = revealProgress(frame, 0, fps, 1.2);
  const yearSize = horizontal ? 38 : 36;
  const labelSize = horizontal ? 34 : 33;

  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }}>
        {horizontal ? (
          <line
            x1={trackStart}
            y1={frameH / 2}
            x2={trackStart + (trackEnd - trackStart) * lineProgress}
            y2={frameH / 2}
            stroke={COLORS.inkSoft}
            strokeWidth={6}
            strokeLinecap="round"
          />
        ) : (
          <line
            x1={frameW / 2}
            y1={trackStart}
            x2={frameW / 2}
            y2={trackStart + (trackEnd - trackStart) * lineProgress}
            stroke={COLORS.inkSoft}
            strokeWidth={6}
            strokeLinecap="round"
          />
        )}

        {events.map((e, i) => {
          const p = revealProgress(frame, revealMap[e.id] ?? 0, fps, 0.6);
          if (p <= 0) return null;
          const frac = (e.year - fromYear) / span;
          // 4 яруса (2 сверху, 2 снизу) — снижает шанс наложения подписей на плотной шкале
          const tier = i % 4;
          const above = tier < 2;
          const tierDepth = tier % 2;
          const pos = trackStart + (trackEnd - trackStart) * frac;
          const cx = horizontal ? pos : frameW / 2;
          const cy = horizontal ? frameH / 2 : pos;
          const r = 14 * p;
          const labelOffset = horizontal ? 70 + tierDepth * 100 : 70 + tierDepth * 220;
          const tx = horizontal ? cx : (above ? frameW / 2 + labelOffset + 150 : frameW / 2 - labelOffset - 150);
          const ty = horizontal ? (above ? cy - labelOffset : cy + labelOffset + 40) : cy;
          const lines = data.hide_words ? [] : wrapLines(e.label, 16);
          return (
            <g key={e.id} opacity={p}>
              <line
                x1={cx}
                y1={cy}
                x2={horizontal ? cx : tx}
                y2={horizontal ? ty : cy}
                stroke={COLORS.gold}
                strokeWidth={3}
              />
              <circle cx={cx} cy={cy} r={r} fill={COLORS.red} stroke={COLORS.parchmentLight} strokeWidth={3} />
              <text
                x={tx}
                y={horizontal ? ty : cy - 14}
                textAnchor="middle"
                fontFamily={FONT_SERIF}
                fontWeight={700}
                fontSize={yearSize}
                fill={COLORS.red}
              >
                {fmtYear(e.year)}
              </text>
              <text
                x={tx}
                y={(horizontal ? ty : cy) + 36}
                textAnchor="middle"
                fontFamily={FONT_HAND}
                fontSize={labelSize}
                fill={COLORS.ink}
              >
                {lines.map((line, li) => (
                  <tspan key={li} x={tx} dy={li === 0 ? 0 : labelSize + 2}>
                    {line}
                  </tspan>
                ))}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};
