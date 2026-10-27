import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import sharp from 'sharp';
import { normalizeScenes, resolveShotPlayback, qualityWarnings } from '../src/utils/quality.mjs';

// Самостоятельный шорт: флаг "standalone_short": true в файле ИЛИ путь shorts_scenes/… / shortN.json.
export function isStandalonePath(file) { return /(^|[\\/])shorts_scenes[\\/]/i.test(String(file)) || /(^|[\\/])short\d+\.json$/i.test(String(file)); }
export function isStandaloneShort(raw, file) { return raw?.standalone_short === true || (raw?.standalone_short !== false && !!file && isStandalonePath(file)); }
// Читает scenes-файл; для самостоятельного шорта (флаг или путь) выставляет standalone_short=true, чтобы Main не рисовал плашки.
export function readScenes(file) {
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (isStandaloneShort(raw, file)) raw.standalone_short = true;
  return normalizeScenes(raw);
}
export async function hashFile(file) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}
export function parseVideoProbe(j, where = 'video') {
  const stream = j.streams?.[0];
  if (!stream?.width || !stream?.height) throw new Error(`${where}: no decodable video stream/dimensions`);
  const fraction = (v) => { const [n, d = 1] = String(v).split('/').map(Number); return d ? n / d : NaN; };
  const sourceFps = fraction(stream.avg_frame_rate) || fraction(stream.r_frame_rate);
  // Never trust format.duration: audio can outlive the last video frame.
  // For WebM/unknown stream duration, inspect video packet endpoints instead.
  const packets = (j.packets || []).filter((p) => Number.isFinite(Number(p.pts_time)));
  const packetStart = Number.isFinite(Number(stream.start_time)) ? Number(stream.start_time) : packets.reduce((min, p) => Math.min(min, Number(p.pts_time)), Infinity);
  const packetDuration = packets.length ? packets.reduce((max, p) => Math.max(max, Number(p.pts_time) + (Number(p.duration_time) || 1 / sourceFps)), -Infinity) - packetStart : NaN;
  const candidates = [Number(stream.duration), Number(stream.duration_ts) * fraction(stream.time_base), packetDuration];
  const durationSec = candidates.find((d) => Number.isFinite(d) && d > 0);
  if (!durationSec || !Number.isFinite(sourceFps) || sourceFps <= 0) throw new Error(`${where}: cannot determine video duration/frame rate`);
  return { width: stream.width, height: stream.height, durationSec, sourceFps };
}
export async function inspectMedia(file, kind) {
  if (kind === 'video') {
    const j = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration,duration_ts,time_base,start_time,avg_frame_rate,r_frame_rate', '-of', 'json', file], { encoding: 'utf8' }));
    const stream = j.streams?.[0];
    if (stream && !(Number(stream.duration) > 0) && !(Number(stream.duration_ts) > 0)) {
      const packets = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_packets', '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', file], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }));
      j.packets = packets.packets;
    }
    return parseVideoProbe(j, file);
  }
  const info = await sharp(file).metadata();
  if (!info.width || !info.height) throw new Error(`${file}: cannot determine image dimensions`);
  const rotated = [5, 6, 7, 8].includes(info.orientation);
  return { width: rotated ? info.height : info.width, height: rotated ? info.width : info.height };
}

// Complete before texture generation, bundling, Chrome or rendering. Inject probe
// in tests; default implementation is local ffprobe/sharp only. No writes — a
// video shorter than its shot slot is resolved into a slowdown/freeze fallback
// (never a loop, never a hard failure) and reported as a warning, not thrown.
export async function preflight(input, jobDir, probe = inspectMedia) {
  const scenesFile = normalizeScenes(input);
  const shots = scenesFile.scenes.filter((s) => s.type === 'media').flatMap((s) => (s.data.shots || []).map((shot) => ({ scene: s, shot })));
  const files = shots.map(({ scene, shot }) => {
    if (/^[a-z]+:\/\//i.test(shot.src)) throw new Error(`scene ${scene.id} shot ${shot.id}: media must be an existing local file`);
    const absolutePath = path.resolve(jobDir, shot.src);
    if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) throw new Error(`scene ${scene.id} shot ${shot.id}: media not found: ${absolutePath}`);
    return { scene, shot, absolutePath };
  });
  const media = [];
  const warnings = [];
  const seen = new Map();
  for (const { scene, shot, absolutePath } of files) {
    const key = `${shot.kind}:${absolutePath}`;
    if (!seen.has(key)) seen.set(key, { meta: await probe(absolutePath, shot.kind), sha256: await hashFile(absolutePath) });
    const { meta, sha256 } = seen.get(key);
    if (shot.kind === 'video') {
      const resolved = resolveShotPlayback(shot, scenesFile.fps, meta);
      shot.playbackRate = resolved.rate;
      if (resolved.fallback === 'slowdown') warnings.push({ sceneId: scene.id, code: 'video-slowdown-fallback', elementId: shot.id, message: `shot ${shot.id}: source too short for its slot; slowed to ${resolved.rate.toFixed(3)}x to fill it without looping.` });
      if (resolved.fallback === 'freeze') {
        shot.freezeAtSec = resolved.freezeAtSec;
        warnings.push({ sceneId: scene.id, code: 'video-freeze-fallback', elementId: shot.id, message: `shot ${shot.id}: source too short even at 0.6x; freezing the last frame from ${resolved.freezeAtSec.toFixed(3)}s (Ken Burns keeps moving) instead of looping.` });
      }
    }
    shot.mediaMeta = meta;
    media.push({ sceneId: scene.id, shotId: shot.id, absolutePath, sha256, meta, kind: shot.kind, freezeAtSec: shot.freezeAtSec, trimStartSec: shot.trimStartSec });
  }
  // compare: optional still images per side (data.left.src / data.right.src), images only.
  for (const scene of scenesFile.scenes.filter((x) => x.type === 'compare')) {
    for (const side of ['left', 'right']) {
      const src = scene.data[side]?.src;
      if (!src) continue;
      if (/^[a-z]+:\/\//i.test(src)) throw new Error(`scene ${scene.id} ${side}: media must be an existing local file`);
      if (/\.(mp4|mov|webm|m4v)$/i.test(src)) throw new Error(`scene ${scene.id} ${side}: compare supports images only`);
      const absolutePath = path.resolve(jobDir, src);
      if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) throw new Error(`scene ${scene.id} ${side}: media not found: ${absolutePath}`);
      const key = `image:${absolutePath}`;
      if (!seen.has(key)) seen.set(key, { meta: await probe(absolutePath, 'image'), sha256: await hashFile(absolutePath) });
      const { meta, sha256 } = seen.get(key);
      scene.data[side].mediaMeta = meta;
      media.push({ sceneId: scene.id, side, absolutePath, sha256, meta, kind: 'image' });
    }
  }
  return { scenesFile, media, warnings: [...warnings, ...qualityWarnings(scenesFile)] };
}

export function stageMedia(scenesFile, media, bundleLocation) {
  const staged = structuredClone(scenesFile);
  const mediaDir = path.join(bundleLocation, 'media-job');
  fs.mkdirSync(mediaDir, { recursive: true });
  for (const item of media) {
    // Content-addressed filename: safe even with arbitrary scene ids and same basename.
    const name = `${item.sha256}${path.extname(item.absolutePath).toLowerCase()}`;
    const dest = path.join(mediaDir, name);
    if (!fs.existsSync(dest)) fs.copyFileSync(item.absolutePath, dest);
    if (item.side) { staged.scenes.find((s) => s.id === item.sceneId).data[item.side].src = `/media-job/${name}`; continue; }
    const shot = staged.scenes.find((s) => s.id === item.sceneId).data.shots.find((sh) => sh.id === item.shotId);
    shot.src = `/media-job/${name}`;
    if (item.freezeAtSec !== undefined) {
      const freezeName = `${item.sha256}_freeze.jpg`;
      const freezeDest = path.join(mediaDir, freezeName);
      if (!fs.existsSync(freezeDest)) {
        // freezeAtSec is OUTPUT-timeline seconds (how long the slowed-down
        // playback runs before the source is exhausted) — NOT a position in the
        // source file. The frame to freeze on is simply near the end of the
        // source's available (post-trim) range, a few ms inside it to avoid
        // seeking exactly at/after EOF (which yields zero frames from some demuxers).
        const trim = item.trimStartSec || 0;
        const at = Math.max(trim, (item.meta?.durationSec ?? trim) - 0.05);
        execFileSync('ffmpeg', ['-y', '-ss', String(at), '-i', item.absolutePath, '-frames:v', '1', '-q:v', '2', freezeDest], { stdio: 'pipe' });
        if (!fs.existsSync(freezeDest)) throw new Error(`freeze-frame extraction failed for shot ${item.shotId} (scene ${item.sceneId}) at ${at}s`);
      }
      shot.freezeSrc = `/media-job/${freezeName}`;
    }
  }
  return staged;
}
