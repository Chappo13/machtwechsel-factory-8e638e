#!/usr/bin/env node
// Генерирует статичные текстуры пергамента (JPEG) один раз и кеширует их на диск.
// Раньше зерно/виньетка/пятна считались SVG feTurbulence + blend-режимами
// НА КАЖДЫЙ КАДР — это было главной причиной низкого fps рендера. Теперь это
// готовые картинки, которые Chrome просто декодирует один раз.
import sharp from "sharp";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, "..", "public", "textures");

const PARCHMENT_LIGHT = [233, 220, 185];
const PARCHMENT_DARK = [181, 154, 102];
const INK = [43, 33, 24];

function clamp(v) {
  return Math.max(0, Math.min(255, v | 0));
}
function lerp(a, b, t) {
  return a + (b - a) * t;
}

function makeGrid(gw, gh) {
  const g = new Float32Array(gw * gh);
  for (let i = 0; i < g.length; i++) g[i] = Math.random();
  return g;
}
function sampleGrid(grid, gw, gh, u, v) {
  const gx = u * (gw - 1);
  const gy = v * (gh - 1);
  const x0 = Math.floor(gx);
  const y0 = Math.floor(gy);
  const x1 = Math.min(gw - 1, x0 + 1);
  const y1 = Math.min(gh - 1, y0 + 1);
  const fx = gx - x0;
  const fy = gy - y0;
  const v00 = grid[y0 * gw + x0];
  const v10 = grid[y0 * gw + x1];
  const v01 = grid[y1 * gw + x0];
  const v11 = grid[y1 * gw + x1];
  return lerp(lerp(v00, v10, fx), lerp(v01, v11, fx), fy);
}

function genParchment(W, H, seed) {
  // псевдослучайность не критична к качеству RNG — Math.random достаточно,
  // seed используется только чтобы long/short отличались по пятнам
  const buf = Buffer.alloc(W * H * 3);
  const blotGw = 40;
  const blotGh = Math.max(8, Math.round((blotGw * H) / W));
  const blotGrid = makeGrid(blotGw, blotGh);
  const grainGw = 220;
  const grainGh = Math.max(40, Math.round((grainGw * H) / W));
  const grainGrid = makeGrid(grainGw, grainGh);

  // несколько тёмных пятен-клякс
  const stains = [];
  const nStains = 10 + (seed % 5);
  for (let i = 0; i < nStains; i++) {
    stains.push({
      x: Math.random() * W,
      y: Math.random() * H,
      r: (Math.min(W, H) * (0.05 + Math.random() * 0.14)),
      strength: 0.12 + Math.random() * 0.22,
    });
  }

  const cx = W * (0.35 + 0.15 * Math.random());
  const cy = H * (0.25 + 0.15 * Math.random());

  for (let y = 0; y < H; y++) {
    const v = y / H;
    for (let x = 0; x < W; x++) {
      const u = x / W;
      const dx = (x - cx) / (W * 0.78);
      const dy = (y - cy) / (H * 0.72);
      let t = Math.min(1, Math.sqrt(dx * dx + dy * dy));

      let r = lerp(PARCHMENT_LIGHT[0], PARCHMENT_DARK[0], t);
      let g = lerp(PARCHMENT_LIGHT[1], PARCHMENT_DARK[1], t);
      let b = lerp(PARCHMENT_LIGHT[2], PARCHMENT_DARK[2], t);

      // крупные облачные разводы бумаги
      const blot = sampleGrid(blotGrid, blotGw, blotGh, u, v);
      const shade = (blot - 0.5) * 46;
      r += shade;
      g += shade * 0.88;
      b += shade * 0.62;

      // среднее зерно
      const grain = sampleGrid(grainGrid, grainGw, grainGh, u, v);
      const gshade = (grain - 0.5) * 20;
      r += gshade;
      g += gshade * 0.9;
      b += gshade * 0.7;

      // мелкий шум (зерно бумаги)
      const fine = (Math.random() - 0.5) * 12;
      r += fine;
      g += fine * 0.9;
      b += fine * 0.75;

      // виньетка
      const vx = u - 0.5;
      const vy = v - 0.5;
      const vig = Math.sqrt(vx * vx + vy * vy) * 1.55;
      const vigF = Math.max(0, vig - 0.42) * 1.1;
      r -= vigF * 130;
      g -= vigF * 118;
      b -= vigF * 100;

      // рваный / подпалённый край
      const edgeDist = Math.min(u, 1 - u, v * (W / H), (1 - v) * (W / H));
      const edgeJitter = (sampleGrid(blotGrid, blotGw, blotGh, u, v) - 0.5) * 0.04;
      const edgeT = Math.max(0, 0.05 - (edgeDist + edgeJitter)) * 10;
      if (edgeT > 0) {
        r = lerp(r, INK[0], Math.min(1, edgeT) * 0.8);
        g = lerp(g, INK[1], Math.min(1, edgeT) * 0.8);
        b = lerp(b, INK[2], Math.min(1, edgeT) * 0.8);
      }

      const idx = (y * W + x) * 3;
      buf[idx] = clamp(r);
      buf[idx + 1] = clamp(g);
      buf[idx + 2] = clamp(b);
    }
  }

  // чернильные пятна и штрихи линовки поверх (блочные операции, дёшево)
  for (const s of stains) {
    const x0 = Math.max(0, Math.floor(s.x - s.r));
    const x1 = Math.min(W, Math.ceil(s.x + s.r));
    const y0 = Math.max(0, Math.floor(s.y - s.r));
    const y1 = Math.min(H, Math.ceil(s.y + s.r));
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const dx = x - s.x;
        const dy = y - s.y;
        const d = Math.sqrt(dx * dx + dy * dy) / s.r;
        if (d > 1) continue;
        const a = (1 - d) * s.strength * (0.5 + Math.random() * 0.5);
        const idx = (y * W + x) * 3;
        buf[idx] = clamp(lerp(buf[idx], INK[0], a));
        buf[idx + 1] = clamp(lerp(buf[idx + 1], INK[1], a));
        buf[idx + 2] = clamp(lerp(buf[idx + 2], INK[2], a));
      }
    }
  }

  // едва заметные линии разлиновки (горизонтальные), как в тетради
  const lineGap = Math.round(H / 26);
  for (let y = lineGap; y < H; y += lineGap) {
    for (let x = 0; x < W; x++) {
      const idx = (y * W + x) * 3;
      const a = 0.05;
      buf[idx] = clamp(lerp(buf[idx], INK[0], a));
      buf[idx + 1] = clamp(lerp(buf[idx + 1], INK[1], a));
      buf[idx + 2] = clamp(lerp(buf[idx + 2], INK[2], a));
    }
  }

  return buf;
}

function genCorkTile(size) {
  // доска объявлений: раньше точки рисовались как CSS radial-gradient repeat
  // (тысячи процедурных градиентов на кадр!) — теперь это один маленький
  // растровый тайл, который браузер просто повторяет как текстуру.
  const buf = Buffer.alloc(size * size * 4);
  const dotR = size * 0.045;
  const positions = [
    [size * 0.5, size * 0.5],
    [0, 0], [size, 0], [0, size], [size, size],
  ];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let a = 0;
      for (const [px, py] of positions) {
        const d = Math.sqrt((x - px) ** 2 + (y - py) ** 2);
        a = Math.max(a, Math.max(0, 1 - d / dotR));
      }
      const idx = (y * size + x) * 4;
      buf[idx] = 156;
      buf[idx + 1] = 122;
      buf[idx + 2] = 78;
      buf[idx + 3] = clamp(a * 130);
    }
  }
  return buf;
}

function genGrainTile(size) {
  // маленький повторяющийся тайл шума для дешёвой "живой" анимации зерна
  // (двигаем background-position по кадрам вместо перерасчёта фильтра)
  const buf = Buffer.alloc(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    const n = Math.random();
    const v = clamp(128 + (n - 0.5) * 180);
    buf[i * 4] = INK[0];
    buf[i * 4 + 1] = INK[1];
    buf[i * 4 + 2] = INK[2];
    buf[i * 4 + 3] = clamp((1 - Math.abs(n - 0.5) * 2) * 70 + Math.random() * 40);
  }
  return buf;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const targets = [
    { name: "parchment-long.jpg", w: 1920, h: 1080, seed: 1 },
    { name: "parchment-short.jpg", w: 1080, h: 1920, seed: 2 },
  ];

  for (const t of targets) {
    const outPath = path.join(OUT_DIR, t.name);
    if (fs.existsSync(outPath)) {
      console.log("skip (exists)", t.name);
      continue;
    }
    console.log("generating", t.name, `${t.w}x${t.h}...`);
    const buf = genParchment(t.w, t.h, t.seed);
    await sharp(buf, { raw: { width: t.w, height: t.h, channels: 3 } })
      .jpeg({ quality: 88 })
      .toFile(outPath);
    console.log("wrote", outPath);
  }

  const corkPath = path.join(OUT_DIR, "cork-tile.png");
  if (!fs.existsSync(corkPath)) {
    console.log("generating cork-tile.png...");
    const size = 36;
    const buf = genCorkTile(size);
    await sharp(buf, { raw: { width: size, height: size, channels: 4 } })
      .png()
      .toFile(corkPath);
    console.log("wrote", corkPath);
  } else {
    console.log("skip (exists) cork-tile.png");
  }

  const grainPath = path.join(OUT_DIR, "grain-tile.png");
  if (!fs.existsSync(grainPath)) {
    console.log("generating grain-tile.png...");
    const size = 220;
    const buf = genGrainTile(size);
    await sharp(buf, { raw: { width: size, height: size, channels: 4 } })
      .png()
      .toFile(grainPath);
    console.log("wrote", grainPath);
  } else {
    console.log("skip (exists) grain-tile.png");
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
