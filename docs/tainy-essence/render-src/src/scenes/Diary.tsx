import React, { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap, revealProgress } from "../utils/time";
import { Reveal } from "../components/Reveal";
import { PanZoomCamera, CamKey } from "../components/PanZoomCamera";
import { layoutDiary } from "./diaryLayout";
import { RoughShape } from "../sketches/RoughShape";
import { fitText } from "../utils/autoFitText.mjs";
import { DiaryItem } from "../types";

export const Diary: React.FC<SceneProps> = ({
  data,
  beats,
  sceneStart,
  fps,
  format,
  frameW,
  frameH,
  seed,
}) => {
  const frame = useCurrentFrame();
  const items = data.items || [];
  const topMargin = 150;

  const { boxes, posMap, canvasW, canvasH, horizontal, sizeScale } = useMemo(
    () => layoutDiary(items, format, frameW, frameH, topMargin),
    [items, format, frameW, frameH]
  );

  const ids = items.map((i) => i.id);
  const revealMap = useMemo(
    () => buildRevealMap(ids, beats, sceneStart, fps),
    [ids.join(","), beats, sceneStart, fps]
  );

  const camKeys: CamKey[] = useMemo(() => {
    const scaleFit = Math.min(1, frameW / canvasW, frameH / canvasH);
    const base: CamKey[] = [
      { frame: 0, cx: canvasW / 2, cy: canvasH / 2, scale: Math.max(scaleFit, horizontal ? frameH / canvasH : frameW / canvasW) },
    ];
    boxes.forEach((b) => {
      const f = Math.max(0, revealMap[b.id] ?? 0);
      base.push({
        frame: f,
        cx: Math.min(canvasW - frameW / 2, Math.max(frameW / 2, b.x + b.w / 2)),
        cy: Math.min(canvasH - frameH / 2, Math.max(frameH / 2, b.y + b.h / 2)),
        scale: horizontal ? frameH / canvasH : frameW / canvasW,
      });
    });
    base.sort((a, b) => a.frame - b.frame);
    return base;
  }, [boxes, revealMap, canvasW, canvasH, frameW, frameH, horizontal]);

  const needsCamera = canvasW > frameW + 2 || canvasH > frameH + 2;

  const connectors = items.filter((i) => i.kind === "arrow" || (i.kind === "underline" && !i.text));

  const content = (
    <div style={{ position: "relative", width: canvasW, height: canvasH }}>
      <div
        style={{
          position: "absolute",
          top: 40,
          left: 0,
          right: 0,
          textAlign: "center",
          fontFamily: FONT_SERIF,
          fontSize: format === "long" ? 78 : 70,
          fontWeight: 600,
          color: COLORS.ink,
          letterSpacing: 1,
        }}
      >
        {data.heading}
      </div>

      <svg
        width={canvasW}
        height={canvasH}
        style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
      >
        {connectors.map((c) => {
          const from = c.from ? posMap[c.from] : undefined;
          const to = c.to ? posMap[c.to] : undefined;
          if (!from || !to) return null;
          const p = revealProgress(frame, revealMap[c.id] ?? 0, fps, 0.5);
          if (p <= 0) return null;
          const x1 = from.x + from.w / 2;
          const y1 = from.y + from.h / 2;
          const x2 = to.x + to.w / 2;
          const y2 = to.y + to.h / 2;
          const cx = x1 + (x2 - x1) * p;
          const cy = y1 + (y2 - y1) * p;
          if (c.kind === "underline") {
            const uy = from.y + from.h + 6;
            return (
              <path
                key={c.id}
                d={`M ${from.x + 10} ${uy} Q ${from.x + from.w / 2} ${uy + 10} ${from.x + from.w * p - 10} ${uy}`}
                stroke={COLORS.red}
                strokeWidth={5}
                fill="none"
                strokeLinecap="round"
              />
            );
          }
          return (
            <g key={c.id}>
              <line x1={x1} y1={y1} x2={cx} y2={cy} stroke={COLORS.inkSoft} strokeWidth={4} strokeDasharray="2 10" strokeLinecap="round" />
              {p > 0.85 && (
                <polygon
                  points={`${cx},${cy} ${cx - 14},${cy - 7} ${cx - 14},${cy + 7}`}
                  fill={COLORS.inkSoft}
                  transform={`rotate(${(Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI}, ${cx}, ${cy})`}
                />
              )}
            </g>
          );
        })}
      </svg>

      {boxes.map((b) => {
        const p = revealProgress(frame, revealMap[b.id] ?? 0, fps, b.item.kind === "sketch" ? 1.0 : 0.7);
        if (p <= 0) return null;
        return (
          <div key={b.id} style={{ position: "absolute", left: b.x, top: b.y, width: b.w, height: b.h }}>
            <DiaryBlock item={b.item} progress={p} w={b.w} h={b.h} seed={seed + b.id.length} format={format} sizeScale={sizeScale} />
          </div>
        );
      })}
    </div>
  );

  if (needsCamera) {
    return (
      <PanZoomCamera keyframes={camKeys} frameW={frameW} frameH={frameH}>
        {content}
      </PanZoomCamera>
    );
  }
  return <div style={{ width: frameW, height: frameH, position: "relative" }}>{content}</div>;
};

const DiaryBlock: React.FC<{ item: DiaryItem; progress: number; w: number; h: number; seed: number; format: "long" | "short"; sizeScale: number }> = ({
  item,
  progress,
  w,
  h,
  seed,
  format,
  sizeScale,
}) => {
  // Жёсткий минимум рукописного текста (46px long / 56px short) — независимо от
  // количества заметок на странице текст никогда не должен выглядеть "мелким".
  const floorBody = format === "long" ? 46 : 56;
  const floorNote = format === "long" ? 42 : 50;
  const bodySize = Math.max(floorBody, Math.round((format === "long" ? 52 : 58) * sizeScale));
  const noteSize = Math.max(floorNote, Math.round((format === "long" ? 46 : 52) * sizeScale));
  const circleSize = Math.max(floorNote, Math.round((format === "long" ? 44 : 48) * sizeScale));

  if (item.kind === "sketch" && item.sketch) {
    return (
      <Reveal progress={progress} mode="scale" style={{ width: w, height: h }}>
        <RoughShape name={item.sketch} size={Math.min(w, h)} stroke={COLORS.ink} strokeWidth={4} seed={seed} />
      </Reveal>
    );
  }
  if (item.kind === "circle_text") {
    return (
      <Reveal progress={progress} mode="scale" style={{ width: w, height: h, position: "relative" }}>
        <svg width={w} height={h} style={{ position: "absolute", inset: 0 }}>
          <ellipse
            cx={w / 2}
            cy={h / 2}
            rx={w / 2 - 8}
            ry={h / 2 - 8}
            fill="none"
            stroke={COLORS.red}
            strokeWidth={5}
          />
        </svg>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            fontFamily: FONT_HAND,
            fontSize: circleSize,
            color: COLORS.ink,
            padding: 24,
          }}
        >
          {item.text}
        </div>
      </Reveal>
    );
  }
  // text / note / underline(с текстом)
  const isNote = item.kind === "note";
  // note — это маленькая "карточка"-стикер: текст должен центрироваться и
  // заполнять её, а не висеть мелким обрывком слева с пустотой вокруг (та же
  // жалоба, что и на карточки доски — решение то же самое, fitText).
  const notePad = 20;
  const noteFit = isNote
    ? fitText({
        text: item.text || "",
        maxWidth: w - notePad * 2,
        maxHeight: h - notePad * 2,
        minFont: noteSize,
        maxFont: Math.round(noteSize * 1.7),
        maxLines: 4,
      })
    : null;
  if (isNote) {
    return (
      <div
        style={{
          width: w,
          height: h,
          background: "rgba(176,141,87,0.16)",
          border: `2px dashed ${COLORS.gold}`,
          borderRadius: 8,
          padding: notePad,
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Reveal progress={progress} mode="scale">
          <div
            style={{
              fontFamily: FONT_HAND,
              fontSize: noteFit!.fontSize,
              lineHeight: `${noteFit!.lineHeight}px`,
              color: COLORS.ink,
              textAlign: "center",
            }}
          >
            {noteFit!.lines.map((line, li) => (
              <div key={li}>{line}</div>
            ))}
          </div>
        </Reveal>
      </div>
    );
  }
  return (
    <div
      style={{
        width: w,
        height: h,
        background: "transparent",
        border: "none",
        padding: 16,
        display: "flex",
        alignItems: "center",
      }}
    >
      <Reveal progress={progress} mode="wipe-x">
        <div
          style={{
            fontFamily: FONT_HAND,
            fontSize: bodySize,
            lineHeight: 1.15,
            color: item.kind === "underline" ? COLORS.red : COLORS.ink,
            textDecoration: item.kind === "underline" ? "underline" : "none",
            textDecorationColor: COLORS.red,
          }}
        >
          {item.text}
        </div>
      </Reveal>
    </div>
  );
};
