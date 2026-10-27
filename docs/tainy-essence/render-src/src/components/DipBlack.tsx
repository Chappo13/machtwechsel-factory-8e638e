import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { clamp } from "../utils/time";

// Переход "в чёрное и обратно", ~0.4с: быстрый провал в чёрный, короткая
// пауза, затем отпускание — рисуется локально в начале входящей сцены.
export const DipBlack: React.FC<{ durSec?: number }> = ({ durSec = 0.4 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durFrames = fps * durSec;
  if (frame >= durFrames) return null;
  const t = clamp(frame / durFrames);
  // первая треть — чёрный целиком, затем плавное отпускание
  const opacity = t < 0.3 ? 1 : 1 - (t - 0.3) / 0.7;
  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 50 }}>
      <div style={{ position: "absolute", inset: 0, background: "#0a0704", opacity }} />
    </AbsoluteFill>
  );
};
