// Единый список регионов карты: используют MapScene/RouteMap (проекция пинов) и scripts/gen-maps.mjs (растр подложки).
// spanDeg — сколько градусов долготы видно по меньшей стороне кадра (scale меркатора = minDim / (spanDeg * pi/180)).
// Зеркало для пайплайна: pipeline/code_graphics.py REGIONS (тест сверяет их).
export const REGION_CFG = {
  world: { center: [15, 10], spanDeg: 360 },
  egypt: { center: [31, 27], spanDeg: 16 },
  mediterranean: { center: [18, 35], spanDeg: 55 },
  middle_east: { center: [45, 28], spanDeg: 38 },
  south_america: { center: [-62, -18], spanDeg: 58 },
  mesoamerica: { center: [-92, 17], spanDeg: 32 },
  europe: { center: [15, 50], spanDeg: 46 },
  asia: { center: [95, 32], spanDeg: 110 },
  russia: { center: [95, 61], spanDeg: 140 },
  // 15.10 (кодовая графика): регионы для карт маршрутов/находок
  north_atlantic: { center: [-27, 63.5], spanDeg: 32 },
  north_america: { center: [-100, 45], spanDeg: 70 },
  africa: { center: [20, 3], spanDeg: 80 },
  south_asia: { center: [78, 22], spanDeg: 40 },
  east_asia: { center: [112, 36], spanDeg: 56 },
  black_sea: { center: [34, 44], spanDeg: 20 },
  west_europe: { center: [2, 48], spanDeg: 26 },
  east_europe: { center: [32, 46], spanDeg: 30 },
};
export const MAP_REGIONS = Object.keys(REGION_CFG);
