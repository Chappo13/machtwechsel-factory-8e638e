import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { revealProgress, easeOut } from "../utils/time";

const NBSP = " ";

export const fmtMeters = (v: number): string => {
  const r = Math.round(v * 10) / 10;
  return `${String(r).replace(".", ",")}${NBSP}м`;
};

export type SubjectKind = "depth" | "pyramid" | "building" | "tower";
export type RefKind = "person" | "building" | "bus" | "pole";

export const subjectKind = (label: string): SubjectKind => {
  const l = (label || "").toLowerCase();
  if (/глубин|слой|слои|под землё|под землe|подзем|яма|ям[ыу]|шахт|колодц|котлован|раскоп|грунт|пласт/.test(l)) return "depth";
  if (/пирамид/.test(l)) return "pyramid";
  if (/здани|дом|храм|крепост|стен|дворец|замок|собор/.test(l)) return "building";
  return "tower";
};

export const refKind = (label: string): RefKind => {
  const l = (label || "").toLowerCase();
  if (/человек|люд|рост|взросл|ребёнок|ребенок|мужчин|женщин|баскетбол/.test(l)) return "person";
  if (/автобус|автомоб|машин|грузовик|фур|поезд|вагон|трамва/.test(l)) return "bus";
  if (/этаж|дом|здани|небоскр|башн/.test(l)) return "building";
  return "pole";
};

/** Нормированный силуэт человека: высота 1, центр по x = 0, ноги на y = 1. */
export const HUMAN_BODY =
  "M -0.035,0.128 C -0.095,0.145 -0.135,0.175 -0.142,0.255 L -0.15,0.43 Q -0.152,0.462 -0.124,0.462 Q -0.098,0.462 -0.098,0.432 L -0.094,0.30 L -0.088,0.50 L -0.084,0.965 Q -0.084,1 -0.058,1 L -0.012,1 L -0.008,0.58 L 0.008,0.58 L 0.012,1 L 0.058,1 Q 0.084,1 0.084,0.965 L 0.088,0.50 L 0.094,0.30 L 0.098,0.432 Q 0.098,0.462 0.124,0.462 Q 0.152,0.462 0.15,0.43 L 0.142,0.255 C 0.135,0.175 0.095,0.145 0.035,0.128 Z";

const Human: React.FC<{ cx: number; base: number; h: number }> = ({ cx, base, h }) => (
  <g transform={`translate(${cx} ${base - h}) scale(${h})`}>
    <path d={HUMAN_BODY} fill={COLORS.ink} stroke={COLORS.ink} strokeWidth={0.004} strokeLinejoin="round" />
    <rect x={-0.02} y={0.1} width={0.04} height={0.04} fill={COLORS.ink} />
    <ellipse cx={0} cy={0.065} rx={0.047} ry={0.056} fill={COLORS.ink} />
  </g>
);

const Building: React.FC<{ cx: number; base: number; h: number; w: number; floors?: number; fill?: string }> = ({ cx, base, h, w, floors, fill }) => {
  const n = floors ?? Math.max(2, Math.round(h / 60));
  const rows = Array.from({ length: n });
  return (
    <g>
      <rect x={cx - w / 2} y={base - h} width={w} height={h} fill={fill ?? "rgba(43,33,24,0.07)"} stroke={COLORS.ink} strokeWidth={2.5} />
      <rect x={cx - w / 2 - 6} y={base - h - 8} width={w + 12} height={8} fill={COLORS.ink} />
      {rows.map((_, i) => {
        const y = base - h + (h / n) * (i + 0.28);
        const wh = (h / n) * 0.44;
        return [0, 1, 2].map((j) => (
          <rect key={`${i}-${j}`} x={cx - w / 2 + w * (0.14 + j * 0.3)} y={y} width={w * 0.16} height={wh} fill="rgba(43,33,24,0.55)" />
        ));
      })}
    </g>
  );
};

const Bus: React.FC<{ cx: number; base: number; len: number }> = ({ cx, base, len }) => {
  const h = len * 0.26;
  const x0 = cx - len / 2;
  return (
    <g>
      <rect x={x0} y={base - h - len * 0.04} width={len} height={h} rx={len * 0.04} fill="rgba(43,33,24,0.08)" stroke={COLORS.ink} strokeWidth={2.5} />
      {Array.from({ length: 6 }).map((_, i) => (
        <rect key={i} x={x0 + len * (0.07 + i * 0.145)} y={base - h - len * 0.01} width={len * 0.1} height={h * 0.38} fill="rgba(43,33,24,0.55)" />
      ))}
      <circle cx={x0 + len * 0.22} cy={base - len * 0.04} r={len * 0.05} fill={COLORS.ink} />
      <circle cx={x0 + len * 0.78} cy={base - len * 0.04} r={len * 0.05} fill={COLORS.ink} />
    </g>
  );
};

const Pole: React.FC<{ cx: number; base: number; h: number }> = ({ cx, base, h }) => (
  <g>
    <line x1={cx} y1={base} x2={cx} y2={base - h} stroke={COLORS.ink} strokeWidth={4} strokeLinecap="round" />
    {Array.from({ length: 5 }).map((_, i) => (
      <line key={i} x1={cx - 10} y1={base - (h * (i + 1)) / 5} x2={cx + 10} y2={base - (h * (i + 1)) / 5} stroke={COLORS.ink} strokeWidth={2} />
    ))}
    <polygon points={`${cx},${base - h} ${cx + h * 0.22},${base - h + h * 0.07} ${cx},${base - h + h * 0.14}`} fill={COLORS.red} />
  </g>
);

const Obelisk: React.FC<{ cx: number; base: number; h: number; w: number }> = ({ cx, base, h, w }) => (
  <g>
    <polygon
      points={`${cx - w / 2},${base} ${cx - w * 0.32},${base - h * 0.88} ${cx},${base - h} ${cx + w * 0.32},${base - h * 0.88} ${cx + w / 2},${base}`}
      fill="rgba(139,30,30,0.1)"
      stroke={COLORS.ink}
      strokeWidth={2.5}
      strokeLinejoin="round"
    />
    <line x1={cx - w * 0.32} y1={base - h * 0.88} x2={cx + w * 0.32} y2={base - h * 0.88} stroke={COLORS.ink} strokeWidth={1.5} opacity={0.5} />
    {[0.25, 0.5, 0.75].map((f) => (
      <line key={f} x1={cx - w * (0.5 - 0.18 * f)} y1={base - h * 0.88 * f} x2={cx + w * (0.5 - 0.18 * f)} y2={base - h * 0.88 * f} stroke={COLORS.ink} strokeWidth={1} opacity={0.25} />
    ))}
  </g>
);

const Pyramid: React.FC<{ cx: number; base: number; h: number; w: number }> = ({ cx, base, h, w }) => (
  <g>
    <polygon points={`${cx - w / 2},${base} ${cx},${base - h} ${cx + w / 2},${base}`} fill="rgba(176,141,87,0.25)" stroke={COLORS.ink} strokeWidth={2.5} strokeLinejoin="round" />
    <polygon points={`${cx},${base - h} ${cx + w / 2},${base} ${cx + w * 0.1},${base}`} fill="rgba(43,33,24,0.14)" />
    {[0.2, 0.4, 0.6, 0.8].map((f) => (
      <line key={f} x1={cx - (w / 2) * (1 - f)} y1={base - h * f} x2={cx + (w / 2) * (1 - f)} y2={base - h * f} stroke={COLORS.ink} strokeWidth={1} opacity={0.3} />
    ))}
  </g>
);

/** Подпись без переноса: имя (подгоняется по ширине) и размер крупно. */
const Caption: React.FC<{ cx: number; top: number; maxW: number; label: string; size: number; opacity: number; accent?: boolean }> = ({ cx, top, maxW, label, size, opacity, accent }) => {
  const nameFont = Math.max(24, Math.min(40, (maxW / Math.max(8, label.length)) * 2.1));
  return (
    <div style={{ position: "absolute", left: cx - maxW / 2, top, width: maxW, textAlign: "center", opacity, whiteSpace: "nowrap" }}>
      {label && <div style={{ fontFamily: FONT_HAND, fontSize: nameFont, lineHeight: 1.05, color: accent ? COLORS.ink : COLORS.inkSoft }}>{label}</div>}
      <div style={{ fontFamily: FONT_SERIF, fontWeight: 800, fontSize: 54, lineHeight: 1.1, color: accent ? COLORS.red : COLORS.ink }}>{fmtMeters(size)}</div>
    </div>
  );
};

export const Scale: React.FC<SceneProps> = ({ data, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const subject = data.subject || { label: "Объект", size_m: 100 };
  const reference = data.reference || { label: "Человек", size_m: 1.8 };
  const sKind = subjectKind(subject.label);
  const rKind = refKind(reference.label);
  const isDepth = sKind === "depth";
  const wide = format === "long";

  const pSub = revealProgress(frame, fps * 0.3, fps, 1.1);
  const pRef = revealProgress(frame, fps * 1.1, fps, 0.8);
  const pNum = data.number ? revealProgress(frame, fps * 2.0, fps, 0.6) : 0;

  // верхняя зона под заголовок-число: рисунок никогда не заходит выше этой линии
  const unit = frameH / 1080;
  const topZone = (data.number ? 300 : 90) * unit;
  const captionH = 130 * unit;
  const bottomLimit = frameH - 70 * unit;

  const cxSubject = frameW * (wide ? 0.34 : 0.32);
  const cxRef = frameW * (wide ? 0.72 : 0.76);
  const subjW = frameW * (wide ? 0.2 : 0.3);

  const sM = subject.size_m;
  const rM = reference.size_m;

  let pxPerM: number;
  let surfaceY: number; // линия земли, на которой стоит эталон
  if (isDepth) {
    // эталон стоит над землёй, глубина уходит вниз; подписи рядом, не под рисунком
    const avail = bottomLimit - captionH - topZone - 6 * unit;
    pxPerM = avail / (sM + Math.max(rM, (frameH * 0.045) / Math.max(1, avail / (sM + rM))));
    surfaceY = topZone + Math.max(rM * pxPerM, frameH * 0.045) + 6 * unit;
  } else {
    const baseY = bottomLimit - captionH;
    const avail = baseY - topZone;
    pxPerM = avail / Math.max(sM, rM);
    surfaceY = baseY;
  }

  const subjH = sM * pxPerM * easeOut(pSub);
  const refHTrue = rM * pxPerM;
  const refH = Math.max(refHTrue, frameH * 0.045) * easeOut(pRef);
  const fullDepth = sM * pxPerM;

  const lineL = frameW * 0.08;
  const lineR = frameW * 0.92;
  const secL = cxSubject - subjW / 2;
  const secR = cxSubject + subjW / 2;

  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }}>
        <defs>
          <pattern id="soilHatch" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
            <line x1="0" y1="0" x2="0" y2="14" stroke={COLORS.ink} strokeWidth="1.2" opacity="0.28" />
          </pattern>
        </defs>

        {isDepth ? (
          <>
            {/* линия поверхности */}
            <line x1={lineL} y1={surfaceY} x2={secL} y2={surfaceY} stroke={COLORS.inkSoft} strokeWidth={3} />
            <line x1={secR} y1={surfaceY} x2={lineR} y2={surfaceY} stroke={COLORS.inkSoft} strokeWidth={3} />
            <g opacity={pSub}>
              <rect x={secL} y={surfaceY} width={subjW} height={Math.max(2, subjH)} fill="rgba(156,122,78,0.30)" />
              <rect x={secL} y={surfaceY} width={subjW} height={Math.max(2, subjH)} fill="url(#soilHatch)" />
              {[0.3, 0.55, 0.8].map((f) => (
                <path key={f} d={`M ${secL} ${surfaceY + subjH * f} q ${subjW * 0.25} -10 ${subjW * 0.5} 0 t ${subjW * 0.5} 0`} fill="none" stroke={COLORS.ink} strokeWidth={1.2} opacity={0.35} />
              ))}
              <line x1={secL} y1={surfaceY} x2={secL} y2={surfaceY + subjH} stroke={COLORS.ink} strokeWidth={3} />
              <line x1={secR} y1={surfaceY} x2={secR} y2={surfaceY + subjH} stroke={COLORS.ink} strokeWidth={3} />
              <line x1={secL} y1={surfaceY + subjH} x2={secR} y2={surfaceY + subjH} stroke={COLORS.ink} strokeWidth={4} />
              {/* размерная стрелка глубины */}
              {subjH > 30 && (
                <g stroke={COLORS.red} strokeWidth={3} fill={COLORS.red}>
                  <line x1={secR + 26} y1={surfaceY + 4} x2={secR + 26} y2={surfaceY + subjH - 4} />
                  <polygon points={`${secR + 26},${surfaceY + 2} ${secR + 18},${surfaceY + 20} ${secR + 34},${surfaceY + 20}`} stroke="none" />
                  <polygon points={`${secR + 26},${surfaceY + subjH - 2} ${secR + 18},${surfaceY + subjH - 20} ${secR + 34},${surfaceY + subjH - 20}`} stroke="none" />
                </g>
              )}
            </g>
          </>
        ) : (
          <line x1={lineL} y1={surfaceY} x2={lineR} y2={surfaceY} stroke={COLORS.inkSoft} strokeWidth={3} />
        )}

        {!isDepth && subjH > 2 && (
          <g opacity={pSub}>
            {sKind === "pyramid" && <Pyramid cx={cxSubject} base={surfaceY} h={subjH} w={Math.min(subjH * 1.5, subjW * 1.4)} />}
            {sKind === "building" && <Building cx={cxSubject} base={surfaceY} h={subjH} w={Math.min(subjH * 0.8, subjW * 1.1)} />}
            {sKind === "tower" && <Obelisk cx={cxSubject} base={surfaceY} h={subjH} w={Math.min(subjH * 0.22, subjW * 0.6)} />}
          </g>
        )}

        {refH > 2 && (
          <g opacity={pRef}>
            {rKind === "person" && <Human cx={cxRef} base={surfaceY} h={refH} />}
            {rKind === "building" && <Building cx={cxRef} base={surfaceY} h={refH} w={Math.min(refH * 0.8, frameW * 0.16)} floors={Math.max(1, Math.round(rM / 3))} />}
            {rKind === "bus" && <Bus cx={cxRef} base={surfaceY} len={Math.min(refH, frameW * 0.3)} />}
            {rKind === "pole" && <Pole cx={cxRef} base={surfaceY} h={refH} />}
          </g>
        )}
      </svg>

      {/* подписи: имя + размер без переносов */}
      {isDepth ? (
        <>
          <Caption cx={cxSubject} top={Math.min(surfaceY + fullDepth + 14 * unit, frameH - 130 * unit)} maxW={Math.max(subjW + 80, 360)} label={data.hide_words ? "" : subject.label} size={sM} opacity={pSub} accent />
          <Caption cx={cxRef} top={surfaceY + 18 * unit} maxW={frameW * 0.28} label={data.hide_words ? "" : reference.label} size={rM} opacity={pRef} />
        </>
      ) : (
        <>
          <Caption cx={cxSubject} top={surfaceY + 16 * unit} maxW={frameW * 0.3} label={data.hide_words ? "" : subject.label} size={sM} opacity={pSub} accent />
          <Caption cx={cxRef} top={surfaceY + 16 * unit} maxW={frameW * 0.3} label={data.hide_words ? "" : reference.label} size={rM} opacity={pRef} />
        </>
      )}

      {data.number && pNum > 0 && (
        <div
          style={{
            position: "absolute",
            top: 50 * unit,
            left: 0,
            right: 0,
            textAlign: "center",
            opacity: pNum,
            transform: `translateY(${(1 - easeOut(pNum)) * -20}px)`,
            whiteSpace: "nowrap",
          }}
        >
          <div style={{ fontFamily: FONT_SERIF, fontWeight: 800, fontSize: 110, lineHeight: 1.05, color: COLORS.red }}>
            {data.number.value}
            {NBSP}
            {data.number.unit}
          </div>
          <div style={{ fontFamily: FONT_HAND, fontSize: 42, color: COLORS.ink }}>{data.hide_words ? "" : data.number.label}</div>
        </div>
      )}
    </div>
  );
};
