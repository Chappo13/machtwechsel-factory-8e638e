import React, { useMemo } from "react";
import { staticFile, useCurrentFrame } from "remotion";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { revealProgress, easeOut } from "../utils/time";
import { boardTiming } from "../utils/revealTiming.mjs";
import { fitText } from "../utils/autoFitText.mjs";
import { PanZoomCamera, CamKey } from "../components/PanZoomCamera";

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

// Карточка всегда рассчитана под СВОЙ текст: короткая фраза -> маленькая
// квадратная карточка с крупным центрированным текстом на всю карточку;
// заголовок+деталь -> заголовок мелкой "этикеткой" сверху + крупный
// центрированный текст детали. Пустых областей по 80% карточки быть не должно
// (жалоба по пилоту) — поэтому размер карточки считается ПОСЛЕ fitText, а не наоборот.
function layoutCard(title: string, text: string | undefined, format: "long" | "short", sizeScale: number) {
  const minFont = Math.round((format === "long" ? 56 : 64) * Math.min(1, sizeScale));
  const maxFont = Math.round(96 * sizeScale);
  const minW = Math.round(260 * sizeScale);
  const maxW = Math.round(560 * sizeScale);
  const minH = Math.round(220 * sizeScale);
  const maxH = Math.round(420 * sizeScale);
  const padX = 36;
  const padY = 32;

  const hasDetail = Boolean(text && text.trim());
  const mainText = hasDetail ? text! : title;
  const labelText = hasDetail ? title : undefined;
  const labelFont = Math.round(26 * sizeScale);
  const labelBlock = labelText ? labelFont * 1.5 + 14 : 0;

  // Пробуем размеры карточки от компактного к максимальному, пока текст не
  // влезет при минимальном допустимом шрифте — так фраза в три слова получает
  // маленькую квадратную карточку, а не распластанный пустой прямоугольник.
  let chosen = null as null | { w: number; h: number; fit: ReturnType<typeof fitText> };
  for (let w = minW; w <= maxW; w += 24) {
    const availW = w - padX * 2;
    const fit = fitText({ text: mainText, maxWidth: availW, maxHeight: maxH - padY * 2 - labelBlock, minFont, maxFont, maxLines: 3 });
    // truncated=true значит "даже на этой ширине не влезло без обрезки" — такую
    // ширину нельзя принимать как маленькую квадратную карточку, иначе текст
    // обрежется многоточием там, где более широкая карточка вместила бы его целиком.
    if (fit.truncated) continue;
    const neededH = labelBlock + fit.lines.length * fit.lineHeight + padY * 2 + 10;
    const h = Math.max(minH, Math.min(maxH, Math.round(neededH)));
    chosen = { w, h, fit };
    break;
  }
  if (!chosen) {
    // Ничего не влезло целиком даже на максимальной ширине — берём максимум,
    // это уже честный "худший случай" (длинный текст), а не ошибка подбора.
    const fit = fitText({ text: mainText, maxWidth: maxW - padX * 2, maxHeight: maxH - padY * 2 - labelBlock, minFont, maxFont, maxLines: 3 });
    chosen = { w: maxW, h: maxH, fit };
  }

  const isQuestion = mainText.trim().endsWith("?");
  return { w: chosen.w, h: chosen.h, fit: chosen.fit, labelText, labelFont, isQuestion, padX, padY, labelBlock };
}

export const Board: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH, durationInFrames }) => {
  const frame = useCurrentFrame();
  const cards = data.cards || [];
  const links = data.links || [];

  // мало карточек — делаем их крупнее, чтобы доска не выглядела пустой запиской в углу
  const sizeScale = cards.length <= 2 ? 1.35 : cards.length === 3 ? 1.2 : cards.length <= 4 ? 1.05 : 1;

  const cardLayouts = useMemo(() => {
    const map: Record<string, ReturnType<typeof layoutCard>> = {};
    for (const c of cards) map[c.id] = layoutCard(c.title, c.textId ? undefined : c.text, format, sizeScale);
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, format, sizeScale]);

  // Grid-ячейка — максимум по всем карточкам, чтобы раскладка не перекрывалась;
  // карточки поменьше центрируются внутри своей ячейки, а не лепятся в угол.
  const cellW = Math.max(260, ...cards.map((c) => cardLayouts[c.id].w));
  const cellH = Math.max(220, ...cards.map((c) => cardLayouts[c.id].h));
  const cols = Math.max(1, Math.min(cards.length, format === "long" ? 4 : 2));
  const rows = Math.ceil(cards.length / cols);
  const gapX = 70;
  const gapY = 70;
  const gridW = cols * cellW + (cols - 1) * gapX + 160;
  const gridH = rows * cellH + (rows - 1) * gapY + 220;
  const canvasW = Math.max(frameW, gridW);
  const canvasH = Math.max(frameH, gridH);

  const actualGridW = cols * cellW + (cols - 1) * gapX;
  const actualGridH = rows * cellH + (rows - 1) * gapY;
  const baseX = canvasW === frameW ? Math.max(40, (frameW - actualGridW) / 2) : 100;
  const baseY = canvasH === frameH ? Math.max(100, (frameH - actualGridH) / 2) : 140;

  const posMap = useMemo(() => {
    const map: Record<string, { x: number; y: number; cellCx: number; cellCy: number }> = {};
    cards.forEach((c, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const jx = ((hash(c.id) % 13) - 6) * 2;
      const jy = ((hash(c.id + "y") % 11) - 5) * 2;
      const cellX = baseX + col * (cellW + gapX);
      const cellY = baseY + row * (cellH + gapY);
      const { w, h } = cardLayouts[c.id];
      map[c.id] = {
        x: cellX + (cellW - w) / 2 + jx,
        y: cellY + (cellH - h) / 2 + jy,
        cellCx: cellX + cellW / 2,
        cellCy: cellY + cellH / 2,
      };
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, cols, baseX, baseY, cellW, cellH, cardLayouts]);

  const timing = useMemo(() => boardTiming(data, beats, sceneStart, fps, durationInFrames), [data, beats, sceneStart, fps, durationInFrames]);
  const revealMap = timing.card;

  const camKeys: CamKey[] = useMemo(() => {
    const fitScale = Math.min(1, frameW / canvasW, frameH / canvasH);
    const pushScale = Math.min(1.45, Math.max(1, Math.min(frameW / cellW, frameH / cellH) * 0.62));
    const keys: CamKey[] = [
      { frame: 0, cx: posMap[cards[0]?.id]?.cellCx ?? canvasW / 2, cy: posMap[cards[0]?.id]?.cellCy ?? canvasH / 2, scale: 1 },
    ];
    cards.forEach((c) => {
      const p = posMap[c.id];
      const revealFrame = Math.max(0, revealMap[c.id] ?? 0);
      // камера "наезжает" на каждую новую карточку в момент появления
      keys.push({ frame: revealFrame, cx: p.cellCx, cy: p.cellCy, scale: pushScale });
    });
    // в конце — отъезд, видна вся доска целиком
    keys.push({ frame: timing.pullBack, cx: canvasW / 2, cy: canvasH / 2, scale: fitScale });
    keys.sort((a, b) => a.frame - b.frame);
    return keys;
  }, [cards, posMap, revealMap, canvasW, canvasH, frameW, frameH, cellW, cellH, durationInFrames, fps, timing.pullBack]);

  const needsCamera = canvasW > frameW + 2 || canvasH > frameH + 2;

  const stampP = data.stamp ? revealProgress(frame, timing.stamp, fps, 0.4) : 0;
  const stampEase = easeOut(stampP);

  const content = (
    <div
      style={{
        position: "relative",
        width: canvasW,
        height: canvasH,
        backgroundImage: `url(${staticFile("textures/cork-tile.png")})`,
        backgroundSize: "36px 36px",
        backgroundRepeat: "repeat",
        backgroundColor: "rgba(156,122,78,0.08)",
      }}
    >
      <svg width={canvasW} height={canvasH} style={{ position: "absolute", inset: 0 }}>
        {links.map((l) => {
          const from = posMap[l.from];
          const to = posMap[l.to];
          if (!from || !to) return null;
          const p = revealProgress(frame, timing.link[l.id], fps, 0.6);
          if (p <= 0) return null;
          const x1 = from.cellCx;
          const y1 = from.cellCy;
          const x2 = to.cellCx;
          const y2 = to.cellCy;
          const mx = x1 + (x2 - x1) * p;
          const my = y1 + (y2 - y1) * p;
          return (
            <g key={l.id}>
              <line x1={x1} y1={y1} x2={mx} y2={my} stroke={COLORS.red} strokeWidth={2.6} opacity={0.85} />
              {l.label && p > 0.9 && (
                <text
                  x={(x1 + x2) / 2}
                  y={(y1 + y2) / 2 - 10}
                  textAnchor="middle"
                  fontFamily={FONT_HAND}
                  fontSize={30}
                  fill={COLORS.red}
                  style={{ paintOrder: "stroke", stroke: "rgba(233,220,185,0.85)", strokeWidth: 5 }}
                >
                  {l.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {cards.map((c, i) => {
        const p = revealProgress(frame, revealMap[c.id] ?? 0, fps, 0.6);
        if (p <= 0) return null;
        const pos = posMap[c.id];
        const layout = cardLayouts[c.id];
        const rot = ((hash(c.id) % 7) - 3) * 1.4;
        const scale = 0.7 + 0.3 * easeOut(p);
        const textP = c.textId ? revealProgress(frame, timing.text[c.textId], fps, 0.6) : 1;
        const underlineP = revealProgress(frame, (revealMap[c.id] ?? 0) + Math.round(fps * 0.3), fps, 0.5);
        const mainLines = layout.fit.lines;
        return (
          <div
            key={c.id}
            style={{
              position: "absolute",
              left: pos.x,
              top: pos.y,
              width: layout.w,
              height: layout.h,
              transform: `rotate(${rot}deg) scale(${scale})`,
              opacity: p,
              background: "#f1e6c8",
              boxShadow: "0 8px 0 rgba(20,12,4,0.35)",
              border: "1px solid rgba(43,33,24,0.25)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: `${layout.padY}px ${layout.padX}px`,
              boxSizing: "border-box",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: -14,
                left: layout.w / 2 - 12,
                width: 24,
                height: 24,
                borderRadius: "50%",
                background: COLORS.red,
                boxShadow: "0 2px 0 rgba(0,0,0,0.45)",
              }}
            />
            {layout.labelText && (
              <div
                style={{
                  fontFamily: FONT_SERIF,
                  fontWeight: 700,
                  fontSize: layout.labelFont,
                  color: COLORS.gold,
                  textTransform: "uppercase",
                  letterSpacing: 1.5,
                  marginBottom: 10,
                  textAlign: "center",
                }}
              >
                {c.title}
              </div>
            )}
            <div
              style={{
                fontFamily: FONT_HAND,
                fontWeight: layout.labelText ? 400 : 700,
                fontSize: layout.fit.fontSize,
                lineHeight: `${layout.fit.lineHeight}px`,
                color: layout.isQuestion ? COLORS.red : COLORS.ink,
                textAlign: "center",
                opacity: textP,
                width: "100%",
              }}
            >
              {mainLines.map((line, li) => (
                <div key={li}>{line}</div>
              ))}
            </div>
            {layout.isQuestion && (
              <svg
                width={layout.w * 0.5}
                height={14}
                style={{ position: "absolute", bottom: layout.padY * 0.55, left: layout.w * 0.25, overflow: "visible" }}
              >
                <path
                  d={`M 2 7 Q ${layout.w * 0.25 * underlineP} ${underlineP > 0.5 ? 0 : 12} ${layout.w * 0.5 * underlineP - 2} 7`}
                  stroke={COLORS.red}
                  strokeWidth={3.5}
                  fill="none"
                  strokeLinecap="round"
                  opacity={underlineP}
                />
              </svg>
            )}
          </div>
        );
      })}

      {data.stamp && stampP > 0 && (
        <div
          style={{
            position: "absolute",
            right: canvasW * 0.18,
            top: canvasH * 0.16,
            transform: `rotate(-18deg) scale(${0.6 + 0.4 * stampEase})`,
            opacity: Math.min(1, stampP * 1.4),
            border: `6px solid ${COLORS.red}`,
            color: COLORS.red,
            fontFamily: FONT_SERIF,
            fontWeight: 900,
            fontSize: 66,
            padding: "10px 26px",
            letterSpacing: 4,
            textTransform: "uppercase",
            mixBlendMode: "multiply",
          }}
        >
          {data.stamp}
        </div>
      )}
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
