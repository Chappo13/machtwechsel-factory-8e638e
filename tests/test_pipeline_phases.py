"""
Pipeline phase tests — каждая фаза отдельно, независимо.

Usage:
    cd ~/projects/youtube-factory
    python -m tests.test_pipeline_phases

Топик: "Bitcoin price crash 2022" (EN, 1 min — экономия токенов)
TTS: MOCK через FFmpeg silence
Output: /tmp/yt_factory_test/
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import types
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────
# Шаг 1: sys.path — добавляем корень проекта
# ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, "/tmp/py_packages")  # httpx, pyyaml

# ─────────────────────────────────────────────────────────
# Шаг 2: Реальные зависимости из /tmp/py_packages
# ─────────────────────────────────────────────────────────
# httpx, dotenv, pyyaml установлены в /tmp/py_packages
import requests as _requests


# ─────────────────────────────────────────────────────────
# Шаг 3: Real LLM через requests -> OpenRouter
# ─────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TEST_MODEL = "google/gemini-2.5-flash"


def _llm_sync(prompt: str, model: str = TEST_MODEL, max_tokens: int = 2000,
               temperature: float = 0.7, system_prompt: str = None, **_ignored) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    resp = _requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": TEST_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _llm_async(prompt: str, model: str = TEST_MODEL, **kw) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _llm_sync(prompt, model, **kw))


# Подменяем backend.utils.llm
llm_mod = types.ModuleType("backend.utils.llm")
llm_mod.call_llm = _llm_async
sys.modules["backend.utils.llm"] = llm_mod

utils_mod = types.ModuleType("backend.utils")
utils_mod.llm = llm_mod
sys.modules["backend.utils"] = utils_mod

# ─────────────────────────────────────────────────────────
# Настройки
# ─────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

TEST_TOPIC = "Bitcoin price crash 2022"
TEST_LANG = "de"
TEST_DURATION_MIN = 1
OUTPUT_DIR = Path("/tmp/yt_factory_test")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VOICEOVER_DURATION = 60.0  # секунды (mock TTS = 60s silence)

# Fallback-скрипт если Phase 1 упадёт
FALLBACK_SCRIPT = """In November 2021, Bitcoin reached an all-time high of $69,000.
According to Bloomberg, the total crypto market cap hit $3 trillion — making it larger
than the GDP of France. Millions of retail investors poured their savings in.
Then, in 2022, it all collapsed.

Bitcoin crashed 75% from peak to trough. According to CoinGlass data,
over $2 trillion in crypto market value was erased in 12 months. The collapse of
Terra Luna in May 2022 wiped out $60 billion in a single week. Three Arrows Capital,
one of the largest crypto hedge funds, went bankrupt with $10 billion in losses.

What triggered the crash? According to the Federal Reserve's own statements,
aggressive interest rate hikes starting in March 2022 drained liquidity from
speculative assets. But that wasn't the only cause.

A study by the National Bureau of Economic Research found that 64% of Bitcoin
trading volume in 2021 was wash trading — fake volume designed to inflate prices.
When the music stopped, retail investors were left holding the bag.
The FTX collapse in November 2022 was the final blow — $32 billion in value gone overnight."""

# ─────────────────────────────────────────────────────────
# Results tracking
# ─────────────────────────────────────────────────────────
results: list[tuple] = []  # (phase_num, name, ok, detail, duration)


def report(phase: int, name: str, ok: bool, detail: str = "", duration: float = 0.0):
    status = "[PASS]" if ok else "[FAIL]"
    dur_str = f" {duration:.1f}s" if duration > 0 else ""
    line = f"  {status} Phase {phase}: {name}{dur_str}"
    if detail:
        line += f"\n         {detail}"
    print(line)
    results.append((phase, name, ok, detail, duration))


# ─────────────────────────────────────────────────────────
# Phase 1: generate_script
# ─────────────────────────────────────────────────────────
async def test_phase_1() -> str | None:
    from backend.pipeline.script import generate_script
    t0 = time.time()
    try:
        script = await generate_script(
            topic=TEST_TOPIC,
            lang=TEST_LANG,
            duration_minutes=TEST_DURATION_MIN,
        )
        assert isinstance(script, str) and len(script) > 500, "Script too short (<500 chars)"
        report(1, "generate_script", True,
               f"{len(script)} chars returned", time.time() - t0)
        return script
    except Exception as e:
        report(1, "generate_script", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Phase 2: improve_script
# ─────────────────────────────────────────────────────────
async def test_phase_2(script: str) -> str:
    from backend.pipeline.script import improve_script
    t0 = time.time()
    try:
        improved = await improve_script(script=script, lang=TEST_LANG, max_iterations=1)
        assert isinstance(improved, str) and len(improved) > 50, "Result too short"
        report(2, "improve_script", True,
               f"{len(script)} -> {len(improved)} chars", time.time() - t0)
        return improved
    except Exception as e:
        report(2, "improve_script", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return script


# ─────────────────────────────────────────────────────────
# Phase 3: apply_virality_filter
# ─────────────────────────────────────────────────────────
async def test_phase_3(script: str) -> str:
    from backend.pipeline.virality import apply_virality_filter
    t0 = time.time()
    try:
        viral = await apply_virality_filter(script=script, lang=TEST_LANG, niche="finance")
        assert isinstance(viral, str) and len(viral) > 50, "Result too short"
        report(3, "apply_virality_filter", True,
               f"{len(script)} -> {len(viral)} chars", time.time() - t0)
        return viral
    except Exception as e:
        report(3, "apply_virality_filter", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return script


# ─────────────────────────────────────────────────────────
# Phase 4: TTS MOCK — FFmpeg silence
# ─────────────────────────────────────────────────────────
async def test_phase_4_mock() -> tuple[Path | None, float]:
    t0 = time.time()
    try:
        vo_path = OUTPUT_DIR / "voiceover.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono",
            "-t", "60",
            "-q:a", "9",
            "-acodec", "libmp3lame",
            str(vo_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, f"ffmpeg error: {result.stderr.decode()[-200:]}"
        assert vo_path.exists() and vo_path.stat().st_size > 0, "File missing or empty"

        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(vo_path)],
            capture_output=True, text=True,
        )
        dur = float(probe.stdout.strip())
        report(4, "generate_voiceover [MOCK]", True,
               f"silence {dur:.0f}s -> {vo_path.name}", time.time() - t0)
        return vo_path, dur
    except Exception as e:
        report(4, "generate_voiceover [MOCK]", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return None, VOICEOVER_DURATION


# ─────────────────────────────────────────────────────────
# Phase 5: plan_scenes
# ─────────────────────────────────────────────────────────
async def test_phase_5(script: str, duration: float) -> list[dict]:
    from backend.pipeline.clips import plan_scenes
    t0 = time.time()
    try:
        scenes = await plan_scenes(
            script=script,
            topic=TEST_TOPIC,
            lang=TEST_LANG,
            total_duration=duration,
        )
        assert isinstance(scenes, list) and len(scenes) > 0, "Empty scene list"
        assert "queries" in scenes[0], f"Missing 'queries' in scene[0]: {list(scenes[0].keys())}"
        report(5, "plan_scenes", True,
               f"{len(scenes)} scenes planned", time.time() - t0)
        return scenes
    except Exception as e:
        report(5, "plan_scenes", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        # Fallback scene plan
        return [
            {"start": 0, "end": 30, "text": "Bitcoin peak 2021", "queries": ["bitcoin price chart 2021", "cryptocurrency trading screen", "stock market bull run"], "mood": "dramatic"},
            {"start": 30, "end": 60, "text": "Bitcoin crash 2022", "queries": ["stock market crash red", "crypto bear market 2022", "financial crisis recession"], "mood": "tense"},
        ]


# ─────────────────────────────────────────────────────────
# Phase 6: download_clips (первые 2 сцены)
# ─────────────────────────────────────────────────────────
async def test_phase_6(scene_plan: list[dict]) -> list[dict]:
    t0 = time.time()
    try:
        from backend.pipeline.clips import download_clips
        clips_dir = OUTPUT_DIR / "clips"
        clips_dir.mkdir(exist_ok=True)

        mini_plan = scene_plan[:2]
        clip_map = await download_clips(scene_plan=mini_plan, output_dir=clips_dir)
        assert isinstance(clip_map, list), "Expected list"

        found = sum(1 for c in clip_map if Path(c["path"]).exists())
        sources = list(set(c.get("source", "?") for c in clip_map))
        report(6, "download_clips", True,
               f"{found}/{len(mini_plan)} clips downloaded, sources={sources}", time.time() - t0)
        return clip_map
    except Exception as e:
        report(6, "download_clips", False,
               f"{type(e).__name__}: {str(e)[:250]}", time.time() - t0)
        return []


# ─────────────────────────────────────────────────────────
# Phase 7: find_music
# ─────────────────────────────────────────────────────────
async def test_phase_7(duration: float) -> Path | None:
    t0 = time.time()
    try:
        from backend.pipeline.music import find_music
        music_dir = OUTPUT_DIR / "music"
        music_dir.mkdir(exist_ok=True)

        music_path = await find_music(mood="documentary", duration=duration, output_dir=music_dir)

        has_key = bool(os.getenv("FREESOUND_API_KEY"))
        if music_path and Path(music_path).exists():
            size_kb = Path(music_path).stat().st_size / 1024
            report(7, "find_music", True,
                   f"{Path(music_path).name} ({size_kb:.0f} KB)", time.time() - t0)
            return music_path
        else:
            if has_key:
                report(7, "find_music", False,
                       "FREESOUND_API_KEY present but no track returned", time.time() - t0)
            else:
                report(7, "find_music", True,
                       "No FREESOUND_API_KEY — None returned (expected)", time.time() - t0)
            return None
    except Exception as e:
        report(7, "find_music", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Phase 8: assemble_video (если есть клипы)
# ─────────────────────────────────────────────────────────
async def test_phase_8(clips: list[dict], voiceover_path: Path | None,
                        music_path: Path | None) -> Path | None:
    from backend.pipeline.assembly import assemble_video
    t0 = time.time()
    try:
        valid_clips = [c for c in clips if Path(c["path"]).exists()]
        if not valid_clips:
            report(8, "assemble_video", True,
                   "No real clips — SKIP (expected without stock API results)", time.time() - t0)
            return None
        if not voiceover_path or not voiceover_path.exists():
            report(8, "assemble_video", False,
                   "Voiceover missing", time.time() - t0)
            return None

        output_path = OUTPUT_DIR / "test_output.mp4"
        result = await assemble_video(
            clips=valid_clips,
            voiceover=str(voiceover_path),
            music=str(music_path) if music_path and Path(music_path).exists() else None,
            music_volume=0.12,
            output_path=output_path,
            style="documentary",
        )
        size_mb = Path(result).stat().st_size / (1024 * 1024)
        report(8, "assemble_video", True,
               f"-> {Path(result).name} ({size_mb:.1f} MB)", time.time() - t0)
        return result
    except Exception as e:
        report(8, "assemble_video", False,
               f"{type(e).__name__}: {str(e)[:300]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Phase 9: generate_metadata
# ─────────────────────────────────────────────────────────
async def test_phase_9(script: str) -> dict | None:
    from backend.pipeline.metadata import generate_metadata
    t0 = time.time()
    try:
        meta = await generate_metadata(topic=TEST_TOPIC, script=script, lang=TEST_LANG)
        assert isinstance(meta, dict), "Not a dict"
        assert "titles" in meta and len(meta["titles"]) > 0, "No titles"
        assert "description" in meta and len(meta["description"]) > 10, "Description too short"
        assert "tags" in meta, "No tags field"
        report(9, "generate_metadata", True,
               f"titles={len(meta['titles'])}, tags={len(meta.get('tags', []))}, "
               f"desc={len(meta['description'])} chars",
               time.time() - t0)
        print()
        for i, title in enumerate(meta["titles"], 1):
            print(f"         Title {i}: {title}")
        if meta.get("titles_ru"):
            print("         ---")
            for i, title in enumerate(meta["titles_ru"], 1):
                print(f"         RU {i}: {title}")
        return meta
    except Exception as e:
        report(9, "generate_metadata", False,
               f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
async def main():
    t_start = time.time()

    print()
    print("=" * 62)
    print("  YouTube Factory — Pipeline Phase Tests")
    print(f"  Topic : {TEST_TOPIC}")
    print(f"  Lang  : {TEST_LANG}  |  Duration: {TEST_DURATION_MIN} min")
    print(f"  Model : {TEST_MODEL}")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 62)
    print()

    if not OPENROUTER_API_KEY:
        print("  WARNING: OPENROUTER_API_KEY not set — LLM phases will fail\n")

    # ── LLM Script ──────────────────────────────────────────
    print("-- LLM Script Phases ------------------------------------------")
    script_raw = await test_phase_1()
    working = script_raw if script_raw else FALLBACK_SCRIPT

    improved = await test_phase_2(working)
    viral = await test_phase_3(improved)
    final_script = viral or improved or working

    # ── TTS Mock ─────────────────────────────────────────────
    print()
    print("-- TTS Phase (Mock) -------------------------------------------")
    vo_path, vo_dur = await test_phase_4_mock()

    # ── Video ─────────────────────────────────────────────────
    print()
    print("-- Video Phases -----------------------------------------------")
    scenes = await test_phase_5(final_script, vo_dur)
    clips = await test_phase_6(scenes)
    music = await test_phase_7(vo_dur)

    # ── Assembly ──────────────────────────────────────────────
    print()
    print("-- Assembly ---------------------------------------------------")
    await test_phase_8(clips, vo_path, music)

    # ── Metadata ──────────────────────────────────────────────
    print()
    print("-- Metadata ---------------------------------------------------")
    await test_phase_9(final_script)

    # ── Summary ──────────────────────────────────────────────
    total_time = time.time() - t_start
    ok_count = sum(1 for _, _, ok, _, _ in results if ok)
    fail_count = len(results) - ok_count

    print()
    print("=" * 62)
    print(f"  SUMMARY: {ok_count}/{len(results)} passed | {fail_count} failed | {total_time:.1f}s total")
    print("=" * 62)

    if fail_count > 0:
        print()
        print("  Failed:")
        for phase, name, ok, detail, dur in results:
            if not ok:
                print(f"    Phase {phase} ({name}): {detail[:120]}")

    # ── Write to _tasklog.md ─────────────────────────────────
    _write_tasklog(ok_count, fail_count, total_time)

    sys.exit(0 if fail_count == 0 else 1)


def _write_tasklog(ok: int, fail: int, total_time: float):
    tasklog = PROJECT_ROOT / "_tasklog.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"\n## Pipeline Phase Test — {now}",
        f"**Topic:** {TEST_TOPIC} | **Lang:** {TEST_LANG} | **Model:** {TEST_MODEL}",
        f"**Result:** {ok}/{ok+fail} passed in {total_time:.1f}s",
        "",
        "| Phase | Name | Status | Time | Detail |",
        "|-------|------|--------|------|--------|",
    ]
    for phase, name, passed, detail, dur in results:
        status = "PASS" if passed else "FAIL"
        short_detail = detail[:80].replace("|", "\\|") if detail else ""
        lines.append(f"| {phase} | {name} | {status} | {dur:.1f}s | {short_detail} |")

    entry = "\n".join(lines) + "\n"

    try:
        with open(tasklog, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"\n  Results written to _tasklog.md")
    except Exception as e:
        print(f"\n  Warning: could not write _tasklog.md: {e}")


if __name__ == "__main__":
    asyncio.run(main())
