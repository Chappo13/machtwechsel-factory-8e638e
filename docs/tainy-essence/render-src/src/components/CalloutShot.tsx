import React from "react";
import { Img, useCurrentFrame, useVideoConfig } from "remotion";
import { Callout } from "../types";
import { clamp, easeInOut } from "../utils/time";

// Красный круг, который «рисуется» (stroke-dashoffset), стрелка и плавный наезд на деталь реального фото.
// Круг и стрелка живут в координатах картинки внутри той же трансформации, что и пиксели, поэтому
// всегда сидят ровно на цели. Толщина линии постоянна на экране (делится на текущий scale).
export const CALLOUT_RED = "#EB1414";
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

export const CalloutShot: React.FC<{
  src: string;
  mediaW: number;
  mediaH: number;
  frameW: number;
  frameH: number;
  durationInFrames: number;
  focus: { x: number; y: number };
  callout: Callout;
}> = ({ src, mediaW, mediaH, frameW, frameH, durationInFrames, focus, callout: c }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  // базовая камера: cover, лёгкий Ken Burns по длине плана
  const cover = Math.max(frameW / mediaW, frameH / mediaH);
  const pBase = clamp(frame / Math.max(1, durationInFrames - 1));
  const s0 = cover * (1 + 0.05 * pBase);
  const clampCenter = (cx: number, cy: number, s: number) => ({
    cx: clamp(cx, frameW / 2 / s, mediaW - frameW / 2 / s),
    cy: clamp(cy, frameH / 2 / s, mediaH - frameH / 2 / s),
  });
  const base = clampCenter(focus.x * mediaW, focus.y * mediaH, s0);

  // целевая камера: деталь целиком в кадре с полями, ниже шапки
  const bx = c.zoomBox.x * mediaW, by = c.zoomBox.y * mediaH, bw = c.zoomBox.w * mediaW, bh = c.zoomBox.h * mediaH;
  // конечный масштаб: деталь в кадре с полями, но не меньше cover*1.08 (картинка всегда закрывает кадр, без полей)
  const s1 = Math.max(cover * 1.08, Math.min(c.zoomMax ?? 3.2, Math.min((frameW * 0.84) / bw, (frameH * 0.6) / bh)));
  const tgt = clampCenter(bx + bw / 2, by + bh / 2, s1);
  const zp = easeInOut(clamp((t - c.zoomAt) / (c.zoomDur ?? 1.5)));
  const sc = Math.exp(Math.log(s0) + (Math.log(s1) - Math.log(s0)) * zp);
  const cc = clampCenter(base.cx + (tgt.cx - base.cx) * zp, base.cy + (tgt.cy - base.cy) * zp, sc);
  const tx = frameW / 2 - cc.cx * sc;
  const ty = frameH / 2 - cc.cy * sc;

  const circP = easeOut(clamp((t - c.circleAt) / 0.9));
  const arrAt = c.arrowAt ?? c.circleAt + 0.7;
  const arrP = easeOut(clamp((t - arrAt) / 0.55));
  const fade = 1 - clamp((zp - 0.35) / 0.45); // рамка гаснет, пока камера въезжает в деталь
  const lw = 8 / sc;

  const cx = c.circle.cx * mediaW, cy = c.circle.cy * mediaH, rx = c.circle.rx * mediaW, ry = c.circle.ry * mediaW;
  const rot = c.circle.rot ?? -4;
  // стрелка: хвост на угле arrowAngleDeg от круга, остриё на краю эллипса
  const ang = ((c.arrowAngleDeg ?? 200) * Math.PI) / 180;
  const edgeX = cx + rx * Math.cos(ang) * 1.0, edgeY = cy + ry * Math.sin(ang) * 1.0;
  const gap = 14 / sc;
  const len = (c.arrowLen ?? 0.16) * mediaW;
  const tipX = edgeX + Math.cos(ang) * gap, tipY = edgeY + Math.sin(ang) * gap;
  const tailX = tipX + Math.cos(ang) * len, tailY = tipY + Math.sin(ang) * len;
  const curX = tailX + (tipX - tailX) * arrP, curY = tailY + (tipY - tailY) * arrP;
  const head = 34 / sc;
  const dirA = Math.atan2(tipY - tailY, tipX - tailX);
  const hx = (a: number) => curX - Math.cos(dirA + a) * head, hy = (a: number) => curY - Math.sin(dirA + a) * head;

  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: mediaW, height: mediaH, transform: `translate(${tx}px, ${ty}px) scale(${sc})`, transformOrigin: "0 0", filter: "sepia(0.16) saturate(0.92) contrast(1.06) brightness(0.98)" }}>
      <Img src={src} style={{ width: mediaW, height: mediaH, objectFit: "fill" }} />
      <svg width={mediaW} height={mediaH} style={{ position: "absolute", inset: 0, overflow: "visible", opacity: fade, filter: `drop-shadow(0 ${3 / sc}px ${7 / sc}px rgba(0,0,0,0.55))` }}>
        {circP > 0 && (
          <g transform={`rotate(${rot} ${cx} ${cy})`}>
            <path
              d={`M ${cx - rx} ${cy} a ${rx} ${ry} 0 1 1 ${2 * rx} 0 a ${rx} ${ry} 0 1 1 ${-2 * rx} 0`}
              pathLength={1}
              fill="none"
              stroke={CALLOUT_RED}
              strokeWidth={lw}
              strokeLinecap="round"
              strokeDasharray={1}
              strokeDashoffset={1 - circP}
            />
          </g>
        )}
        {arrP > 0 && (
          <g stroke={CALLOUT_RED} fill={CALLOUT_RED}>
            <line x1={tailX} y1={tailY} x2={curX} y2={curY} strokeWidth={lw} strokeLinecap="round" />
            {arrP > 0.8 && <polyline points={`${hx(0.5)},${hy(0.5)} ${curX},${curY} ${hx(-0.5)},${hy(-0.5)}`} fill="none" strokeWidth={lw} strokeLinecap="round" strokeLinejoin="round" />}
          </g>
        )}
      </svg>
    </div>
  );
};
