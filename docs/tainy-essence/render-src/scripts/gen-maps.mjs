#!/usr/bin/env node
// Растеризует базовые карты (контуры стран) в PNG один раз на диск. Раньше
// MapScene рисовал ОДИН гигантский <path> (177 стран) СВГ-вектором на каждый
// кадр — дорогая растеризация повторялась без необходимости, т.к. контуры не
// меняются внутри сцены. Теперь это картинка; поверх неё остаются только
// дешёвые живые элементы (пины/маршрут).
//
// REGION_CFG должен совпадать с src/scenes/MapScene.tsx — там же используется
// для проекции пинов поверх этой самой картинки.
import sharp from "sharp";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { geoMercator, geoPath, geoGraticule } from "d3-geo";
import { feature } from "topojson-client";
import { REGION_CFG } from "../src/utils/regions.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, "..", "public", "textures", "maps");
const worldTopo = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "node_modules", "world-atlas", "countries-110m.json"), "utf-8")
);

const worldTopo50 = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "node_modules", "world-atlas", "countries-50m.json"), "utf-8")
);
// Регионы кодовой графики (карты маршрутов): детальный берег (50m), плотная суша и тонкая сетка без подписей.
const DETAIL_REGIONS = new Set(["north_atlantic", "north_america", "africa", "south_asia", "east_asia", "black_sea", "west_europe", "east_europe"]);

const FORMATS = { long: [1920, 1080], short: [1080, 1920] };
const INK = "#4a3a28";

function svgFor(region, w, h) {
  const cfg = REGION_CFG[region];
  const minDim = Math.min(w, h);
  const scale = minDim / (cfg.spanDeg * (Math.PI / 180));
  const projection = geoMercator().center(cfg.center).scale(scale).translate([w / 2, h / 2]);
  const path = geoPath(projection);
  const detail = DETAIL_REGIONS.has(region);
  const topo = detail ? worldTopo50 : worldTopo;
  const fc = feature(topo, topo.objects.countries);
  let d = "";
  for (const f of fc.features) d += path(f) || "";
  if (detail) {
    const grat = path(geoGraticule().step([10, 5]).extent([[-180, -80], [180, 80]])());
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <path d="${grat}" fill="none" stroke="${INK}" stroke-width="1.4" opacity="0.16"/>
    <path d="${d}" fill="rgba(176,141,87,0.38)" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>
  </svg>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <rect width="${w}" height="${h}" fill="none"/>
    <path d="${d}" fill="rgba(139,30,30,0.07)" stroke="${INK}" stroke-width="2.4" stroke-linejoin="round"/>
  </svg>`;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  for (const region of Object.keys(REGION_CFG)) {
    for (const [fmt, [w, h]] of Object.entries(FORMATS)) {
      const outPath = path.join(OUT_DIR, `${region}-${fmt}.png`);
      if (fs.existsSync(outPath)) {
        console.log("skip (exists)", `${region}-${fmt}.png`);
        continue;
      }
      const svg = svgFor(region, w, h);
      await sharp(Buffer.from(svg)).png().toFile(outPath);
      console.log("wrote", `${region}-${fmt}.png`);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
