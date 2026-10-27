import React, { useMemo } from "react";
import { COLORS, FONT_SERIF, FONT_HAND } from "../theme";
import { Chapter, Format } from "../types";

// Постоянная плашка сверху — название канала + текущая глава (жёлтая плашка,
// как в референсе Сафина). Делает любой кадр "насыщенным" и даёт зрителю
// ориентир, даже если конкретная сцена скромная по контенту.
export const HeaderStrip: React.FC<{
  channel: string;
  chapters: Chapter[];
  t: number;
  format: Format;
  brandEn?: boolean; // мелкая английская строка под водяным знаком
  showChapterBadge?: boolean; // scenes.json: chapter_badge:false — без русской плашки главы (мультиязычные версии)
}> = ({ channel, chapters, t, format, brandEn = false, showChapterBadge = true }) => {
  const current = useMemo(() => {
    let best: Chapter | undefined;
    for (const c of chapters) {
      if (c.start <= t) best = c;
      else break;
    }
    return best;
  }, [chapters, t]);

  const small = format === "short";

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: small ? "20px 28px" : "22px 44px",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          fontFamily: FONT_SERIF,
          fontWeight: 700,
          fontSize: small ? 26 : 28,
          letterSpacing: 3,
          color: COLORS.inkSoft,
          opacity: 0.8,
          textTransform: "uppercase",
        }}
      >
        {channel}
        {brandEn && (
          <div style={{ fontSize: small ? 13 : 15, letterSpacing: small ? 3.4 : 4.2, fontWeight: 600, marginTop: 4, opacity: 0.9 }}>
            SECRETS OF THE ANCIENTS
          </div>
        )}
      </div>
      {current && showChapterBadge && (
        <div
          style={{
            fontFamily: FONT_HAND,
            fontSize: small ? 28 : 32,
            color: COLORS.ink,
            background: "#d9ad4a",
            padding: small ? "4px 16px" : "5px 22px",
            borderRadius: 6,
            transform: "rotate(-1deg)",
            maxWidth: small ? 560 : 820,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {current.title}
        </div>
      )}
    </div>
  );
};
