import React from "react";
import { Composition } from "remotion";
import { Main } from "./Main";
import { normalizeScenes } from "./utils/quality.mjs";
import { MainProps } from "./types";
import { DIMENSIONS } from "./theme";
import emptyScenes from "./emptyScenes.json";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Main"
      component={Main}
      durationInFrames={25 * 60}
      fps={25}
      width={DIMENSIONS.long.width}
      height={DIMENSIONS.long.height}
      defaultProps={{
        scenesFile: emptyScenes,
        format: "long",
        subtitles: false,
      } as MainProps}
      calculateMetadata={async ({ props }) => {
        const p = props as MainProps;
        const scenesFile = normalizeScenes(p.scenesFile);
        const fps = scenesFile.fps;
        const dims = DIMENSIONS[p.format] || DIMENSIONS.long;
        const durationInFrames = Math.max(1, Math.round(scenesFile.duration_sec * fps));
        return {
          fps,
          width: dims.width,
          height: dims.height,
          durationInFrames,
          props: { ...p, scenesFile },
        };
      }}
    />
  );
};
