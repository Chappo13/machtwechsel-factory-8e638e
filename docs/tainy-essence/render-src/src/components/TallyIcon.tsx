import React from "react";
import { COLORS } from "../theme";
import { ShipSilhouette } from "./ShipSilhouette";
import { TallyIconKind } from "../types";

// Силуэты, нарисованные кодом (без картинок и без слов): корабль, человек, монета, амфора, точка.
// Каждый занимает прямоугольник width x (width * ratio); ratio — TALLY_ICON_RATIO.
export const TALLY_ICON_RATIO: Record<TallyIconKind, number> = { ship: 0.75, person: 1.25, coin: 1, amphora: 1.3, dot: 1 };

export const TallyIcon: React.FC<{ kind: TallyIconKind; width: number; wave?: boolean; tone?: "ink" | "red" | "gold" }> = ({ kind, width, wave = true, tone = "ink" }) => {
  const c = tone === "red" ? COLORS.red : tone === "gold" ? COLORS.gold : COLORS.ink;
  const h = width * TALLY_ICON_RATIO[kind];
  if (kind === "ship") return <ShipSilhouette width={width} wave={wave} hull={c} />;
  if (kind === "person") {
    return (
      <svg width={width} height={h} viewBox="0 0 80 100" style={{ overflow: "visible" }}>
        <circle cx={40} cy={17} r={13} fill={c} />
        <path d="M18 100 L18 52 Q18 34 40 34 Q62 34 62 52 L62 100 Z" fill={c} />
        <path d="M30 100 L30 70 M50 100 L50 70" stroke={COLORS.parchmentLight} strokeWidth={2.4} opacity={0.5} />
      </svg>
    );
  }
  if (kind === "coin") {
    return (
      <svg width={width} height={h} viewBox="0 0 100 100" style={{ overflow: "visible" }}>
        <circle cx={50} cy={50} r={46} fill={COLORS.gold} stroke={COLORS.ink} strokeWidth={4} />
        <circle cx={50} cy={50} r={34} fill="none" stroke={COLORS.ink} strokeWidth={3} opacity={0.7} />
        <path d="M50 28 L50 72 M36 40 Q50 30 64 40 M36 60 Q50 70 64 60" fill="none" stroke={COLORS.ink} strokeWidth={4} strokeLinecap="round" opacity={0.75} />
      </svg>
    );
  }
  if (kind === "amphora") {
    return (
      <svg width={width} height={h} viewBox="0 0 80 104" style={{ overflow: "visible" }}>
        <path d="M30 4 L50 4 L50 14 Q50 22 56 26 Q72 32 72 56 Q72 84 48 94 L48 100 L32 100 L32 94 Q8 84 8 56 Q8 32 24 26 Q30 22 30 14 Z" fill={tone === "ink" ? COLORS.red : c} stroke={COLORS.ink} strokeWidth={3} strokeLinejoin="round" />
        <path d="M24 26 Q2 26 6 50 M56 26 Q78 26 74 50" fill="none" stroke={COLORS.ink} strokeWidth={5} strokeLinecap="round" />
        <path d="M12 52 Q40 60 68 52 M14 68 Q40 76 66 68" fill="none" stroke={COLORS.parchmentLight} strokeWidth={3} opacity={0.55} />
      </svg>
    );
  }
  return (
    <svg width={width} height={h} viewBox="0 0 100 100" style={{ overflow: "visible" }}>
      <circle cx={50} cy={50} r={42} fill={c} />
      <circle cx={36} cy={36} r={10} fill={COLORS.parchmentLight} opacity={0.25} />
    </svg>
  );
};
