import React, { useMemo } from "react";
import { AbsoluteFill, Audio, Sequence, Series, useCurrentFrame, useVideoConfig } from "remotion";
import { MainProps } from "./types";
import { Parchment } from "./components/Parchment";
import { Subtitles } from "./components/Subtitles";
import { AudioHint } from "./components/AudioHint";
import { DateChip } from "./components/DateChip";
import { HeaderStrip } from "./components/HeaderStrip";
import { CrossfadeEcho } from "./components/CrossfadeEcho";
import { SceneRouter } from "./scenes/SceneRouter";
import { planSceneTransitions } from "./utils/transitions.mjs";

const CROSSFADE_SEC = 0.4;
export const OVERLAY_LAYER_Z = 100; // > любого zIndex эффектов сцен (макс. 50)

// audioSrc — опциональный вход только для Mac-сборщика (mac/tainy-build.mjs),
// который рендерит со вшитой предсведённой озвучкой. Серверный конвейер
// (render.mjs) звук не передаёт и не добавляет — там звук приходит позже на
// этапе mix, композиция остаётся немой (audioSrc===undefined).
export const Main: React.FC<MainProps> = ({ scenesFile, format, subtitles, audioSrc, audioStartFrame }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;

  const scenes = scenesFile.scenes;
  // границы сцен в кадрах считаем от абсолютных секунд, чтобы сумма длительностей
  // точно совпадала с общей длиной ролика (без дрейфа из-за округления).
  const boundaries: number[] = [];
  scenes.forEach((s, i) => {
    if (i === 0) boundaries.push(Math.round(s.start * fps));
    boundaries.push(Math.round(s.end * fps));
  });

  // Детерминированный план переходов между сценами (см. utils/transitions.mjs):
  // cut | crossfade | dip_black | film_burn | wipe. Устойчив к рендеру по частям
  // (--from/--to, chunk-sec) — считается от полного scenesFile, не от текущего окна.
  // standalone_short: самостоятельный шорт (shorts_scenes/shortN.json) — никаких плашек/глав/дат, только медиа + марка канала.
  const standalone = scenesFile.standalone_short === true;
  const chapters = standalone ? [] : scenesFile.chapters || [];
  const overlays = standalone ? [] : scenesFile.overlays || [];
  const transitionKinds = useMemo(
    () => planSceneTransitions(scenes, chapters, fps, 45, { standalone }),
    [scenes, scenesFile.chapters, fps, standalone]
  );
  const crossfadeFrames = Math.round(fps * CROSSFADE_SEC);

  return (
    <AbsoluteFill style={{ backgroundColor: "#dcc89a" }}>
      <Parchment width={width} height={height} format={format} />
      <Series>
        {scenes.map((scene, i) => {
          const dur = Math.max(1, boundaries[i + 1] - boundaries[i]);
          const kind = transitionKinds[i];
          const nextKind = transitionKinds[i + 1];
          return (
            <Series.Sequence key={scene.id} durationInFrames={dur} layout="none">
              <SceneRouter
                scene={scene}
                fps={fps}
                format={format}
                frameW={width}
                frameH={height}
                durationInFrames={dur}
                // crossfade рисуется отдельным "эхом" (ниже) поверх хвоста
                // предыдущей сцены — сама сцена в этом случае входит обычным cut
                transitionIn={kind === "crossfade" ? "cut" : kind}
                fadeOutFrames={nextKind === "crossfade" ? crossfadeFrames : 0}
              />
            </Series.Sequence>
          );
        })}
      </Series>
      {scenes.map((scene, i) => {
        if (transitionKinds[i] !== "crossfade") return null;
        const echoFrom = Math.max(0, boundaries[i] - crossfadeFrames);
        const echoDur = boundaries[i] - echoFrom;
        if (echoDur <= 0) return null;
        const dur = Math.max(1, boundaries[i + 1] - boundaries[i]);
        return (
          <Sequence key={`echo-${scene.id}`} from={echoFrom} durationInFrames={echoDur} layout="none">
            <CrossfadeEcho durSec={CROSSFADE_SEC}>
              <SceneRouter
                scene={scene}
                fps={fps}
                format={format}
                frameW={width}
                frameH={height}
                durationInFrames={dur}
                transitionIn="cut"
              />
            </CrossfadeEcho>
          </Sequence>
        );
      })}
      {/* Верхний слой: шапка, плашки и субтитры ВСЕГДА выше любых эффектов сцен (DipBlack/FilmBurn/SceneWipeIn zIndex 50,
          CrossfadeEcho zIndex 40). Раньше они шли без zIndex и перекрывались стыком сцены (плашка «пропадала и возвращалась»).
          Слой один на весь ролик, вне Series/Sequence: не перемонтируется на границах кадров, время только абсолютное. */}
      <AbsoluteFill style={{ zIndex: OVERLAY_LAYER_Z, pointerEvents: "none" }}>
        <HeaderStrip
          channel={typeof scenesFile.channel_name === "string" ? scenesFile.channel_name : "ТАЙНЫ ДРЕВНИХ"}
          chapters={chapters}
          t={t}
          format={format}
          showChapterBadge={scenesFile.chapter_badge !== false}
          brandEn={scenesFile.brand_en === true}
        />
        {format === "long" && overlays.map((ov, i) => ov.type === "audio_hint" ? (
          <AudioHint key={`ov-${i}`} overlay={ov} t={t} fps={fps} format={format} />
        ) : null)}
        {overlays.map((ov, i) => ov.type === "date_chip" ? (
          <DateChip key={`dc-${i}`} overlay={ov} t={t} format={format} />
        ) : null)}
        {subtitles && !standalone && scenesFile.shorts_subtitles === true && <Subtitles words={scenesFile.words || []} t={t} format={format} />}
      </AbsoluteFill>
      {audioSrc && (
        // from=audioStartFrame выравнивает ОБРЕЗАННЫЙ (0-based) аудиофайл шортса
        // с его окном на глобальной шкале композиции при рендере через frameRange —
        // иначе семпл звука брался бы с позиции currentGlobalFrame, а не с начала файла.
        <Sequence from={audioStartFrame ?? 0} layout="none">
          <Audio src={audioSrc} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
