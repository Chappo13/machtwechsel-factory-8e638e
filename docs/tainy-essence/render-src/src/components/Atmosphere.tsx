import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { AtmosKind } from "../types";

// Детерминированный слой атмосферы поверх кадра: снег, морская пыль, туман, пыль в луче, искры/угли.
// Все позиции — чистая функция номера кадра и seed (никакого Math.random). Видимость повышена относительно
// пилота (владелец 15.10: «слишком незаметно»), но остаётся тактичной: частицы мелкие, цвет приглушённый.
function rng(seed: number) {
  let a = (seed * 2654435761) >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const mod = (v: number, m: number) => ((v % m) + m) % m;
const KIND_SALT: Record<AtmosKind, number> = { snow: 1, spray: 2, fog: 3, dust: 4, embers: 5 };

export const Atmosphere: React.FC<{ kind: AtmosKind; seed?: number; intensity?: number; fadeInSec?: number }> = ({ kind, seed = 1, intensity = 1, fadeInSec = 0.8 }) => {
  const frame = useCurrentFrame();
  const { fps, width: W, height: H } = useVideoConfig();
  const t = frame / fps;
  const r = rng(seed * 977 + KIND_SALT[kind]);
  const items: React.ReactNode[] = [];
  const scale = Math.min(W, H) / 1080; // размеры частиц привязаны к меньшей стороне кадра
  const fadeIn = Math.min(1, t / Math.max(0.01, fadeInSec));

  if (kind === "snow") {
    const n = Math.round(240 * intensity);
    for (let i = 0; i < n; i++) {
      const x0 = r() * W, y0 = r() * H, sz = (2 + r() * r() * 6.5) * scale, vy = (46 + sz * 20 + r() * 40) * scale, wind = (-34 - r() * 60) * scale, ph = r() * 6.28, amp = (8 + r() * 22) * scale, al = 0.55 + r() * 0.4;
      const x = mod(x0 + wind * t + Math.sin(t * 0.9 + ph) * amp, W + 60) - 30;
      const y = mod(y0 + vy * t, H + 60) - 30;
      items.push(<circle key={i} cx={x} cy={y} r={sz} fill="#f4f7f9" opacity={Math.min(1, al)} />);
    }
  } else if (kind === "spray") {
    // морская пыль: капли разной величины летят вверх-вбок дугой и гаснут, у крупных короткий хвост; снизу лёгкая дымка
    const n = Math.round(150 * intensity);
    for (let i = 0; i < n; i++) {
      const x0 = r() * W, base = H * (0.35 + r() * 0.6), v = (160 + r() * 360) * scale, rr = (1.8 + r() * r() * 6) * scale, rise = (40 + r() * 150) * scale, cyc = 1.0 + r() * 1.5, ph = r(), dir = 0.6 + r() * 0.8;
      const k = mod(t / cyc + ph, 1); // жизнь капли 0..1
      const x = mod(x0 + v * dir * t * 0.35, W + 120) - 60 + k * v * 0.35;
      const y = base - rise * Math.sin(k * Math.PI * 0.9) + rise * 0.55 * k * k;
      const fade = Math.sin(k * Math.PI);
      const al = (0.55 + r() * 0.4) * fade;
      items.push(<circle key={i} cx={x} cy={y} r={rr} fill="#f1f6f9" opacity={al} />);
      if (rr > 3.2) items.push(<line key={`t${i}`} x1={x} y1={y} x2={x - v * 0.05} y2={y + rr * 0.9} stroke="#f1f6f9" strokeWidth={rr * 0.8} strokeLinecap="round" opacity={al * 0.5} />);
    }
    items.push(<rect key="mist" x={0} y={H * 0.5} width={W} height={H * 0.5} fill="url(#mistGrad)" opacity={Math.min(0.5, 0.34 * intensity)} />);
  } else if (kind === "fog") {
    const n = 8;
    for (let i = 0; i < n; i++) {
      const rx = (420 + r() * 480) * scale, ry = (130 + r() * 170) * scale, y = H * (0.25 + r() * 0.65), sp = (10 + r() * 20) * scale, x0 = r() * (W + 2 * rx), al = 0.3 + r() * 0.22 * intensity;
      const x = mod(x0 + sp * t, W + 2 * rx) - rx;
      items.push(<ellipse key={i} cx={x} cy={y + Math.sin(t * 0.25 + i) * 12} rx={rx} ry={ry} fill="url(#fogGrad)" opacity={Math.min(0.62, al * 1.5)} />);
    }
  } else if (kind === "dust") {
    // пылинки в луче света: тёплые, медленно плывут вверх и вбок, мерцают; несколько крупных размытых «боке»
    const n = Math.round(130 * intensity);
    for (let i = 0; i < n; i++) {
      const x0 = r() * W, y0 = r() * H, sz = (1.6 + r() * r() * 5) * scale, vy = (-8 - r() * 16) * scale, vx = (6 + r() * 14) * scale, ph = r() * 6.28, amp = (10 + r() * 24) * scale, al = 0.5 + r() * 0.45, tw = 0.5 + 0.5 * Math.sin(t * (0.8 + r() * 1.6) + ph);
      const x = mod(x0 + vx * t + Math.sin(t * 0.5 + ph) * amp, W + 40) - 20;
      const y = mod(y0 + vy * t + Math.cos(t * 0.4 + ph) * amp * 0.5, H + 40) - 20;
      items.push(<circle key={i} cx={x} cy={y} r={sz} fill="#f7e6bd" opacity={Math.min(1, al * (0.45 + 0.55 * tw))} />);
    }
    for (let i = 0; i < 7; i++) {
      const x0 = r() * W, y0 = r() * H, sz = (14 + r() * 22) * scale, vx = (4 + r() * 8) * scale, ph = r() * 6.28;
      const x = mod(x0 + vx * t, W + 80) - 40;
      items.push(<circle key={`b${i}`} cx={x} cy={y0 + Math.sin(t * 0.3 + ph) * 18} r={sz} fill="url(#dustGrad)" opacity={0.32 * intensity} />);
    }
  } else {
    // искры и угли: вверх, с покачиванием и мерцанием, тёплое свечение
    const n = Math.round(110 * intensity);
    for (let i = 0; i < n; i++) {
      const x0 = r() * W, sz = (1.8 + r() * r() * 5.5) * scale, v = (60 + r() * 130) * scale, ph = r() * 6.28, amp = (10 + r() * 30) * scale, cyc = 3 + r() * 4, off = r();
      const k = mod(t / cyc + off, 1); // 0 внизу, 1 вверху
      const y = H * (1.04 - k * 1.1) + 0 * v;
      const x = mod(x0 + Math.sin(t * 1.3 + ph) * amp + k * 40 * scale, W);
      const life = Math.sin(Math.min(1, k * 1.15) * Math.PI);
      const fl = 0.7 + 0.3 * Math.sin(t * (6 + r() * 6) + ph);
      const hot = r() > 0.55;
      items.push(
        <g key={i} opacity={Math.min(1, life * fl * 1.1)}>
          <circle cx={x} cy={y} r={sz * 3.2} fill="url(#emberGlow)" />
          <circle cx={x} cy={y} r={sz} fill={hot ? "#ffd27a" : "#ff8a3a"} />
        </g>
      );
    }
  }
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: fadeIn }}>
      <defs>
        <radialGradient id="fogGrad"><stop offset="0" stopColor="#dfe5e8" stopOpacity="0.95" /><stop offset="1" stopColor="#dfe5e8" stopOpacity="0" /></radialGradient>
        <linearGradient id="mistGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#d6dee3" stopOpacity="0" /><stop offset="1" stopColor="#d6dee3" stopOpacity="0.85" /></linearGradient>
        <radialGradient id="dustGrad"><stop offset="0" stopColor="#fff1cc" stopOpacity="0.9" /><stop offset="1" stopColor="#fff1cc" stopOpacity="0" /></radialGradient>
        <radialGradient id="emberGlow"><stop offset="0" stopColor="#ff9a3c" stopOpacity="0.75" /><stop offset="1" stopColor="#ff5a1f" stopOpacity="0" /></radialGradient>
      </defs>
      {items}
    </svg>
  );
};
