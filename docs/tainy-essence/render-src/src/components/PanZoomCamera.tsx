import React from "react";
import { useCurrentFrame } from "remotion";
import { easeInOut } from "../utils/time";

export type CamKey = { frame: number; cx: number; cy: number; scale: number };

// Камера едет по "широкой" доске/странице дневника от блока к блоку.
// keyframes — отсортированные по frame опорные точки (центр + масштаб).
export const PanZoomCamera: React.FC<{
  children: React.ReactNode;
  keyframes: CamKey[];
  frameW: number;
  frameH: number;
}> = ({ children, keyframes, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const kfs = keyframes.length > 0 ? keyframes : [{ frame: 0, cx: frameW / 2, cy: frameH / 2, scale: 1 }];

  let a = kfs[0];
  let b = kfs[kfs.length - 1];
  for (let i = 0; i < kfs.length - 1; i++) {
    if (frame >= kfs[i].frame && frame <= kfs[i + 1].frame) {
      a = kfs[i];
      b = kfs[i + 1];
      break;
    }
  }
  if (frame <= kfs[0].frame) {
    a = kfs[0];
    b = kfs[0];
  }
  if (frame >= kfs[kfs.length - 1].frame) {
    a = kfs[kfs.length - 1];
    b = kfs[kfs.length - 1];
  }

  const span = Math.max(1, b.frame - a.frame);
  const raw = span === 0 ? 1 : (frame - a.frame) / span;
  const p = easeInOut(Math.min(1, Math.max(0, raw)));

  const cx = a.cx + (b.cx - a.cx) * p;
  const cy = a.cy + (b.cy - a.cy) * p;
  const scale = a.scale + (b.scale - a.scale) * p;

  const tx = frameW / 2 - cx * scale;
  const ty = frameH / 2 - cy * scale;

  return (
    <div style={{ width: frameW, height: frameH, overflow: "hidden", position: "relative" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          transformOrigin: "0 0",
        }}
      >
        {children}
      </div>
    </div>
  );
};
