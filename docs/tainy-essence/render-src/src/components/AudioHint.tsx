import React from "react";
import { COLORS, FONT_SERIF } from "../theme";
import { AudioHintOverlay } from "../types";
import { clamp, easeInOut } from "../utils/time";
import { audioHintFade } from "../utils/overlayFade.mjs";

// Одна стеклянная плашка в начале длинного ролика: [Subscribe] [Like] [⚙ → динамик + RU EN ES...].
// Иконки + короткие английские подписи (lingua franca). Один раз на ролик; на шортсах не рисуется.
const ICON = COLORS.parchmentLight;

const svg = (w: number, h: number, children: React.ReactNode, style?: React.CSSProperties) => (
  <svg width={w} height={h} viewBox="0 0 24 24" fill="none" stroke={ICON} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={style}>{children}</svg>
);

const Bell: React.FC<{ s: number; swing: number }> = ({ s, swing }) => (
  <div style={{ width: 44 * s, height: 34 * s, borderRadius: 10 * s, background: "#b3261e", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 2px 8px rgba(0,0,0,0.35)" }}>
    {svg(24 * s, 24 * s, <><path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.6 1.6H4.4z" fill="#fff" fillOpacity="0.25" /><path d="M10 20.5a2 2 0 0 0 4 0" /></>, { transform: `rotate(${swing}deg)`, transformOrigin: "50% 15%", stroke: "#fff" })}
  </div>
);
const Thumb: React.FC<{ s: number; pop: number }> = ({ s, pop }) =>
  svg(34 * s, 34 * s, <><path d="M7 11v9H4v-9z" /><path d="M7 11l4-7c1.6 0 2.4 1.2 2 3l-.6 3H19a1.8 1.8 0 0 1 1.8 2.2l-1.4 6.2A2 2 0 0 1 17.4 20H7" fill={ICON} fillOpacity="0.18" /></>, { transform: `scale(${pop})` });
const Gear: React.FC<{ s: number; rot: number }> = ({ s, rot }) =>
  svg(28 * s, 28 * s, <><circle cx="12" cy="12" r="3.2" /><circle cx="12" cy="12" r="6.6" /><path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.9 1.9M16.6 16.6l1.9 1.9M18.5 5.5l-1.9 1.9M7.4 16.6l-1.9 1.9" /></>, { transform: `rotate(${rot}deg)` });
const Arrow: React.FC<{ s: number }> = ({ s }) => (
  <svg width={24 * s} height={24 * s} viewBox="0 0 24 24" fill="none" stroke={COLORS.gold} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h15M13 6l6 6-6 6" /></svg>
);
const Speaker: React.FC<{ s: number; phase: number }> = ({ s, phase }) => (
  <svg width={30 * s} height={26 * s} viewBox="0 0 28 24" fill="none" stroke={ICON} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 9h4l6-5v16l-6-5H3z" fill={ICON} fillOpacity="0.18" />
    <path d="M17 8.5a5 5 0 0 1 0 7" opacity={0.45 + 0.55 * Math.max(0, Math.sin(phase))} />
    <path d="M20.5 5.5a9.5 9.5 0 0 1 0 13" opacity={0.3 + 0.7 * Math.max(0, Math.sin(phase - 0.9))} />
  </svg>
);

export const AudioHint: React.FC<{ overlay: AudioHintOverlay; t: number; fps: number; format: "long" | "short" }> = ({ overlay, t, format }) => {
  if (format !== "long") return null;
  const { inP, o } = audioHintFade(t, overlay); // t = абсолютное время ролика (не локальный кадр сцены)
  if (o <= 0) return null;
  const large = overlay.size === "large";
  const s = large ? 1.3 : 1;
  const local = t - overlay.start;
  const langs = overlay.langs;
  const active = Math.floor(Math.max(0, local - 1.1) / 0.7) % langs.length;
  const audioLabel = overlay.label ?? (large ? "Choose your audio language" : "Audio");
  const pos: React.CSSProperties = overlay.position === "bottom-left" ? { left: 44, bottom: 28 } : { right: 44, top: 108 };
  const slide = (1 - inP) * 14 * (overlay.position === "bottom-left" ? 1 : -1);
  const col = (delay: number): React.CSSProperties => {
    const p = easeInOut(clamp((local - delay) / 0.4));
    return { opacity: p, transform: `translateY(${(1 - p) * 6}px)`, display: "flex", flexDirection: "column", alignItems: "center", gap: 7 * s };
  };
  const cap: React.CSSProperties = { fontFamily: FONT_SERIF, fontWeight: 600, fontSize: 19 * s, letterSpacing: 0.6, color: ICON, opacity: 0.88, whiteSpace: "nowrap", lineHeight: 1 };
  const divider = <div style={{ width: 1, alignSelf: "stretch", background: "rgba(233,220,185,0.22)" }} />;
  const bellSwing = Math.sin(local * 9) * 14 * Math.max(0, 1 - Math.abs(local - 1.0) / 0.9);
  const thumbPop = 1 + 0.18 * Math.max(0, Math.sin(Math.min(1, Math.max(0, (local - 1.5) / 0.5)) * Math.PI));
  return (
    <div style={{ position: "absolute", ...pos, opacity: o, transform: `translateY(${slide}px)`, pointerEvents: "none" }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 16 * s, padding: `${12 * s}px ${20 * s}px ${13 * s}px`,
        background: "linear-gradient(135deg, rgba(34,26,18,0.76), rgba(20,14,10,0.6))",
        backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)",
        border: "1px solid rgba(233,220,185,0.28)", borderRadius: 18 * s,
        boxShadow: "0 6px 22px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.12)",
      }}>
        {overlay.subscribe && (<><div style={col(0.15)}><Bell s={s} swing={bellSwing} /><div style={cap}>Subscribe</div></div>{divider}</>)}
        {overlay.like && (<><div style={col(0.35)}><div style={{ height: 34 * s, display: "flex", alignItems: "center" }}><Thumb s={s} pop={thumbPop} /></div><div style={cap}>Like</div></div>{divider}</>)}
        <div style={col(0.55)}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 * s }}>
            <Gear s={s} rot={local * 40} /><Arrow s={s} /><Speaker s={s} phase={local * 6} />
            <div style={{ display: "flex", gap: 6 * s, marginLeft: 6 * s }}>
              {langs.map((l, i) => {
                const show = easeInOut(clamp((local - 0.7 - i * 0.06) / 0.3));
                const on = i === active && local > 1.1;
                return (
                  <div key={l} style={{
                    fontFamily: FONT_SERIF, fontWeight: 700, fontSize: 19 * s, letterSpacing: 1.2, lineHeight: 1,
                    padding: `${6 * s}px ${8 * s}px`, borderRadius: 8 * s, opacity: show,
                    color: on ? COLORS.ink : ICON, background: on ? COLORS.gold : "rgba(233,220,185,0.12)",
                    border: `1px solid ${on ? COLORS.gold : "rgba(233,220,185,0.3)"}`,
                  }}>{l}</div>
                );
              })}
            </div>
          </div>
          <div style={cap}>{audioLabel}</div>
        </div>
      </div>
    </div>
  );
};
