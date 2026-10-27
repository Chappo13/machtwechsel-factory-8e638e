import React, { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap, revealProgress } from "../utils/time";
import { GearMechanism } from "./GearMechanism";
import { RoughShape } from "../sketches/RoughShape";

export const Blueprint: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, frameW, frameH, seed }) => {
  const frame = useCurrentFrame();
  const labels = data.labels || [];
  const dims = data.dims || [];
  const ids = [...labels.map((l) => l.id), ...dims.map((d) => d.id)];
  const revealMap = useMemo(() => buildRevealMap(ids, beats, sceneStart, fps), [ids.join(","), beats, sceneStart, fps]);
  const drawP = revealProgress(frame, 0, fps, 1.4);

  const cx = frameW / 2;
  const cy = frameH / 2 + 30;

  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      <div
        style={{
          position: "absolute",
          top: 44,
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: FONT_SERIF,
          fontSize: 64,
          fontWeight: 600,
          color: COLORS.ink,
        }}
      >
        {data.title}
      </div>
      {/* рамка чертежа */}
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }}>
        <rect x={40} y={110} width={frameW - 80} height={frameH - 170} fill="none" stroke={COLORS.gold} strokeWidth={2} strokeDasharray="14 10" opacity={0.7} />
        {[0, 1, 2, 3].map((i) => (
          <line key={i} x1={40 + (i * (frameW - 80)) / 3} y1={110} x2={40 + (i * (frameW - 80)) / 3} y2={130} stroke={COLORS.gold} strokeWidth={1.5} opacity={0.5} />
        ))}
      </svg>

      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }} opacity={drawP}>
        {data.object === "gear_mechanism" && <GearMechanism frameW={frameW} frameH={frameH} cx={cx} cy={cy} scale={frameW > frameH ? 1.5 : 1.1} />}
        {data.object === "pyramid_section" && (
          <g transform={`translate(${cx - 160},${cy - 150})`}>
            <polygon points="160,0 320,260 0,260" fill="rgba(176,141,87,0.15)" stroke={COLORS.ink} strokeWidth={3} />
            <line x1={160} y1={0} x2={160} y2={260} stroke={COLORS.ink} strokeWidth={1.5} strokeDasharray="6 6" />
            <path d="M 60 190 L 100 190 L 100 150 L 140 150 L 140 110 L 180 110" fill="none" stroke={COLORS.red} strokeWidth={2.5} />
          </g>
        )}
        {data.object === "wall_masonry" && (
          <g transform={`translate(${cx - 220},${cy - 120})`}>
            {Array.from({ length: 4 }).map((_, row) =>
              Array.from({ length: 6 }).map((__, col) => (
                <rect
                  key={`${row}-${col}`}
                  x={col * 75 + (row % 2 === 0 ? 0 : 37)}
                  y={row * 62}
                  width={70}
                  height={56}
                  fill="rgba(176,141,87,0.12)"
                  stroke={COLORS.ink}
                  strokeWidth={2}
                />
              ))
            )}
          </g>
        )}
        {data.object === "obelisk" && (
          <g transform={`translate(${cx},${cy - 170})`}>
            <polygon points="-55,0 55,0 55,300 70,320 -70,320" fill="rgba(176,141,87,0.15)" stroke={COLORS.ink} strokeWidth={3} />
            <polygon points="-70,320 70,320 0,380" fill="rgba(176,141,87,0.2)" stroke={COLORS.ink} strokeWidth={3} />
            <line x1={-20} y1={60} x2={20} y2={60} stroke={COLORS.red} strokeWidth={2} />
          </g>
        )}
        {data.object === "generic_artifact" && (
          <foreignObject x={cx - 110} y={cy - 110} width={220} height={220}>
            <RoughShape name="scroll" size={220} stroke={COLORS.ink} seed={seed} />
          </foreignObject>
        )}

        {dims.map((d, i) => {
          const p = revealProgress(frame, revealMap[d.id] ?? 0, fps, 0.5);
          if (p <= 0) return null;
          const y = frameH - 100 - i * 0;
          const x = 120 + i * 260;
          return (
            <g key={d.id} opacity={p}>
              <line x1={x} y1={y} x2={x + 160} y2={y} stroke={COLORS.red} strokeWidth={2} markerEnd="url(#arrowEnd)" />
              <text x={x + 80} y={y - 12} textAnchor="middle" fontFamily={FONT_SERIF} fontSize={34} fill={COLORS.red}>
                {d.text}
              </text>
            </g>
          );
        })}
      </svg>

      {labels.map((l, i) => {
        const p = revealProgress(frame, revealMap[l.id] ?? 0, fps, 0.6);
        if (p <= 0) return null;
        const positions = [
          { left: 90, top: 150 },
          { right: 90, top: 150 },
          { left: 90, bottom: 110 },
          { right: 90, bottom: 110 },
        ];
        const pos = positions[i % positions.length];
        return (
          <div
            key={l.id}
            style={{
              position: "absolute",
              ...pos,
              maxWidth: 360,
              fontFamily: FONT_HAND,
              fontSize: 40,
              color: COLORS.ink,
              opacity: p,
              background: "rgba(233,220,185,0.75)",
              padding: "4px 10px",
              borderRadius: 6,
            }}
          >
            {l.text}
          </div>
        );
      })}
    </div>
  );
};
