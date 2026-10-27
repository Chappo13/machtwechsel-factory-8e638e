import React from "react";
import { AbsoluteFill, Freeze, useCurrentFrame, useVideoConfig } from "remotion";
import { clamp } from "../utils/time";

// "Растворение" без раздувания общей длительности: вместо настоящего наложения
// двух идущих сцен (которое требует TransitionSeries и съедает кадры из общего
// хронометража — критично для синхронизации со звуком) показываем ПЕРВЫЙ кадр
// входящей сцены (Freeze на локальном кадре 0), плавно проявляя его поверх
// хвоста уходящей — та, в свою очередь, сама гаснет в своих последних кадрах
// (см. SceneRouter.fadeOutFrames). Ровно в момент начала настоящей сцены эхо
// исчезает, и основной <Series> подхватывает её уже с кадра 0 — стык незаметен,
// т.к. это один и тот же пиксель-в-пиксель рендер первого кадра.
export const CrossfadeEcho: React.FC<{ durSec?: number; children: React.ReactNode }> = ({ durSec = 0.4, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const durFrames = Math.max(1, Math.round(fps * durSec));
  const opacity = clamp(frame / durFrames);
  return (
    <AbsoluteFill style={{ opacity, zIndex: 40 }}>
      <Freeze frame={0}>{children}</Freeze>
    </AbsoluteFill>
  );
};
