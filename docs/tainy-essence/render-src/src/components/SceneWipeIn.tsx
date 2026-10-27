import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS } from "../theme";
import { clamp, easeInOut } from "../utils/time";

// Переход между сценами в стиле "страница перелистывается / чернильная клякса",
// ~0.5с. Рисуется локально в начале сцены (не трогает общую длительность клипа).
export const SceneWipeIn: React.FC<{ durSec?: number; skip?: boolean }> = ({
  durSec = 0.5,
  skip = false,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  if (skip) return null;
  const durFrames = fps * durSec;
  if (frame >= durFrames) return null;
  const p = easeInOut(clamp(frame / durFrames));
  const travel = width * 1.15 * p;

  const jag = "0% 0%, 8% 4%, 16% 0%, 24% 6%, 33% 1%, 42% 7%, 51% 2%, 60% 6%, 69% 0%, 78% 5%, 88% 1%, 100% 0%, 100% 100%, 0% 100%";

  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 50 }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(100deg, ${COLORS.ink} 0%, #150e08 60%, ${COLORS.ink} 100%)`,
          clipPath: `polygon(${jag})`,
          transform: `translateX(${-travel}px) skewX(-4deg)`,
          boxShadow: "8px 0 0 rgba(0,0,0,0.4)",
        }}
      />
    </AbsoluteFill>
  );
};
