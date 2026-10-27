#!/usr/bin/env node
// node render.mjs --job <jobdir> --format long|short --out <file> [--from s --to s]
// --validate-only runs local preflight only (no browser/bundle/output writes).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
import { readScenes, preflight, stageMedia } from './lib/preflight.mjs';
import { renderCodeHash, fingerprint, renderRange, chunkRanges, prepareChunkCache, cachedPartMatches, recordPart } from './lib/chunk-cache.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export function parseArgs(argv) {
  const out = {};
  const allowed = new Set(['job', 'format', 'out', 'from', 'to', 'concurrency', 'chunk-sec', 'qa-frames', 'scenes', 'gl']);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--validate-only') { out['validate-only'] = true; continue; }
    const key = argv[i].slice(2);
    if (!argv[i].startsWith('--') || !allowed.has(key) || argv[i + 1] === undefined || argv[i + 1].startsWith('--')) throw new Error(`Invalid argument ${argv[i]}`);
    out[key] = argv[++i];
  }
  return out;
}
function findHeadlessShell(root) {
  const stack = [root];
  while (stack.length) {
    let entries; const dir = stack.pop();
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { continue; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) stack.push(full);
      else if (e.isFile() && e.name === 'chrome-headless-shell') return full;
    }
  }
  return null;
}
// One frame per drawn scene (its midpoint) + one per media shot (its midpoint),
// named by id so the pipeline can match them back to scenes.json for visual QA.
// atSec is relative to the RENDERED OUTPUT file, not the full composition —
// scenes/shots outside the rendered --from/--to or chunk window are skipped.
export function qaFrameTargets(scenesFile, range, fps) {
  const windowStartSec = range[0] / fps;
  const windowEndSec = (range[1] + 1) / fps;
  const targets = [];
  for (const s of scenesFile.scenes) {
    if (s.type === 'media') {
      for (const shot of s.data.shots || []) {
        const mid = (shot.start + shot.end) / 2;
        if (mid >= windowStartSec && mid < windowEndSec) targets.push({ name: `${s.id}_${shot.id}`, atSec: mid - windowStartSec });
      }
    } else {
      const mid = (s.start + s.end) / 2;
      if (mid >= windowStartSec && mid < windowEndSec) targets.push({ name: s.id, atSec: mid - windowStartSec });
    }
  }
  return targets;
}
export function extractQaFrames(scenesFile, range, fps, outFile, qaDir) {
  fs.mkdirSync(qaDir, { recursive: true });
  const targets = qaFrameTargets(scenesFile, range, fps);
  const files = [];
  for (const t of targets) {
    const dest = path.join(qaDir, `${t.name}.jpg`);
    execFileSync('ffmpeg', ['-y', '-ss', String(t.atSec), '-i', outFile, '-frames:v', '1', '-q:v', '3', dest], { stdio: 'pipe' });
    files.push(dest);
  }
  return files;
}
export function partIsValid(file, expectedFrames) {
  if (!fs.existsSync(file)) return false;
  try {
    const count = Number(execFileSync('ffprobe', ['-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', file], { encoding: 'utf8' }).trim());
    // Exact count: +/-1 per chunk would introduce cumulative jumps in concat.
    return Number.isInteger(count) && count === expectedFrames;
  } catch { return false; }
}
export async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const jobDir = args.job, format = args.format, out = args.out;
  if (!jobDir || !['long', 'short'].includes(format) || (!out && !args['validate-only'])) throw new Error('Usage: --job <jobdir> --format long|short --out <file> [--from s --to s] [--validate-only]');
  const from = args.from === undefined ? undefined : Number(args.from);
  const to = args.to === undefined ? undefined : Number(args.to);
  const concurrency = args.concurrency === undefined ? 1 : Number(args.concurrency);
  if (concurrency !== 1 && !(args.scenes && concurrency === 2)) throw new Error('This renderer is resource-limited: --concurrency must be 1 (2 allowed only with --scenes)');
  const chunkSec = args['chunk-sec'] === undefined ? (format === 'long' ? 120 : 0) : Number(args['chunk-sec']);
  if (!Number.isFinite(chunkSec) || chunkSec < 0) throw new Error('--chunk-sec must be a finite number >= 0');
  // --scenes <файл относительно --job или абсолютный>: самостоятельный шорт (shorts_scenes/shortN.json); медиа-пути считаются от --job.
  const scenesPath = args.scenes ? path.resolve(jobDir, args.scenes) : path.join(jobDir, 'scenes.json');
  const raw = readScenes(scenesPath);
  if (raw.standalone_short) console.log(`STANDALONE short scenes: ${scenesPath}; ${raw.scenes.length} scenes, ${raw.duration_sec}s`);
  const range = renderRange(raw, from, to);
  const totalFrames = range[1] - range[0] + 1;
  if (chunkSec > 0 && Math.round(chunkSec * raw.fps) < 1) throw new Error('--chunk-sec must span at least one frame');
  const checked = await preflight(raw, jobDir);
  for (const warning of checked.warnings) console.warn(`QUALITY ${warning.sceneId} ${warning.code}: ${warning.message}`);
  if (args['validate-only']) {
    console.log(`VALID ${checked.scenesFile.scenes.length} scenes; ${checked.media.length} media; ${checked.warnings.length} warnings; frameRange=${range.join(':')}`);
    return checked;
  }

  // Nothing costly above this line: no texture generation, bundler, Chrome or render.
  const browserRoot = '/home/agent/workspace/.playwright-browsers/chromium_headless_shell-1243';
  const browserExecutable = findHeadlessShell(browserRoot);
  if (!browserExecutable) throw new Error(`chrome-headless-shell not found under ${browserRoot}`);
  const { bundle } = await import('@remotion/bundler');
  const { renderMedia, selectComposition } = await import('@remotion/renderer');
  for (const name of ['gen-textures.mjs', 'gen-maps.mjs']) execFileSync(process.execPath, [path.join(__dirname, 'scripts', name)], { stdio: 'inherit' });
  const codeHash = await renderCodeHash(__dirname);
  const cacheDir = path.join(__dirname, '.cache');
  const bundleDir = path.join(cacheDir, 'bundle');
  const hashFile = path.join(cacheDir, 'bundle-hash.txt');
  fs.mkdirSync(cacheDir, { recursive: true });
  const needBundle = !fs.existsSync(bundleDir) || !fs.existsSync(hashFile) || fs.readFileSync(hashFile, 'utf8').trim() !== codeHash;
  if (needBundle) {
    const built = await bundle({ entryPoint: path.join(__dirname, 'src', 'index.ts'), publicDir: path.join(__dirname, 'public'), onProgress: () => {} });
    fs.rmSync(bundleDir, { recursive: true, force: true });
    fs.cpSync(built, bundleDir, { recursive: true });
    fs.writeFileSync(hashFile, codeHash);
  }
  const scenesFile = stageMedia(checked.scenesFile, checked.media, bundleDir);
  const inputProps = { scenesFile, format, subtitles: format === 'short' && !scenesFile.standalone_short };
  const composition = await selectComposition({ serveUrl: bundleDir, id: 'Main', inputProps, browserExecutable });
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  const options = {
    codec: 'h264', concurrency, muted: true,
    offthreadVideoCacheSizeInBytes: 256 * 1024 * 1024, offthreadVideoThreads: 1,
    imageFormat: 'jpeg', jpegQuality: 82,
    chromiumOptions: { disableWebSecurity: true, gl: args.gl || 'swiftshader' },
  };
  const common = { ...options, composition, serveUrl: bundleDir, inputProps, browserExecutable };
  const ranges = chunkRanges(range, chunkSec ? Math.round(chunkSec * composition.fps) : totalFrames);
  if (ranges.length === 1) {
    await renderMedia({ ...common, outputLocation: out, frameRange: range, onProgress: ({ progress }) => console.log(`PROGRESS ${Math.round(progress * 100)}`) });
  } else {
    // One full composition for EVERY chunk and --from/--to window. Absolute
    // frameRange preserves media position, previous reveals and camera continuity.
    const signature = fingerprint({
      scenesFile: checked.scenesFile, codeHash,
      media: checked.media.map(({ sceneId, sha256, meta }) => ({ sceneId, sha256, meta })),
      options, format, subtitles: inputProps.subtitles, range, ranges,
      composition: { width: composition.width, height: composition.height, fps: composition.fps, durationInFrames: composition.durationInFrames },
    });
    const partsDir = `${out}.parts`;
    const cache = prepareChunkCache(partsDir, signature, ranges);
    const partPath = (i) => path.join(partsDir, `part${String(i).padStart(4, '0')}.mp4`);
    let done = 0;
    for (let i = 0; i < ranges.length; i++) {
      const [start, end] = ranges[i], expected = end - start + 1, file = partPath(i);
      const reusable = await cachedPartMatches(cache, i, file, expected) && partIsValid(file, expected);
      if (!reusable) {
        const temp = `${file}.tmp.mp4`;
        fs.rmSync(temp, { force: true });
        await renderMedia({ ...common, outputLocation: temp, frameRange: [start, end], onProgress: ({ progress }) => console.log(`PROGRESS ${Math.round((done + progress * expected) / totalFrames * 100)}`) });
        if (!partIsValid(temp, expected)) throw new Error(`Chunk ${i}: unexpected frame count; not cached`);
        fs.renameSync(temp, file);
        await recordPart(cache, i, file, expected);
      }
      done += expected;
      console.log(`PROGRESS ${Math.round(done / totalFrames * 100)}`);
    }
    const listFile = path.join(partsDir, 'list.txt');
    const quote = (file) => path.resolve(file).replaceAll("'", "'\\''");
    fs.writeFileSync(listFile, ranges.map((_, i) => `file '${quote(partPath(i))}'`).join('\n'));
    execFileSync('ffmpeg', ['-y', '-f', 'concat', '-safe', '0', '-i', listFile, '-c', 'copy', out], { stdio: 'inherit' });
  }
  console.log('PROGRESS 100');
  console.log(`OK ${out}`);
  if (args['qa-frames']) {
    const files = extractQaFrames(checked.scenesFile, range, composition.fps, out, args['qa-frames']);
    console.log(`QA_FRAMES ${files.length} ${args['qa-frames']}`);
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => { console.error(error?.stack || String(error)); process.exitCode = 1; });
}
