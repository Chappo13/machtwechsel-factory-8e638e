import React, { useMemo } from "react";
import { AbsoluteFill } from "remotion";
import { COLORS, FONT_SERIF } from "../theme";
import { groupWords, activeGroup, activeWordIndex } from "../utils/subtitleGroups.mjs";
import { Word, Format } from "../types";

// Субтитры группами по 2-4 слова: группа появляется целиком и держится до
// следующей (не растёт по слову, не прыгает между "фразой" и "одним словом").
// Позиция и максимальная ширина ФИКСИРОВАНЫ — нижняя треть, безопасная зона
// над интерфейсом платформы (TikTok/Reels/Shorts держат свои кнопки в нижних
// ~12-15% кадра и справа ~15% — наш bottom/width этого не задевает).
export const Subtitles: React.FC<{
  words: Word[];
  t: number;
  format: Format;
}> = ({ words, t, format }) => {
  const groups = useMemo(() => groupWords(words), [words]);
  const group = activeGroup(groups, t);
  if (!group) return null;
  const wordIdx = activeWordIndex(group, t);

  const fontSize = format === "long" ? 54 : 52;
  // short: держим субтитр выше зоны подписи media-сцен (нижние ~22% кадра) и
  // выше типичного UI платформы — фиксированная позиция, не зависит от текста
  const bottom = format === "long" ? 70 : 460;
  const maxWidth = format === "long" ? 1400 : 900;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom,
          transform: "translateX(-50%)",
          width: maxWidth,
          display: "flex",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            fontFamily: FONT_SERIF,
            fontWeight: 700,
            fontSize,
            color: COLORS.parchmentLight,
            background: "rgba(43,33,24,0.78)",
            padding: "10px 34px",
            borderRadius: 10,
            letterSpacing: 0.5,
            textTransform: "uppercase",
            boxShadow: "0 3px 0 rgba(0,0,0,0.3)",
            textAlign: "center",
            maxWidth: "100%",
          }}
        >
          {group.words.map((w, i) => (
            <span key={i} style={{ opacity: i === wordIdx ? 1 : 0.68 }}>
              {i > 0 ? " " : ""}
              {w.w}
            </span>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
