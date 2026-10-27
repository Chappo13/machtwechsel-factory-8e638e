import React from "react";
import { Img, useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap } from "../utils/revealTiming.mjs";
import { clamp, easeInOut, easeOut, revealProgress } from "../utils/time";
import { CompareSide } from "../types";

// «Было → стало» / «официальная версия vs находка». Две стороны с короткими
// тезис-подписями; у каждой может быть фото. mode "split" — две рамки рядом (на
// вертикали одна над другой), "slider" — одно фото на весь кадр и шторка-разделитель,
// которая отодвигается на beat правой стороны (нужны фото у обеих сторон).
export const Compare: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const long = format === "long";
  const reveal = buildRevealMap(["left", "right"], beats, sceneStart, fps, 0.9);
  const pL = easeOut(revealProgress(frame, reveal.left, fps, 0.7));
  const pR = easeOut(revealProgress(frame, reveal.right, fps, 0.7));
  const left = data.left as CompareSide, right = data.right as CompareSide;
  const slider = data.mode === "slider" && Boolean(left.src && right.src);

  const padX = long ? 90 : 56;
  const top = long ? (data.title ? 150 : 110) : 230;
  const bottom = long ? 110 : 360;
  const areaW = frameW - padX * 2, areaH = frameH - top - bottom;
  const gap = long ? 70 : 64;
  const panelW = long ? (areaW - gap) / 2 : areaW;
  const panelH = long ? areaH : (areaH - gap) / 2;
  const panels = [
    { side: left, p: pL, x: padX, y: top, tint: COLORS.inkSoft, tag: "A" },
    { side: right, p: pR, x: long ? padX + panelW + gap : padX, y: long ? top : top + panelH + gap, tint: COLORS.red, tag: "B" },
  ];
  const vsP = easeOut(revealProgress(frame, Math.min(reveal.left, reveal.right) + fps * 0.4, fps, 0.6));

  if (slider) {
    // шторка: сначала виден только left, на beat right она плавно уезжает к середине
    const sweep = easeInOut(revealProgress(frame, reveal.right, fps, 1.1));
    const pos = 1 - 0.5 * sweep; // доля ширины, где проходит граница
    const boxW = areaW, boxH = areaH;
    return (
      <div style={{ width: frameW, height: frameH, position: "relative" }}>
        {data.title && <Title text={data.title} long={long} frameW={frameW} />}
        <div style={{ position: "absolute", left: padX, top, width: boxW, height: boxH, border: `6px solid ${COLORS.paperShadow}`, boxShadow: "0 12px 30px rgba(43,33,24,0.35)", overflow: "hidden", background: "#1c1610" }}>
          <Photo src={right.src!} w={boxW} h={boxH} />
          <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${(1 - pos) * 100}% 0 0)` }}>
            <Photo src={left.src!} w={boxW} h={boxH} />
          </div>
          <div style={{ position: "absolute", top: 0, bottom: 0, left: `${pos * 100}%`, width: 5, marginLeft: -2.5, background: COLORS.gold, boxShadow: "0 0 14px rgba(0,0,0,0.5)" }} />
          <Tag text={left.label} sub={left.caption} p={pL} x={24} y={boxH - 24} long={long} color={COLORS.inkSoft} anchor="left" />
          <Tag text={right.label} sub={right.caption} p={pR} x={24} y={boxH - 24} long={long} color={COLORS.red} anchor="right" />
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      {data.title && <Title text={data.title} long={long} frameW={frameW} />}
      {panels.map(({ side, p, x, y, tint, tag }) => (
        <div key={tag} style={{ position: "absolute", left: x, top: y, width: panelW, height: panelH, opacity: p, transform: `translate${long ? "Y" : "X"}(${(1 - p) * (long ? 40 : (tag === "A" ? -40 : 40))}px)` }}>
          <div style={{ position: "absolute", inset: 0, border: `6px solid ${tint}`, background: side.src ? "#1c1610" : "rgba(233,220,185,0.55)", boxShadow: "0 10px 26px rgba(43,33,24,0.3)", overflow: "hidden" }}>
            {side.src ? <Photo src={side.src} w={panelW - 12} h={panelH - 12} /> : <PlainFace side={side} long={long} tint={tint} />}
          </div>
          {side.src && <Tag text={side.label} sub={side.caption} p={1} x={long ? 20 : 20} y={panelH - 18} long={long} color={tint} anchor="left" />}
        </div>
      ))}
      {!slider && (
        <div style={{ position: "absolute", left: long ? padX + panelW + gap / 2 - 38 : frameW / 2 - 38, top: long ? top + panelH / 2 - 38 : top + panelH + gap / 2 - 38, width: 76, height: 76, borderRadius: 38, background: COLORS.ink, color: COLORS.parchmentLight, border: `3px solid ${COLORS.gold}`, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 30, transform: `scale(${vsP})`, opacity: vsP }}>
          VS
        </div>
      )}
    </div>
  );
};

const Photo: React.FC<{ src: string; w: number; h: number }> = ({ src, w, h }) => (
  <Img src={src} style={{ width: w, height: h, objectFit: "cover", filter: "sepia(0.2) contrast(1.05) saturate(0.9)" }} />
);

const Title: React.FC<{ text: string; long: boolean; frameW: number }> = ({ text, long, frameW }) => (
  <div style={{ position: "absolute", top: long ? 44 : 130, left: 0, width: frameW, textAlign: "center", fontFamily: FONT_HAND, fontSize: long ? 62 : 56, color: COLORS.ink }}>{text}</div>
);

const PlainFace: React.FC<{ side: CompareSide; long: boolean; tint: string }> = ({ side, long, tint }) => (
  <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 6%", textAlign: "center" }}>
    <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: long ? 92 : 78, lineHeight: 1.08, color: tint }}>{side.label}</div>
    <div style={{ width: 120, height: 4, background: COLORS.gold, margin: "26px 0" }} />
    {side.caption && <div style={{ fontFamily: FONT_HAND, fontSize: long ? 50 : 46, color: COLORS.ink, lineHeight: 1.1 }}>{side.caption}</div>}
  </div>
);

const Tag: React.FC<{ text: string; sub?: string; p: number; x: number; y: number; long: boolean; color: string; anchor: "left" | "right" }> = ({ text, sub, p, x, y, long, color, anchor }) => (
  <div style={{ position: "absolute", [anchor]: x, bottom: undefined, top: y, transform: "translateY(-100%)", opacity: clamp(p), maxWidth: "46%" }}>
    <div style={{ background: "rgba(20,14,10,0.78)", borderLeft: `6px solid ${color === COLORS.inkSoft ? COLORS.gold : color}`, padding: "10px 22px", textAlign: anchor }}>
      <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: long ? 44 : 40, color: COLORS.parchmentLight, lineHeight: 1.1 }}>{text}</div>
      {sub && <div style={{ fontFamily: FONT_SERIF, fontSize: long ? 28 : 26, color: COLORS.parchmentDark, marginTop: 4 }}>{sub}</div>}
    </div>
  </div>
);
