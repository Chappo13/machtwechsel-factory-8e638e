#!/usr/bin/env node
// Сборка готовых роликов на Mac (Apple Silicon) из пакета, который собирает
// пайплайн. Запускается через двойной клик по "Собрать ролик.command" на
// рабочем столе (создаётся setup.sh) либо вручную:
//   node mac/tainy-build.mjs [путь к tainy-*.zip | путь к уже распакованной папке]
//
// Отличия от серверного render.mjs (тот рассчитан на общий перегруженный
// Linux-сервер и держит concurrency=1): здесь рендерим локально на мощном Mac
// со вшитым звуком, более высоким качеством (crf~18) и используем столько
// ядер, сколько разумно отдать под один рендер.
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RENDER_DIR = path.resolve(__dirname, ".."); // render/mac/.. = render/
const IS_MAC = process.platform === "darwin";
const HOME = os.homedir();
const TAINY_DIR = path.join(HOME, "Tainy");
const VERSION_FILE = path.join(TAINY_DIR, ".render_version");
const LOG_DIR = path.join(TAINY_DIR, "logs");

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`;
}

fs.mkdirSync(LOG_DIR, { recursive: true });
const logFile = path.join(LOG_DIR, `build-${stamp()}.log`);
const logStream = fs.createWriteStream(logFile, { flags: "a" });
function log(line) {
  const text = typeof line === "string" ? line : String(line);
  process.stdout.write(text + "\n");
  logStream.write(text + "\n");
}
function fail(message, error) {
  log("");
  log(`ОШИБКА: ${message}`);
  if (error) log(String(error?.stack || error));
  log(`Подробности — в файле: ${logFile}`);
  if (IS_MAC) {
    try {
      execFileSync("osascript", ["-e", `display notification "${message.replace(/"/g, "'")}" with title "Тайны Древних — ошибка"`]);
    } catch { /* уведомление необязательно */ }
  }
  process.exitCode = 1;
}

function fmtEta(sec) {
  if (!Number.isFinite(sec) || sec < 0) return "считаю…";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m <= 0) return `${s} с`;
  return `${m} мин ${s} с`;
}

function sanitizeFilename(name) {
  return String(name || "ролик").replace(/[\/:\\?*"<>|]/g, " ").replace(/\s+/g, " ").trim().slice(0, 120) || "ролик";
}

function findLatestZip(downloadsDir) {
  if (!fs.existsSync(downloadsDir)) return null;
  const candidates = fs.readdirSync(downloadsDir)
    .filter((f) => /^tainy-.*\.zip$/i.test(f))
    .map((f) => ({ f, t: fs.statSync(path.join(downloadsDir, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  return candidates.length ? path.join(downloadsDir, candidates[0].f) : null;
}

function unzip(zipPath, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  execFileSync("unzip", ["-o", "-q", zipPath, "-d", destDir], { stdio: "inherit" });
}

function readJsonIfExists(file) {
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8"));
}

async function ensureRenderProject(manifest) {
  const installed = fs.existsSync(VERSION_FILE) ? fs.readFileSync(VERSION_FILE, "utf-8").trim() : null;
  const wanted = manifest?.render_version ? String(manifest.render_version) : null;
  const projectMissing = !fs.existsSync(path.join(RENDER_DIR, "package.json")) || !fs.existsSync(path.join(RENDER_DIR, "node_modules"));
  if (!wanted) {
    log("В manifest.json нет render_version — пропускаю проверку версии рендера.");
    return;
  }
  if (installed === wanted && !projectMissing) {
    log(`Версия рендера актуальна (${wanted}).`);
    return;
  }
  log(`Версия рендера изменилась (было: ${installed ?? "нет"}, стало: ${wanted}) — обновляю...`);
  const setupScript = path.join(RENDER_DIR, "mac", "setup.sh");
  if (!fs.existsSync(setupScript)) {
    log("Внимание: mac/setup.sh не найден рядом — обновление пропущено, использую то, что уже установлено.");
    return;
  }
  execFileSync("bash", [setupScript], { stdio: "inherit" });
  fs.mkdirSync(TAINY_DIR, { recursive: true });
  fs.writeFileSync(VERSION_FILE, wanted);
  log("Рендер обновлён.");
}

function describeMetadata(pack) {
  const metaJson = readJsonIfExists(path.join(pack, "metadata.json"));
  const metaTxtPath = path.join(pack, "metadata.txt");
  if (fs.existsSync(metaTxtPath)) return fs.readFileSync(metaTxtPath, "utf-8");
  if (!metaJson) return "";
  const lines = [];
  if (metaJson.titles?.length) { lines.push("Варианты заголовка:"); for (const t of metaJson.titles) lines.push(`- ${t}`); lines.push(""); }
  if (metaJson.description) { lines.push("Описание:", metaJson.description, ""); }
  if (metaJson.tags?.length) { lines.push("Теги: " + metaJson.tags.join(", "), ""); }
  if (metaJson.chapters?.length) {
    lines.push("Главы:");
    for (const c of metaJson.chapters) {
      const t = Number(c.t) || 0;
      const mm = Math.floor(t / 60), ss = String(Math.round(t % 60)).padStart(2, "0");
      lines.push(`${mm}:${ss} ${c.title}`);
    }
  }
  return lines.join("\n");
}

function pickCoverThumb(pack, manifest, metaJson) {
  const thumbsDir = path.join(pack, "thumbs");
  if (!fs.existsSync(thumbsDir)) return null;
  const files = fs.readdirSync(thumbsDir).filter((f) => /\.(png|jpe?g)$/i.test(f)).sort();
  if (!files.length) return null;
  const chosenName = manifest?.chosenThumb || manifest?.cover || metaJson?.chosenThumb || metaJson?.cover || metaJson?.thumbnail;
  if (chosenName && files.includes(chosenName)) return chosenName;
  return files[0];
}

async function renderOne({ label, outFile, scenesFile, format, frameRange, audioSrc, audioStartFrameAbs, bundleLocation, concurrency, subtitles = format === "short" }) {
  const { renderMedia, selectComposition } = await import("@remotion/renderer");
  const inputProps = { scenesFile, format, subtitles, audioSrc, audioStartFrame: audioStartFrameAbs };
  const composition = await selectComposition({ serveUrl: bundleLocation, id: "Main", inputProps });

  const common = {
    composition,
    serveUrl: bundleLocation,
    codec: "h264",
    crf: 18,
    concurrency,
    muted: !audioSrc,
    audioCodec: audioSrc ? "aac" : undefined,
    audioBitrate: audioSrc ? "192k" : undefined,
    imageFormat: "jpeg",
    jpegQuality: 90,
    inputProps,
    outputLocation: outFile,
    frameRange,
  };

  const start = Date.now();
  let lastPrinted = -1;
  const onProgress = ({ progress }) => {
    const pct = Math.round(progress * 100);
    if (pct === lastPrinted) return;
    lastPrinted = pct;
    const elapsed = (Date.now() - start) / 1000;
    const rate = progress > 0.01 ? progress / elapsed : 0;
    const eta = rate > 0 ? (1 - progress) / rate : NaN;
    log(`Рендер «${label}»: ${pct}% (осталось ~${fmtEta(eta)})`);
  };

  try {
    await renderMedia({ ...common, chromiumOptions: { gl: "angle" }, onProgress });
  } catch (e) {
    log(`Не получилось с gl=angle (${e?.message || e}), пробую gl=swiftshader...`);
    await renderMedia({ ...common, chromiumOptions: { gl: "swiftshader" }, onProgress });
  }
  log(`«${label}» готов: ${outFile}`);
}

async function main() {
  log(`=== ${new Date().toLocaleString("ru-RU")} Сборка ролика ===`);
  // версия самого скрипта (аудит M6): видно, обновился ли Mac, когда сервер менял mac/tainy-build.mjs
  try {
    const selfHash = crypto.createHash("sha256").update(fs.readFileSync(fileURLToPath(import.meta.url))).digest("hex").slice(0, 12);
    const inst = fs.existsSync(VERSION_FILE) ? fs.readFileSync(VERSION_FILE, "utf-8").trim() : "нет";
    log(`tainy-build.mjs версия скрипта: ${selfHash}; установленная версия рендера: ${inst}`);
  } catch { /* версия необязательна */ }
  const argPath = process.argv[2];

  let zipPath = null;
  let packDirInput = null;
  if (argPath) {
    const resolved = path.resolve(argPath);
    if (fs.statSync(resolved).isDirectory()) packDirInput = resolved;
    else zipPath = resolved;
  } else {
    zipPath = findLatestZip(path.join(HOME, "Downloads"));
    if (!zipPath) throw new Error("В папке Загрузки не найден архив tainy-*.zip. Скачайте его и запустите снова (или перетащите файл на ярлык).");
  }

  const workDir = path.join(TAINY_DIR, ".work", stamp());
  let pack = packDirInput;
  if (zipPath) {
    log(`Нашёл архив: ${zipPath}`);
    log("Распаковываю...");
    unzip(zipPath, workDir);
    pack = workDir;
    // архив может содержать общий подкаталог — поднимаем, если так
    if (!fs.existsSync(path.join(pack, "scenes.json"))) {
      const entries = fs.readdirSync(pack);
      const sub = entries.find((e) => fs.statSync(path.join(pack, e)).isDirectory() && fs.existsSync(path.join(pack, e, "scenes.json")));
      if (sub) pack = path.join(pack, sub);
    }
  }
  if (!fs.existsSync(path.join(pack, "scenes.json"))) throw new Error(`В пакете нет scenes.json: ${pack}`);

  const manifest = readJsonIfExists(path.join(pack, "manifest.json"));
  if (manifest?.render_version) log(`manifest.render_version: ${manifest.render_version}`);
  if (manifest?.render_only && !process.env.TAINY_ONLY) log(`manifest.render_only=${manifest.render_only}`);
  // Защита от русского звука вместо основного языка: пак собран, пока дубляж основного языка не был готов.
  const pLang = String(manifest?.primary_language || "").toLowerCase();
  if (pLang && pLang !== "ru" && manifest?.primary_ready === false) {
    const only = process.env.TAINY_ONLY || manifest?.render_only || null;
    if (!(only === "shorts" && manifest?.primary_shorts_ready === true)) {
      const L = pLang.toUpperCase();
      log("");
      log("##############################################################");
      log(`  СТОП: в этом паке основной язык (${L}) ещё не готов, звук длинного ролика был бы русским. Скачай свежий пак, когда сервер напишет, что готово.`);
      log("##############################################################");
      if (IS_MAC) {
        try {
          execFileSync("osascript", ["-e", `display alert "СТОП: пак не готов" message "Основной язык (${L}) ещё не готов, звук был бы русским. Скачай свежий пак, когда сервер напишет, что готово."`]);
        } catch { /* окно необязательно */ }
      }
      logStream.end(() => process.exit(2));
      return;
    }
    log(`Основной язык (${pLang.toUpperCase()}) для длинного не готов, но озвучка шортсов готова: рендерю только шортсы (TAINY_ONLY=shorts).`);
  }
  await ensureRenderProject(manifest);

  if (!fs.existsSync(path.join(RENDER_DIR, "node_modules"))) {
    throw new Error("Проект рендера не установлен (нет node_modules). Запустите mac/setup.sh.");
  }

  const scenesFileRaw = JSON.parse(fs.readFileSync(path.join(pack, "scenes.json"), "utf-8"));
  const shorts = readJsonIfExists(path.join(pack, "shorts.json")) || [];
  const metaJson = readJsonIfExists(path.join(pack, "metadata.json"));
  const title = metaJson?.titles?.[0] || scenesFileRaw.title || "ролик";

  // --- подготовка рендер-движка: валидация + стадирование медиа (те же
  // чистые/IO-функции, что использует серверный render.mjs — поведение
  // идентично, никакого отдельного пути валидации для Mac) ---
  const { normalizeScenes } = await import(path.join(RENDER_DIR, "src", "utils", "quality.mjs"));
  const { preflight, stageMedia } = await import(path.join(RENDER_DIR, "lib", "preflight.mjs"));
  const { bundle } = await import("@remotion/bundler");

  const canonical = normalizeScenes(scenesFileRaw);
  log("Проверяю сцены и медиа (preflight)...");
  const checked = await preflight(canonical, pack);
  for (const w of checked.warnings) log(`  [проверка] ${w.sceneId} ${w.code}: ${w.message}`);

  log("Собираю проект рендера (bundle)...");
  const bundleLocation = await bundle({ entryPoint: path.join(RENDER_DIR, "src", "index.ts"), publicDir: path.join(RENDER_DIR, "public"), onProgress: () => {} });
  const stagedScenesFile = stageMedia(checked.scenesFile, checked.media, bundleLocation);

  // аудио пакета (пред-сведённое) копируем в тот же раздаваемый каталог бандла
  const audioDir = path.join(bundleLocation, "mac-audio");
  fs.mkdirSync(audioDir, { recursive: true });
  function stageAudio(srcRel) {
    const abs = path.join(pack, srcRel);
    if (!fs.existsSync(abs)) return null;
    const name = srcRel.replace(/[\\/]/g, "_");
    fs.copyFileSync(abs, path.join(audioDir, name));
    return `/mac-audio/${name}`;
  }

  const cpus = os.cpus().length || 4;
  const concurrency = Math.max(2, Math.floor(cpus / 2));
  log(`Ядер: ${cpus}, concurrency: ${concurrency}`);

  const dateStr = new Date().toISOString().slice(0, 10);
  const outDir = path.join(HOME, "Movies", "Тайны Древних", `${dateStr} ${sanitizeFilename(title)}`);
  fs.mkdirSync(outDir, { recursive: true });

  // --- ролик целиком ---
  // manifest.render_only: "shorts" — длинный уже отрендерен, делаем только шортсы; "long" — только длинный
  const renderOnly = process.env.TAINY_ONLY || manifest?.render_only || null;
  const longAudio = stageAudio("audio/long.m4a");
  const fps = stagedScenesFile.fps;
  const totalFrames = Math.round(stagedScenesFile.duration_sec * fps);
  if (renderOnly === "shorts") log("Длинный ролик пропускаю (render_only=shorts): рендерю только шортсы.");
  else await renderOne({
    label: "ролик",
    outFile: path.join(outDir, "ролик.mp4"),
    scenesFile: stagedScenesFile,
    format: "long",
    frameRange: [0, totalFrames - 1],
    audioSrc: longAudio,
    audioStartFrameAbs: 0,
    bundleLocation,
    concurrency,
  });

  // --- шортсы ---
  // Два режима на каждый шорт:
  //  - script: свой мини-таймлайн shorts_scenes/shortN.json (standalone_short), рендерим целиком [0, duration*fps-1],
  //    звук audio/shortN.m4a с кадра 0, без субтитров/плашек;
  //  - window (legacy): та же полная композиция длинного, окно кадров [from,to] (ракурс/реплей не сбрасывается на границе окна).
  const scriptMode = manifest?.shorts_mode === "script";
  const manifestScenes = Array.isArray(manifest?.shorts_scenes) ? manifest.shorts_scenes : [];
  const shortsCount = Math.max(shorts.length, manifestScenes.length, scriptMode ? 5 : 0);
  for (let i = 0; i < shortsCount && renderOnly !== "long"; i++) {
    const n = i + 1;
    const rel = manifestScenes[i] || `shorts_scenes/short${n}.json`;
    const scenesAbs = path.join(pack, rel);
    const hasScript = fs.existsSync(scenesAbs);
    if (!hasScript && scriptMode && (manifestScenes[i] || shorts[i])) throw new Error(`shorts_mode=script, но нет файла ${rel} для шорта ${n}`);
    if (!hasScript && !shorts[i]) continue; // нет ни сценария, ни окна — этого шорта в пакете нет
    if (hasScript) {
      const rawShort = JSON.parse(fs.readFileSync(scenesAbs, "utf-8"));
      rawShort.standalone_short = true; // shorts_scenes/shortN.json всегда самостоятельный (флаг в файле необязателен)
      const checkedShort = await preflight(normalizeScenes(rawShort), pack); // та же проверка и пробы медиа, что у длинного
      for (const w of checkedShort.warnings) log(`  [проверка шорт ${n}] ${w.sceneId} ${w.code}: ${w.message}`);
      // stageMedia content-addressed: уже скопированные для длинного/других шортов файлы не копируются повторно
      const stagedShort = stageMedia(checkedShort.scenesFile, checkedShort.media, bundleLocation);
      const sFps = stagedShort.fps;
      const sFrames = Math.round(stagedShort.duration_sec * sFps);
      const shotCount = stagedShort.scenes.reduce((a, sc) => a + (sc.type === "media" ? (sc.data.shots || []).length : 0), 0);
      const shortAudio = stageAudio(`audio/short${n}.m4a`);
      log(`Шорт ${n}: режим script (${rel}), сцен ${stagedShort.scenes.length}, планов ${shotCount}, ${stagedShort.duration_sec.toFixed(2)} с, кадров ${sFrames}${shortAudio ? "" : ", ВНИМАНИЕ: нет audio/short" + n + ".m4a — рендер без звука"}`);
      await renderOne({
        label: `шорт ${n}`,
        outFile: path.join(outDir, `шорт${n}.mp4`),
        scenesFile: stagedShort,
        format: "short",
        frameRange: [0, sFrames - 1],
        audioSrc: shortAudio,
        audioStartFrameAbs: 0,
        bundleLocation,
        concurrency,
        subtitles: false,
      });
      continue;
    }
    const s = shorts[i];
    const from = Number(s.from), to = Number(s.to);
    const startFrame = Math.round(from * fps);
    const endFrame = Math.round(to * fps) - 1;
    const shortAudio = stageAudio(`audio/short${n}.m4a`) || stageAudio(`audio/${s.id}.m4a`);
    log(`Шорт ${n}: режим window (окно ${from}-${to} с длинного ролика), кадры ${startFrame}-${endFrame}`);
    await renderOne({
      label: `шорт ${n}`,
      outFile: path.join(outDir, `шорт${n}.mp4`),
      scenesFile: stagedScenesFile,
      format: "short",
      frameRange: [startFrame, endFrame],
      audioSrc: shortAudio,
      audioStartFrameAbs: startFrame,
      bundleLocation,
      concurrency,
    });
  }

  // --- обложка + остальные превью ---
  const thumbsDir = path.join(pack, "thumbs");
  if (fs.existsSync(thumbsDir)) {
    const chosen = pickCoverThumb(pack, manifest, metaJson);
    for (const f of fs.readdirSync(thumbsDir)) {
      const dest = f === chosen ? "обложка.png" : f;
      fs.copyFileSync(path.join(thumbsDir, f), path.join(outDir, dest));
    }
  }

  // --- описание ---
  const description = describeMetadata(pack);
  if (description) fs.writeFileSync(path.join(outDir, "описание.txt"), description, "utf-8");

  log(`Готово: ${outDir}`);

  if (IS_MAC) {
    try { execFileSync("open", [outDir]); } catch { /* необязательно */ }
    try {
      execFileSync("osascript", ["-e", `display notification "Ролик и шортсы готовы" with title "Тайны Древних" subtitle "${sanitizeFilename(title)}"`]);
    } catch { /* необязательно */ }
  } else {
    log("(open Finder / уведомление пропущены — не macOS)");
  }

  // подчистим временную распаковку архива
  if (zipPath) { try { fs.rmSync(workDir, { recursive: true, force: true }); } catch { /* не критично */ } }
}

main().catch((e) => fail(e?.message || String(e), e));
