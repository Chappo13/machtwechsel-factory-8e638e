// Типы по контракту ROOT/CONTRACTS.md -> scenes.json

export type Word = { w: string; start: number; end: number };

export type Beat = { id: string; t: number };

export type Chapter = { title: string; start: number };

export type DiaryItem = {
  id: string;
  kind: "text" | "note" | "circle_text" | "arrow" | "underline" | "sketch";
  text?: string;
  sketch?: SketchName;
  from?: string;
  to?: string;
};

export type SketchName =
  | "pyramid"
  | "gear"
  | "skull"
  | "eye"
  | "sphinx"
  | "temple"
  | "stone_block"
  | "ship"
  | "scroll"
  | "star"
  | "globe"
  | "mummy"
  | "moai"
  | "monolith";

export type MapRegion =
  | "world"
  | "egypt"
  | "mediterranean"
  | "middle_east"
  | "south_america"
  | "mesoamerica"
  | "europe"
  | "asia"
  | "russia"
  | "north_atlantic"
  | "north_america"
  | "africa"
  | "south_asia"
  | "east_asia"
  | "black_sea"
  | "west_europe"
  | "east_europe";

export type MapPin = { id: string; label: string; lat: number; lon: number };

export type TimelineEvent = { id: string; year: number; label: string };

export type BlueprintObject =
  | "gear_mechanism"
  | "pyramid_section"
  | "wall_masonry"
  | "obelisk"
  | "generic_artifact";

export type BoardCard = { id: string; title: string; text?: string; textId?: string };
export type BoardLink = { id: string; from: string; to: string; label?: string };

export type DocLine = { id: string; text: string; redact?: string[] };

export type SceneType =
  | "title_card"
  | "diary"
  | "map"
  | "timeline"
  | "blueprint"
  | "board"
  | "document"
  | "scale"
  | "number"
  | "stars"
  | "quote"
  | "media"
  | "compare"
  | "counter"
  | "steps"
  | "fact_stack"
  | "table"
  | "map_route" // карта-маршрут: линия + маркер, английские подписи мест, год числом
  | "tally"; // счётчик предметов силуэтами (корабль/человек/монета/амфора/точка), только числа

export type TallyIconKind = "ship" | "person" | "coin" | "amphora" | "dot";
export type AtmosKind = "snow" | "spray" | "fog" | "dust" | "embers";
export type MapPlace = { lat: number; lon: number; en: string; at?: number }; // en: АНГЛИЙСКОЕ название КАПСОМ

export type StepIcon = "gear" | "flask" | "bolt" | "coin" | "sun" | "water" | "fire" | "hammer" | "scroll" | "eye" | "key" | "ship" | "stone" | "skull";
export type CompareSide = { label: string; caption?: string; src?: string; mediaMeta?: MediaMeta };
export type CounterItem = { id: string; value: number; label: string; unit?: string; from?: number; decimals?: number; plain?: boolean };
export type StepItem = { id: string; label: string; icon?: StepIcon };
export type FactItem = { id: string; big: string; label: string };
export type TableRow = { id: string; cells: string[] };
export type LowerThird = { id: string; title: string; subtitle?: string };

export type MediaAnnotation = {
  id: string;
  kind: "circle" | "arrow" | "label" | "box" | "underline" | "loupe";
  zoom?: number; // только loupe: кратность увеличения 1.5..4 (по умолчанию 2.4)
  // Canonical normalized image coordinates; legacy forms normalize at read boundary.
  bbox: { x: number; y: number; w: number; h: number };
  confidence?: number;
  text?: string;
};

// Метаданные исходника (размеры/длительность), которые дозаполняет render.mjs
// через ffprobe/sharp перед рендером — пайплайну их считать не нужно.
export type Box = { x: number; y: number; w: number; h: number };
// Красный круг (stroke-dashoffset) + стрелка + наезд на деталь РЕАЛЬНОГО фото. Всё в нормализованных координатах картинки 0..1.
export type Callout = {
  circle: { cx: number; cy: number; rx: number; ry: number; rot?: number };
  arrowAngleDeg?: number; // откуда летит стрелка (0 = справа от круга, 90 = снизу), экранные градусы
  arrowLen?: number; // длина в долях ширины картинки
  zoomBox: Box; // деталь, на которую наезжаем
  circleAt: number; // секунды от начала плана
  arrowAt?: number;
  zoomAt: number;
  zoomDur?: number;
  zoomMax?: number;
};
// Фокус-зум: плавный наезд на точку интереса (лицо/предмет) на стилле. box — предмет целиком: зум никогда не обрезает его.
export type FocusZoom = { x: number; y: number; box?: Box; to?: number };

export type MediaMeta = { width: number; height: number; durationSec?: number; sourceFps?: number };

// Один план внутри media-сцены. start/end — АБСОЛЮТНЫЕ секунды от начала ролика
// (как scene.start/end), планы идут подряд без дыр внутри своей сцены. Сцена с
// одним src (legacy) канонизируется в shots:[один план на всю сцену] на границе
// normalizeScenes — downstream-код (Media.tsx, preflight) всегда читает shots.
export type MediaShot = {
  id: string;
  start: number;
  end: number;
  src: string;
  kind?: "video" | "image";
  fit?: "cover" | "contain";
  trimStartSec?: number;
  playbackRate?: number;
  focus?: { x: number; y: number };
  caption?: string;
  credit?: string;
  annotations?: MediaAnnotation[];
  mediaMeta?: MediaMeta; // проставляет preflight
  callout?: Callout; // красный круг + стрелка + наезд (только реальные фото)
  atmos?: { kind: AtmosKind; intensity?: number }; // слой частиц поверх плана
  zoom?: FocusZoom; // фокус-зум на стилле (вместо 2.5D-параллакса)
  // Видео короче слота даже на 0.6x: кадр-стоп-кадр продолжает Ken Burns без рывка.
  // Проставляет preflight; pipeline эти поля не задаёт.
  freezeAtSec?: number; // локальные секунды ПЛАНА, с которых начинается стоп-кадр
  freezeSrc?: string;
};

export type SceneData = {
  hide_words?: boolean; // графика без слов: рендер прячет подписи-слова (число/единица/год остаются)
  // title_card
  title?: string;
  subtitle?: string;
  // diary
  heading?: string;
  items?: DiaryItem[];
  // map
  region?: MapRegion;
  pins?: MapPin[];
  route?: string[];
  // map_route: route_pts проходятся прогрессивно (одна точка = место находки), places — до 3 подписей АНГЛИЙСКИМ КАПСОМ
  route_pts?: { lat: number; lon: number }[];
  places?: MapPlace[];
  marker?: "ship" | "person" | "dot";
  year?: string; // только число/дата латиницей: "941", "5TH CENTURY BC"
  route_from?: number; // сек от начала сцены
  route_to?: number;
  // tally: total силуэтов; remain задан = часть «тонет» (total -> remain), иначе счёт 1..total
  icon?: TallyIconKind;
  total?: number;
  remain?: number;
  tally_at?: number; // сек: когда начинают тонуть
  tally_dur?: number;
  // timeline
  from_year?: number;
  to_year?: number;
  events?: TimelineEvent[];
  // blueprint
  object?: BlueprintObject;
  labels?: { id: string; text: string }[];
  dims?: { id: string; text: string }[];
  // board
  cards?: BoardCard[];
  links?: BoardLink[];
  stamp?: string;
  stampId?: string;
  // document
  date?: string;
  lines?: DocLine[];
  // scale
  subject?: { label: string; size_m: number };
  reference?: { label: string; size_m: number };
  number?: { value: number; unit?: string; label: string };
  // number
  value?: number;
  unit?: string;
  label?: string;
  prefix?: string;
  // stars
  constellation?: "orion" | "big_dipper" | "cygnus" | "pleiades";
  overlay?: "pyramids";
  // quote
  text?: string;
  author?: string;

  // compare
  left?: CompareSide;
  right?: CompareSide;
  mode?: "split" | "slider";
  // counter / steps / fact_stack / table
  steps?: StepItem[];
  facts?: FactItem[];
  columns?: string[];
  rows?: TableRow[];
  // media
  lower_third?: LowerThird;
  src?: string;
  kind?: "video" | "image";
  fit?: "cover" | "contain";
  trimStartSec?: number;
  playbackRate?: number;
  focus?: { x: number; y: number };
  caption?: string;
  credit?: string;
  annotations?: MediaAnnotation[];
  mediaMeta?: MediaMeta; // проставляет render.mjs, в контракте pipeline не участвует
  // Несколько последовательных планов в одной сцене (разные клипы/фото с переходом
  // "под старину" между ними). Канонизируется из одиночного src, если не задано.
  shots?: MediaShot[];
};

export type Scene = {
  id: string;
  type: SceneType;
  start: number;
  end: number;
  data: SceneData;
  beats?: Beat[];
};

export type ScenesFile = {
  fps: number;
  duration_sec: number;
  title: string;
  chapters?: Chapter[];
  words?: Word[];
  overlays?: Overlay[];
  channel_name?: string; // 21.10: водяной знак канала сверху слева; "" = без знака, нет поля = ТАЙНЫ ДРЕВНИХ
  brand_en?: boolean; // мелкая строка SECRETS OF THE ANCIENTS под водяным знаком канала
  chapter_badge?: boolean; // false = не рисовать жёлтую плашку с названием главы (по умолчанию true)
  standalone_short?: boolean; // самостоятельный шорт (shorts_scenes/shortN.json): без глав/слов/оверлеев, оверлеи и субтитры не рисуются
  shorts_subtitles?: boolean; // true = жечь русские субтитры в шортсах (по умолчанию нет: шортсы многоязычные, текст на экране не нужен)
  scenes: Scene[];
};

// Верхнеуровневые оверлеи поверх ролика (опционально; старые scenes.json без поля валидны).
export type AudioHintOverlay = {
  type: "audio_hint";
  start: number; // абсолютные секунды от начала ролика
  end: number;
  langs: string[]; // 2-буквенные коды, например ["RU","EN","ES"]
  position?: "top-right" | "bottom-left";
  subscribe?: boolean; // колонка «Subscribe» (по умолчанию нет — старые файлы не меняются)
  like?: boolean; // колонка «Like»
  size?: "compact" | "large";
  label?: string; // необязательная короткая надпись (напр. "Choose your audio language")
};
// Дата на экране как подкрепление речи (15.10, без слов): «985», «19TH CENTURY», «2560 BC», «5TH CENTURY BC», «40M YEARS AGO», «12,000 YEARS AGO».
export type DateChipOverlay = {
  type: "date_chip";
  start: number;
  end: number;
  text: string; // 1–40 символов, одна строка
  position?: "top-left" | "top-right" | "bottom-left";
  size?: "compact" | "large";
};
export type Overlay = AudioHintOverlay | DateChipOverlay;

export type Format = "long" | "short";

export type MainProps = {
  scenesFile: ScenesFile;
  format: Format;
  subtitles: boolean;
  audioSrc?: string; // только Mac-сборщик; server render.mjs это не передаёт
  audioStartFrame?: number; // глобальный кадр, с которого звучит audioSrc (для шортсов)
};
