import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND } from "../theme";
import { SceneProps } from "./sceneProps";
import { revealProgress } from "../utils/time";
import { Reveal } from "../components/Reveal";

export const Quote: React.FC<SceneProps> = ({ data, fps, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const pText = revealProgress(frame, fps * 0.3, fps, 1.1);
  const pAuthor = revealProgress(frame, fps * 1.3, fps, 0.7);

  return (
    <div
      style={{
        width: frameW,
        height: frameH,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 10%",
      }}
    >
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 120, color: COLORS.gold, lineHeight: 0.4, marginBottom: 20 }}>“</div>
      <Reveal progress={pText} mode="fade">
        <div
          style={{
            fontFamily: FONT_DISPLAY,
            fontStyle: "italic",
            fontWeight: 500,
            fontSize: frameW > frameH ? 56 : 46,
            color: COLORS.ink,
            textAlign: "center",
            lineHeight: 1.35,
          }}
        >
          {data.text}
        </div>
      </Reveal>
      {data.author && (
        <Reveal progress={pAuthor} mode="fade" style={{ marginTop: 30 }}>
          <div style={{ fontFamily: FONT_HAND, fontSize: 38, color: COLORS.red }}>— {data.author}</div>
        </Reveal>
      )}
    </div>
  );
};
