"""
Pipeline phase tests — runs each phase independently with minimal data.

Usage:
    cd ~/projects/youtube-factory
    python3 backend/tests/test_pipeline.py

Strategy:
- httpx и dotenv мокируются ДО импорта backend (они не установлены в системе)
- LLM вызовы идут через requests (установлен системно) напрямую в OpenRouter
- TTS (phase 4): MOCK — FFmpeg silence, без Voicer API
- Clips/Music: реальные вызовы если есть ключи, иначе graceful skip
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest.mock as mock
from pathlib import Path

# ─────────────────────────────────────────────────────────
# Шаг 1: Мокируем недоступные модули ДО любых импортов backend
# ─────────────────────────────────────────────────────────

# Mock dotenv
dotenv_mod = types.ModuleType("dotenv")
dotenv_mod.load_dotenv = lambda *a, **kw: None
sys.modules["dotenv"] = dotenv_mod

# Mock httpx (нужен для backend/utils/llm.py, tts.py, etc.)
httpx_mod = types.ModuleType("httpx")

class _FakeTimeout:
    def __init__(self, *a, **kw): pass

class _FakeResponse:
    def __init__(self, data=None, status=200):
        self.status_code = status
        self._data = data or {}
        self.text = json.dumps(self._data)
        self.content = b""
        self.headers = {"content-type": "application/json"}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx_mod.HTTPStatusError(f"{self.status_code}", request=None, response=self)
    def json(self):
        return self._data

class _FakeHTTPStatusError(Exception):
    def __init__(self, msg, request=None, response=None):
        super().__init__(msg)
        self.response = response or _FakeResponse(status=500)

class _FakeTimeoutException(Exception):
    pass

httpx_mod.AsyncClient = None  # будет заменён ниже
httpx_mod.Timeout = _FakeTimeout
httpx_mod.HTTPStatusError = _FakeHTTPStatusError
httpx_mod.TimeoutException = _FakeTimeoutException
sys.modules["httpx"] = httpx_mod

# ─────────────────────────────────────────────────────────
# Шаг 2: Реальный LLM через requests (синхронный в asyncio)
# ─────────────────────────────────────────────────────────
import requests as _requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Самая дешёвая и быстрая модель для тестов
TEST_MODEL = "google/gemini-2.5-flash"


def _llm_call_sync(
    prompt: str,
    model: str = TEST_MODEL,
    max_tokens: int = 2000,
    temperature: float = 0.7,
    system_prompt: str = None,
    fallback_model: str = None,
    **_ignored,
) -> str:
    """LLM вызов через requests. fallback_model и прочие kwargs игнорируются."""
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


async def _llm_call_async(prompt: str, model: str = TEST_MODEL, **kw) -> str:
    """Обёртка async для синхронного вызова."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _llm_call_sync(prompt, model, **kw))


# Подменяем call_llm в backend.utils.llm (мок на уровне модуля)
llm_mod = types.ModuleType("backend.utils.llm")
llm_mod.call_llm = _llm_call_async
sys.modules["backend.utils.llm"] = llm_mod

# Также нужно создать фиктивный backend.utils чтобы импорт сработал
utils_mod = types.ModuleType("backend.utils")
utils_mod.llm = llm_mod
sys.modules["backend.utils"] = utils_mod

# ─────────────────────────────────────────────────────────
# Шаг 3: Добавляем путь к проекту
# ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─────────────────────────────────────────────────────────
# Логирование
# ─────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")

# ─────────────────────────────────────────────────────────
# Тестовые данные
# ─────────────────────────────────────────────────────────
TEST_TOPIC = "Wirecard Betrug Deutschland"
TEST_LANG = "de"
TEST_DURATION_MIN = 2

SAMPLE_SCRIPT = """Im Jahr 2020 brach der größte Bilanzskandal der deutschen Wirtschaftsgeschichte aus.
Wirecard AG, einst ein Börsenliebling mit 24 Milliarden Euro Marktkapitalisierung, kollabierte über Nacht.
Laut Staatsanwaltschaft München fehlen 1,9 Milliarden Euro — einfach verschwunden.

Die Wirtschaftsprüfer von EY hatten das Testat neun Jahre lang erteilt.
Bloomberg und Financial Times hatten gewarnt. Niemand hörte hin.

Wie konnte das passieren? Was wusste die BaFin wirklich? Und wer hat profitiert?
Das ist die Geschichte eines Systems, das vollständig versagt hat.

In der Zentrale in Aschheim bei München arbeiteten 6.000 Menschen.
Am 25. Juni 2020 stellte das Unternehmen Insolvenzantrag.
CEO Markus Braun wurde verhaftet. Jan Marsalek floh — bis heute nicht gefunden.

Die Deutsche Bank hatte Wirecard als solides Fintech eingestuft.
Der DAX-Konzern galt als Vorzeigeunternehmen für digitale Innovation.
Doch laut Insolvenzverwalter Michael Jaffé war das Geschäftsmodell teilweise eine Fiktion."""

# ─────────────────────────────────────────────────────────
# Результаты
# ─────────────────────────────────────────────────────────
results = []

def report(phase, name, ok, detail="", duration=0.0):
    status = "OK" if ok else "FAIL"
    dur = f" [{duration:.1f}s]" if duration > 0 else ""
    line = f"  Phase {phase}: {name} -- {status}{dur}"
    if detail:
        line += f"\n         {detail}"
    print(line)
    results.append((phase, name, ok, detail))


# ─────────────────────────────────────────────────────────
# Phase 1: generate_script
# ─────────────────────────────────────────────────────────
async def test_phase_1():
    from backend.pipeline.script import generate_script
    t0 = time.time()
    try:
        script = await generate_script(
            topic=TEST_TOPIC,
            lang=TEST_LANG,
            duration_minutes=TEST_DURATION_MIN,
        )
        assert isinstance(script, str) and len(script) > 100, "Script too short"
        report(1, "generate_script", True, f"{len(script)} chars", time.time() - t0)
        return script
    except Exception as e:
        report(1, "generate_script", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Phase 2: improve_script
# ─────────────────────────────────────────────────────────
async def test_phase_2(script):
    from backend.pipeline.script import improve_script
    t0 = time.time()
    try:
        improved = await improve_script(script=script, lang=TEST_LANG, max_iterations=1)
        assert isinstance(improved, str) and len(improved) > 100, "Too short"
        report(2, "improve_script", True, f"{len(script)} -> {len(improved)} chars", time.time() - t0)
        return improved
    except Exception as e:
        report(2, "improve_script", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return script


# ─────────────────────────────────────────────────────────
# Phase 3: apply_virality_filter
# ─────────────────────────────────────────────────────────
async def test_phase_3(script):
    from backend.pipeline.virality import apply_virality_filter
    t0 = time.time()
    try:
        viral = await apply_virality_filter(script=script, lang=TEST_LANG, niche="finance")
        assert isinstance(viral, str) and len(viral) > 100, "Too short"
        report(3, "apply_virality_filter", True, f"{len(script)} -> {len(viral)} chars", time.time() - t0)
        return viral
    except Exception as e:
        report(3, "apply_virality_filter", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return script


# ─────────────────────────────────────────────────────────
# Phase 4: generate_voiceover -- MOCK (FFmpeg silence)
# ─────────────────────────────────────────────────────────
async def test_phase_4_mock(output_dir):
    """MOCK: FFmpeg silence вместо реального TTS."""
    t0 = time.time()
    try:
        output_path = output_dir / "voiceover.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono",
            "-t", "10",
            "-q:a", "9",
            "-acodec", "libmp3lame",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        assert result.returncode == 0, f"ffmpeg: {result.stderr.decode()[-150:]}"
        assert output_path.exists() and output_path.stat().st_size > 0

        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output_path)],
            capture_output=True, text=True,
        )
        dur = float(probe.stdout.strip())
        report(4, "generate_voiceover [MOCK]", True, f"silence {dur:.1f}s -> voiceover.mp3", time.time() - t0)
        return output_path, dur
    except Exception as e:
        report(4, "generate_voiceover [MOCK]", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return None, 10.0


# ─────────────────────────────────────────────────────────
# Phase 5: plan_scenes
# ─────────────────────────────────────────────────────────
async def test_phase_5(script, duration):
    from backend.pipeline.clips import plan_scenes
    t0 = time.time()
    try:
        scenes = await plan_scenes(
            script=script, topic=TEST_TOPIC, lang=TEST_LANG, total_duration=duration,
        )
        assert isinstance(scenes, list) and len(scenes) > 0, "No scenes"
        assert "queries" in scenes[0], "Missing queries field"
        report(5, "plan_scenes", True, f"{len(scenes)} scenes", time.time() - t0)
        return scenes
    except Exception as e:
        report(5, "plan_scenes", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return [{"start": 0, "end": 5, "text": TEST_TOPIC, "queries": ["germany finance wirecard scandal"], "mood": "dramatic"}]


# ─────────────────────────────────────────────────────────
# Phase 6: download_clips
# ─────────────────────────────────────────────────────────
async def test_phase_6(scene_plan, output_dir):
    t0 = time.time()
    try:
        # Мокируем httpx.AsyncClient для stock клиента
        # (используем requests внутри AsyncClient wrapper)
        import contextlib

        class _HttpxClientWrapper:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def get(self, url, **kw):
                r = _requests.get(url, headers=kw.get("headers", {}), params=kw.get("params", {}), timeout=30)
                resp = _FakeResponse(data=r.json() if r.headers.get("content-type","").startswith("application/json") else {}, status=r.status_code)
                resp.content = r.content
                resp.text = r.text
                return resp
            async def post(self, url, **kw):
                r = _requests.post(url, headers=kw.get("headers", {}), json=kw.get("json", {}), timeout=30)
                resp = _FakeResponse(data=r.json() if r.headers.get("content-type","").startswith("application/json") else {}, status=r.status_code)
                resp.content = r.content
                return resp

        httpx_mod.AsyncClient = _HttpxClientWrapper

        from backend.pipeline.clips import download_clips
        mini_plan = scene_plan[:2]
        clips_dir = output_dir / "clips"
        clips_dir.mkdir(exist_ok=True)

        clip_map = await download_clips(scene_plan=mini_plan, output_dir=clips_dir)
        assert isinstance(clip_map, list)
        found = sum(1 for c in clip_map if Path(c["path"]).exists())
        sources = list(set(c.get("source", "?") for c in clip_map))
        report(6, "download_clips", True, f"{found}/{len(mini_plan)} clips, sources={sources}", time.time() - t0)
        return clip_map
    except Exception as e:
        report(6, "download_clips", False, f"{type(e).__name__}: {str(e)[:200]}", time.time() - t0)
        return []


# ─────────────────────────────────────────────────────────
# Phase 7: find_music
# ─────────────────────────────────────────────────────────
async def test_phase_7(output_dir, duration):
    t0 = time.time()
    try:
        # httpx.AsyncClient уже настроен в phase 6
        from backend.pipeline.music import find_music
        music_path = await find_music(mood="dramatic", duration=duration, output_dir=output_dir)

        if music_path and Path(music_path).exists():
            size_kb = Path(music_path).stat().st_size / 1024
            report(7, "find_music", True, f"{Path(music_path).name} ({size_kb:.0f} KB)", time.time() - t0)
        else:
            has_key = bool(os.getenv("FREESOUND_API_KEY"))
            if has_key:
                report(7, "find_music", False, "Key present but no track returned", time.time() - t0)
            else:
                report(7, "find_music", True, "No FREESOUND_API_KEY -- skip (expected)", time.time() - t0)
        return music_path
    except Exception as e:
        report(7, "find_music", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Phase 8: assemble_video
# ─────────────────────────────────────────────────────────
async def test_phase_8(clips, voiceover_path, music_path, output_dir):
    from backend.pipeline.assembly import assemble_video
    t0 = time.time()
    try:
        if not clips:
            report(8, "assemble_video", False, "No clips -- skip", time.time() - t0)
            return None
        if not voiceover_path or not voiceover_path.exists():
            report(8, "assemble_video", False, "No voiceover -- skip", time.time() - t0)
            return None

        valid_clips = [c for c in clips if Path(c["path"]).exists()]
        if not valid_clips:
            report(8, "assemble_video", False, "No valid clip files", time.time() - t0)
            return None

        output_path = output_dir / "test_output.mp4"
        result = await assemble_video(
            clips=valid_clips,
            voiceover=str(voiceover_path),
            music=str(music_path) if music_path and Path(music_path).exists() else None,
            music_volume=0.12,
            output_path=output_path,
            style="documentary",
        )
        size_mb = Path(result).stat().st_size / (1024 * 1024)
        report(8, "assemble_video", True, f"-> {Path(result).name} ({size_mb:.1f} MB)", time.time() - t0)
        return result
    except Exception as e:
        report(8, "assemble_video", False, f"{type(e).__name__}: {str(e)[:250]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Phase 9: generate_metadata
# ─────────────────────────────────────────────────────────
async def test_phase_9(script):
    from backend.pipeline.metadata import generate_metadata
    t0 = time.time()
    try:
        meta = await generate_metadata(topic=TEST_TOPIC, script=script, lang=TEST_LANG)
        assert isinstance(meta, dict)
        assert "titles" in meta and len(meta["titles"]) > 0, "No titles"
        assert "description" in meta and len(meta["description"]) > 10, "No description"
        assert "tags" in meta, "No tags"
        report(9, "generate_metadata", True,
               f"titles={len(meta['titles'])}, tags={len(meta.get('tags',[]))}, desc={len(meta['description'])} chars",
               time.time() - t0)
        print()
        for i, title in enumerate(meta["titles"], 1):
            print(f"         Title {i}: {title}")
        return meta
    except Exception as e:
        report(9, "generate_metadata", False, f"{type(e).__name__}: {str(e)[:150]}", time.time() - t0)
        return None


# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
async def main():
    print("\n" + "=" * 60)
    print("  YouTube Factory -- Pipeline Phase Tests")
    print(f"  Topic: {TEST_TOPIC}")
    print(f"  Lang: {TEST_LANG} | Duration: {TEST_DURATION_MIN}min")
    print(f"  LLM: {TEST_MODEL}")
    print("=" * 60 + "\n")

    if not OPENROUTER_API_KEY:
        print("  WARNING: OPENROUTER_API_KEY not set — LLM phases will fail\n")

    t_total = time.time()

    with tempfile.TemporaryDirectory(prefix="yt_test_") as tmp:
        tmp_dir = Path(tmp)
        print(f"  Temp: {tmp_dir}\n")

        # LLM фазы
        print("-- LLM Script Phases ------------------------------------------")
        script = await test_phase_1()
        working = script if script else SAMPLE_SCRIPT
        improved = await test_phase_2(working)
        viral = await test_phase_3(improved)
        final_script = viral or improved or working

        # TTS mock
        print("\n-- TTS Phase (Mock) -------------------------------------------")
        vo_path, vo_dur = await test_phase_4_mock(tmp_dir)

        # Видео фазы
        print("\n-- Video Phases -----------------------------------------------")
        scenes = await test_phase_5(final_script, vo_dur)
        clips = await test_phase_6(scenes, tmp_dir)
        music = await test_phase_7(tmp_dir, vo_dur)

        # Сборка
        print("\n-- Assembly ---------------------------------------------------")
        await test_phase_8(clips, vo_path, music, tmp_dir)

        # Метаданные
        print("\n-- Metadata ---------------------------------------------------")
        await test_phase_9(final_script)

    total = time.time() - t_total
    ok = sum(1 for _, _, ok, _ in results if ok)
    fail = len(results) - ok

    print("\n" + "=" * 60)
    print(f"  SUMMARY: {ok}/{len(results)} passed | {fail} failed | {total:.1f}s total")
    print("=" * 60)

    if fail > 0:
        print("\n  Failed phases:")
        for phase, name, ok_f, detail in results:
            if not ok_f:
                print(f"    Phase {phase} ({name}): {detail}")
        sys.exit(1)
    else:
        print("\n  All phases passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
