import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { clamp, easeOut } from "../utils/time";

// Лёгкая вспышка-засветка плёнки, ~0.35с: тёплая белая вспышка быстро гаснет.
export const FilmBurn: React.FC<{ durSec?: number }> = ({ durSec = 0.35 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durFrames = fps * durSec;
  if (frame >= durFrames) return null;
  const t = clamp(frame / durFrames);
  const opacity = 1 - easeOut(t);
  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 50 }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse 70% 60% at 50% 45%, rgba(255,244,214,0.95) 0%, rgba(255,214,150,0.55) 45%, rgba(255,214,150,0) 80%)",
          opacity,
          mixBlendMode: "screen",
        }}
      />
    </AbsoluteFill>
  );
};
