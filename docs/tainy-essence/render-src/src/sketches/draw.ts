// Скетч-иконки для дневника (roughjs, "рукописный" стиль). Координатное
// пространство каждой иконки: 0..200 x 0..200. rc — RoughSVG (roughjs/bin/svg).
import type { RoughSVG } from "roughjs/bin/svg";
import { SketchName } from "../types";

type Opt = { stroke: string; strokeWidth?: number; seed: number; fill?: string };

function opts(o: Opt, extra: Record<string, unknown> = {}) {
  return {
    stroke: o.stroke,
    strokeWidth: o.strokeWidth ?? 2.4,
    roughness: 1.8,
    bowing: 1.2,
    seed: o.seed,
    fill: o.fill,
    fillStyle: "hachure",
    hachureGap: 6,
    ...extra,
  };
}

export function drawSketch(rc: RoughSVG, name: SketchName, o: Opt): SVGElement {
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const add = (el: SVGElement) => g.appendChild(el);
  const O = opts(o);

  switch (name) {
    case "pyramid": {
      add(rc.polygon([[100, 30], [175, 170], [25, 170]], O));
      add(rc.line(100, 30, 100, 170, O));
      add(rc.line(60, 170, 120, 90, O));
      break;
    }
    case "gear": {
      const cx = 100, cy = 100, rOut = 55, rIn = 38, teeth = 8;
      let d = "";
      for (let i = 0; i < teeth; i++) {
        const a0 = (i / teeth) * Math.PI * 2;
        const a1 = a0 + (Math.PI * 2) / teeth / 2;
        const a2 = a0 + (Math.PI * 2) / teeth;
        const p = (r: number, a: number) => `${cx + r * Math.cos(a)},${cy + r * Math.sin(a)}`;
        d += `M ${p(rIn, a0)} L ${p(rOut, a0 + 0.05)} L ${p(rOut, a1 - 0.05)} L ${p(rIn, a1)} L ${p(rIn, a2)} `;
      }
      add(rc.path(d, opts(o, { fill: undefined })));
      add(rc.circle(cx, cy, rIn * 1.1, O));
      add(rc.circle(cx, cy, 10, opts(o, { fill: o.stroke })));
      break;
    }
    case "skull": {
      add(rc.circle(100, 85, 55, O));
      add(rc.rectangle(78, 120, 44, 35, O));
      add(rc.circle(82, 85, 12, opts(o, { fill: o.stroke })));
      add(rc.circle(118, 85, 12, opts(o, { fill: o.stroke })));
      add(rc.line(95, 110, 90, 125, O));
      add(rc.line(105, 110, 110, 125, O));
      add(rc.line(80, 148, 92, 148, O));
      add(rc.line(98, 148, 110, 148, O));
      add(rc.line(116, 148, 128, 148, O));
      break;
    }
    case "eye": {
      add(rc.path("M 25 100 Q 100 40 175 100 Q 100 160 25 100 Z", O));
      add(rc.circle(100, 100, 26, O));
      add(rc.circle(100, 100, 10, opts(o, { fill: o.stroke })));
      for (let i = 0; i < 7; i++) {
        const a = Math.PI + (i / 6) * Math.PI;
        add(rc.line(100 + 30 * Math.cos(a), 100 + 30 * Math.sin(a), 100 + 55 * Math.cos(a), 100 + 55 * Math.sin(a), O));
      }
      break;
    }
    case "sphinx": {
      add(rc.ellipse(100, 150, 150, 35, O));
      add(rc.polygon([[45, 150], [60, 95], [140, 95], [155, 150]], O));
      add(rc.rectangle(80, 45, 40, 55, O));
      add(rc.line(80, 95, 60, 95, O));
      add(rc.line(120, 95, 140, 95, O));
      break;
    }
    case "temple": {
      add(rc.line(35, 170, 165, 170, O));
      add(rc.line(35, 70, 165, 70, O));
      for (let i = 0; i < 6; i++) {
        const x = 45 + i * 22;
        add(rc.line(x, 70, x, 170, O));
      }
      add(rc.polygon([[25, 70], [100, 25], [175, 70]], O));
      break;
    }
    case "stone_block": {
      add(rc.polygon([[35, 60], [160, 40], [175, 150], [50, 170]], O));
      add(rc.line(35, 60, 50, 170, O));
      add(rc.line(160, 40, 175, 150, O));
      break;
    }
    case "ship": {
      add(rc.path("M 20 120 Q 100 160 180 120 L 165 150 Q 100 175 35 150 Z", O));
      add(rc.line(100, 120, 100, 30, O));
      add(rc.path("M 100 35 L 150 70 L 100 100 Z", O));
      add(rc.line(60, 100, 60, 125, O));
      break;
    }
    case "scroll": {
      add(rc.rectangle(45, 45, 110, 110, O));
      add(rc.ellipse(45, 45, 22, 22, O));
      add(rc.ellipse(45, 155, 22, 22, O));
      add(rc.ellipse(155, 45, 22, 22, O));
      add(rc.ellipse(155, 155, 22, 22, O));
      add(rc.line(65, 80, 135, 80, O));
      add(rc.line(65, 100, 135, 100, O));
      add(rc.line(65, 120, 115, 120, O));
      break;
    }
    case "star": {
      const pts: [number, number][] = [];
      for (let i = 0; i < 10; i++) {
        const r = i % 2 === 0 ? 70 : 30;
        const a = -Math.PI / 2 + (i / 10) * Math.PI * 2;
        pts.push([100 + r * Math.cos(a), 100 + r * Math.sin(a)]);
      }
      add(rc.polygon(pts, O));
      break;
    }
    case "globe": {
      add(rc.circle(100, 100, 65, O));
      add(rc.ellipse(100, 100, 65, 28, O));
      add(rc.ellipse(100, 100, 28, 130, O));
      add(rc.line(35, 100, 165, 100, O));
      break;
    }
    case "mummy": {
      add(rc.ellipse(100, 100, 70, 115, O));
      for (let i = 0; i < 6; i++) {
        add(rc.line(60 - i, 55 + i * 15, 140 + i, 60 + i * 15, O));
      }
      add(rc.ellipse(100, 70, 18, 10, O));
      break;
    }
    case "moai": {
      add(rc.path("M 70 170 L 65 90 Q 65 35 100 25 Q 135 35 135 90 L 130 170 Z", O));
      add(rc.line(70, 170, 130, 170, O));
      add(rc.rectangle(78, 65, 15, 10, opts(o, { fill: o.stroke })));
      add(rc.rectangle(107, 65, 15, 10, opts(o, { fill: o.stroke })));
      add(rc.line(85, 95, 115, 95, O));
      break;
    }
    case "monolith": {
      add(rc.polygon([[75, 170], [78, 35], [122, 35], [125, 170]], O));
      add(rc.line(78, 35, 122, 35, O));
      break;
    }
    default:
      add(rc.rectangle(50, 50, 100, 100, O));
  }
  return g;
}
