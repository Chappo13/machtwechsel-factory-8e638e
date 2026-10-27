import React, { useMemo } from "react";
import { Easing, interpolate, staticFile, useCurrentFrame } from "remotion";
import { geoMercator } from "d3-geo";
import { COLORS, FONT_DISPLAY, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { REGION_CFG_EXPORT } from "./MapScene";
import { MapRegion } from "../types";
import { ShipSilhouette } from "../components/ShipSilhouette";
import { TallyIcon } from "../components/TallyIcon";

// Карта-маршрут (map_route): линия рисуется прогрессивно, по ней движется маркер (корабль / человек / точка),
// пины; подписи только АНГЛИЙСКИМИ названиями мест КАПСОМ (до 3, data.places[].en) и число-год (data.year).
// Один пункт (route_pts из одной точки) = «место находки»: пульсирующий пин с подписью и медленный наезд.
// Подложка — растр из gen-maps.mjs (тот же, что у обычной карты).
const catmull = (pts: [number, number][], seg = 40) => {
  if (pts.length < 3) return pts.length === 2 ? Array.from({ length: seg + 1 }, (_, k) => [pts[0][0] + ((pts[1][0] - pts[0][0]) * k) / seg, pts[0][1] + ((pts[1][1] - pts[0][1]) * k) / seg] as [number, number]) : pts;
  const out: [number, number][] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
    for (let k = 0; k < seg; k++) {
      const u = k / seg, u2 = u * u, u3 = u2 * u;
      out.push([
        0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * u + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * u2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * u3),
        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * u + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * u2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * u3),
      ]);
    }
  }
  out.push(pts[pts.length - 1]);
  return out;
};

export const RouteMap: React.FC<SceneProps> = ({ data, fps, format, frameW, frameH, durationInFrames }) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const durSec = durationInFrames / fps;
  const region = (data.region || "north_atlantic") as MapRegion;
  const cfg = REGION_CFG_EXPORT[region] || REGION_CFG_EXPORT.world;
  const mapImg = staticFile(`textures/maps/${region}-${format}.png`);
  const rawPts = data.route_pts || [];
  const places = (data.places || []).slice(0, 3);
  const marker = data.marker || "ship";
  const portrait = frameH > frameW;

  const { pts, cum, total, proj } = useMemo(() => {
    const minDim = Math.min(frameW, frameH);
    const proj = geoMercator().center(cfg.center).scale(minDim / (cfg.spanDeg * (Math.PI / 180))).translate([frameW / 2, frameH / 2]);
    const xy = rawPts.map((p) => proj([p.lon, p.lat]) as [number, number]);
    const sm = catmull(xy);
    const c = [0];
    for (let i = 1; i < sm.length; i++) c.push(c[i - 1] + Math.hypot(sm[i][0] - sm[i - 1][0], sm[i][1] - sm[i - 1][1]));
    return { pts: sm, cum: c, total: c[c.length - 1], proj };
  }, [rawPts, frameW, frameH, cfg]);
  if (pts.length === 0) return <div style={{ width: frameW, height: frameH }} />;

  const single = pts.length < 2 || total < 4;
  const r0 = data.route_from ?? 0.9, r1 = data.route_to ?? Math.max(r0 + 1, durSec - 1.2);
  const prog = single ? 1 : interpolate(t, [r0, r1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.sin) });
  const dist = prog * total;
  let k = 1;
  while (k < cum.length - 1 && cum[k] < dist) k++;
  const f = single ? 0 : (dist - cum[k - 1]) / Math.max(1e-6, cum[k] - cum[k - 1]);
  const a0 = pts[Math.max(0, k - 1)], a1 = pts[Math.min(pts.length - 1, k)];
  const shipX = single ? pts[0][0] : a0[0] + (a1[0] - a0[0]) * f;
  const shipY = single ? pts[0][1] : a0[1] + (a1[1] - a0[1]) * f;
  const a = pts[Math.max(0, k - 6)], b = pts[Math.min(pts.length - 1, k + 6)];
  const heading = Math.atan2(b[1] - a[1], b[0] - a[0]);
  const moving = !single && prog > 0 && prog < 1;
  const flip = Math.cos(heading) > 0; // корабль нарисован носом влево
  const tiltDeg = (() => { let d = ((flip ? heading : heading + Math.PI) * 180) / Math.PI; while (d > 180) d -= 360; while (d < -180) d += 360; return Math.max(-20, Math.min(20, d)); })();
  const drawn = single ? [] : pts.slice(0, k).concat([[shipX, shipY]]);
  const d = drawn.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");

  const pinIn = (at: number) => interpolate(t, [at, at + 0.45], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.back(1.7)) });
  const start = pts[0], end = pts[pts.length - 1];
  const pStart = pinIn(0.25), pEnd = single ? 0 : pinIn(r1 - 0.35);
  const bob = Math.sin(t * 3.1) * 2.5;

  // наезд к середине маршрута (для одной точки сильнее)
  const zMax = single ? 0.2 : 0.07;
  const z = 1 + zMax * interpolate(t, [0, durSec], [0, 1], { easing: Easing.inOut(Easing.sin) });
  const ox = (start[0] + end[0]) / 2, oy = (start[1] + end[1]) / 2;

  const yearP = interpolate(t, [0.5, 1.1], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp", easing: Easing.out(Easing.cubic) });
  const pinEl = (p: [number, number], pr: number, pulse: boolean, big = false) => {
    if (pr <= 0) return null;
    const rr = (big ? 20 : 15) * pr;
    const pt = (t % 1.4) / 1.4;
    return (
      <g>
        {pulse && <circle cx={p[0]} cy={p[1]} r={rr * (1 + pt * 1.9)} fill="none" stroke={COLORS.red} strokeWidth={2.5} opacity={0.55 * (1 - pt) * pr} />}
        <circle cx={p[0]} cy={p[1]} r={rr * 2.2} fill={COLORS.red} opacity={0.16 * pr} />
        <circle cx={p[0]} cy={p[1]} r={rr} fill={COLORS.red} stroke={COLORS.parchmentLight} strokeWidth={3} />
      </g>
    );
  };

  // подписи мест: английские названия КАПСОМ у пинов; появляются, когда маркер подходит к месту
  const fs = portrait ? 50 : 58;
  const placeEls = places.map((pl, i) => {
    const p = proj([pl.lon, pl.lat]) as [number, number];
    let nearest = 0, bestD = 1e12;
    for (let j = 0; j < pts.length; j += 2) { const dd = Math.hypot(pts[j][0] - p[0], pts[j][1] - p[1]); if (dd < bestD) { bestD = dd; nearest = j; } }
    const frac = single ? 0 : cum[nearest] / Math.max(1, total);
    const onRoute = bestD < 60;
    const u = Math.acos(1 - 2 * Math.min(1, Math.max(0, frac))) / Math.PI; // обратная к easing.inOut(sin)
    const at = single || (onRoute && frac < 0.04) ? 0.35 : onRoute ? r0 + (r1 - r0) * u - 0.15 : (pl.at ?? 0.6 + i * 0.5);
    const pr = pinIn(at);
    // линия маршрута подходит к месту сверху: подпись уходит вниз, чтобы линия не резала буквы
    const nbs = [pts[Math.min(pts.length - 1, nearest + 12)], pts[Math.max(0, nearest - 12)]];
    const routeAbove = onRoute && nbs.some((q) => q[1] < p[1] - 25 && Math.abs(q[0] - p[0]) < 160);
    return { pl, p, at, pr, onRoute, frac, i, routeAbove, w: pl.en.length * fs * 0.66 };
  });
  // раскладка подписей: над точкой; при нехватке места сверху или пересечении с соседней подписью, ниже
  const placed: { x0: number; x1: number; y0: number; y1: number }[] = [];
  const labels = placeEls.map((e) => {
    const pad = 14;
    const clampX = (x: number) => Math.min(Math.max(x, e.w / 2 + 70), frameW - e.w / 2 - 70);
    let x = clampX(e.p[0]);
    let up = e.p[1] > frameH * 0.2 && !e.routeAbove;
    let y = up ? e.p[1] - 34 : e.p[1] + fs + 22;
    const box = () => ({ x0: x - e.w / 2 - pad, x1: x + e.w / 2 + pad, y0: y - fs, y1: y + 14 });
    const hit = (bx: { x0: number; x1: number; y0: number; y1: number }) => placed.some((q) => bx.x0 < q.x1 && bx.x1 > q.x0 && bx.y0 < q.y1 && bx.y1 > q.y0);
    if (hit(box())) { up = !up; y = up ? e.p[1] - 34 : e.p[1] + fs + 22; }
    placed.push(box());
    return { ...e, x, y };
  });

  const yearPos: React.CSSProperties = portrait ? { left: 70, top: 190 } : { left: 90, bottom: 80 };

  return (
    <div style={{ width: frameW, height: frameH, position: "relative", overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${z})`, transformOrigin: `${ox}px ${oy}px` }}>
        <img src={mapImg} width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }} />
        <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
          {prog > 0 && !single && <path d={d} fill="none" stroke={COLORS.red} strokeWidth={6} strokeDasharray="16 11" strokeLinecap="round" strokeLinejoin="round" />}
          {pinEl(start, pStart, single ? true : prog < 1, single)}
          {pinEl(end, pEnd, prog >= 1)}
          {prog > 0 && !single && (
            <g transform={`translate(${shipX}, ${shipY + (marker === "dot" ? 0 : bob)}) rotate(${moving && marker === "ship" ? tiltDeg : 0}) scale(${marker === "ship" && flip ? -1 : 1}, 1)`} opacity={Math.min(1, prog * 12) * (prog >= 1 ? 0 : 1)}>
              {marker === "ship" && <g transform="translate(-65, -84)"><ShipSilhouette width={130} hull={COLORS.ink} wave={false} /></g>}
              {marker === "person" && <g transform="translate(-34, -86)"><TallyIcon kind="person" width={68} /></g>}
              {marker === "dot" && (
                <g>
                  <circle r={30} fill={COLORS.gold} opacity={0.28} />
                  <circle r={15} fill={COLORS.ink} stroke={COLORS.parchmentLight} strokeWidth={4} />
                </g>
              )}
            </g>
          )}
          {labels.map((e) => {
            const nearEnds = Math.hypot(e.p[0] - start[0], e.p[1] - start[1]) < 70 || Math.hypot(e.p[0] - end[0], e.p[1] - end[1]) < 70;
            return (
              <g key={e.i} opacity={e.pr}>
                {!nearEnds && e.pr > 0 && <circle cx={e.p[0]} cy={e.p[1]} r={11 * e.pr} fill={COLORS.ink} stroke={COLORS.parchmentLight} strokeWidth={3} />}
                <text x={e.x} y={e.y} textAnchor="middle" fontFamily={FONT_DISPLAY} fontWeight={900} fontSize={fs} letterSpacing={4} fill={COLORS.ink}
                  style={{ paintOrder: "stroke", stroke: COLORS.parchmentLight, strokeWidth: 9, strokeLinejoin: "round" }}>{e.pl.en}</text>
              </g>
            );
          })}
        </svg>
      </div>
      {data.year && (
        <div style={{ position: "absolute", ...yearPos, opacity: yearP, transform: `translateY(${(1 - yearP) * 16}px)` }}>
          <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 900, fontSize: portrait ? 104 : 120, lineHeight: 1, color: COLORS.ink, fontVariantNumeric: "lining-nums", letterSpacing: 2, textShadow: `0 0 12px ${COLORS.parchmentLight}, 0 0 4px ${COLORS.parchmentLight}` }}>{data.year}</div>
          <div style={{ height: 5, background: COLORS.gold, marginTop: 6, width: `${yearP * 100}%` }} />
        </div>
      )}
    </div>
  );
};
void FONT_SERIF;
