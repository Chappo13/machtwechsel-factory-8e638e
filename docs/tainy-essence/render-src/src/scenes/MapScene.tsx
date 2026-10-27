import React, { useMemo } from "react";
import { staticFile, useCurrentFrame } from "remotion";
import { geoMercator } from "d3-geo";
import { COLORS, FONT_HAND, FONT_SERIF } from "../theme";
import { SceneProps } from "./sceneProps";
import { buildRevealMap, revealProgress } from "../utils/time";
import { MapRegion } from "../types";
import { REGION_CFG as REGION_CFG_SHARED } from "../utils/regions.mjs";

// Конфиг регионов — в utils/regions.mjs (общий с scripts/gen-maps.mjs и RouteMap).
const REGION_CFG = REGION_CFG_SHARED as Record<MapRegion, { center: [number, number]; spanDeg: number }>;
export const REGION_CFG_EXPORT = REGION_CFG;

export const MapScene: React.FC<SceneProps> = ({ data, beats, sceneStart, fps, format, frameW, frameH }) => {
  const frame = useCurrentFrame();
  const region = (data.region || "world") as MapRegion;
  const cfg = REGION_CFG[region] || REGION_CFG.world;
  const pins = data.pins || [];

  // контуры стран растеризованы заранее (scripts/gen-maps.mjs) — тут только
  // дешёвая проекция координат пинов, без пересчёта полигонов 177 стран на кадр
  const project = useMemo(() => {
    const minDim = Math.min(frameW, frameH);
    const scale = minDim / (cfg.spanDeg * (Math.PI / 180));
    const projection = geoMercator().center(cfg.center).scale(scale).translate([frameW / 2, frameH / 2]);
    return (lon: number, lat: number): [number, number] => {
      const r = projection([lon, lat]);
      return r ? [r[0], r[1]] : [frameW / 2, frameH / 2];
    };
  }, [region, frameW, frameH]);
  const mapImg = staticFile(`textures/maps/${region}-${format}.png`);

  const ids = pins.map((p) => p.id);
  const revealMap = useMemo(() => buildRevealMap(ids, beats, sceneStart, fps), [ids.join(","), beats, sceneStart, fps]);

  const routeIds = data.route || [];

  // Региональный фон рисуется заранее на весь диапазон региона (например,
  // "mediterranean" целиком) — если все пины сидят в одном углу, они выглядят
  // мелкими и теряются. Поэтому дополнительно зумим img+svg ВМЕСТЕ (один и тот
  // же project() -> координаты пинов и подложки остаются согласованы) к
  // bounding box пинов, с запасом сверху под подписи.
  const zoom = useMemo(() => {
    if (pins.length === 0) return { scale: 1, tx: 0, ty: 0 };
    const pts = pins.map((p) => project(p.lon, p.lat));
    const minX = Math.min(...pts.map((p) => p[0]));
    const maxX = Math.max(...pts.map((p) => p[0]));
    const minY = Math.min(...pts.map((p) => p[1]));
    const maxY = Math.max(...pts.map((p) => p[1]));
    const padX = frameW * 0.2;
    const padTop = frameH * 0.28; // подписи пинов рисуются НАД точкой
    const padBottom = frameH * 0.14;
    const boxW = Math.max(maxX - minX, 1) + padX * 2;
    const boxH = Math.max(maxY - minY, 1) + padTop + padBottom;
    const fitScale = Math.min(frameW / boxW, frameH / boxH);
    const scale = Math.min(3, Math.max(1, fitScale));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2 - (padTop - padBottom) / 2 / scale;
    return { scale, tx: frameW / 2 - cx * scale, ty: frameH / 2 - cy * scale };
  }, [pins, project, frameW, frameH]);

  return (
    <div style={{ width: frameW, height: frameH, position: "relative" }}>
      {data.region && !data.hide_words && (
        <div
          style={{
            position: "absolute",
            top: 50,
            left: 0,
            right: 0,
            textAlign: "center",
            fontFamily: FONT_SERIF,
            fontSize: 54,
            color: COLORS.inkSoft,
            textTransform: "uppercase",
            letterSpacing: 3,
          }}
        >
          {regionLabel(region)}
        </div>
      )}
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${zoom.tx}px, ${zoom.ty}px) scale(${zoom.scale})`,
          transformOrigin: "0 0",
        }}
      >
      <img src={mapImg} width={frameW} height={frameH} style={{ position: "absolute", inset: 0 }} />
      <svg width={frameW} height={frameH} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        {routeIds.length > 1 &&
          routeIds.slice(0, -1).map((fromId, i) => {
            const toId = routeIds[i + 1];
            const fromPin = pins.find((p) => p.id === fromId);
            const toPin = pins.find((p) => p.id === toId);
            if (!fromPin || !toPin) return null;
            const revFrom = revealMap[fromId] ?? 0;
            const revTo = revealMap[toId] ?? 0;
            const p = revealProgress(frame, Math.max(revFrom, revTo - fps * 0.3), fps, 0.8);
            if (p <= 0) return null;
            const [x1, y1] = project(fromPin.lon, fromPin.lat);
            const [x2, y2] = project(toPin.lon, toPin.lat);
            const mx = x1 + (x2 - x1) * p;
            const my = y1 + (y2 - y1) * p;
            return (
              <path
                key={`${fromId}-${toId}`}
                d={`M ${x1} ${y1} L ${mx} ${my}`}
                stroke={COLORS.red}
                strokeWidth={3}
                fill="none"
                strokeDasharray="10 8"
                strokeLinecap="round"
              />
            );
          })}

        {pins.map((p) => {
          const prog = revealProgress(frame, revealMap[p.id] ?? 0, fps, 0.6);
          if (prog <= 0) return null;
          const [x, y] = project(p.lon, p.lat);
          // r=16 -> ⌀32px у подложки ДО общего зума карты (zoom.scale>=1) —
          // с запасом перекрывает требование "пины не меньше 28px"
          const r = 16 * prog;
          // пульсирующее кольцо вокруг полностью проявленного пина — приковывает
          // внимание на карте, где иначе точка может потеряться на подложке
          const pulseFrame = Math.max(0, frame - (revealMap[p.id] ?? 0));
          const pulseT = ((pulseFrame / fps) % 1.4) / 1.4;
          const pulseR = r * (1 + pulseT * 1.8);
          const pulseOpacity = Math.max(0, 0.55 * (1 - pulseT)) * prog;
          return (
            <g key={p.id} opacity={prog}>
              <circle cx={x} cy={y} r={pulseR} fill="none" stroke={COLORS.red} strokeWidth={2.5 / zoom.scale} opacity={pulseOpacity} />
              <circle cx={x} cy={y} r={r * 2.2} fill={COLORS.red} opacity={0.18} />
              <circle cx={x} cy={y} r={r} fill={COLORS.red} stroke={COLORS.parchmentLight} strokeWidth={3} />
              {!data.hide_words && <text
                x={x}
                y={y - 18}
                textAnchor="middle"
                fontFamily={FONT_HAND}
                fontSize={format === "long" ? 40 : 38}
                fill={COLORS.ink}
                style={{ paintOrder: "stroke", stroke: COLORS.parchmentLight, strokeWidth: 5 }}
              >
                {p.label}
              </text>}
            </g>
          );
        })}
      </svg>
      </div>
    </div>
  );
};

function regionLabel(r: MapRegion) {
  const map: Record<string, string> = {
    world: "Карта мира",
    egypt: "Египет",
    mediterranean: "Средиземноморье",
    middle_east: "Ближний Восток",
    south_america: "Южная Америка",
    mesoamerica: "Мезоамерика",
    europe: "Европа",
    asia: "Азия",
    russia: "Россия",
  };
  return map[r] ?? "";
}
