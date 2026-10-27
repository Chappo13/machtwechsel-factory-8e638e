import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeScenes, normalizeAnnotation, qualityWarnings, assertVideoDuration, sceneFrames } from '../src/utils/quality.mjs';
import { buildRevealMap, boardTiming, annotationTiming } from '../src/utils/revealTiming.mjs';
import { annotationLabel } from "../src/utils/annotationLabel.mjs";
import { mediaLayout, focusZoomLayout } from '../src/utils/mediaLayout.mjs';
import { fitText } from '../src/utils/autoFitText.mjs';
import { pickSceneTransition, pickShotTransition, planSceneTransitions } from '../src/utils/transitions.mjs';
import { groupWords, activeGroup, activeWordIndex } from '../src/utils/subtitleGroups.mjs';
import { preflight, stageMedia, parseVideoProbe, hashFile } from '../lib/preflight.mjs';
import { fingerprint, stableJson, renderCodeHash, renderRange, chunkRanges, prepareChunkCache, cachedPartMatches, recordPart } from '../lib/chunk-cache.mjs';
import { parseArgs, partIsValid, qaFrameTargets } from '../render.mjs'; // Must NOT start CLI, bundler or browser.
import { execFileSync } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, '../..');
const file = (scene = {}) => ({ fps: 25, duration_sec: 8, title: 'Test', scenes: [{ id: 's', type: 'media', start: 0, end: 8, data: { src: 'clip.mp4', kind: 'video' }, beats: [], ...scene }] });
const box = { x: 0.2, y: 0.2, w: 0.3, h: 0.3 };
function scratch(t) { const dir = fs.mkdtempSync(path.join(here, '.tmp-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true })); return dir; }
function canonical(scene) { return normalizeScenes(file(scene)); }
// Deterministic local fixture clip, owned by this test run only — the shared
// jobs/ stock media is live-edited by other concurrent agents/pipelines, so
// tests must not assert its exact duration/dimensions.
function makeClip(dir, name, seconds, fps = 25) {
  const out = path.join(dir, name);
  execFileSync('ffmpeg', ['-y', '-f', 'lavfi', '-i', `testsrc=size=320x180:rate=${fps}:duration=${seconds}`, '-pix_fmt', 'yuv420p', out], { stdio: 'pipe' });
  return out;
}

test('canonical defaults are explicit and do not mutate input', () => {
  const input = file(), result = normalizeScenes(input);
  const shot = result.scenes[0].data.shots[0];
  assert.equal(shot.fit, 'cover'); assert.equal(shot.trimStartSec, 0); assert.equal(shot.playbackRate, 1);
  assert.equal(input.scenes[0].data.fit, undefined);
  assert.deepEqual(normalizeScenes(result), result);
});
test('multiple shots must tile the scene exactly; gaps/overlaps and non-contiguous shots are rejected', () => {
  const shots = [
    { id: 'a', start: 0, end: 3, src: 'a.jpg' },
    { id: 'b', start: 3, end: 5, src: 'b.mp4' },
    { id: 'c', start: 5, end: 8, src: 'c.jpg' },
  ];
  const ok = canonical({ data: { shots } });
  assert.equal(ok.scenes[0].data.shots.length, 3);
  assert.equal(ok.scenes[0].data.shots[1].kind, 'video'); assert.equal(ok.scenes[0].data.shots[0].kind, 'image');
  assert.throws(() => canonical({ data: { shots: [{ id: 'a', start: 0, end: 3, src: 'a.jpg' }, { id: 'b', start: 3.5, end: 8, src: 'b.jpg' }] } }), /gap\/overlap/);
  assert.throws(() => canonical({ data: { shots: [{ id: 'a', start: 0, end: 3, src: 'a.jpg' }, { id: 'b', start: 2, end: 8, src: 'b.jpg' }] } }), /gap\/overlap/);
  assert.throws(() => canonical({ data: { shots: [{ id: 'a', start: 0, end: 5, src: 'a.jpg' }] } }), /tile the scene exactly/);
  assert.throws(() => canonical({ data: { shots: [{ id: 'a', start: 0, end: 3, src: 'a.jpg' }, { id: 'a', start: 3, end: 8, src: 'b.jpg' }] } }), /duplicate id/);
  assert.throws(() => canonical({ data: { shots: [] } }), /at least one shot/);
});
test('a legacy single src is canonicalized into exactly one shot spanning the whole scene', () => {
  const s = canonical({ data: { src: 'x.mp4', caption: 'hello' } }).scenes[0].data;
  assert.equal(s.shots.length, 1); assert.equal(s.shots[0].start, 0); assert.equal(s.shots[0].end, 8); assert.equal(s.shots[0].caption, 'hello');
  assert.equal(s.src, undefined); assert.equal(s.caption, undefined);
});
test('legacy array bbox -> canonical top-left/size + label; canonical kind required', () => {
  const a = normalizeAnnotation({ id: 'a', bbox: [0.83, 0.25, 0.97, 0.67], text: 'artifact' });
  assert.equal(a.kind, 'label'); assert.equal(a.bbox.x, 0.83); assert.ok(Math.abs(a.bbox.w - 0.14) < 1e-10);
  assert.throws(() => normalizeAnnotation({ id: 'a', bbox: box }), /kind required/);
  assert.deepEqual(normalizeAnnotation(a), a);
});
test('flat legacy coordinates use centers, then become canonical', () => {
  const a = normalizeAnnotation({ id: 'a', kind: 'circle', x: 0.5, y: 0.5, w: 0.2, h: 0.4 });
  assert.deepEqual(a.bbox, { x: 0.4, y: 0.3, w: 0.2, h: 0.4 }); assert.ok(!('x' in a));
});
for (const [name, bbox] of Object.entries({ reversed: [0.8, 0.1, 0.2, 0.5], nan: { ...box, x: NaN }, infinity: { ...box, w: Infinity }, string: { ...box, h: '0.2' }, negative: { ...box, x: -0.1 }, zero: { ...box, w: 0 }, outside: { ...box, w: 0.9 }, wrongLength: [0, 0, 1] })) {
  test(`reject invalid bbox: ${name}`, () => assert.throws(() => normalizeAnnotation({ id: 'a', kind: 'label', bbox }), /bbox|finite/));
}
for (const [name, data] of Object.entries({ trimNegative: { trimStartSec: -1 }, trimNan: { trimStartSec: NaN }, speedZero: { playbackRate: 0 }, speedHuge: { playbackRate: 5 }, speedString: { playbackRate: '1' }, fit: { fit: 'fill' }, focus: { focus: { x: 1.1, y: 0 } }, focusNan: { focus: { x: 0, y: NaN } }, kind: { kind: 'loop' } })) {
  test(`reject invalid media option: ${name}`, () => assert.throws(() => canonical({ data: { src: 'x.mp4', ...data } })));
}
test('reject invalid timeline, scene type and scene IDs', () => {
  for (const s of [{ type: 'unknown' }, { start: 1 }, { end: 0 }, { end: Infinity }, { start: -1 }, { start: 0, end: 0.001 }]) assert.throws(() => canonical(s));
  const f = file(); f.scenes.push({ ...f.scenes[0], start: 8, end: 9 }); f.duration_sec = 9;
  assert.throws(() => normalizeScenes(f), /duplicate id/);
});
test('continuous timeline uses rounded absolute boundaries, rejects actual gaps/overlaps', () => {
  const f = file(); f.scenes = [ { ...f.scenes[0], end: 3.515 }, { ...f.scenes[0], id: 's2', start: 3.515, end: 8 } ];
  const c = normalizeScenes(f); assert.equal(c.scenes.reduce((n, s) => n + sceneFrames(s, 25), 0), 200);
  f.scenes[1].start = 3.6; assert.throws(() => normalizeScenes(f), /gap\/overlap/);
  f.scenes[1].start = 3.4; assert.throws(() => normalizeScenes(f), /gap\/overlap/);
});
test('word alignment overlap across paragraphs is sorted, not rejected', () => {
  // Self-contained: jobs/ fixtures are shared with other concurrently-running
  // agents/pipelines and can be rewritten or deleted mid-run (observed in practice),
  // so this must not depend on their presence/content.
  const f = file();
  f.words = [{ w: 'a', start: 2, end: 2.5 }, { w: 'b', start: 0.5, end: 1 }, { w: 'c', start: 1.5, end: 2 }];
  const c = normalizeScenes(f);
  assert.deepEqual(c.words.map((w) => w.w), ['b', 'c', 'a']);
  assert.ok(c.words.every((w, i) => i === 0 || w.start >= c.words[i - 1].start));
});
const board = { cards: [{ id: 'a', title: 'A', text: 'Detail', textId: 'a_text' }, { id: 'b', title: 'B' }], links: [{ id: 'wire', from: 'a', to: 'b' }], stamp: 'Evidence', stampId: 'verdict' };
test('element and beat IDs unique per scene, links must resolve, beats must target elements within bounds', () => {
  for (const beats of [[{ id: 'nope', t: 1 }], [{ id: 'a', t: -1 }], [{ id: 'a', t: 8 }], [{ id: 'a', t: 7.999 }], [{ id: 'a', t: NaN }], [{ id: 'a', t: 1 }, { id: 'a', t: 2 }]]) assert.throws(() => canonical({ type: 'board', data: board, beats }));
  assert.throws(() => canonical({ type: 'board', data: { cards: [{ id: 'a' }, { id: 'a' }] } }), /duplicate id/);
  assert.throws(() => canonical({ type: 'board', data: { cards: [{ id: 'a' }], links: [{ id: 'l', from: 'a', to: 'missing' }] } }), /missing card/);
  assert.throws(() => canonical({ type: 'board', data: { cards: [{ id: 'a', textId: 'a' }] } }), /textId|duplicate/);
});
test('absolute beat frames align exactly with rounded scene boundaries', () => {
  assert.equal(buildRevealMap(['a'], [{ id: 'a', t: 3.53 }], 3.515, 25).a, 0);
  assert.equal(buildRevealMap(['a'], [{ id: 'a', t: 3.56 }], 3.515, 25).a, 1);
});
test('explicit link beat is independent, textId reveals detail separately, stamp beat supported', () => {
  const b = boardTiming(board, [{ id: 'a', t: 10 }, { id: 'b', t: 11 }, { id: 'a_text', t: 12 }, { id: 'wire', t: 14 }, { id: 'verdict', t: 15 }], 10, 25, 200);
  assert.equal(b.card.a, 0); assert.equal(b.card.b, 25); assert.equal(b.text.a_text, 50); assert.equal(b.link.wire, 100); assert.equal(b.stamp, 125); assert.ok(b.pullBack < 200);
});
test('a link or detail cannot appear before its card; warn about clamped explicit wire', () => {
  const beats = [{ id: 'a', t: 2 }, { id: 'b', t: 3 }, { id: 'wire', t: 1 }, { id: 'a_text', t: 1 }];
  const b = boardTiming(board, beats, 0, 25, 200); assert.equal(b.link.wire, 75); assert.equal(b.text.a_text, 50);
  assert.ok(qualityWarnings(canonical({ type: 'board', data: board, beats })).some((w) => w.code === 'link-before-card'));
});
test('Board pullback and stamp use local 6-second duration even at late absolute scene start', () => {
  const b = boardTiming({ cards: [{ id: 'a' }], stamp: 'X' }, [{ id: 'a', t: 60 }], 60, 25, 150);
  assert.equal(b.stamp, 83); assert.equal(b.pullBack, 117);
});
test('explicit annotation beats are not delayed by caption; only missing beats stagger after caption', () => {
  const d = { caption: 'Explanation', annotations: [{ id: 'a' }, { id: 'b' }, { id: 'c' }] };
  const m = annotationTiming(d, [{ id: 'a', t: 10.2 }], 10, 25);
  assert.equal(m.a, 5); assert.equal(m.b, 25); assert.equal(m.c, 34);
});
test('warnings include late evidence, unexplained images and fallback-only evidence', () => {
  const c = canonical({ type: 'media', data: { src: 'x.jpg', annotations: [{ id: 'a', kind: 'label', bbox: box }] }, beats: [{ id: 'a', t: 7.5 }] });
  assert.deepEqual(qualityWarnings(c).map((w) => w.code), ['short-visibility', 'unexplained-image']);
  assert.ok(qualityWarnings(canonical({ type: 'board', data: board })).some((w) => w.code === 'untimed-evidence'));
});
test('stock 8.0667s cannot cover pilot scene 13.675s', () => {
  const s = { id: 'stock', start: 3.5, end: 17.175, data: { trimStartSec: 0, playbackRate: 1 } };
  assert.throws(() => assertVideoDuration(s, 25, { durationSec: 8.0667, sourceFps: 30 }), /video too short.*Loops are forbidden/);
});
test('video duration accounts for trim + playbackRate + rounded absolute frames', () => {
  const s = canonical({ data: { src: 'x.mp4', trimStartSec: 2, playbackRate: 2 } }).scenes[0].data.shots[0];
  assert.doesNotThrow(() => assertVideoDuration(s, 25, { durationSec: 18, sourceFps: 30 }));
  assert.throws(() => assertVideoDuration(s, 25, { durationSec: 17.9, sourceFps: 30 }), /too short/);
  assert.throws(() => assertVideoDuration(s, 25, { durationSec: 2, sourceFps: 30 }), /trim starts/);
});
test('duration rounding tolerance never exceeds one output or one source frame', () => {
  const s = canonical().scenes[0].data.shots[0];
  assert.doesNotThrow(() => assertVideoDuration(s, 25, { durationSec: 7.999999, sourceFps: 30 }));
  assert.throws(() => assertVideoDuration(s, 25, { durationSec: 7.95, sourceFps: 30 }), /too short/);
  const r = assertVideoDuration(s, 25, { durationSec: 8, sourceFps: 60 }); assert.equal(r.tolerance, 1 / 60);
});
test('ffprobe stream duration wins over longer audio/container duration', () => {
  assert.equal(parseVideoProbe({ streams: [{ width: 1920, height: 1080, duration: '8.0667', avg_frame_rate: '30/1' }], format: { duration: '20' } }).durationSec, 8.0667);
  assert.throws(() => parseVideoProbe({ streams: [] }), /no decodable/);
});
test('preflight rejects missing local file before any probe; injected probe stays offline', async (t) => {
  const dir = scratch(t); let probed = false;
  await assert.rejects(preflight(file(), dir, async () => { probed = true; }), /media not found/); assert.equal(probed, false);
  fs.writeFileSync(path.join(dir, 'clip.mp4'), 'fixture bytes, no encoded video');
  const result = await preflight(file(), dir, async () => ({ width: 1920, height: 1080, durationSec: 8.1, sourceFps: 30 }));
  assert.equal(result.media[0].sha256.length, 64); assert.equal(result.scenesFile.scenes[0].data.shots[0].mediaMeta.width, 1920);
  assert.deepEqual(fs.readdirSync(dir), ['clip.mp4']);
});
test('real ffprobe preflight resolves a too-short clip via fallback instead of rejecting', async (t) => {
  const dir = scratch(t);
  const clip = makeClip(dir, 'short.mp4', 3); // 3s source, needs to fill a 10s slot
  const scenesFile = { fps: 25, duration_sec: 10, title: 'T', scenes: [{ id: 's', type: 'media', start: 0, end: 10, data: { src: 'short.mp4' }, beats: [] }] };
  const result = await preflight(scenesFile, dir);
  const shot = result.scenesFile.scenes[0].data.shots[0];
  // 3s source cannot fill a 10s slot even at the 0.6x speed floor (3/0.6=5s): freeze, never loop/crash.
  assert.equal(shot.playbackRate, 0.6);
  assert.ok(shot.freezeAtSec > 4.9 && shot.freezeAtSec < 5.1);
  assert.ok(result.warnings.some((w) => w.code === 'video-freeze-fallback' && w.sceneId === 's'));
  assert.ok(fs.existsSync(clip));
  // stageMedia must actually produce a real, non-empty freeze JPEG by seeking
  // WITHIN the 3s source (not to freezeAtSec=5s, which is output-timeline, past EOF).
  const bundleDir = path.join(dir, 'bundle');
  const staged = stageMedia(result.scenesFile, result.media, bundleDir);
  const stagedShot = staged.scenes[0].data.shots[0];
  assert.match(stagedShot.freezeSrc, /^\/media-job\/.+_freeze\.jpg$/);
  const freezeFile = path.join(bundleDir, stagedShot.freezeSrc.replace('/media-job/', 'media-job/'));
  assert.ok(fs.statSync(freezeFile).size > 500);
});
test('a clip needing only mild slowdown gets the slowdown fallback, not freeze', async (t) => {
  const dir = scratch(t);
  makeClip(dir, 'short.mp4', 6); // 6s source for an 8s slot: 6/8=0.75x, within the 0.6-1 range
  const scenesFile = { fps: 25, duration_sec: 8, title: 'T', scenes: [{ id: 's', type: 'media', start: 0, end: 8, data: { src: 'short.mp4' }, beats: [] }] };
  const result = await preflight(scenesFile, dir);
  const shot = result.scenesFile.scenes[0].data.shots[0];
  assert.ok(Math.abs(shot.playbackRate - 0.75) < 0.01);
  assert.equal(shot.freezeAtSec, undefined);
  assert.ok(result.warnings.some((w) => w.code === 'video-slowdown-fallback' && w.sceneId === 's'));
});
for (const [name, frameW, frameH] of [['landscape', 1920, 1080], ['portrait', 1080, 1920]]) {
  test(`contain preserves FULL artifact and caption safe area in ${name}`, () => {
    for (const p of [0, 0.25, 0.5, 0.75, 1]) {
      const l = mediaLayout({ mediaW: 1036, mediaH: 924, frameW, frameH, fit: 'contain', progress: p, caption: true, format: name === 'portrait' ? 'short' : 'long' });
      assert.equal(l.fit, 'contain'); assert.ok(l.tx >= 0 && l.ty >= frameH * 0.11 - 1e-6);
      assert.ok(l.tx + 1036 * l.scale <= frameW + 1e-6); assert.ok(l.ty + 924 * l.scale <= frameH * 0.76 + 1e-6);
    }
  });
  test(`cover never leaves gaps, even with edge focus in ${name}`, () => {
    for (const focus of [{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 0.5, y: 0.5 }]) for (const p of [0, 0.3, 1]) {
      const l = mediaLayout({ mediaW: 1920, mediaH: 1080, frameW, frameH, focus, progress: p });
      assert.ok(l.tx <= 1e-6 && l.ty <= 1e-6); assert.ok(l.tx + 1920 * l.scale >= frameW - 1e-6); assert.ok(l.ty + 1080 * l.scale >= frameH - 1e-6);
    }
  });
}
test('edge annotations force stable contain fallback instead of cropping key evidence', () => {
  const b = { x: 0.83, y: 0.25, w: 0.14, h: 0.42 };
  for (const p of [0, 0.2, 0.5, 1]) {
    const l = mediaLayout({ mediaW: 1036, mediaH: 924, frameW: 1920, frameH: 1080, annotations: [{ bbox: b }], focus: { x: 0, y: 0 }, progress: p });
    assert.ok(l.tx + b.x * 1036 * l.scale >= 0); assert.ok(l.tx + (b.x + b.w) * 1036 * l.scale <= 1920);
    assert.ok(l.ty + b.y * 924 * l.scale >= 1080 * 0.11 - 1e-6); assert.ok(l.ty + (b.y + b.h) * 924 * l.scale <= 1080 * 0.94 + 1e-6);
  }
});
test('widely separated boxes cannot both fit cover: deterministic contain at ALL frames', () => {
  const annotations = [{ bbox: { x: 0, y: 0, w: 0.1, h: 0.1 } }, { bbox: { x: 0.9, y: 0.9, w: 0.1, h: 0.1 } }];
  const layouts = [0, 0.5, 1].map((progress) => mediaLayout({ mediaW: 1920, mediaH: 1080, frameW: 1080, frameH: 1920, annotations, progress }));
  assert.ok(layouts.every((l) => l.fit === 'contain')); assert.deepEqual(layouts[0], layouts[2]);
});
test('range windows and chunks are contiguous ABSOLUTE composition frames', () => {
  const range = renderRange({ fps: 25, duration_sec: 20 }, 3.5, 17.175);
  assert.deepEqual(range, [88, 428]); assert.deepEqual(chunkRanges(range, 100), [[88, 187], [188, 287], [288, 387], [388, 428]]);
  assert.equal(chunkRanges(range, 100).reduce((n, [s, e]) => n + e - s + 1, 0), 341);
  for (const pair of [[NaN, 10], [10, 9], [-1, 5], [0, 21], [0, 0.001]]) assert.throws(() => renderRange({ fps: 25, duration_sec: 20 }, ...pair));
  assert.throws(() => chunkRanges(range, 0));
});
test('fingerprint covers scenes/code/media bytes/range/options, stable for object key ordering', () => {
  const base = { scenesFile: file(), codeHash: 'v1', media: [{ sha256: 'aaa' }], range: [0, 199], options: { jpegQuality: 82 }, format: 'long' };
  const hash = fingerprint(base);
  for (const key of Object.keys(base)) { const variant = structuredClone(base); variant[key] = { changed: true }; assert.notEqual(fingerprint(variant), hash); }
  assert.equal(fingerprint({ a: 1, b: 2 }), fingerprint({ b: 2, a: 1 })); assert.equal(stableJson({ a: undefined, b: 2 }), '{"b":2}');
});
test('content hash detects equal-size media replacement and source/public/CLI change', async (t) => {
  const dir = scratch(t), media = path.join(dir, 'media'); fs.writeFileSync(media, 'abcd'); const old = await hashFile(media); fs.writeFileSync(media, 'abce'); assert.notEqual(await hashFile(media), old);
  for (const name of ['src/x.ts', 'public/x.png', 'render.mjs', 'lib/x.mjs', 'scripts/gen.mjs', 'package-lock.json']) {
    const p = path.join(dir, name); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, 'before'); const before = await renderCodeHash(dir); fs.writeFileSync(p, 'after!'); assert.notEqual(await renderCodeHash(dir), before);
  }
});
test('old frame-count-only cache is invalid; matching manifest resumes, changes invalidate', async (t) => {
  const dir = scratch(t), p = path.join(dir, 'part0000.mp4'); fs.writeFileSync(p, 'old frames'); fs.writeFileSync(path.join(dir, 'keep.txt'), 'keep');
  let cache = prepareChunkCache(dir, 'v1', [[0, 9]]); assert.equal(cache.reusable, false); assert.equal(fs.existsSync(p), false);
  fs.writeFileSync(p, 'new frames'); await recordPart(cache, 0, p, 10);
  cache = prepareChunkCache(dir, 'v1', [[0, 9]]); assert.equal(cache.reusable, true); assert.ok(await cachedPartMatches(cache, 0, p, 10)); assert.equal(await cachedPartMatches(cache, 0, p, 9), false);
  fs.writeFileSync(p, 'bad frames'); assert.equal(await cachedPartMatches(cache, 0, p, 10), false);
  cache = prepareChunkCache(dir, 'v2', [[0, 9]]); assert.equal(cache.reusable, false); assert.equal(fs.existsSync(p), false); assert.ok(fs.existsSync(path.join(dir, 'keep.txt')));
  assert.ok(!fs.readdirSync(dir).some((n) => n.endsWith('.tmp')));
});
test('corrupt manifest or changed ranges never reuse existing chunks', (t) => {
  const dir = scratch(t); fs.writeFileSync(path.join(dir, 'manifest.json'), '{bad json'); assert.equal(prepareChunkCache(dir, 'x', [[0, 9]]).reusable, false);
  assert.equal(prepareChunkCache(dir, 'x', [[0, 10]]).reusable, false);
});
test('CLI can be imported offline, parses validate-only and rejects malformed args', () => {
  assert.deepEqual(parseArgs(['--job', 'x', '--format', 'long', '--validate-only']), { job: 'x', format: 'long', 'validate-only': true });
  assert.deepEqual(parseArgs(['--job', 'x', '--format', 'long', '--out', 'o.mp4', '--qa-frames', 'qa']), { job: 'x', format: 'long', out: 'o.mp4', 'qa-frames': 'qa' });
  assert.throws(() => parseArgs(['--out'])); assert.throws(() => parseArgs(['--unknown', '1']));
});
test('qa-frame targets are one per drawn scene midpoint + one per media shot midpoint, windowed to the render range', () => {
  const sf = canonical({ type: 'title_card', data: { title: 'x' } });
  sf.scenes = [
    { id: 's1', type: 'title_card', start: 0, end: 2, data: { title: 'x' }, beats: [] },
    { id: 's2', type: 'media', start: 2, end: 6, data: { shots: [{ id: 'sh1', start: 2, end: 4, src: 'a.jpg' }, { id: 'sh2', start: 4, end: 6, src: 'b.jpg' }] }, beats: [] },
  ];
  sf.duration_sec = 6;
  const canon = normalizeScenes(sf);
  const all = qaFrameTargets(canon, [0, 149], 25); // 0..6s, full window
  assert.deepEqual(all.map((t) => t.name), ['s1', 's2_sh1', 's2_sh2']);
  assert.ok(Math.abs(all[0].atSec - 1) < 1e-9); assert.ok(Math.abs(all[1].atSec - 3) < 1e-9); assert.ok(Math.abs(all[2].atSec - 5) < 1e-9);
  const windowed = qaFrameTargets(canon, [50, 149], 25); // render starts at 2s: s1's midpoint (1s) falls outside
  assert.deepEqual(windowed.map((t) => t.name), ['s2_sh1', 's2_sh2']);
  assert.ok(Math.abs(windowed[0].atSec - 1) < 1e-9); // 3s absolute - 2s window start
});
test('duration regression audit: no scene reads global useVideoConfig; no Loop remains', () => {
  for (const name of fs.readdirSync(path.join(here, '../src/scenes')).filter((n) => n.endsWith('.tsx'))) assert.doesNotMatch(fs.readFileSync(path.join(here, '../src/scenes', name), 'utf8'), /useVideoConfig/);
  assert.doesNotMatch(fs.readFileSync(path.join(here, '../src/scenes/Media.tsx'), 'utf8'), /\bLoop\b/);
  for (const name of ['SceneWipeIn.tsx', 'Parchment.tsx']) assert.equal(fs.readFileSync(path.join(here, '../src/components', name), 'utf8'), fs.readFileSync(path.join(project, 'reviews/20261007-direction-v2/baseline/render/src/components', name), 'utf8'));
});


test('unknown video duration must not fall back to a longer container/audio duration', () => {
  assert.throws(() => parseVideoProbe({ streams: [{ width: 640, height: 360, avg_frame_rate: '25/1' }], format: { duration: '60' } }), /cannot determine/);
});
test('video packet endpoints prove duration when stream duration is absent', () => {
  const meta = parseVideoProbe({ streams: [{ width: 640, height: 360, start_time: '1', avg_frame_rate: '25/1' }], packets: [{ pts_time: '1', duration_time: '0.04' }, { pts_time: '8.96', duration_time: '0.04' }] });
  assert.equal(meta.durationSec, 8);
});
test('time_base duration fallback handles stream duration_ts', () => {
  assert.equal(parseVideoProbe({ streams: [{ width: 640, height: 360, avg_frame_rate: '25/1', duration_ts: '200', time_base: '1/25' }] }).durationSec, 8);
});
test('annotation labels preserve full explanatory text and stable screen size', () => {
  const text = 'Это сохранившиеся зубчатые колёса древнего механизма, а не современная реконструкция';
  for (const scale of [0.3, 1, 2]) {
    const l = annotationLabel({ text, rect: { x: 1800 / scale, y: 300 / scale, w: 50 / scale, h: 100 / scale }, scale, xMin: 40 / scale, xMax: 1880 / scale, yMin: 120 / scale, yMax: 800 / scale });
    assert.equal(l.lines.join(' '), text); assert.equal(l.fontSize * scale, 36);
    assert.ok(l.x - l.width / 2 >= 40 / scale - 1e-6); assert.ok(l.x + l.width / 2 <= 1880 / scale + 1e-6);
    assert.ok(l.y >= 120 / scale && l.y + (l.lines.length - 1) * l.lineHeight <= 800 / scale + 1e-6);
  }
});
test('safe crop protects interior box for an entire pan without fit-mode jumps', () => {
  const b = { x: 0.35, y: 0.3, w: 0.3, h: 0.3 };
  const modes = new Set();
  for (let i = 0; i <= 100; i++) {
    const l = mediaLayout({ mediaW: 1920, mediaH: 1080, frameW: 1920, frameH: 1080, annotations: [{ bbox: b }], focus: { x: 1, y: 0 }, progress: i / 100 });
    modes.add(l.fit);
    assert.ok(l.tx + b.x * 1920 * l.scale >= 0); assert.ok(l.tx + (b.x + b.w) * 1920 * l.scale <= 1920);
    assert.ok(l.ty + b.y * 1080 * l.scale >= 1080 * 0.11 - 1e-6); assert.ok(l.ty + (b.y + b.h) * 1080 * l.scale <= 1080 * 0.94 + 1e-6);
  }
  assert.equal(modes.size, 1);
});


test('a real ffmpeg-produced video and a real sharp-readable image both probe correctly offline', async (t) => {
  const dir = scratch(t);
  makeClip(dir, 'clip.mp4', 9); // generous 9s source for an 8s slot: no fallback needed
  const video = file({ data: { src: 'clip.mp4', kind: 'video' } });
  const v = await preflight(video, dir);
  const vshot = v.scenesFile.scenes[0].data.shots[0];
  assert.ok(vshot.mediaMeta.durationSec > 8); assert.equal(vshot.playbackRate, 1); assert.equal(vshot.freezeAtSec, undefined);
  fs.writeFileSync(path.join(dir, 'pixel.jpg'), Buffer.from('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAj/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=', 'base64'));
  const image = file({ data: { src: 'pixel.jpg', kind: 'image', fit: 'contain', caption: 'Test artifact' } });
  const i = await preflight(image, dir); const ishot = i.scenesFile.scenes[0].data.shots[0]; assert.equal(ishot.mediaMeta.width, 1); assert.equal(ishot.mediaMeta.height, 1);
});
test('chunk frame-count validation is exact, not previous +/-1 tolerance', async (t) => {
  const dir = scratch(t);
  const video = makeClip(dir, 'clip.mp4', 2, 25); // exactly 50 frames at 25fps
  assert.equal(partIsValid(video, 50), true); assert.equal(partIsValid(video, 49), false); assert.equal(partIsValid(video, 51), false);
});
test('long explanation gets reading-time warning even if its reveal finishes', () => {
  const c = canonical({ type: 'board', data: { cards: [{ id: 'a', title: 'Title', text: 'one two three four five six seven eight nine ten eleven twelve' }] }, beats: [{ id: 'a', t: 5 }] });
  assert.ok(qualityWarnings(c).some((w) => w.code === 'short-visibility' && w.elementId === 'a'));
});


test('zoom cannot rescue an unsafe initial crop: every frame has valid stable geometry', () => {
  for (const y of [0.1, 0.12, 0.13, 0.14, 0.15]) {
    const fits = new Set();
    for (const progress of [0, 0.01, 0.25, 0.5, 0.75, 1]) {
      const l = mediaLayout({ mediaW: 1920, mediaH: 1080, frameW: 1920, frameH: 1080, annotations: [{ bbox: { x: 0.4, y, w: 0.2, h: 0.2 } }], progress });
      assert.ok(l && Number.isFinite(l.scale) && Number.isFinite(l.tx) && Number.isFinite(l.ty)); fits.add(l.fit);
    }
    assert.equal(fits.size, 1);
  }
});


test('fitText: short phrase gets the largest font that fits, never below the minimum', () => {
  const r = fitText({ text: 'И зачем?', maxWidth: 380, maxHeight: 200, minFont: 56, maxFont: 120, maxLines: 3 });
  assert.ok(r.fontSize >= 56);
  assert.equal(r.lines.length, 1);
  assert.equal(r.lines[0], 'И зачем?');
});
test('fitText: long text wraps onto multiple balanced lines instead of one long + one short', () => {
  const r = fitText({ text: 'Кто же на самом деле построил этот удивительный механизм', maxWidth: 600, maxHeight: 300, minFont: 32, maxFont: 90, maxLines: 3 });
  assert.ok(r.lines.length >= 2 && r.lines.length <= 3);
  const lens = r.lines.map((l) => l.length);
  assert.ok(Math.max(...lens) - Math.min(...lens) <= Math.max(...lens)); // not absurdly lopsided
  assert.equal(r.lines.join(' ').replace(/\s+/g, ' '), 'Кто же на самом деле построил этот удивительный механизм');
});
test('fitText: never renders below the minimum font even when text cannot fully fit maxLines', () => {
  const r = fitText({ text: 'Очень длинный текст который точно не влезет в три строки при большом минимальном размере шрифта совсем никак', maxWidth: 300, maxHeight: 150, minFont: 56, maxFont: 56, maxLines: 3 });
  assert.equal(r.fontSize, 56);
  assert.equal(r.lines.length, 3);
  assert.ok(r.lines[2].endsWith('…'));
});


test('scene transitions: first scene is always a plain cut', () => {
  assert.equal(pickSceneTransition({ sceneId: 'any', index: 0, isChapterStart: true, secSinceLastWipe: 0, prevKind: null }), 'cut');
});
test('scene transitions: wipe only allowed on a chapter start AND after the minimum gap', () => {
  for (let i = 0; i < 50; i++) {
    const notChapter = pickSceneTransition({ sceneId: `s${i}`, index: 1, isChapterStart: false, secSinceLastWipe: 1000, prevKind: null });
    assert.notEqual(notChapter, 'wipe');
    const tooSoon = pickSceneTransition({ sceneId: `s${i}`, index: 1, isChapterStart: true, secSinceLastWipe: 10, prevKind: null });
    assert.notEqual(tooSoon, 'wipe');
  }
});
test('scene transitions: never repeats the previous kind back to back', () => {
  for (const prevKind of ['crossfade', 'dip_black', 'film_burn', 'wipe']) {
    for (let i = 0; i < 100; i++) {
      const kind = pickSceneTransition({ sceneId: `scene-${i}-${prevKind}`, index: 1, isChapterStart: true, secSinceLastWipe: 1000, prevKind });
      assert.notEqual(kind, prevKind);
    }
  }
});
test('scene transitions: deterministic from the same inputs', () => {
  const args = { sceneId: 'stable-id', index: 3, isChapterStart: true, secSinceLastWipe: 1000, prevKind: 'cut' };
  const a = pickSceneTransition(args), b = pickSceneTransition({ ...args });
  assert.equal(a, b);
});
test('planSceneTransitions: wipe fires at most once per the minimum gap even with many chapter starts, and never repeats', () => {
  const chapters = Array.from({ length: 10 }, (_, i) => ({ title: `c${i}`, start: i * 10 }));
  const scenes = Array.from({ length: 10 }, (_, i) => ({ id: `s${i}`, start: i * 10, end: i * 10 + 10 }));
  const kinds = planSceneTransitions(scenes, chapters, 25, 45);
  assert.equal(kinds[0], 'cut');
  for (let i = 1; i < kinds.length; i++) assert.notEqual(kinds[i], kinds[i - 1]);
  const wipeCount = kinds.filter((k) => k === 'wipe').length;
  assert.ok(wipeCount <= 3); // 90s total / 45s minimum gap
});
test('planSceneTransitions: wipe never appears outside a chapter start', () => {
  const chapters = [{ title: 'only', start: 0 }];
  const scenes = Array.from({ length: 8 }, (_, i) => ({ id: `s${i}`, start: i * 60, end: i * 60 + 60 }));
  const kinds = planSceneTransitions(scenes, chapters, 25, 45);
  for (let i = 1; i < kinds.length; i++) assert.notEqual(kinds[i], 'wipe');
});
test('shot transitions: first shot is a plain cut; same source never gets a hard cut', () => {
  assert.equal(pickShotTransition({ shotId: 'x', index: 0, sameAsset: false }), 'cut');
  for (let i = 0; i < 50; i++) {
    assert.equal(pickShotTransition({ shotId: `same-${i}`, index: 1, sameAsset: true }), 'crossfade');
  }
});
test('shot transitions: different sources are mostly a hard cut', () => {
  let cuts = 0, total = 200;
  for (let i = 0; i < total; i++) {
    if (pickShotTransition({ shotId: `diff-${i}`, index: 1, sameAsset: false }) === 'cut') cuts++;
  }
  assert.ok(cuts / total > 0.5);
});


test('subtitle groups: 2-4 words, breaks at long pauses, never 1 word unless forced', () => {
  const words = [
    { w: 'Это', start: 0, end: 0.2 }, { w: 'антикитерский', start: 0.25, end: 0.9 }, { w: 'механизм', start: 0.95, end: 1.4 },
    { w: 'бронзовый', start: 2.2, end: 2.7 }, { w: 'компьютер', start: 2.75, end: 3.3 },
  ];
  const groups = groupWords(words);
  assert.ok(groups.every((g) => g.words.length >= 1 && g.words.length <= 4));
  // большая пауза (2.2-1.4=0.8s > 0.45s) должна разорвать группу между "механизм" и "бронзовый"
  const breakIdx = groups.findIndex((g) => g.words[g.words.length - 1].w === 'механизм');
  assert.ok(breakIdx >= 0);
  assert.equal(groups[breakIdx + 1].words[0].w, 'бронзовый');
});
test('subtitle groups: sentence punctuation forces a break even without a long pause', () => {
  const words = [
    { w: 'Привет.', start: 0, end: 0.3 }, { w: 'Мир', start: 0.35, end: 0.6 }, { w: 'большой', start: 0.65, end: 1.0 },
  ];
  const groups = groupWords(words, { minGroup: 2 });
  assert.equal(groups[0].words.map((w) => w.w).join(' '), 'Привет.');
});
test('subtitle groups: caps at maxGroup words even with no pauses/punctuation', () => {
  const words = Array.from({ length: 10 }, (_, i) => ({ w: `w${i}`, start: i * 0.3, end: i * 0.3 + 0.25 }));
  const groups = groupWords(words, { maxGroup: 4 });
  assert.ok(groups.every((g) => g.words.length <= 4));
  assert.equal(groups.flatMap((g) => g.words).length, 10);
});
test('active group: whole group shown from its start until the NEXT group starts, not growing word by word', () => {
  const groups = [
    { words: [{ w: 'a', start: 0, end: 0.3 }, { w: 'b', start: 0.4, end: 0.7 }], start: 0, end: 0.7 },
    { words: [{ w: 'c', start: 1.0, end: 1.3 }], start: 1.0, end: 1.3 },
  ];
  // на протяжении ВСЕЙ первой группы (включая момент, когда звучит только "a") видна группа целиком
  assert.deepEqual(activeGroup(groups, 0.05).words.map((w) => w.w), ['a', 'b']);
  assert.deepEqual(activeGroup(groups, 0.6).words.map((w) => w.w), ['a', 'b']);
  // держится до начала следующей группы, даже если первая давно отзвучала (пауза)
  assert.deepEqual(activeGroup(groups, 0.9).words.map((w) => w.w), ['a', 'b']);
  assert.deepEqual(activeGroup(groups, 1.0).words.map((w) => w.w), ['c']);
});
test('active group: nothing shown before the first group or long after the last', () => {
  const groups = [{ words: [{ w: 'a', start: 1, end: 1.3 }], start: 1, end: 1.3 }];
  assert.equal(activeGroup(groups, 0.5), null);
  assert.equal(activeGroup(groups, 1.3 + 0.6), null);
  assert.ok(activeGroup(groups, 1.3 + 0.1));
});
test('active word index tracks which word in the (fixed) group is currently spoken', () => {
  const group = { words: [{ w: 'a', start: 0, end: 0.3 }, { w: 'b', start: 0.4, end: 0.7 }], start: 0, end: 0.7 };
  assert.equal(activeWordIndex(group, 0.1), 0);
  assert.equal(activeWordIndex(group, 0.5), 1);
  assert.equal(activeWordIndex(group, -1), -1);
});

// ---- montage scene types (compare/counter/steps/fact_stack/table, loupe, lower_third) ----
const montage = (type, data, beats = []) => ({ fps: 25, duration_sec: 8, title: 'T', scenes: [{ id: 'm', type, start: 0, end: 8, data, beats }] });
test('montage fixture job passes preflight for long and short', async () => {
  const dir = path.join(here, '../fixtures/montage');
  const checked = await preflight(JSON.parse(fs.readFileSync(path.join(dir, 'scenes.json'), 'utf8')), dir);
  assert.equal(checked.scenesFile.scenes.length, 7);
  assert.ok(checked.media.some((m) => m.side === 'left'));
  assert.equal(checked.scenesFile.scenes[0].data.lower_third.id, 'lt1');
});
test('new scene types: valid shapes normalize, beats address element ids', () => {
  const steps = { steps: [{ id: 'a', label: 'Медь' }, { id: 'b', label: 'Железо', icon: 'hammer' }, { id: 'c', label: 'Ток', icon: 'bolt' }] };
  assert.doesNotThrow(() => normalizeScenes(montage('steps', steps, [{ id: 'b', t: 2 }])));
  assert.throws(() => normalizeScenes(montage('steps', steps, [{ id: 'zzz', t: 2 }])), /does not target/);
  assert.doesNotThrow(() => normalizeScenes(montage('compare', { left: { label: 'А' }, right: { label: 'Б' } }, [{ id: 'right', t: 3 }])));
});
test('new scene types: invalid shapes are rejected', () => {
  const bad = (type, data) => assert.throws(() => normalizeScenes(montage(type, data)));
  bad('steps', { steps: [{ id: 'a', label: 'x' }, { id: 'b', label: 'y' }] });
  bad('steps', { steps: [{ id: 'a', label: 'x', icon: 'rocket' }, { id: 'b', label: 'y' }, { id: 'c', label: 'z' }] });
  bad('counter', { items: [{ id: 'n', value: '3', label: 'x' }] });
  bad('counter', { items: [] });
  bad('fact_stack', { facts: [{ id: 'a', big: '1', label: 'x' }] });
  bad('fact_stack', { facts: ['1', '2', '3'].map((b, i) => ({ id: `f${i}`, big: b.repeat(13), label: 'x' })) });
  bad('table', { columns: ['a'], rows: [] });
  bad('table', { columns: ['a', 'b'], rows: [{ id: 'r1', cells: ['x'] }, { id: 'r2', cells: ['x', 'y'] }] });
  bad('compare', { left: { label: 'один два три четыре пять шесть семь' }, right: { label: 'Б' } });
  bad('compare', { left: { label: 'А' } });
});
test('loupe annotation and lower_third validation', () => {
  const ok = { id: 'a1', kind: 'loupe', zoom: 2.5, text: 'зубья', bbox: box };
  assert.equal(normalizeAnnotation(ok).zoom, 2.5);
  assert.throws(() => normalizeAnnotation({ ...ok, zoom: 9 }), /zoom/);
  const media = { src: 'x.jpg', lower_third: { id: 'lt', title: 'Музей', subtitle: 'Афины, 1902' } };
  assert.doesNotThrow(() => normalizeScenes(file({ data: media, beats: [{ id: 'lt', t: 1 }] })));
  assert.throws(() => normalizeScenes(file({ data: { ...media, lower_third: { id: 'lt' } } })), /lower_third/);
});

// --- audio_hint overlay (top-level optional overlays[]) ---
const hint = (o = {}) => ({ type: 'audio_hint', start: 3, end: 7, langs: ['RU', 'en', 'ES'], ...o });
test('overlays are optional: a file without them is unchanged', () => {
  assert.equal(canonical({}).overlays, undefined);
});
test('audio_hint overlay normalizes langs to uppercase and defaults position', () => {
  const f = normalizeScenes({ ...file(), overlays: [hint()] });
  assert.deepEqual(f.overlays[0].langs, ['RU', 'EN', 'ES']);
  assert.equal(f.overlays[0].position, 'top-right');
});
for (const [name, ov] of Object.entries({
  'unknown type': { type: 'banner' }, 'end before start': { start: 5, end: 4 }, 'past duration': { end: 99 },
  'one lang': { langs: ['RU'] }, 'long code': { langs: ['RU', 'ENG'] }, 'dup lang': { langs: ['RU', 'ru'] },
  'NaN start': { start: NaN }, 'bad position': { position: 'center' }, 'non-array langs': { langs: 'RU,EN' },
})) {
  test(`reject invalid audio_hint: ${name}`, () => assert.throws(() => normalizeScenes({ ...file(), overlays: [hint(ov)] }), /overlays\[0\]/));
}
test('overlays must be an array', () => assert.throws(() => normalizeScenes({ ...file(), overlays: {} }), /overlays/));
test('audio_hint optional label: string up to 40 chars', () => {
  assert.equal(normalizeScenes({ ...file(), overlays: [hint({ label: 'Choose your audio language' })] }).overlays[0].label, 'Choose your audio language');
  assert.throws(() => normalizeScenes({ ...file(), overlays: [hint({ label: 'x'.repeat(41) })] }), /label/);
  assert.throws(() => normalizeScenes({ ...file(), overlays: [hint({ label: 5 })] }), /label/);
});
test('audio_hint subscribe/like/size validation', () => {
  const f = normalizeScenes({ ...file(), overlays: [hint({ subscribe: true, like: true, size: 'large' })] });
  assert.equal(f.overlays[0].size, 'large');
  assert.throws(() => normalizeScenes({ ...file(), overlays: [hint({ like: 'yes' })] }), /like/);
  assert.throws(() => normalizeScenes({ ...file(), overlays: [hint({ size: 'huge' })] }), /size/);
});

// --- date_chip overlay (дата на экране, 14.10) ---
const chip = (o = {}) => ({ type: 'date_chip', start: 2, end: 5.5, text: '1349 год', ...o });
test('date_chip overlay is valid, defaults to top-left and coexists with audio_hint', () => {
  const f = normalizeScenes({ ...file(), overlays: [hint(), chip()] });
  assert.equal(f.overlays[1].position, 'top-left');
  assert.equal(f.overlays[1].text, '1349 год');
});
test('date_chip trims text and accepts XIV век / ≈ forms', () => {
  for (const t of ['XIV век', '≈9500 до н. э.', '≈40 млн лет назад', 'VIII век н. э.'])
    assert.equal(normalizeScenes({ ...file(), overlays: [chip({ text: `  ${t} ` })] }).overlays[0].text, t);
});
for (const [name, ov] of Object.entries({
  'empty text': { text: '  ' }, 'long text': { text: 'x'.repeat(41) }, 'multi-line': { text: '1349\nгод' }, 'CR': { text: '1349\rгод' },
  'non-string': { text: 1349 }, 'missing text': { text: undefined }, 'NaN start': { start: NaN }, 'Infinity end': { end: Infinity },
  'end before start': { start: 5, end: 4 }, 'past duration': { end: 99 }, 'negative start': { start: -1 },
'bad position': { position: 'center' }, 'bad size': { size: 'huge' },
})) {
  test(`reject invalid date_chip: ${name}`, () => assert.throws(() => normalizeScenes({ ...file(), overlays: [chip(ov)] }), /overlays\[0\]/));
}
test('date_chip position/size accepted values', () => {
  const f = normalizeScenes({ ...file(), overlays: [chip({ position: 'bottom-left', size: 'large' })] });
  assert.equal(f.overlays[0].position, 'bottom-left');
  assert.equal(f.overlays[0].size, 'large');
});
test('date_chip longer than 10s is rejected', () => {
  const long = { ...file(), duration_sec: 30, scenes: [{ ...file().scenes[0], end: 30 }] };
  assert.throws(() => normalizeScenes({ ...long, overlays: [chip({ start: 1, end: 12 })] }), /overlays\[0\]/);
  assert.doesNotThrow(() => normalizeScenes({ ...long, overlays: [chip({ start: 1, end: 11 })] }));
});
test('DateChip component: null outside window, drawn in both long and short', () => {
  const comp = fs.readFileSync(path.join(here, '../src/components/DateChip.tsx'), 'utf8');
  assert.match(comp, /if \(o <= 0\) return null/);
  assert.doesNotMatch(comp, /format !== "long"\) return null/);
  const main = fs.readFileSync(path.join(here, '../src/Main.tsx'), 'utf8');
  assert.match(main, /ov\.type === "date_chip" \? \(\s*<DateChip[^>]*format=\{format\}/);
});

// ---- audio_hint / date_chip: одна непрерывная плашка (1.3.1) ----
import { audioHintOpacity, dateChipOpacity, AUDIO_HINT_FADE_IN, AUDIO_HINT_FADE_OUT } from '../src/utils/overlayFade.mjs';

function sweep(fn, from, to, step = 0.04) { const v = []; for (let t = from; t <= to + 1e-9; t += step) v.push([Math.round(t * 100) / 100, fn(t)]); return v; }

test('audio_hint opacity: 0 before, smooth ramp up, exact hold, smooth ramp down, 0 after, no dips', () => {
  for (const [start, end] of [[3, 9], [3, 12]]) {
    const ov = { start, end };
    const vals = sweep((t) => audioHintOpacity(t, ov), start - 1, end + 1);
    const fadeIn = AUDIO_HINT_FADE_IN, fadeOut = AUDIO_HINT_FADE_OUT;
    assert.ok(fadeIn >= 0.5 && fadeOut >= 0.5);
    let phase = 'pre', prev = 0;
    for (const [t, o] of vals) {
      assert.ok(o >= 0 && o <= 1, `opacity in [0,1] at ${t}`);
      if (t <= start + 1e-6) assert.ok(o < 1e-9, `0 before start (${t})`);
      else if (t >= end - 1e-6) assert.ok(o < 1e-9, `0 after end (${t})`);
      else if (t >= start + fadeIn && t <= end - fadeOut) assert.ok(Math.abs(o - 1) < 1e-9, `hold = 1 at ${t}`);
      else if (t < start + fadeIn) assert.ok(o >= prev - 1e-12, `monotone up at ${t}`);
      else assert.ok(o <= prev + 1e-12, `monotone down at ${t}`);
      if (t > start && t < start + fadeIn) { assert.equal(phase === 'down', false); phase = 'up'; }
      if (t > end - fadeOut && t < end) phase = 'down';
      prev = o;
    }
    // ровно один максимум-плато и ни одного провала: после достижения 1 до начала спада значение не падает
    const ones = vals.map(([, o], i) => (o > 1 - 1e-9 ? i : -1)).filter((i) => i >= 0);
    for (let i = ones[0]; i <= ones[ones.length - 1]; i++) assert.ok(vals[i][1] > 1 - 1e-9, `dip inside hold at ${vals[i][0]}`);
    // плавность: шаг 0.04 с не даёт скачка > 0.2
    for (let i = 1; i < vals.length; i++) assert.ok(Math.abs(vals[i][1] - vals[i - 1][1]) < 0.2, `no jump at ${vals[i][0]}`);
  }
});

test('overlay opacity does not depend on scene boundaries (pure function of absolute time)', () => {
  const ov = { start: 3, end: 9 };
  const boundaries = [5.2, 9.04, 4.8];
  for (const b of boundaries) for (const dt of [-0.081, -0.04, 0, 0.04, 0.081]) {
    const t = b + dt;
    assert.equal(audioHintOpacity(t, ov), audioHintOpacity(t, { ...ov }));
  }
  const dc = { start: 50.14, end: 53.64 };
  const vals = sweep((t) => dateChipOpacity(t, dc), 49, 55);
  const maxAt = vals.findIndex(([, o]) => o > 1 - 1e-9);
  assert.ok(maxAt > 0);
  for (let i = 1; i < vals.length; i++) { const [t, o] = vals[i]; if (t < 50.54) assert.ok(o >= vals[i - 1][1] - 1e-12); if (t > 53.24) assert.ok(o <= vals[i - 1][1] + 1e-12); }
});

test('Main mounts HeaderStrip/overlays once, in a top layer above every scene effect (no remount, not covered by transitions)', () => {
  const main = fs.readFileSync(path.join(here, '../src/Main.tsx'), 'utf8');
  const z = Number(/OVERLAY_LAYER_Z = (\d+)/.exec(main)?.[1]);
  let maxScene = 0;
  const walk = (dir) => { for (const e of fs.readdirSync(dir, { withFileTypes: true })) { const f = path.join(dir, e.name); if (e.isDirectory()) walk(f); else if (/\.tsx$/.test(e.name) && f !== path.join(here, '../src/Main.tsx')) for (const m of fs.readFileSync(f, 'utf8').matchAll(/zIndex:\s*(\d+)/g)) maxScene = Math.max(maxScene, Number(m[1])); } };
  walk(path.join(here, '../src'));
  assert.ok(maxScene >= 50 && z > maxScene, `overlay layer z=${z} must exceed scene effects z=${maxScene}`);
  const layerStart = main.indexOf('zIndex: OVERLAY_LAYER_Z');
  const seriesEnd = main.lastIndexOf('</Series>');
  assert.ok(layerStart > seriesEnd, 'overlay layer is outside Series');
  for (const comp of ['<AudioHint', '<DateChip', '<HeaderStrip']) { assert.equal(main.split(comp).length - 1, 1, `${comp} mounted once`); assert.ok(main.indexOf(comp) > layerStart); }
  // ни одна сцена не создаёт AudioHint/DateChip
  const sc = path.join(here, '../src/scenes');
  for (const f of fs.readdirSync(sc)) assert.ok(!/AudioHint|DateChip/.test(fs.readFileSync(path.join(sc, f), 'utf8')), `${f} must not render overlays`);
});

test('chapter_badge is an optional boolean top-level flag', () => {
  const base = { fps: 25, duration_sec: 8, title: 'T', scenes: [{ id: 's', type: 'media', start: 0, end: 8, data: { src: 'clip.mp4', kind: 'video' }, beats: [] }] };
  assert.equal(normalizeScenes(base).chapter_badge, undefined);
  assert.equal(normalizeScenes({ ...base, chapter_badge: false }).chapter_badge, false);
  assert.throws(() => normalizeScenes({ ...base, chapter_badge: 'no' }), /chapter_badge/);
  const hs = fs.readFileSync(path.join(here, '../src/components/HeaderStrip.tsx'), 'utf8');
  assert.ok(/showChapterBadge/.test(hs));
});

test('brand_en flag and hide_words graphics are accepted; hide_words scenes keep numbers', () => {
  const base = { fps: 25, duration_sec: 8, title: 'T', brand_en: true, chapter_badge: false, scenes: [{ id: 's', type: 'number', start: 0, end: 8, data: { value: 48, unit: 'м', label: 'высота', hide_words: true }, beats: [] }] };
  const n = normalizeScenes(base);
  assert.equal(n.brand_en, true); assert.equal(n.scenes[0].data.hide_words, true);
  assert.throws(() => normalizeScenes({ ...base, brand_en: 1 }), /brand_en/);
  for (const f of ['NumberScene', 'Counter', 'Scale', 'TimelineScene', 'MapScene']) assert.ok(/hide_words/.test(fs.readFileSync(path.join(here, `../src/scenes/${f}.tsx`), 'utf8')), `${f} honours hide_words`);
});

// ---- 15.10 кодовая графика: map_route / tally / эффекты шота / фокус-зум ----
const codeFile = (scene) => ({ fps: 25, duration_sec: 8, title: 'T', scenes: [{ id: 's', start: 0, end: 8, beats: [], ...scene }] });
test('map_route: valid, English CAPS places, no Cyrillic, <=3 places', () => {
  const ok = { type: 'map_route', data: { region: 'north_atlantic', route_pts: [{ lat: 61, lon: -45 }, { lat: 64, lon: -22 }], places: [{ lat: 64, lon: -22, en: 'ICELAND' }], year: '985', marker: 'ship' } };
  assert.doesNotThrow(() => normalizeScenes(codeFile(ok)));
  const bad = (patch) => () => normalizeScenes(codeFile({ ...ok, data: { ...ok.data, ...patch } }));
  assert.throws(bad({ places: [{ lat: 1, lon: 1, en: 'Исландия' }] }), /English CAPS/);
  assert.throws(bad({ year: '985 год' }), /no Russian/);
  assert.throws(bad({ region: 'atlantis' }), /region must be/);
  assert.throws(bad({ route_pts: [{ lat: 95, lon: 0 }] }), /out of range/);
  assert.throws(bad({ places: Array.from({ length: 4 }, () => ({ lat: 1, lon: 1, en: 'X' })) }), /at most 3/);
});
test('tally: total 1..60, remain <= total, known icon', () => {
  const t = (d) => () => normalizeScenes(codeFile({ type: 'tally', data: d }));
  assert.doesNotThrow(t({ total: 15, remain: 4, icon: 'ship' }));
  assert.doesNotThrow(t({ total: 5, icon: 'amphora' }));
  assert.throws(t({ total: 61 }), /1\.\.60/);
  assert.throws(t({ total: 5, remain: 6 }), /remain/);
  assert.throws(t({ total: 5, icon: 'dragon' }), /icon/);
});
test('shot effects: callout / atmos / zoom validated, still-only', () => {
  const shot = (extra, kind = 'image') => normalizeScenes(codeFile({ type: 'media', data: { src: kind === 'image' ? 'a.jpg' : 'a.mp4', kind, ...extra } }));
  const callout = { circle: { cx: 0.5, cy: 0.5, rx: 0.1, ry: 0.1 }, zoomBox: { x: 0.4, y: 0.4, w: 0.2, h: 0.2 }, circleAt: 1, zoomAt: 3 };
  const sc = (extra) => codeFile({ type: 'media', data: { shots: [{ id: 'a', start: 0, end: 8, src: 'a.jpg', ...extra }] } });
  assert.doesNotThrow(() => normalizeScenes(sc({ callout, atmos: { kind: 'embers', intensity: 1.2 }, zoom: { x: 0.5, y: 0.4, to: 1.2, box: { x: 0.4, y: 0.3, w: 0.2, h: 0.2 } } })));
  assert.throws(() => normalizeScenes(sc({ atmos: { kind: 'lava' } })), /atmos\.kind/);
  assert.throws(() => normalizeScenes(sc({ zoom: { x: 1.5, y: 0.5 } })), /\[0,1\]/);
  assert.throws(() => normalizeScenes(sc({ callout: { ...callout, zoomBox: { x: 0.9, y: 0.9, w: 0.3, h: 0.3 } } })), /zoomBox/);
  assert.throws(() => normalizeScenes(codeFile({ type: 'media', data: { shots: [{ id: 'a', start: 0, end: 8, src: 'a.mp4', zoom: { x: 0.5, y: 0.5 } }] } })), /only for still/);
  void shot;
});
test('focusZoomLayout: push-in keeps the subject box fully in frame, never shows image edges', () => {
  const geo = { mediaW: 1376, mediaH: 768, frameW: 1920, frameH: 1080 };
  for (const zoom of [{ x: 0.3, y: 0.4, to: 1.4, box: { x: 0.22, y: 0.25, w: 0.16, h: 0.3 } }, { x: 0.85, y: 0.2, to: 1.3 }, { x: 0.5, y: 0.5, box: { x: 0.1, y: 0.1, w: 0.8, h: 0.8 } }]) {
    let prev = 0;
    for (let i = 0; i <= 20; i++) {
      const L = focusZoomLayout({ ...geo, zoom, progress: i / 20 });
      assert.ok(L.scale >= prev - 1e-9, 'scale must grow monotonically (push-in)'); prev = L.scale;
      assert.ok(L.tx <= 1e-6 && L.ty <= 1e-6 && L.tx + geo.mediaW * L.scale >= geo.frameW - 1e-6 && L.ty + geo.mediaH * L.scale >= geo.frameH - 1e-6, 'covers the frame');
      const b = zoom.box || { x: zoom.x - 0.1, y: zoom.y - 0.1, w: 0.2, h: 0.2 };
      const x0 = Math.max(0, b.x) * geo.mediaW * L.scale + L.tx, x1 = Math.min(1, b.x + b.w) * geo.mediaW * L.scale + L.tx;
      const y0 = Math.max(0, b.y) * geo.mediaH * L.scale + L.ty, y1 = Math.min(1, b.y + b.h) * geo.mediaH * L.scale + L.ty;
      assert.ok(x0 >= -1 && x1 <= geo.frameW + 1 && y0 >= -1 && y1 <= geo.frameH + 1, `subject inside frame at p=${i / 20}`);
    }
  }
});

// ---- standalone shorts (shorts_scenes/shortN.json) ----
const portrait = { frameW: 1080, frameH: 1920 };
const visibleBox = (L, geo, b) => ({
  x0: b.x * geo.mediaW * L.scale + L.tx, x1: (b.x + b.w) * geo.mediaW * L.scale + L.tx,
  y0: b.y * geo.mediaH * L.scale + L.ty, y1: (b.y + b.h) * geo.mediaH * L.scale + L.ty,
});
test('portrait focusZoomLayout (16:9 -> 9:16): off-center focus is never cropped out, no image edges', () => {
  const geo = { mediaW: 1920, mediaH: 1080, ...portrait };
  const cases = [
    { x: 0.15, y: 0.5, to: 1.3, box: { x: 0.08, y: 0.3, w: 0.14, h: 0.4 } },
    { x: 0.88, y: 0.35, to: 1.25, box: { x: 0.82, y: 0.2, w: 0.12, h: 0.3 } },
    { x: 0.5, y: 0.5, to: 1.2 },
    { x: 0.95, y: 0.9, to: 1.4 },
    { x: 0.2, y: 0.5, box: { x: 0.05, y: 0.1, w: 0.5, h: 0.8 } }, // бокс шире окна: фокус всё равно в кадре
  ];
  for (const zoom of cases) {
    for (let i = 0; i <= 20; i++) {
      const L = focusZoomLayout({ ...geo, zoom, progress: i / 20, safeBottom: 1920 * 0.27 });
      assert.ok(L.tx <= 1e-6 && L.ty <= 1e-6 && L.tx + geo.mediaW * L.scale >= geo.frameW - 1e-6 && L.ty + geo.mediaH * L.scale >= geo.frameH - 1e-6, 'covers the frame');
      const fx = zoom.x * geo.mediaW * L.scale + L.tx, fy = zoom.y * geo.mediaH * L.scale + L.ty;
      assert.ok(fx >= 0 && fx <= geo.frameW && fy >= 0 && fy <= geo.frameH, `focus point (${zoom.x},${zoom.y}) visible at p=${i / 20}: ${fx.toFixed(0)},${fy.toFixed(0)}`);
      if (zoom.box && zoom.box.w * geo.mediaW * L.scale <= geo.frameW * 0.9) {
        const v = visibleBox(L, geo, zoom.box);
        assert.ok(v.x0 >= -1 && v.x1 <= geo.frameW + 1, `narrow subject box fully inside at p=${i / 20}`);
      }
    }
  }
});
test('portrait mediaLayout (short, cover): focus point visible from the first frame to the last, gentle push-in only', () => {
  const geo = { mediaW: 1920, mediaH: 1080, ...portrait, format: 'short' };
  for (const focus of [{ x: 0.1, y: 0.5 }, { x: 0.9, y: 0.4 }, { x: 0.5, y: 0.5 }, { x: 0.75, y: 0.8 }]) {
    let prev = 0;
    for (let i = 0; i <= 20; i++) {
      const L = mediaLayout({ ...geo, focus, progress: i / 20 });
      assert.equal(L.fit, 'cover');
      assert.ok(L.scale >= prev - 1e-9 && L.scale <= Math.max(geo.frameW / geo.mediaW, geo.frameH / geo.mediaH) * 1.081, 'monotonic gentle push-in <= 8%'); prev = L.scale;
      const fx = focus.x * geo.mediaW * L.scale + L.tx, fy = focus.y * geo.mediaH * L.scale + L.ty;
      assert.ok(fx >= 0 && fx <= geo.frameW && fy >= 0 && fy <= geo.frameH, `focus ${JSON.stringify(focus)} visible at p=${i / 20}`);
      assert.ok(L.tx <= 1e-6 && L.tx + geo.mediaW * L.scale >= geo.frameW - 1e-6, 'no side edges');
    }
  }
});
test('long-format mediaLayout is unchanged by the short portrait rule (focus pan still starts centered)', () => {
  const L0 = mediaLayout({ mediaW: 1920, mediaH: 1080, frameW: 1920, frameH: 1080, focus: { x: 0.9, y: 0.5 }, progress: 0, format: 'long' });
  assert.ok(Math.abs(L0.tx) < 1e-6 && Math.abs(L0.ty) < 1e-6);
  const Lp = mediaLayout({ mediaW: 1080, mediaH: 1920, frameW: 1920, frameH: 1080, focus: { x: 0.5, y: 0.9 }, progress: 0, format: 'long' });
  assert.ok(Lp.ty <= 0 && Math.abs(Lp.ty - (1080 / 2 - 0.5 * 1920 * Lp.scale)) < 1e-6, 'long keeps centered start');
});

const standaloneShort = (extra = {}) => {
  const shot = (id, s, e, src, o = {}) => ({ id, start: s, end: e, src, kind: 'image', fit: 'cover', focus: { x: 0.8, y: 0.4 }, zoom: { x: 0.8, y: 0.4, to: 1.2 }, ...o });
  return { fps: 25, duration_sec: 9, title: 'short', chapters: [], words: [], sources: [], overlays: [], scenes: [
    { id: 's1', type: 'media', start: 0, end: 4.4, data: { shots: [shot('a', 0, 4.4, 'media/a.jpg')] }, beats: [] },
    { id: 's2', type: 'media', start: 4.4, end: 9, data: { shots: [shot('b', 4.4, 9, 'media/b.mp4', { kind: 'video', zoom: undefined, trimStartSec: 1, playbackRate: 1 })] }, beats: [] },
  ], ...extra };
};
test('standalone short: no chapters/words/overlays, 9 s, accepted without errors or caption nags', () => {
  const f = normalizeScenes(standaloneShort({ standalone_short: true }));
  assert.equal(f.standalone_short, true);
  assert.equal(f.scenes[0].start, 0);
  assert.equal(qualityWarnings(f).filter((x) => x.code === 'unexplained-image').length, 0);
  assert.equal(normalizeScenes(standaloneShort()).standalone_short, undefined);
  assert.throws(() => normalizeScenes(standaloneShort({ standalone_short: 'yes' })), /standalone_short/);
  assert.throws(() => normalizeScenes(standaloneShort({ scenes: standaloneShort().scenes.map((s, i) => (i ? { ...s, start: 5 } : s)) })), /gap|overlap/);
  // legacy long file still nags about uncaptioned stills
  assert.equal(qualityWarnings(normalizeScenes(standaloneShort())).filter((x) => x.code === 'unexplained-image').length, 1);
});
test('standalone short: detection by flag and by path; explicit false wins', async () => {
  const { isStandaloneShort } = await import('../lib/preflight.mjs');
  assert.equal(isStandaloneShort({ standalone_short: true }, 'x/scenes.json'), true);
  assert.equal(isStandaloneShort({}, '/p/shorts_scenes/short3.json'), true);
  assert.equal(isStandaloneShort({}, '/p/short2.json'), true);
  assert.equal(isStandaloneShort({}, '/p/scenes.json'), false);
  assert.equal(isStandaloneShort({ standalone_short: false }, '/p/shorts_scenes/short1.json'), false);
});
test('standalone short: scene transitions are soft crossfades; legacy planning is unchanged', () => {
  const f = normalizeScenes(standaloneShort({ standalone_short: true }));
  assert.deepEqual(planSceneTransitions(f.scenes, [], 25, 45, { standalone: true }), ['cut', 'crossfade']);
  assert.deepEqual(planSceneTransitions(f.scenes, [], 25), planSceneTransitions(f.scenes, [], 25, 45, {}));
});
test('Main draws no chapter badge / date chips / audio hint for standalone shorts; legacy window path stays in tainy-build', () => {
  const main = fs.readFileSync(path.join(here, '../src/Main.tsx'), 'utf8');
  assert.match(main, /standalone_short === true/);
  assert.match(main, /const overlays = standalone \? \[\]/);
  assert.match(main, /const chapters = standalone \? \[\]/);
  const build = fs.readFileSync(path.join(here, '../mac/tainy-build.mjs'), 'utf8');
  assert.match(build, /frameRange: \[startFrame, endFrame\]/, 'legacy window path kept');
  assert.match(build, /audioStartFrameAbs: startFrame/);
  assert.match(build, /frameRange: \[0, sFrames - 1\]/);
  assert.match(build, /subtitles: false/);
  assert.match(build, /renderOnly !== "long"/);
  assert.match(build, /renderOnly === "shorts"/);
});
test('check-scenes CLI: OK on standalone short file and on a pack dir; ERR on a broken or media-less one', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cs-'));
  fs.mkdirSync(path.join(dir, 'shorts_scenes')); fs.mkdirSync(path.join(dir, 'media'));
  fs.writeFileSync(path.join(dir, 'media/a.jpg'), 'x'); fs.writeFileSync(path.join(dir, 'media/b.mp4'), 'x');
  fs.writeFileSync(path.join(dir, 'scenes.json'), JSON.stringify(standaloneShort()));
  fs.writeFileSync(path.join(dir, 'shorts_scenes/short1.json'), JSON.stringify(standaloneShort()));
  const script = path.join(here, '../scripts/check-scenes.mjs');
  assert.match(execFileSync('node', [script, path.join(dir, 'shorts_scenes/short1.json')], { encoding: 'utf8' }), /^OK standalone_short scenes=2 shots=2 duration=9s/);
  const out = execFileSync('node', [script, dir], { encoding: 'utf8' });
  assert.match(out, /scenes\.json: OK scenes=2/); assert.match(out, /shorts_scenes\/short1\.json: OK standalone_short/);
  const bad = standaloneShort(); bad.scenes[1].start = 5;
  fs.writeFileSync(path.join(dir, 'shorts_scenes/short2.json'), JSON.stringify(bad));
  assert.throws(() => execFileSync('node', [script, path.join(dir, 'shorts_scenes/short2.json')], { stdio: 'pipe' }));
  fs.rmSync(path.join(dir, 'media/b.mp4'));
  assert.throws(() => execFileSync('node', [script, path.join(dir, 'shorts_scenes/short1.json')], { stdio: 'pipe' }));
  fs.rmSync(dir, { recursive: true, force: true });
});
