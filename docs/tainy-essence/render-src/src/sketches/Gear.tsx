import React, { useMemo } from "react";
import { useCurrentFrame } from "remotion";

// Одна реально вращающаяся шестерня (SVG path, зубья считаются параметрически).
// Скорость вращения обратно пропорциональна числу зубьев — визуально похоже на
// настоящее зацепление (чем крупнее шестерня/больше зубьев, тем медленнее).
export const Gear: React.FC<{
  cx: number;
  cy: number;
  rOut: number;
  rIn: number;
  teeth: number;
  stroke: string;
  fill: string;
  direction?: 1 | -1;
  baseDegPerFrame?: number;
  refTeeth?: number;
}> = ({
  cx,
  cy,
  rOut,
  rIn,
  teeth,
  stroke,
  fill,
  direction = 1,
  baseDegPerFrame = 1.1,
  refTeeth = 10,
}) => {
  const frame = useCurrentFrame();
  const speed = baseDegPerFrame * (refTeeth / teeth) * direction;
  const angle = frame * speed;

  // форма зубьев не зависит от кадра — считаем один раз, крутим только transform
  const d = useMemo(() => {
    let out = "";
    const r0 = rIn * 0.98;
    for (let i = 0; i < teeth; i++) {
      const a0 = (i / teeth) * Math.PI * 2;
      const a1 = a0 + (Math.PI * 2) / teeth / 2;
      const a2 = a0 + (Math.PI * 2) / teeth;
      const p = (r: number, a: number) => `${r * Math.cos(a)},${r * Math.sin(a)}`;
      out += `M ${p(r0, a0)} L ${p(rOut, a0 + 0.04)} L ${p(rOut, a1 - 0.04)} L ${p(r0, a1)} L ${p(r0, a2)} `;
    }
    return out;
  }, [teeth, rOut, rIn]);

  return (
    <g transform={`translate(${cx},${cy}) rotate(${angle})`}>
      <path d={d} fill={fill} stroke={stroke} strokeWidth={2} strokeLinejoin="round" />
      <circle r={rIn * 0.97} fill={fill} stroke={stroke} strokeWidth={2} />
      <circle r={rIn * 0.22} fill="none" stroke={stroke} strokeWidth={2.5} />
      {/* спицы */}
      {[0, 1, 2, 3].map((i) => (
        <line
          key={i}
          x1={0}
          y1={0}
          x2={(rIn * 0.85) * Math.cos((i * Math.PI) / 2)}
          y2={(rIn * 0.85) * Math.sin((i * Math.PI) / 2)}
          stroke={stroke}
          strokeWidth={2}
          opacity={0.6}
        />
      ))}
    </g>
  );
};
