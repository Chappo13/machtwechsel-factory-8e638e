"""
FCPXML 1.9 export for DaVinci Resolve.

Вместо финального рендера видео — генерирует DaVinci-таймлайн с уже
расставленными клипами, voiceover, music (с volume keyframes ~12%) и
заметками о QA-флагах. Сергей открывает в DaVinci, проверяет, добавляет
motion graphics из своих шаблонов, рендерит сам.

Структура папки на выходе:
  project.fcpxml          ← timeline
  voice.mp3               ← голос (уже есть)
  music.mp3               ← фоновая музыка (уже есть, если есть)
  clips/                  ← клипы (уже есть)
  motion-notes.md         ← что вставить как графику + готовые тексты
  QA-flags.md             ← список клипов с низким relevance score
  open-davinci.command    ← macOS launcher (chmod +x)
"""

import json
import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

# Video format
WIDTH = 1920
HEIGHT = 1080
FPS = 30
TB = 3000                # FCPXML time base
FRAME = TB // FPS        # 100 — длина одного кадра
FORMAT_ID = "r0"

# Картинки (стиллы) — у них нет длительности файла; в fcpxml даём asset длину = вся
# таймлиния, а spine кадрирует по таймингу сцены. Для мультяшного канала (vi/Ngẫm),
# где клиент рендерит сам в DaVinci, видеоряд = картинки напрямую, без MP4-кодирования.
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Audio
SAMPLE_RATE = 48000
MUSIC_VOLUME_DB = -13.0  # ~22% — слышно под голосом. Музыка бэйкается на полной
# громкости (orchestrator build_music_bed volume=1.0); приглушение делается только здесь,
# один раз. Было -18.4dB ПЛЮС бэйк 0.12 → двойное приглушение ≈ -36dB, музыку не слышно.

# QA threshold (relevance score < threshold → flag)
QA_RELEVANCE_THRESHOLD = 0.55


# ─── helpers ────────────────────────────────────────────────────────────────

def sec_to_rational(sec: float) -> str:
    """Секунды → 'N/3000s', выровнено по кадрам."""
    frames = round(sec * FPS)
    return f"{frames * FRAME}/{TB}s"


def file_url(p: Path) -> str:
    """Абсолютный URI для FCPXML asset src (fallback для путей вне workspace).
    quote кодирует пробелы/&/спецсимволы, сохраняя '/' — иначе ломается XML/URL."""
    return "file://" + quote(str(p.resolve()), safe="/")


def rel_src(p: Path, workspace: Path) -> str:
    """ОТНОСИТЕЛЬНЫЙ src от папки с project.fcpxml → проект портативный,
    DaVinci находит клипы без relocate при переносе папки. Напр. 'clips/clip_000.mp4'.
    Если путь вне workspace — fallback на абсолютный file://."""
    try:
        rel = os.path.relpath(str(Path(p).resolve()), str(Path(workspace).resolve()))
    except ValueError:
        return file_url(p)
    if rel.startswith(".."):
        return file_url(p)
    return quote(rel.replace(os.sep, "/"), safe="/")


def ffprobe_duration(path: Path) -> float:
    """Длительность аудио/видео файла в секундах через ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=15
        )
        return float(r.stdout.strip())
    except Exception as e:
        logger.warning(f"ffprobe failed for {path.name}: {e}")
        return 0.0


# ─── FCPXML building ────────────────────────────────────────────────────────

def _build_format() -> str:
    return (
        f'<format id="{FORMAT_ID}" name="FFVideoFormat1080p{FPS}" '
        f'frameDuration="{FRAME}/{TB}s" width="{WIDTH}" height="{HEIGHT}" '
        f'colorSpace="1-1-1 (Rec. 709)"/>'
    )


def _build_video_asset(asset_id: str, path: Path, duration_sec: float, workspace: Path) -> str:
    dur = sec_to_rational(duration_sec)
    name = escape(path.stem)
    return (
        f'<asset id="{asset_id}" name="{name}" start="0s" duration="{dur}" '
        f'hasVideo="1" hasAudio="0" format="{FORMAT_ID}" videoSources="1" '
        f'src="{escape(rel_src(path, workspace))}"/>'
    )


def _build_still_asset(asset_id: str, path: Path, workspace: Path) -> str:
    """Asset для КАРТИНКИ-стилла. КЛЮЧЕВОЕ: duration="0s" (вне времени).
    Раньше стиллу проставлялась duration = вся таймлиния (~689с) + видео-формат →
    DaVinci считал PNG видеофайлом на 689с, лез проверять, видел 1 кадр и НЕ линковал
    (Media Offline даже при указанной папке). duration="0s" → DaVinci знает что это
    стилл, ставит его на любую длину на таймлайне и находит файл."""
    name = escape(path.stem)
    return (
        f'<asset id="{asset_id}" name="{name}" start="0s" duration="0s" '
        f'hasVideo="1" hasAudio="0" format="{FORMAT_ID}" videoSources="1" '
        f'src="{escape(rel_src(path, workspace))}"/>'
    )


def _build_audio_asset(asset_id: str, path: Path, duration_sec: float, workspace: Path) -> str:
    dur = sec_to_rational(duration_sec)
    name = escape(path.stem)
    return (
        f'<asset id="{asset_id}" name="{name}" start="0s" duration="{dur}" '
        f'hasVideo="0" hasAudio="1" audioSources="1" audioChannels="2" '
        f'audioRate="{SAMPLE_RATE}" src="{escape(rel_src(path, workspace))}"/>'
    )


def _build_video_spine(clips_with_ids: list[dict], voice_dur: float, still: bool = False) -> str:
    """Видеоряд на главной spine, привязанный к таймингам сцен.
    still=True (картинки) → элементы <video> (стиллы), иначе <asset-clip> (видео).

    Раньше клипы клались встык по их duration → паузы между сценами не покрывались,
    сумма < длины голоса → чёрный хвост + видеоряд уезжал от голоса к концу.
    Теперь длительность клипа = до старта следующей сцены (покрывает паузы),
    последний тянется до конца голоса. Видео остаётся в синхроне с речью.
    """
    clips = sorted(clips_with_ids, key=lambda c: c.get("scene_start", 0))
    n = len(clips)
    # Видеоряд ВСТЫК, КАДРОВО-НЕПРЕРЫВНО: offset каждого клипа = округлённая в кадры
    # позиция курсора, а длительность = разница ОКРУГЛЁННЫХ границ (НЕ округляем dur
    # отдельно). Тогда offset(N+1) == offset(N)+duration(N) по построению. Раньше offset
    # и duration округлялись независимо при float-курсоре → round(a+b)≠round(a)+round(b)
    # → ±1 кадр щель = чёрная вспышка между клипами (или безвредное наложение).
    max_start = max((float(c.get("scene_start", 0)) for c in clips), default=0.0)
    scale = (voice_dur / max_start) if max_start > voice_dur else 1.0
    parts = []
    cursor = 0.0
    for idx, c in enumerate(clips):
        if cursor >= voice_dur - 0.3:
            break  # дальше голоса не кладём
        if idx + 1 < n:
            nxt = float(clips[idx + 1].get("scene_start", 0)) * scale
            needed = nxt - cursor  # тянемся к таймингу следующей сцены (синхрон)
        else:
            needed = voice_dur - cursor  # последний — до конца голоса
        media = float(c.get("media_dur", 0)) or float(c.get("duration", 0.3))
        dur = min(max(needed, 0.3), media)  # не длиннее файла → нет пустоты
        if cursor + dur > voice_dur:
            dur = max(0.3, voice_dur - cursor)
        start_frame = round(cursor * FPS)
        end_frame = round((cursor + dur) * FPS)
        if end_frame <= start_frame:
            end_frame = start_frame + 1  # минимум 1 кадр
        offset = f"{start_frame * FRAME}/{TB}s"
        dur_r = f"{(end_frame - start_frame) * FRAME}/{TB}s"
        if still:
            # стилл держится dur_r на таймлайне; start="0s" — точка входа в кадр
            parts.append(
                f'        <video ref="{c["asset_id"]}" offset="{offset}" '
                f'name="{escape(c["name"])}" start="0s" duration="{dur_r}"/>'
            )
        else:
            parts.append(
                f'        <asset-clip ref="{c["asset_id"]}" offset="{offset}" '
                f'name="{escape(c["name"])}" duration="{dur_r}" format="{FORMAT_ID}"/>'
            )
        cursor += dur
    if cursor < voice_dur - 1.0:
        logger.warning(f"видеоряд короче голоса на {voice_dur - cursor:.1f}с (медиа не хватило)")
    return "\n".join(parts), cursor


def _build_audio_clip(asset_id: str, name: str, lane: int, duration_sec: float,
                     volume_db: float = 0.0, audio_role: str = "dialogue") -> str:
    """Audio clip on negative lane (under spine)."""
    dur = sec_to_rational(duration_sec)
    volume_attr = ""
    if abs(volume_db) > 0.01:
        # DaVinci понимает adjust-volume в FCPXML
        volume_attr = (
            f'\n          <adjust-volume amount="{volume_db:.1f}dB"/>'
        )
    return (
        f'        <asset-clip ref="{asset_id}" lane="{lane}" offset="0s" '
        f'name="{escape(name)}" duration="{dur}" audioRole="{audio_role}">'
        f'{volume_attr}\n        </asset-clip>'
    )


def build_fcpxml(
    workspace: Path,
    clips: list[dict],
    voiceover_path: Path,
    music_path: Optional[Path] = None,
    music_volume_db: float = MUSIC_VOLUME_DB,
    project_name: str = "YouTube Factory Project",
    event_name: str = "YT Factory",
) -> Path:
    """
    Generate FCPXML 1.9 ready for DaVinci import.

    Args:
        workspace: output directory (writes project.fcpxml here)
        clips: list of dicts with keys:
            - path (str | Path) — clip file
            - scene_start, scene_end (float) — timeline position from scene plan
            - relevance_score (float, optional) — for QA flagging
            - scene_text (str, optional) — narration for this scene
            - search_query (str, optional) — what was searched for
        voiceover_path: voiceover audio file
        music_path: background music file (optional)
        music_volume_db: music volume in dB (default -18.4 dB = 12%)
        project_name, event_name: DaVinci library names

    Returns:
        Path to written project.fcpxml
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    # Voiceover duration is the master timeline length
    voice_dur = ffprobe_duration(voiceover_path)
    if voice_dur <= 0:
        raise RuntimeError(f"Cannot read voiceover duration: {voiceover_path}")
    timeline_dur = sec_to_rational(voice_dur)

    # ── assets ──
    resources = [_build_format()]

    # voice asset
    resources.append(_build_audio_asset("av1", voiceover_path, voice_dur, workspace))

    # music asset (optional)
    music_asset_id = None
    music_dur = 0.0
    if music_path and Path(music_path).exists():
        music_dur = ffprobe_duration(Path(music_path))
        if music_dur > 0:
            music_asset_id = "am1"
            resources.append(_build_audio_asset(music_asset_id, Path(music_path), music_dur, workspace))

    # clip assets — нумеруем r10, r11, ...
    clips_with_ids = []
    qa_flagged = []
    # последний валидный (декодируемый) клип — им заполняем слот битой/пропавшей
    # сцены, чтобы в DaVinci не было ни офлайн-красных клипов, ни дыр (тайминг сцены
    # сохраняем). Раньше битый файл эмитился как asset с недекодируемым src → красный.
    last_good_path: Optional[Path] = None
    last_good_media = 0.0
    # Сид: первый годный клип — чтобы битый ПЕРВЫЙ слот не выпал (forward-scan).
    for _c in clips:
        _p = Path(_c["path"])
        if not _p.exists():
            continue
        if _p.suffix.lower() in IMG_EXTS:
            last_good_path, last_good_media = _p, voice_dur  # стилл — «бесконечная» длина
            break
        _d = ffprobe_duration(_p)
        if _d > 0:
            last_good_path, last_good_media = _p, _d
            break
    for i, c in enumerate(clips):
        cp = Path(c["path"])
        # длительность сцены (по тайм-плану)
        scene_dur = float(c.get("scene_end", 0)) - float(c.get("scene_start", 0))
        asset_id = f"vr{i+10}"
        exists = cp.exists()
        if cp.suffix.lower() in IMG_EXTS:
            # картинка-стилл: длину файла не probe-им; asset = вся таймлиния, spine
            # кадрирует по таймингу сцены. Никакого ffprobe/кодирования.
            if not exists:
                if last_good_path is None:
                    continue
                use_path = last_good_path
            else:
                use_path = cp
                last_good_path, last_good_media = cp, voice_dur
            if scene_dur <= 0:
                scene_dur = float(c.get("duration", 0)) or 3.0
            resources.append(_build_still_asset(asset_id, use_path, workspace))
            clips_with_ids.append({
                "asset_id": asset_id, "name": use_path.stem, "duration": scene_dur,
                "media_dur": voice_dur, "scene_start": float(c.get("scene_start", 0)),
                "path": str(use_path), "scene": i + 1, "relevance": c.get("relevance_score"),
                "scene_text": c.get("scene_text", ""), "query": c.get("search_query", ""),
            })
            continue
        probed_dur = ffprobe_duration(cp) if exists else 0.0
        use_path, use_media = cp, probed_dur
        if not exists or probed_dur <= 0:
            reason = "FILE MISSING" if not exists else "BROKEN FILE (ffprobe failed)"
            qa_flagged.append({
                "scene": i + 1, "reason": reason, "path": str(cp),
                "scene_text": c.get("scene_text", ""),
                "query": c.get("search_query", ""),
            })
            if last_good_path is None:
                logger.warning(f"clip scene {i+1}: {reason}, нет предыдущего клипа — слот пропущен")
                continue
            # подставляем предыдущий валидный клип — нет офлайн-красного, слот заполнен
            logger.warning(f"clip scene {i+1}: {reason} → подставляю {last_good_path.name}")
            use_path, use_media = last_good_path, last_good_media
        else:
            last_good_path, last_good_media = cp, probed_dur
        if scene_dur <= 0:
            scene_dur = use_media
        resources.append(_build_video_asset(asset_id, use_path, use_media, workspace))
        clips_with_ids.append({
            "asset_id": asset_id,
            "name": use_path.stem,
            "duration": scene_dur,
            "media_dur": use_media,
            "scene_start": float(c.get("scene_start", 0)),
            "path": str(use_path),
            "scene": i + 1,
            "relevance": c.get("relevance_score"),
            "scene_text": c.get("scene_text", ""),
            "query": c.get("search_query", ""),
        })
        # QA flag if relevance below threshold
        rel = c.get("relevance_score")
        if rel is not None and rel < QA_RELEVANCE_THRESHOLD:
            qa_flagged.append({
                "scene": i + 1, "reason": f"LOW RELEVANCE ({rel:.2f})",
                "path": str(cp), "scene_text": c.get("scene_text", ""),
                "query": c.get("search_query", ""),
            })

    if not clips_with_ids:
        raise RuntimeError("No usable clips for FCPXML")

    # ── spine ──
    # Картиночная таймлиния → стиллы как <video>; видео (de/es сток) → <asset-clip>.
    _is_img_timeline = bool(clips_with_ids) and Path(clips_with_ids[0]["path"]).suffix.lower() in IMG_EXTS
    video_spine_xml, total_video_dur = _build_video_spine(clips_with_ids, voice_dur, still=_is_img_timeline)
    # Бэкстоп от чёрного хвоста: если суммарного медиа не хватило до конца голоса
    # (сцены всё же покрыли не всю длину) — физически зацикливаем ПОСЛЕДНИЙ клип до
    # нужной длины, переобъявляем его asset и пересобираем spine. Повтор кадра лучше
    # чёрного экрана на полвидео. Основной фикс — upstream (alignment-канва), это сетка.
    if total_video_dur < voice_dur - 1.0 and clips_with_ids and not _is_img_timeline:
        from backend.pipeline.clips import _ensure_slot_length
        deficit = voice_dur - total_video_dur
        last = max(clips_with_ids, key=lambda c: c.get("scene_start", 0))
        target = float(last.get("media_dur", 0.0)) + deficit + 0.5
        logger.warning(
            f"видеоряд короче голоса на {deficit:.0f}с — дотягиваю последний клип "
            f"{Path(last['path']).name} до {target:.0f}с (loop)")
        _ensure_slot_length(Path(last["path"]), target)
        new_media = ffprobe_duration(Path(last["path"]))
        if new_media > last.get("media_dur", 0.0):
            last["media_dur"] = new_media
            aid = last["asset_id"]
            new_asset = _build_video_asset(aid, Path(last["path"]), new_media, workspace)
            resources = [new_asset if f'id="{aid}"' in r else r for r in resources]
            video_spine_xml, total_video_dur = _build_video_spine(clips_with_ids, voice_dur)
    # voice
    voice_audio_xml = _build_audio_clip("av1", voiceover_path.stem,
                                       lane=-1, duration_sec=voice_dur,
                                       volume_db=0.0, audio_role="dialogue")
    # music
    music_audio_xml = ""
    if music_asset_id:
        # music ставим на полную длину timeline (voice_dur), если короче — повторится в DaVinci вручную
        music_audio_xml = "\n" + _build_audio_clip(
            music_asset_id, Path(music_path).stem,
            lane=-2, duration_sec=min(music_dur, voice_dur),
            volume_db=music_volume_db, audio_role="music"
        )

    # ── full XML ──
    resources_xml = "\n    ".join(resources)
    fcpxml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
  <resources>
    {resources_xml}
  </resources>
  <library>
    <event name="{escape(event_name)}">
      <project name="{escape(project_name)}">
        <sequence format="{FORMAT_ID}" duration="{timeline_dur}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
{video_spine_xml}
{voice_audio_xml}{music_audio_xml}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
'''
    out_path = workspace / "project.fcpxml"
    out_path.write_text(fcpxml, encoding="utf-8")

    # ── QA-flags.md ──
    qa_md_path = workspace / "QA-flags.md"
    if qa_flagged:
        lines = ["# QA Flags — клипы для ревью/замены", ""]
        for f in qa_flagged:
            lines.append(f"## Сцена {f['scene']} — {f['reason']}")
            lines.append(f"- Файл: `{Path(f['path']).name}`")
            if f.get("scene_text"):
                lines.append(f"- Озвучка: {f['scene_text'][:200]}")
            if f.get("query"):
                lines.append(f"- Искали: `{f['query']}`")
            lines.append("")
        qa_md_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        qa_md_path.write_text("# QA Flags\n\nВсе клипы прошли проверку.\n", encoding="utf-8")

    # ── motion-notes.md (заготовка с готовыми текстами блоков) ──
    motion_md = workspace / "motion-notes.md"
    if not motion_md.exists():
        lines = [
            "# Motion notes — куда вставлять графику",
            "",
            f"Timeline: {voice_dur:.1f}s ({voice_dur/60:.1f} мин). "
            f"Сцен: {len(clips_with_ids)}, видеоряд: {total_video_dur:.1f}s.",
            "",
            "## Готовые тексты по сценам",
            "Используй для заголовков этапов / lower thirds.",
            "",
        ]
        for c in clips_with_ids:
            lines.append(f"### Сцена {c['scene']} (~{c['duration']:.1f}s)")
            if c.get("scene_text"):
                # первые 100 символов как идея для титра
                lines.append(f"> {c['scene_text'][:160]}")
            lines.append("")
        lines.extend([
            "## Чек-лист для прохода в DaVinci",
            "- [ ] Intro 5-8s — логотип + hook-фраза",
            "- [ ] Lower thirds (имя героя / компании) в первых 30 секундах",
            "- [ ] Section dividers между смысловыми блоками",
            "- [ ] Statistics tables — где приводятся цифры",
            "- [ ] Outro 5-10s — CTA на подписку",
        ])
        motion_md.write_text("\n".join(lines), encoding="utf-8")

    # ── open-davinci.command (macOS launcher) ──
    # DaVinci НЕ резолвит относительные src из подпапок (clips/…) при импорте FCPXML —
    # только аудио в корне подхватывается авто-релинком по имени → картинки = Media
    # Offline. Поэтому при клике конвертим относительные пути в АБСОЛЮТНЫЕ file:// от
    # реального места папки на маке (perl percent-encode: пробелы/юникод/символы) и
    # открываем уже project_local.fcpxml. project.fcpxml (относительный) остаётся как есть.
    launcher = workspace / "open-davinci.command"
    launcher.write_text(
        '#!/bin/bash\n'
        '# Двойной клик в Finder → пути fcpxml → абсолютные → DaVinci Resolve.\n'
        '# ВАЖНО: открывай ИМЕННО этот файл, НЕ project.fcpxml напрямую.\n'
        'cd "$(dirname "$0")" || exit 1\n'
        'DIR="$(pwd)"\n'
        'TARGET="project.fcpxml"\n'
        'if command -v perl >/dev/null 2>&1; then\n'
        '  ENC=$(printf \'%s\' "$DIR" | perl -pe '
        '\'s/([^A-Za-z0-9\\-._~\\/])/sprintf("%%%02X",ord($1))/ge\')\n'
        '  if perl -pe "s{src=\\"(?!file:)([^\\"]*)\\"}'
        '{src=\\"file://${ENC}/\\$1\\"}g" project.fcpxml > project_local.fcpxml 2>/dev/null; then\n'
        '    TARGET="project_local.fcpxml"\n'
        '  fi\n'
        'fi\n'
        'open -a "DaVinci Resolve" "$TARGET"\n',
        encoding="utf-8"
    )
    launcher.chmod(0o755)

    logger.info(f"FCPXML written: {out_path} (clips={len(clips_with_ids)}, "
                f"voice={voice_dur:.1f}s, music={'yes' if music_asset_id else 'no'}, "
                f"qa_flags={len(qa_flagged)})")
    return out_path
