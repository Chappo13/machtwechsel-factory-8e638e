import React from "react";
import { AbsoluteFill, staticFile, useCurrentFrame } from "remotion";
import { Format } from "../types";

// Пергамент теперь ПРЕДРЕНДЕРЕН в JPEG (scripts/gen-textures.mjs) — зерно,
// пятна, виньетка и рваные края посчитаны один раз оффлайн. Раньше это были
// SVG feTurbulence + несколько blend-слоёв НА КАЖДЫЙ кадр, что было главной
// причиной низкого fps. Теперь здесь только дешёвые вещи: статичная картинка +
// лёгкое мерцание свечи (opacity/brightness без фильтров) + анимированный тайл
// зерна через background-position (GPU-композитинг, без пересчёта).
export const Parchment: React.FC<{ width: number; height: number; format: Format }> = ({
  width,
  height,
  format,
}) => {
  const frame = useCurrentFrame();
  const flicker =
    1 + 0.012 * Math.sin(frame / 17) + 0.006 * Math.sin(frame / 5.3) + 0.005 * Math.sin(frame / 41);
  const grainX = (frame * 0.7) % 220;
  const grainY = (frame * 0.4) % 220;

  const src = staticFile(`textures/parchment-${format}.jpg`);
  const grainSrc = staticFile("textures/grain-tile.png");

  return (
    <AbsoluteFill>
      <img
        src={src}
        width={width}
        height={height}
        style={{ position: "absolute", inset: 0, width, height, objectFit: "cover", opacity: flicker }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.1,
          backgroundImage: `url(${grainSrc})`,
          backgroundPosition: `${grainX}px ${grainY}px`,
          backgroundRepeat: "repeat",
        }}
      />
    </AbsoluteFill>
  );
};
