import React, { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap, revealProgress, easeOut } from "../utils/time";
import { Reveal } from "../components/Reveal";
import { DocLine } from "../types";

function splitRedacted(text: string, redact: string[] | undefined) {
  if (!redact || redact.length === 0) return [{ t: text, red: false }];
  const parts: { t: string; red: boolean }[] = [];
  let i = 0;
  const sorted = [...redact].sort((a, b) => b.length - a.length);
  while (i < text.length) {
    const hit = sorted.find((r) => r.length > 0 && text.startsWith(r, i));
    if (hit) {
      parts.push({ t: hit, red: true });
      i += hit.length;
    } else {
      let j = i;
      while (j < text.length && !sorted.some((r) => r.length > 0 && text.startsWith(r, j))) j++;
      parts.push({ t: text.slice(i, j), red: false });
      i = j;
    }
  }
  return parts;
}

export const Document: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH, durationInFrames }) => {
  const frame = useCurrentFrame();
  const lines = data.lines || [];
  const ids = lines.map((l) => l.id);
  const revealMap = useMemo(() => buildRevealMap(ids, beats, sceneStart, fps), [ids.join(","), beats, sceneStart, fps]);

  const paperW = format === "long" ? 1360 : frameW - 90;
  const paperH = format === "long" ? frameH - 140 : frameH - 260;

  const stampP = data.stamp ? revealProgress(frame, Math.round(durationInFrames * 0.6), fps, 0.4) : 0;

  return (
    <div style={{ width: frameW, height: frameH, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div
        style={{
          position: "relative",
          width: paperW,
          height: paperH,
          background: "#efe4c3",
          boxShadow: "0 10px 0 rgba(20,12,4,0.35)",
          padding: "56px 64px",
          border: `1px solid rgba(43,33,24,0.2)`,
        }}
      >
        <div style={{ fontFamily: FONT_SERIF, fontWeight: 700, fontSize: 58, color: COLORS.ink, marginBottom: 10, textAlign: "center" }}>
          {data.heading}
        </div>
        {data.date && (
          <div style={{ fontFamily: FONT_SERIF, fontSize: 30, color: COLORS.inkSoft, textAlign: "center", marginBottom: 34 }}>
            {data.date}
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {lines.map((line) => {
            const p = revealProgress(frame, revealMap[line.id] ?? 0, fps, 0.9);
            if (p <= 0) return null;
            return <DocLineRow key={line.id} line={line} progress={p} revealFrame={revealMap[line.id] ?? 0} frame={frame} fps={fps} />;
          })}
        </div>

        {data.stamp && stampP > 0 && (
          <div
            style={{
              position: "absolute",
              right: 40,
              bottom: 36,
              transform: `rotate(-14deg) scale(${0.6 + 0.4 * easeOut(stampP)})`,
              opacity: Math.min(1, stampP * 1.4),
              border: `5px solid ${COLORS.red}`,
              color: COLORS.red,
              fontFamily: FONT_SERIF,
              fontWeight: 900,
              fontSize: 44,
              padding: "8px 18px",
              letterSpacing: 2,
              textTransform: "uppercase",
              mixBlendMode: "multiply",
            }}
          >
            {data.stamp}
          </div>
        )}
      </div>
    </div>
  );
};

const DocLineRow: React.FC<{ line: DocLine; progress: number; revealFrame: number; frame: number; fps: number }> = ({
  line,
  progress,
  revealFrame,
  frame,
  fps,
}) => {
  const parts = useMemo(() => splitRedacted(line.text, line.redact), [line.text, line.redact]);
  const unredactP = revealProgress(frame, revealFrame + Math.round(fps * 0.5), fps, 0.5);

  return (
    <Reveal progress={progress} mode="wipe-x">
      <div style={{ fontFamily: FONT_SERIF, fontSize: 42, color: COLORS.ink, lineHeight: 1.4 }}>
        {parts.map((part, i) =>
          part.red ? (
            <span key={i} style={{ position: "relative", display: "inline-block" }}>
              <span style={{ visibility: "hidden" }}>{part.t}</span>
              <span style={{ position: "absolute", inset: 0 }}>{part.t}</span>
              <div
                style={{
                  position: "absolute",
                  inset: "2px 0",
                  background: "#1c1410",
                  transform: `translateX(${unredactP > 0 ? -unredactP * 102 : 0}%)`,
                  opacity: unredactP >= 1 ? 0 : 1,
                }}
              />
            </span>
          ) : (
            <span key={i}>{part.t}</span>
          )
        )}
      </div>
    </Reveal>
  );
};
