import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { hashFile } from './preflight.mjs';

export function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).filter((k) => value[k] !== undefined).sort().map((k) => `${JSON.stringify(k)}:${stableJson(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
export function fingerprint(value) { return crypto.createHash('sha256').update(stableJson(value)).digest('hex'); }
export async function renderCodeHash(root) {
  const files = [];
  function walk(dir) {
    if (!fs.existsSync(dir)) return;
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full); else if (e.isFile()) files.push(full);
    }
  }
  for (const dir of ['src', 'lib', 'scripts', 'public']) walk(path.join(root, dir));
  for (const name of ['render.mjs', 'package.json', 'package-lock.json', 'tsconfig.json']) if (fs.existsSync(path.join(root, name))) files.push(path.join(root, name));
  const inputs = [];
  for (const file of files.sort()) inputs.push([path.relative(root, file), await hashFile(file)]);
  return fingerprint(inputs);
}
export function renderRange(file, from, to) {
  const start = from ?? 0;
  let end = to ?? file.duration_sec;
  if (!Number.isFinite(file.duration_sec) || file.duration_sec <= 0 || !Number.isFinite(file.fps) || file.fps < 1 || file.fps > 120) throw new Error('Invalid duration/fps');
  // Legacy shorts rounded to centiseconds: clamp only <=5ms overshoot
  // before quantization, even if that rounding crossed a frame boundary.
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > file.duration_sec + 0.005 + 1e-9) throw new Error('Invalid --from/--to: require 0 <= from < to <= duration_sec (legacy rounding tolerance 0.005s)');
  end = Math.min(end, file.duration_sec);
  if (end <= start) throw new Error('Invalid --from/--to: end must follow start');
  const range = [Math.round(start * file.fps), Math.round(end * file.fps) - 1];
  if (range[1] < range[0]) throw new Error('Selected range contains no frames');
  return range;
}
export function chunkRanges(range, chunkFrames) {
  if (!Number.isInteger(chunkFrames) || chunkFrames < 1) throw new Error('chunkFrames must be a positive integer');
  const ranges = [];
  for (let frame = range[0]; frame <= range[1]; frame += chunkFrames) ranges.push([frame, Math.min(range[1], frame + chunkFrames - 1)]);
  return ranges;
}
export function atomicJson(file, data) {
  const temp = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`;
  try { fs.writeFileSync(temp, `${JSON.stringify(data, null, 2)}\n`); fs.renameSync(temp, file); }
  finally { fs.rmSync(temp, { force: true }); }
}
export function prepareChunkCache(dir, signature, ranges) {
  fs.mkdirSync(dir, { recursive: true });
  const manifestPath = path.join(dir, 'manifest.json');
  let previous;
  try { previous = JSON.parse(fs.readFileSync(manifestPath, 'utf8')); } catch { /* pre-manifest or corrupt cache: never trust */ }
  const reusable = previous?.version === 1 && previous.fingerprint === signature && stableJson(previous.ranges) === stableJson(ranges);
  const manifest = reusable ? { ...previous, parts: previous.parts || {} } : { version: 1, fingerprint: signature, ranges, parts: {} };
  if (!reusable) {
    // Remove only our generated chunks, never arbitrary job files.
    for (const name of fs.readdirSync(dir)) if (/^part\d+\.mp4(?:\.tmp\.mp4)?$/.test(name) || name === 'list.txt') fs.rmSync(path.join(dir, name), { force: true });
  }
  atomicJson(manifestPath, manifest);
  return { manifest, manifestPath, reusable };
}
export async function cachedPartMatches(cache, index, file, expectedFrames) {
  const part = cache.manifest.parts[index];
  if (!part || part.frames !== expectedFrames || !fs.existsSync(file)) return false;
  return part.sha256 === await hashFile(file);
}
export async function recordPart(cache, index, file, frames) {
  cache.manifest.parts[index] = { frames, sha256: await hashFile(file) };
  atomicJson(cache.manifestPath, cache.manifest);
}
