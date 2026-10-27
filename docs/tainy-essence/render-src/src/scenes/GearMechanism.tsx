import React from "react";
import { Gear } from "../sketches/Gear";
import { COLORS } from "../theme";

// Реально вращающийся механизм из зацепленных шестерён разного размера
// (как в антикитерском механизме) — каждая крутится со скоростью, обратной
// числу зубьев, в противоположные стороны у соседей.
export const GearMechanism: React.FC<{ frameW: number; frameH: number; cx: number; cy: number; scale?: number }> = ({
  cx,
  cy,
  scale = 1,
}) => {
  const gears = [
    { dx: -150, dy: -10, rOut: 95, teeth: 24, dir: 1 as const },
    { dx: 40, dy: -90, rOut: 55, teeth: 14, dir: -1 as const },
    { dx: 150, dy: 60, rOut: 70, teeth: 18, dir: 1 as const },
    { dx: -20, dy: 110, rOut: 42, teeth: 10, dir: -1 as const },
  ];
  return (
    <g transform={`translate(${cx},${cy}) scale(${scale})`}>
      {gears.map((g, i) => (
        <Gear
          key={i}
          cx={g.dx}
          cy={g.dy}
          rOut={g.rOut}
          rIn={g.rOut * 0.82}
          teeth={g.teeth}
          direction={g.dir}
          stroke={COLORS.ink}
          fill="rgba(176,141,87,0.22)"
        />
      ))}
    </g>
  );
};
