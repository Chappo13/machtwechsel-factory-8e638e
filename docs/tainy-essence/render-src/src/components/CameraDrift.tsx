import React from "react";
import { useCurrentFrame } from "remotion";

// Камера никогда не статична: медленный дрейф + зум 1-3% на весь кадр сцены.
// seed — чтобы разные сцены двигались немного по-разному (не синхронно).
export const CameraDrift: React.FC<{
  children: React.ReactNode;
  seed?: number;
  durationInFrames: number;
}> = ({ children, seed = 0, durationInFrames }) => {
  const frame = useCurrentFrame();
  const t = frame / Math.max(1, durationInFrames); // 0..1 по сцене
  const s1 = Math.sin(seed * 13.1 + 0.6);
  const s2 = Math.cos(seed * 7.7 + 1.1);
  const scale = 1 + 0.02 * (0.5 + 0.5 * Math.sin(t * Math.PI)) + 0.01 * s1;
  const dx = 10 * Math.sin(t * Math.PI * 2 + seed) * (0.5 + 0.5 * s2);
  const dy = 6 * Math.cos(t * Math.PI * 1.3 + seed);
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transform: `scale(${scale}) translate(${dx}px, ${dy}px)`,
        transformOrigin: "50% 50%",
      }}
    >
      {children}
    </div>
  );
};
