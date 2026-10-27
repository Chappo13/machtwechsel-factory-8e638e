import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { clamp, easeOut } from "../utils/time";

const NBSP = "\u00a0";

export const NumberScene: React.FC<SceneProps> = ({ data, fps, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const countDur = fps * 1.6;
  const p = easeOut(clamp(frame / countDur));
  const value = data.value ?? 0;
  const display = Math.round(value * p);
  const formatted = display.toLocaleString("ru-RU");

  const pulse = 1 + 0.015 * Math.sin(frame / 5);

  return (
    <div
      style={{
        width: frameW,
        height: frameH,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
      }}
    >
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0, opacity: 0.5 * Math.min(1, p * 2) }}>
        {/* едва заметные чернильные кольца за числом: рамка без текста, но кадр не пустой */}
        {[0.34, 0.27, 0.2].map((k, i) => (
          <circle key={i} cx={frameW / 2} cy={frameH * 0.47} r={Math.min(frameW, frameH) * k * (0.92 + 0.08 * p)} fill="none"
            stroke={COLORS.inkSoft} strokeWidth={i === 0 ? 2 : 1} strokeDasharray={i === 1 ? "3 11" : undefined} opacity={0.24 + i * 0.04} />
        ))}
        {[-1, 1].map((d) => (
          <line key={d} x1={frameW / 2 + d * frameW * 0.1} y1={frameH * 0.47 + (frameW > frameH ? 235 : 215)}
            x2={frameW / 2 + d * (frameW * 0.1 + frameW * 0.16 * p)} y2={frameH * 0.47 + (frameW > frameH ? 235 : 215)}
            stroke={COLORS.red} strokeWidth={2} opacity={0.35} strokeLinecap="round" />
        ))}
      </svg>
      <div
        style={{
          whiteSpace: "nowrap",
          fontFamily: FONT_SERIF,
          fontWeight: 900,
          fontSize: frameW > frameH ? 250 : 210,
          color: COLORS.red,
          lineHeight: 1,
          transform: `scale(${p < 1 ? pulse : 1 + 0.01 * Math.sin(frame / 10)})`,
          textShadow: "0 4px 0 rgba(43,33,24,0.15)",
        }}
      >
        {data.prefix ? <span style={{ fontSize: "0.5em" }}>{data.prefix}{NBSP}</span> : null}
        {formatted}
        {data.unit ? <span style={{ fontSize: "0.42em" }}>{NBSP}{data.unit}</span> : null}
      </div>
      <div
        style={{
          marginTop: 18,
          fontFamily: FONT_HAND,
          fontSize: frameW > frameH ? 52 : 46,
          color: COLORS.ink,
          textAlign: "center",
          maxWidth: frameW * 0.7,
          opacity: Math.min(1, p * 1.3),
        }}
      >
        {data.hide_words ? "" : data.label}
      </div>
    </div>
  );
};
