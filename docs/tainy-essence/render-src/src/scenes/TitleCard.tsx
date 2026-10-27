import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, FONT_DISPLAY, FONT_HAND } from "../theme";
import { SceneProps } from "./sceneProps";
import { revealProgress } from "../utils/time";
import { Reveal } from "../components/Reveal";

export const TitleCard: React.FC<SceneProps> = ({ data, fps, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const pTitle = revealProgress(frame, 4, fps, 0.9);
  const pSub = revealProgress(frame, fps * 0.9, fps, 0.8);
  const pLine = revealProgress(frame, fps * 0.3, fps, 0.6);

  return (
    <div
      style={{
        width: frameW,
        height: frameH,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 8%",
      }}
    >
      <Reveal progress={pTitle} mode="fade">
        <div
          style={{
            fontFamily: FONT_DISPLAY,
            fontWeight: 900,
            fontSize: frameW > frameH ? 92 : 76,
            color: COLORS.ink,
            textAlign: "center",
            lineHeight: 1.1,
            textShadow: "0 2px 0 rgba(176,141,87,0.3)",
          }}
        >
          {data.title}
        </div>
      </Reveal>
      <svg width={Math.min(frameW * 0.5, 700)} height={30} style={{ marginTop: 20 }}>
        <path
          d={`M 10 15 Q ${Math.min(frameW * 0.5, 700) * pLine * 0.5} ${pLine > 0.5 ? 5 : 20} ${Math.min(frameW * 0.5, 700) * pLine - 10} 15`}
          stroke={COLORS.red}
          strokeWidth={4}
          fill="none"
          strokeLinecap="round"
          opacity={pLine}
        />
      </svg>
      {data.subtitle && (
        <Reveal progress={pSub} mode="fade" style={{ marginTop: 18 }}>
          <div
            style={{
              fontFamily: FONT_HAND,
              fontSize: frameW > frameH ? 44 : 38,
              color: COLORS.inkSoft,
              textAlign: "center",
            }}
          >
            {data.subtitle}
          </div>
        </Reveal>
      )}
    </div>
  );
};
