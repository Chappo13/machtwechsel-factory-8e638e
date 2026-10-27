import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND } from "../theme";
import { SceneProps } from "./sceneProps";
import { clamp, revealProgress } from "../utils/time";

type Pt = [number, number];
const CONSTELLATIONS: Record<string, { pts: Pt[]; edges: [number, number][] }> = {
  orion: {
    pts: [
      [0.5, 0.08], [0.22, 0.28], [0.78, 0.3], [0.42, 0.5], [0.5, 0.52], [0.58, 0.54],
      [0.3, 0.85], [0.68, 0.88],
    ],
    edges: [[0, 1], [0, 2], [1, 3], [2, 5], [3, 4], [4, 5], [1, 6], [2, 7]],
  },
  big_dipper: {
    pts: [[0.1, 0.5], [0.3, 0.45], [0.5, 0.4], [0.68, 0.45], [0.7, 0.65], [0.5, 0.72], [0.32, 0.65]],
    edges: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 3]],
  },
  cygnus: {
    pts: [[0.5, 0.1], [0.5, 0.4], [0.5, 0.75], [0.2, 0.3], [0.8, 0.3]],
    edges: [[0, 1], [1, 2], [1, 3], [1, 4]],
  },
  pleiades: {
    pts: [[0.5, 0.4], [0.42, 0.3], [0.6, 0.28], [0.35, 0.5], [0.66, 0.5], [0.48, 0.58], [0.58, 0.62]],
    edges: [],
  },
};

export const Stars: React.FC<SceneProps> = ({ data, frameW, frameH, fps, durationInFrames }) => {
  const frame = useCurrentFrame();
  const cfg = CONSTELLATIONS[data.constellation || "orion"] || CONSTELLATIONS.orion;

  const size = Math.min(frameW, frameH) * (frameW > frameH ? 0.75 : 0.85);
  const ox = frameW / 2 - size / 2;
  const oy = frameH * 0.1;

  const starRevealEnd = durationInFrames * 0.6;
  const perStar = starRevealEnd / Math.max(1, cfg.pts.length);

  const overlayP = data.overlay ? revealProgress(frame, durationInFrames * 0.65, fps, 1.2) : 0;
  const labelP = revealProgress(frame, durationInFrames * 0.75, fps, 0.6);

  // мерцание звёзд
  const twinkle = (i: number) => 0.75 + 0.25 * Math.sin(frame / 9 + i * 1.7);

  return (
    <div
      style={{
        width: frameW,
        height: frameH,
        position: "relative",
        background:
          "radial-gradient(ellipse 90% 80% at 50% 42%, #2a2338 0%, #1b1626 55%, #130f1c 100%)",
      }}
    >
      {/* чернильная виньетка ночного неба поверх пергамента */}
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }}>
        {Array.from({ length: 90 }).map((_, i) => {
          const x = (i * 97) % frameW;
          const y = (i * 53) % frameH;
          return <circle key={i} cx={x} cy={y} r={1.3} fill={COLORS.parchmentLight} opacity={0.35 * twinkle(i)} />;
        })}

        {overlayP > 0 && (
          <g opacity={overlayP * 0.5} transform={`translate(${ox},${oy + size * 0.55})`}>
            <polygon points={`${size * 0.1},${size * 0.4} ${size * 0.3},${size * 0.05} ${size * 0.5},${size * 0.4}`} fill="none" stroke={COLORS.gold} strokeWidth={2} />
            <polygon points={`${size * 0.38},${size * 0.4} ${size * 0.55},${size * 0.12} ${size * 0.72},${size * 0.4}`} fill="none" stroke={COLORS.gold} strokeWidth={2} />
            <polygon points={`${size * 0.62},${size * 0.4} ${size * 0.76},${size * 0.16} ${size * 0.9},${size * 0.4}`} fill="none" stroke={COLORS.gold} strokeWidth={2} />
          </g>
        )}

        {cfg.edges.map(([a, b], i) => {
          const fa = a * perStar;
          const fb = b * perStar;
          const p = revealProgress(frame, Math.max(fa, fb), fps, 0.5);
          if (p <= 0) return null;
          const [ax, ay] = cfg.pts[a];
          const [bx, by] = cfg.pts[b];
          const x1 = ox + ax * size;
          const y1 = oy + ay * size;
          const x2 = ox + bx * size;
          const y2 = oy + by * size;
          return (
            <line key={i} x1={x1} y1={y1} x2={x1 + (x2 - x1) * p} y2={y1 + (y2 - y1) * p} stroke={COLORS.gold} strokeWidth={1.3} opacity={0.65} />
          );
        })}

        {cfg.pts.map(([x, y], i) => {
          const p = clamp((frame - i * perStar) / (fps * 0.4));
          if (p <= 0) return null;
          const cx = ox + x * size;
          const cy = oy + y * size;
          const r = 5 * p * twinkle(i);
          return (
            <g key={i} opacity={p}>
              <circle cx={cx} cy={cy} r={r * 2.4} fill={COLORS.gold} opacity={0.25} />
              <circle cx={cx} cy={cy} r={r} fill={COLORS.parchmentLight} stroke={COLORS.gold} strokeWidth={1.2} />
            </g>
          );
        })}
      </svg>

      {data.label && (
        <div
          style={{
            position: "absolute",
            bottom: frameH * 0.12,
            left: 0,
            right: 0,
            textAlign: "center",
            opacity: labelP,
            fontFamily: FONT_HAND,
            fontSize: frameW > frameH ? 48 : 42,
            color: COLORS.parchmentLight,
          }}
        >
          {data.label}
        </div>
      )}
    </div>
  );
};
