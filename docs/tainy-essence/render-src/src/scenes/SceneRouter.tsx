import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Scene, Format } from "../types";
import { SceneProps } from "./sceneProps";
import { clamp } from "../utils/time";
import { CameraDrift } from "../components/CameraDrift";
import { SceneWipeIn } from "../components/SceneWipeIn";
import { DipBlack } from "../components/DipBlack";
import { FilmBurn } from "../components/FilmBurn";
import { TitleCard } from "./TitleCard";
import { Diary } from "./Diary";
import { MapScene } from "./MapScene";
import { TimelineScene } from "./TimelineScene";
import { Blueprint } from "./Blueprint";
import { Board } from "./Board";
import { Document } from "./Document";
import { Scale } from "./Scale";
import { NumberScene } from "./NumberScene";
import { Stars } from "./Stars";
import { Quote } from "./Quote";
import { Media } from "./Media";
import { Compare } from "./Compare";
import { Counter } from "./Counter";
import { Steps } from "./Steps";
import { FactStack } from "./FactStack";
import { TableScene } from "./TableScene";
import { RouteMap } from "./RouteMap";
import { Tally } from "./Tally";

const SELF_CAMERA = new Set(["diary", "board", "media"]);

function hashSeed(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h) % 1000;
}

export type TransitionIn = "cut" | "wipe" | "dip_black" | "film_burn";

export const SceneRouter: React.FC<{
  scene: Scene;
  fps: number;
  format: Format;
  frameW: number;
  frameH: number;
  durationInFrames: number;
  // Чем сцена входит (выбирается снаружи, в Main.tsx, по детерминированной
  // политике — см. utils/transitions.mjs). "cut" — без локального эффекта: либо
  // это первая сцена, либо вход уже отрисован crossfade-"эхом" поверх хвоста
  // предыдущей сцены (см. Main.tsx), и добавлять сюда ещё один эффект не нужно.
  transitionIn?: TransitionIn;
  // Если ненулевое — сцена сама плавно гаснет в своих последних N кадрах
  // (используется, когда СЛЕДУЮЩАЯ сцена входит через crossfade).
  fadeOutFrames?: number;
}> = ({ scene, fps, format, frameW, frameH, durationInFrames, transitionIn = "cut", fadeOutFrames = 0 }) => {
  const frame = useCurrentFrame();
  const props: SceneProps = {
    data: scene.data,
    beats: scene.beats || [],
    sceneStart: scene.start,
    durationInFrames,
    fps,
    format,
    frameW,
    frameH,
    seed: hashSeed(scene.id),
  };

  const Comp = COMPONENTS[scene.type];
  const body = Comp ? <Comp {...props} /> : <FallbackScene type={scene.type} frameW={frameW} frameH={frameH} />;

  const needsDrift = !SELF_CAMERA.has(scene.type);
  const fadeOutOpacity = fadeOutFrames > 0 ? clamp((durationInFrames - frame) / fadeOutFrames) : 1;

  return (
    <AbsoluteFill style={{ opacity: fadeOutOpacity }}>
      {needsDrift ? (
        <CameraDrift seed={hashSeed(scene.id) / 1000} durationInFrames={durationInFrames}>
          {body}
        </CameraDrift>
      ) : (
        body
      )}
      {transitionIn === "wipe" && <SceneWipeIn />}
      {transitionIn === "dip_black" && <DipBlack />}
      {transitionIn === "film_burn" && <FilmBurn />}
    </AbsoluteFill>
  );
};

const COMPONENTS: Record<string, React.FC<SceneProps>> = {
  title_card: TitleCard,
  diary: Diary,
  map: MapScene,
  timeline: TimelineScene,
  blueprint: Blueprint,
  board: Board,
  document: Document,
  scale: Scale,
  number: NumberScene,
  stars: Stars,
  quote: Quote,
  media: Media,
  compare: Compare,
  counter: Counter,
  steps: Steps,
  fact_stack: FactStack,
  table: TableScene,
  map_route: RouteMap,
  tally: Tally,
};

const FallbackScene: React.FC<{ type: string; frameW: number; frameH: number }> = ({ type, frameW, frameH }) => (
  <div style={{ width: frameW, height: frameH, display: "flex", alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontSize: 40 }}>Неизвестный тип сцены: {type}</div>
  </div>
);
