import React from "react";
import { COLORS } from "../theme";
import { DateChipOverlay } from "../types";
import { clamp, easeInOut } from "../utils/time";
import { dateChipFade } from "../utils/overlayFade.mjs";

// Стеклянная плашка с датой («1349 год», «XIV век», «≈40 млн лет назад») — визуальное
// подкрепление того, что диктор произносит дату. Рисуется и в long (16:9), и в short (9:16):
// слева сверху под шапкой (справа — подсказка аудиодорожки и плашка главы, снизу — lower_third и субтитры).
const SERIF = "'Playfair Display', 'PT Serif', serif";

export const DateChip: React.FC<{ overlay: DateChipOverlay; t: number; format: "long" | "short" }> = ({ overlay, t, format }) => {
  const { inP, outP, o } = dateChipFade(t, overlay);
  if (o <= 0) return null;
  const long = format === "long";
  const s = (overlay.size === "large" ? 1.25 : 1) * (long ? 1 : 0.92);
  const place = overlay.position ?? "top-left";
  const pos: React.CSSProperties = place === "top-right" ? { right: long ? 44 : 40, top: long ? 108 : 150 }
    : place === "bottom-left" ? { left: long ? 44 : 40, bottom: long ? 150 : 540 }
    : { left: long ? 44 : 40, top: long ? 108 : 150 };
  const dir = place === "top-right" ? 1 : -1;
  const slide = (outP < inP ? (1 - outP) : (1 - inP)) * 22 * dir;
  const text = overlay.text;
  const sp = text.indexOf(" ");
  const main = sp > 0 ? text.slice(0, sp) : text;
  const rest = sp > 0 ? text.slice(sp + 1) : "";
  const line = easeInOut(clamp((t - overlay.start - 0.15) / 0.5));
  return (
    <div style={{ position: "absolute", ...pos, opacity: o, transform: `translateX(${slide}px)`, pointerEvents: "none" }}>
      <div style={{
        position: "relative", display: "flex", alignItems: "baseline", gap: 12 * s, padding: `${10 * s}px ${24 * s}px ${14 * s}px`,
        background: "linear-gradient(135deg, rgba(34,26,18,0.78), rgba(20,14,10,0.62))",
        backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)",
        border: "1px solid rgba(233,220,185,0.28)", borderRadius: 16 * s, whiteSpace: "nowrap",
        boxShadow: "0 6px 22px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,255,255,0.12)",
      }}>
        <span style={{ fontFamily: SERIF, fontWeight: 900, fontSize: 52 * s, lineHeight: 1.05, letterSpacing: 1, color: COLORS.parchmentLight, fontVariantNumeric: "lining-nums" }}>{main}</span>
        {rest && <span style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 28 * s, lineHeight: 1, letterSpacing: 1.2, color: COLORS.gold }}>{rest}</span>}
        <div style={{ position: "absolute", left: 18 * s, right: 18 * s, bottom: 6 * s, height: 2, background: COLORS.gold, opacity: 0.85, transformOrigin: "left", transform: `scaleX(${line})` }} />
      </div>
    </div>
  );
};
