// Проверка кадров без полного рендера: по одному PNG за раз, concurrency 1.
// node scripts/still.mjs --job <dir> --format long|short --frames 130,360 --out /tmp/stills [--prefix name] [--scenes shorts_scenes/short1.json]
// Запускать под systemd-run (см. pipeline/render.py), на сервере не гонять большие списки кадров.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { preflight, stageMedia, isStandaloneShort } from '../lib/preflight.mjs';
function findHeadlessShell(root) {
  const stack = [root];
  while (stack.length) {
    let entries; const dir = stack.pop();
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { continue; }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) stack.push(full); else if (e.isFile() && e.name === 'chrome-headless-shell') return full;
    }
  }
  return null;
}

const here = path.dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const job = path.resolve(arg('job')), format = arg('format', 'long'), out = path.resolve(arg('out', '/tmp/stills'));
const frames = String(arg('frames', '0')).split(',').map(Number), prefix = arg('prefix', format);
const browserExecutable = findHeadlessShell('/home/agent/workspace/.playwright-browsers/chromium_headless_shell-1243');
if (!browserExecutable) throw new Error('chrome-headless-shell not found');
const { bundle } = await import('@remotion/bundler');
const { renderStill, selectComposition } = await import('@remotion/renderer');
const scenesPath = arg('scenes') ? path.resolve(job, arg('scenes')) : path.join(job, 'scenes.json');
const raw = JSON.parse(fs.readFileSync(scenesPath, 'utf8'));
if (isStandaloneShort(raw, arg('scenes') ? scenesPath : null)) raw.standalone_short = true;
const checked = await preflight(raw, job);
for (const f of ['gen-textures.mjs', 'gen-maps.mjs']) (await import('node:child_process')).execFileSync(process.execPath, [path.join(here, f)], { stdio: 'inherit' });
const bundleDir = await bundle({ entryPoint: path.join(here, '..', 'src', 'index.ts'), publicDir: path.join(here, '..', 'public'), onProgress: () => {} });
const scenesFile = stageMedia(checked.scenesFile, checked.media, bundleDir);
const inputProps = { scenesFile, format, subtitles: format === 'short' && !scenesFile.standalone_short };
const composition = await selectComposition({ serveUrl: bundleDir, id: 'Main', inputProps, browserExecutable });
fs.mkdirSync(out, { recursive: true });
for (const frame of frames) {
  const output = path.join(out, `${prefix}-f${String(frame).padStart(5, '0')}.png`);
  await renderStill({ composition, serveUrl: bundleDir, inputProps, frame, output, browserExecutable, imageFormat: 'png', chromiumOptions: { disableWebSecurity: true, gl: 'swiftshader' } });
  console.log('STILL', output);
}
fs.rmSync(bundleDir, { recursive: true, force: true });
