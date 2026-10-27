// Та же проверка scenes.json, что делает Mac перед рендером (normalizeScenes).
// Запуск: node render/scripts/check-scenes.mjs <scenes.json | shortN.json | папка пакета/job | tainy-*.zip>
//   файл            -> проверяет его (shorts_scenes/shortN.json или standalone_short:true = самостоятельный шорт)
//   папка / .zip    -> scenes.json + все shorts_scenes/short*.json (и manifest.shorts_scenes)
// Печатает OK/ERR по каждому файлу; exit 0 если всё OK, иначе 1.
// 15.10: проверяет и кодовую графику (map_route, tally, shot.callout/atmos/zoom) через normalizeScenes и пишет сводку в stdout;
// русский текст на экране (кроме водяного знака) не допускается в данных map_route/tally и в плашках дат нового формата: это предупреждение.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { normalizeScenes, hasCyrillic, qualityWarnings } from '../src/utils/quality.mjs';
import { isStandaloneShort } from '../lib/preflight.mjs';

function checkFile(file, baseDir, mediaCheck = null) {
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  const standalone = isStandaloneShort(raw, file);
  if (standalone) raw.standalone_short = true;
  const f = normalizeScenes(raw);
  const types = {};
  let callouts = 0, atmos = 0, zooms = 0, shots = 0;
  const missing = [];
  const doMedia = mediaCheck ?? standalone; // длинный plain-файл: как раньше, без проверки наличия медиа
  for (const s of f.scenes) {
    types[s.type] = (types[s.type] || 0) + 1;
    for (const sh of (s.type === 'media' ? s.data.shots || [] : [])) {
      shots++;
      if (sh.callout) callouts++; if (sh.atmos) atmos++; if (sh.zoom) zooms++;
      if (doMedia && baseDir && !/^[a-z]+:\/\//i.test(sh.src) && !fs.existsSync(path.resolve(baseDir, sh.src))) missing.push(sh.src);
    }
  }
  if (missing.length) throw new Error(`${missing.length} media file(s) not found relative to ${baseDir}: ${[...new Set(missing)].slice(0, 3).join(', ')}`);
  if (standalone) {
    if (!f.scenes.length || Math.round(f.scenes[0].start * f.fps) !== 0) throw new Error('standalone short: first scene must start at 0');
    for (const w of qualityWarnings(f).filter((x) => x.code.startsWith('standalone-'))) console.warn(`WARN: ${w.code}: ${w.message}`);
    return `OK standalone_short scenes=${f.scenes.length} shots=${shots} duration=${f.duration_sec}s fps=${f.fps} zooms=${zooms} atmos=${atmos} overlays=${(f.overlays || []).length}`;
  }
  const ru = (f.overlays || []).filter((o) => o.type === 'date_chip' && hasCyrillic(o.text));
  if (ru.length) console.warn(`WARN: ${ru.length} date_chip(s) with Russian text (new format is Latin/digits): ${ru.slice(0, 3).map((o) => o.text).join(', ')}`);
  return `OK scenes=${f.scenes.length} map_route=${types.map_route || 0} tally=${types.tally || 0} callouts=${callouts} atmos=${atmos} zooms=${zooms} date_chips=${(f.overlays || []).filter((o) => o.type === 'date_chip').length}`;
}

const target = process.argv[2];
let failed = false;
try {
  if (!target) throw new Error('usage: check-scenes.mjs <scenes.json|shortN.json|dir|zip>');
  let t = path.resolve(target), tmp = null;
  if (/\.zip$/i.test(t)) { tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'check-scenes-')); execFileSync('unzip', ['-o', '-q', t, '-d', tmp]); t = tmp; }
  if (fs.statSync(t).isDirectory()) {
    if (!fs.existsSync(path.join(t, 'scenes.json'))) { const sub = fs.readdirSync(t).find((e) => fs.existsSync(path.join(t, e, 'scenes.json'))); if (sub) t = path.join(t, sub); }
    const list = [path.join(t, 'scenes.json')];
    const dir = path.join(t, 'shorts_scenes');
    if (fs.existsSync(dir)) for (const n of fs.readdirSync(dir).filter((x) => /^short\d+\.json$/i.test(x)).sort()) list.push(path.join(dir, n));
    for (const file of list) {
      try { console.log(`${path.relative(t, file)}: ${checkFile(file, t, true)}`); }
      catch (e) { failed = true; console.error(`${path.relative(t, file)}: ERR ${e.message}`); }
    }
  } else {
    // для shorts_scenes/shortN.json медиа-пути считаются от родителя shorts_scenes (корень пакета/job)
    const dirName = path.basename(path.dirname(t));
    const base = dirName === 'shorts_scenes' ? path.dirname(path.dirname(t)) : path.dirname(t);
    console.log(checkFile(t, base));
  }
  if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
} catch (e) {
  console.error(e.message);
  failed = true;
}
process.exit(failed ? 1 : 0);
