import { Beat, Format, SceneData } from "../types";

export type SceneProps = {
  data: SceneData;
  beats: Beat[];
  sceneStart: number; // абсолютное время начала сцены, сек
  durationInFrames: number;
  fps: number;
  format: Format;
  frameW: number;
  frameH: number;
  seed: number; // стабильный сид на сцену (для roughjs/дрейфа)
};
