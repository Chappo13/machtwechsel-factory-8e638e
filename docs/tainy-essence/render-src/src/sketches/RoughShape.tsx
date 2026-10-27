import React, { useEffect, useRef } from "react";
import rough from "roughjs/bin/rough";
import { drawSketch } from "./draw";
import { SketchName } from "../types";

export const RoughShape: React.FC<{
  name: SketchName;
  size: number;
  stroke: string;
  strokeWidth?: number;
  seed: number;
  style?: React.CSSProperties;
}> = ({ name, size, stroke, strokeWidth, seed, style }) => {
  const ref = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const rc = rough.svg(svg);
    const g = drawSketch(rc, name, { stroke, strokeWidth, seed });
    svg.appendChild(g);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, stroke, strokeWidth, seed]);

  return (
    <svg
      ref={ref}
      viewBox="0 0 200 200"
      width={size}
      height={size}
      style={style}
    />
  );
};
