import React from "react";
import { COLORS } from "../theme";

// Силуэт викингского корабля, нарисованный кодом (без картинок и без слов).
// Нос и корма приподняты, один прямоугольный парус в красно-светлую полоску.
export const ShipSilhouette: React.FC<{ width?: number; hull?: string; stripeA?: string; stripeB?: string; wave?: boolean; opacity?: number }> = ({
  width = 150, hull = COLORS.ink, stripeA = COLORS.red, stripeB = COLORS.parchmentLight, wave = true, opacity = 1,
}) => {
  const bands = 6;
  const top = (x: number) => 12 - 3 * Math.sin(((x - 32) / 58) * Math.PI);
  const bot = (x: number) => 47 + 4 * Math.sin(((x - 32) / 58) * Math.PI);
  const sx0 = 32, sx1 = 90;
  const quads = Array.from({ length: bands }, (_, i) => {
    const xa = sx0 + ((sx1 - sx0) * i) / bands, xb = sx0 + ((sx1 - sx0) * (i + 1)) / bands;
    return (
      <polygon key={i} points={`${xa},${top(xa)} ${xb},${top(xb)} ${xb},${bot(xb)} ${xa},${bot(xa)}`} fill={i % 2 === 0 ? stripeA : stripeB} />
    );
  });
  return (
    <svg width={width} height={(width * 90) / 120} viewBox="0 0 120 90" style={{ overflow: "visible" }} opacity={opacity}>
      <rect x={59} y={8} width={3} height={52} fill={hull} />
      {quads}
      <path d={`M${sx0} ${top(sx0)} Q61 ${top(61) - 4} ${sx1} ${top(sx1)} L${sx1} ${bot(sx1)} Q61 ${bot(61) + 4} ${sx0} ${bot(sx0)} Z`} fill="none" stroke={hull} strokeWidth={1.6} strokeLinejoin="round" />
      <path d="M5 58 Q1 46 8 36 Q13 41 11 47 Q18 52 24 51 Q60 60 96 51 Q102 52 109 47 Q107 41 112 36 Q119 46 115 58 Q104 76 80 79 L40 79 Q16 76 5 58 Z" fill={hull} />
      {wave && <path d="M-4 82 Q6 76 16 82 T36 82 T56 82 T76 82 T96 82 T116 82 T126 82" fill="none" stroke={hull} strokeWidth={2} opacity={0.45} strokeLinecap="round" />}
    </svg>
  );
};
